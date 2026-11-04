"""Gemeinsame Basis aller Adapter."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin

from ..dates import parse_deadline_de
from ..http import Fetcher, RobotsDisallowed
from ..models import Club, Job, Source, SourceResult

log = logging.getLogger(__name__)

# Textmuster, die eine legitim leere Stellenliste belegen.
DEFAULT_EMPTY_PATTERNS = (
    "keine stellenanzeigen gefunden",
    "keine offenen stellen",
    "aktuell keine offenen stellen",
    "derzeit keine offenen stellen",
    "momentan keine offenen stellen",
    "aktuell keine stellen",
    "keine passenden stellen",
    "keine ergebnisse",
    "no open positions",
    "no jobs found",
)


class Adapter:
    """Holt die Stellen einer Quelle.

    Unterklassen implementieren list_jobs() und optional enrich().
    """

    name = "base"

    def __init__(self, fetcher: Fetcher, club: Club, source: Source,
                 filters: Optional[Dict[str, Any]] = None,
                 browser_factory: Optional[Callable[[], Any]] = None):
        self.fetcher = fetcher
        self.club = club
        self.source = source
        self.params: Dict[str, Any] = source.params or {}
        self._list_html: str = ""
        filters = filters or {}
        self.ignore_titles = [t.lower() for t in (filters.get("ignore_titles") or [])]
        self.speculative_titles = [
            t.lower() for t in (filters.get("speculative_titles") or [])
        ]
        # Dauer-Eintraege wie "Initiativbewerbung", die keine Stelle sind
        self.ignored_entries: List[Job] = []
        self.speculative_entry: Optional[Job] = None
        # Wird nur von den drei JavaScript-Quellen gebraucht. Der Browser
        # startet erst, wenn eine davon ihn wirklich anfordert.
        self._browser_factory = browser_factory

    # -- Hilfsfunktionen fuer Unterklassen --------------------------------
    def absolute(self, href: str) -> str:
        if not href:
            return ""
        return urljoin(self.source.url, href.strip())

    def new_job(self, title: str, url: str, **kwargs: Any) -> Job:
        job = Job(
            club=self.club.name,
            club_short=self.club.short,
            source_id=self.source.id,
            source_label=self.source.label,
            title=(title or "").strip(),
            url=self.absolute(url) if url else "",
            **kwargs
        )
        job.ensure_id()
        return job

    def is_ignored_title(self, title: str) -> bool:
        probe = (title or "").strip().lower()
        if not probe:
            return True
        return any(needle in probe for needle in self.ignore_titles)

    def is_speculative_title(self, title: str) -> bool:
        probe = (title or "").strip().lower()
        return any(needle in probe for needle in self.speculative_titles)

    def _split_ignored(self, jobs: List[Job]) -> List[Job]:
        """Dauer-Eintraege aussortieren, Initiativbewerbung aber merken."""
        keep: List[Job] = []
        for job in jobs:
            if not self.is_ignored_title(job.title):
                keep.append(job)
                continue
            self.ignored_entries.append(job)
            if self.speculative_entry is None and self.is_speculative_title(job.title):
                self.speculative_entry = job
            log.info("  Kein Stellenangebot, übersprungen: %s", job.title)
        return keep

    def require_browser(self):
        """Browsersitzung anfordern. Fehlt sie, scheitert nur diese Quelle."""
        if self._browser_factory is None:
            raise RuntimeError(
                "Quelle {} braucht einen Browser, es wurde aber keiner "
                "bereitgestellt".format(self.source.id))
        return self._browser_factory()

    def empty_patterns(self) -> List[str]:
        return [p.lower() for p in
                (list(self.source.empty_ok) + list(DEFAULT_EMPTY_PATTERNS))]

    def looks_legitimately_empty(self, html: str) -> bool:
        """Sagt die Seite selbst, dass gerade nichts offen ist?"""
        if not html:
            return False
        haystack = html.lower()
        return any(pattern in haystack for pattern in self.empty_patterns())

    # -- Von Unterklassen zu implementieren -------------------------------
    def list_jobs(self) -> List[Job]:
        raise NotImplementedError

    def enrich(self, job: Job) -> None:
        """Detailseite abrufen und die Beschreibung ergaenzen."""
        return None

    # -- Ablauf -----------------------------------------------------------
    def fetch(self, detail_filter: Optional[Callable[[Job], bool]] = None) -> SourceResult:
        result = SourceResult(source_id=self.source.id)
        try:
            jobs = self.list_jobs()
        except RobotsDisallowed as exc:
            result.ok = False
            result.error = "robots.txt verbietet den Abruf: {}".format(exc)
            log.error("%s / %s: %s", self.club.name, self.source.id, result.error)
            return result
        except Exception as exc:                      # eine Quelle darf nicht alles stoppen
            result.ok = False
            result.error = "{}: {}".format(exc.__class__.__name__, exc)
            log.error("%s / %s fehlgeschlagen: %s",
                      self.club.name, self.source.id, result.error)
            return result

        jobs = self._split_ignored(jobs)
        result.jobs = jobs
        if not jobs:
            result.legitimately_empty = self.looks_legitimately_empty(self._list_html)
            return result

        for job in jobs:
            if detail_filter is not None and not detail_filter(job):
                continue
            try:
                self.enrich(job)
            except RobotsDisallowed as exc:
                log.warning("Detailseite gesperrt (%s): %s", job.title, exc)
            except Exception as exc:
                # Fehlende Beschreibung darf die Stelle nicht verwerfen
                log.warning("Detailseite von '%s' nicht lesbar (%s)",
                            job.title, exc.__class__.__name__)
            if job.description and not job.deadline:
                job.deadline = parse_deadline_de(job.description)
        return result
