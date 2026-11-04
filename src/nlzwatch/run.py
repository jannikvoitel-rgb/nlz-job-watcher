"""Ablauf eines Laufs: abrufen, einstufen, speichern, pushen."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .adapters import UnknownAdapter, get_adapter
from .classify import Classifier
from .config import load_clubs, load_filters, project_root
from .http import Fetcher
from .models import Club, Job, Source
from .notify import Notifier
from .store import Store

log = logging.getLogger(__name__)


@dataclass
class SourceReport:
    club: str
    source_id: str
    label: str
    found: int = 0
    new_a: int = 0
    new_b: int = 0
    new_c: int = 0
    closed: int = 0
    first_run: bool = False
    skipped: bool = False
    manual: bool = False
    error: Optional[str] = None
    warned: bool = False


@dataclass
class RunReport:
    sources: List[SourceReport] = field(default_factory=list)
    pushes_sent: int = 0
    requests: int = 0
    browser_pages: int = 0
    open_sport: int = 0
    open_glb: int = 0

    @property
    def errors(self) -> List[SourceReport]:
        return [s for s in self.sources if s.error]

    def summary_lines(self) -> List[str]:
        lines = ["", "Zusammenfassung des Laufs", "=" * 72,
                 "{:<26} {:>8} {:>7} {:>7} {:>7}  {}".format(
                     "Verein / Quelle", "gefunden", "neu A", "neu B", "zu", "Status")]
        for s in self.sources:
            if s.manual:
                status = "manuell beobachten"
            elif s.skipped:
                status = "übersprungen"
            elif s.error:
                status = "FEHLER: {}".format(s.error[:34])
            elif s.first_run:
                status = "Erstlauf (Bestand)"
            else:
                status = "ok"
            lines.append("{:<26} {:>8} {:>7} {:>7} {:>7}  {}".format(
                (s.club + " / " + s.label)[:26],
                s.found, s.new_a, s.new_b, s.closed, status))
        lines.append("-" * 72)
        browser_note = (" | Browser-Seiten: {}".format(self.browser_pages)
                        if self.browser_pages else "")
        lines.append("Offen im Sport: {} (davon GLB: {}) | HTTP-Anfragen: {}{} | "
                     "Pushes: {}".format(self.open_sport, self.open_glb,
                                         self.requests, browser_note,
                                         self.pushes_sent))
        return lines


def should_fetch(enabled: bool, manual: bool, include_manual: bool) -> bool:
    """Wird diese Quelle in diesem Lauf abgerufen?

    Abgeschaltete Quellen bleiben abgeschaltet. Eine Quelle, die als
    manuell gefuehrt wird, kann auf ausdruecklichen Wunsch doch abgerufen
    werden - Hoffenheim etwa antwortet dem eigenen Rechner normal, nur den
    GitHub-Rechnern nicht.
    """
    if enabled:
        return True
    return bool(manual and include_manual)


def empty_result_is_suspect(found: int, previous: int,
                            legitimately_empty: bool) -> bool:
    """Ist ein leeres Ergebnis verdaechtig statt echt?

    Eine Quelle, die vorher Stellen hatte und jetzt keine liefert, ohne
    dass die Seite selbst "nichts offen" meldet, hat keine verwertbare
    Antwort gegeben. Das kann eine klemmende Seite sein oder eine, die
    nicht fertig geladen hat. Beides ist kein Beleg dafuer, dass die
    Stellen weg sind.
    """
    return found == 0 and previous > 0 and not legitimately_empty


class Runner:
    def __init__(self, dry_run: bool = False, only: Optional[List[str]] = None,
                 reclassify: bool = False, skip_details: bool = False,
                 include_manual: bool = False):
        self.dry_run = dry_run
        self.only = [o.lower() for o in (only or [])]
        self.reclassify = reclassify
        self.skip_details = skip_details
        self.include_manual = include_manual

        self.clubs, self.defaults = load_clubs()
        self.filters = load_filters()
        self.classifier = Classifier(self.filters)

        root = project_root()
        self.store = Store(root / "data" / "jobs.json",
                           root / "docs" / "data" / "jobs.json")
        self.store.settings = {
            "new_badge_days": int(self.filters.get("new_badge_days", 7)),
        }
        self.fetcher = Fetcher(
            delay=self.defaults.get("request_delay_seconds", 1.5),
            timeout=self.defaults.get("timeout_seconds", 25),
            retries=self.defaults.get("retries", 3),
            respect_robots=self.defaults.get("respect_robots", True),
        )
        self.notifier = Notifier(self.filters, dry_run=dry_run)
        # Der Browser startet erst, wenn eine JavaScript-Quelle ihn anfordert.
        self._browser = None

    # -- Browser -----------------------------------------------------------
    def _browser_session(self):
        """Browsersitzung fuer den ganzen Lauf, beim ersten Bedarf gestartet."""
        if self._browser is None:
            from .browser import BrowserSession
            self._browser = BrowserSession(
                timeout_seconds=self.defaults.get("timeout_seconds", 25) + 10,
                delay=self.defaults.get("request_delay_seconds", 1.5),
            )
        return self._browser

    def _close_browser(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None

    # -- Auswahl -----------------------------------------------------------
    def _selected(self, club: Club) -> bool:
        if not self.only:
            return True
        return club.short.lower() in self.only or club.name.lower() in self.only

    # -- Ein Lauf ----------------------------------------------------------
    def execute(self) -> RunReport:
        report = RunReport()
        self.store.load()

        new_a: List[Job] = []
        new_b: List[Job] = []
        first_run_happened = False
        warn_queue: List[Dict[str, Any]] = []

        for club in self.clubs:
            if not self._selected(club):
                continue
            for source in club.sources:
                entry = SourceReport(club=club.name, source_id=source.id,
                                     label=source.label)
                report.sources.append(entry)

                if not should_fetch(source.enabled, source.manual,
                                    self.include_manual):
                    entry.skipped = True
                    entry.manual = source.manual
                    # Zustand auch fuer nicht abgerufene Quellen pflegen,
                    # damit die Web-App sie anzeigen kann.
                    self.store.source_state(club, source)
                    if source.manual:
                        log.info("%s / %s: manuell beobachtet - %s",
                                 club.name, source.label,
                                 source.manual_reason or "bewusst nicht abgerufen")
                    else:
                        log.info("%s / %s: Quelle deaktiviert (Adapter '%s' "
                                 "noch offen)", club.name, source.label,
                                 source.adapter)
                    continue

                if source.manual:
                    log.info("%s / %s: manuelle Quelle wird auf Wunsch "
                             "abgerufen", club.name, source.label)
                    entry.manual = True

                try:
                    adapter_cls = get_adapter(source.adapter)
                except UnknownAdapter as exc:
                    entry.error = str(exc)
                    self.store.record_error(club, source, str(exc))
                    continue

                adapter = adapter_cls(self.fetcher, club, source, self.filters,
                                      browser_factory=self._browser_session)
                previous = self.store.previous_count(club, source)
                entry.first_run = self.store.is_first_run(club, source)

                detail_filter = (lambda job: False) if self.skip_details \
                    else self.store.needs_description
                log.info("Abruf: %s / %s", club.name, source.label)
                result = adapter.fetch(detail_filter=detail_filter)

                if not result.ok:
                    entry.error = result.error
                    self.store.record_error(club, source, result.error or "unbekannt")
                    warn_queue.append({
                        "club": club,
                        "detail": "Quelle '{}' nicht abrufbar: {}".format(
                            source.label, (result.error or "")[:120]),
                        "url": source.url,
                    })
                    continue

                monitoring = self.filters.get("monitoring", {}) or {}
                if empty_result_is_suspect(len(result.jobs), previous or 0,
                                           result.legitimately_empty):
                    # Hier nicht zusammenfuehren: merge_source wuerde alle
                    # bekannten Stellen dieser Quelle schliessen. Genau das
                    # waere falsch, denn geantwortet hat die Quelle nicht.
                    entry.error = ("0 Stellen, vorher {} - Bestand "
                                   "unverändert gelassen".format(previous))
                    self.store.record_error(club, source, entry.error)
                    if monitoring.get("warn_on_empty", True):
                        warn_queue.append({
                            "club": club,
                            "detail": "Quelle '{}' liefert plötzlich 0 Stellen "
                                      "(vorher {}). Die bekannten Stellen "
                                      "bleiben offen.".format(source.label,
                                                              previous),
                            "url": source.url,
                        })
                    log.warning("  0 Stellen trotz %s im Bestand - nichts "
                                "geschlossen, Quelle gilt als gestört",
                                previous)
                    continue

                if adapter.speculative_entry is not None:
                    # Das Portal fuehrt selbst einen Initiativbewerbungs-Eintrag.
                    state = self.store.club_state(club)
                    state["speculative_portal"] = {
                        "title": adapter.speculative_entry.title,
                        "url": adapter.speculative_entry.url,
                        "found_via": source.label,
                    }

                merge = self.store.merge_source(club, source, result.jobs)
                entry.found = merge.found
                entry.closed = len(merge.closed)

                # Einstufung erst jetzt: die Beschreibung liegt im Store.
                club_words = self.classifier.compile_club(club.short, club.keywords)
                for job in self.store.jobs_of_source(source.id):
                    if self.reclassify or not job.priority_reason:
                        self.classifier.apply(job, club_words)
                for job in merge.new_jobs:
                    self.classifier.apply(job, club_words)

                for job in merge.new_jobs:
                    if job.priority == "A":
                        entry.new_a += 1
                    elif job.priority == "B":
                        entry.new_b += 1
                    else:
                        entry.new_c += 1

                if merge.first_run:
                    first_run_happened = True
                    log.info("  Erstlauf: %d Stellen als Bestand gespeichert, "
                             "keine Einzelmeldungen", merge.found)
                else:
                    for job in merge.new_jobs:
                        if job.priority == "A":
                            new_a.append(job)
                        elif job.priority == "B":
                            new_b.append(job)

                # Fehlerueberwachung. Der Fall "0 trotz Bestand" ist
                # oben schon abgefangen und kommt hier nicht mehr an.
                prev = previous or 0
                if merge.found == 0 and result.legitimately_empty:
                    log.info("  Seite meldet selbst, dass nichts offen ist - kein Fehler")
                elif prev >= monitoring.get("drop_min_previous", 5) \
                        and merge.found > 0:
                    # Teilausfall: die Quelle antwortet, liefert aber deutlich
                    # weniger. Passiert etwa, wenn ein XML-Feed ausfaellt und
                    # der HTML-Rueckfall nur einen Teil der Stellen zeigt.
                    drop = 1.0 - (merge.found / float(prev))
                    if drop >= monitoring.get("warn_on_drop_ratio", 0.6):
                        warn_queue.append({
                            "club": club,
                            "detail": "Quelle '{}' liefert nur noch {} statt {} "
                                      "Stellen ({:.0f}% weniger).".format(
                                          source.label, merge.found, prev,
                                          drop * 100),
                            "url": source.url,
                        })

                log.info("  %d gefunden, %d neu (A:%d B:%d C:%d), %d geschlossen",
                         merge.found, len(merge.new_jobs), entry.new_a,
                         entry.new_b, entry.new_c, entry.closed)

        # -- Zaehler und Meldungen ----------------------------------------
        self.store.refresh_counts()
        open_jobs = [j for j in self.store.jobs.values() if j.status == "offen"]
        report.open_sport = sum(1 for j in open_jobs if j.priority in ("A", "B"))
        report.open_glb = sum(1 for j in open_jobs if j.priority == "A")

        if first_run_happened:
            self.notifier.push_startup_summary(
                sport_count=report.open_sport,
                glb_count=report.open_glb,
                club_count=len({j.club_short for j in open_jobs}),
            )

        for job in new_a:                       # A immer als eigene Nachricht
            self.notifier.push_job(job)
        if new_b:
            self.notifier.push_bundle(new_b, priority="B")

        for warning in warn_queue:
            club = warning["club"]
            if not self.store.should_warn(club):
                log.info("Warnung für %s heute schon verschickt, unterdrückt",
                         club.name)
                continue
            if self.notifier.push_warning(club.name, warning["detail"],
                                          warning.get("url")):
                self.store.mark_warned(club)
            for entry in report.sources:
                if entry.club == club.name:
                    entry.warned = True

        self.store.save(dry_run=self.dry_run)
        report.pushes_sent = self.notifier.sent
        report.requests = self.fetcher.request_count
        if self._browser is not None:
            report.browser_pages = self._browser.page_count
        self._close_browser()
        self.fetcher.close()
        return report
