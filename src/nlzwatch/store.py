"""Zustand in data/jobs.json: neue Stellen erkennen, geschlossene markieren."""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Club, Job, Source

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@dataclass
class MergeResult:
    """Was ein Abruf einer Quelle veraendert hat."""

    source_id: str
    first_run: bool = False
    new_jobs: List[Job] = field(default_factory=list)
    updated: int = 0
    closed: List[Job] = field(default_factory=list)
    found: int = 0


class Store:
    """Laedt und schreibt data/jobs.json und spiegelt es nach docs/data/."""

    def __init__(self, path: Path, mirror_path: Optional[Path] = None):
        self.path = Path(path)
        self.mirror_path = Path(mirror_path) if mirror_path else None
        self.jobs: Dict[str, Job] = {}
        self.clubs: Dict[str, Dict[str, Any]] = {}
        self._loaded_raw: Dict[str, Any] = {}
        # Werte, die die Web-App braucht und nicht doppelt pflegen soll
        self.settings: Dict[str, Any] = {}

    # -- Laden und Speichern ----------------------------------------------
    def load(self) -> None:
        if not self.path.exists():
            log.info("Kein bestehender Zustand, beginne mit leerer Datei")
            return
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.error("data/jobs.json nicht lesbar (%s) - beginne leer", exc)
            return
        self._loaded_raw = raw
        self.clubs = dict(raw.get("clubs") or {})
        for item in raw.get("jobs") or []:
            try:
                job = Job.from_dict(item)
            except TypeError:
                continue
            if job.id:
                self.jobs[job.id] = job
        log.info("Zustand geladen: %d Stellen, %d Vereine",
                 len(self.jobs), len(self.clubs))

    def to_dict(self) -> Dict[str, Any]:
        jobs = sorted(
            (j.to_dict() for j in self.jobs.values()),
            key=lambda d: (d.get("first_seen") or "", d.get("club") or ""),
            reverse=True,
        )
        return {
            "version": SCHEMA_VERSION,
            "generated_at": now_iso(),
            "settings": self.settings,
            "clubs": self.clubs,
            "jobs": jobs,
        }

    def save(self, dry_run: bool = False) -> None:
        if dry_run:
            log.info("[dry-run] data/jobs.json wird nicht geschrieben "
                     "(%d Stellen im Speicher)", len(self.jobs))
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        tmp.replace(self.path)
        log.info("data/jobs.json geschrieben (%d Stellen)", len(self.jobs))
        if self.mirror_path:
            self.mirror_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.path, self.mirror_path)
            log.info("Kopie fuer die Web-App: %s",
                     self.mirror_path.relative_to(self.path.parent.parent)
                     if self.mirror_path.is_relative_to(self.path.parent.parent)
                     else self.mirror_path)

    # -- Vereins- und Quellenzustand --------------------------------------
    def club_state(self, club: Club) -> Dict[str, Any]:
        state = self.clubs.setdefault(club.short, {})
        state["name"] = club.name
        state["speculative"] = club.speculative
        state.setdefault("sources", {})
        state.setdefault("last_success", None)
        state.setdefault("last_error", None)
        state.setdefault("warned_on", None)
        return state

    def source_state(self, club: Club, source: Source) -> Dict[str, Any]:
        sources = self.club_state(club)["sources"]
        state = sources.setdefault(source.id, {})
        state["label"] = source.label
        state["url"] = source.url
        state["adapter"] = source.adapter
        state["manual"] = source.manual
        if source.manual:
            state["manual_reason"] = source.manual_reason
            state["manual_hint"] = source.manual_hint
        state.setdefault("first_run_done", False)
        state.setdefault("last_success", None)
        state.setdefault("last_error", None)
        state.setdefault("last_count", None)
        return state

    def is_first_run(self, club: Club, source: Source) -> bool:
        return not self.source_state(club, source).get("first_run_done")

    def previous_count(self, club: Club, source: Source) -> Optional[int]:
        return self.source_state(club, source).get("last_count")

    def needs_description(self, job: Job) -> bool:
        """Detailseite nur holen, wenn noch kein Text gespeichert ist."""
        existing = self.jobs.get(job.ensure_id())
        if existing is None:
            return True
        return not (existing.description or "").strip()

    def jobs_of_source(self, source_id: str) -> List[Job]:
        return [j for j in self.jobs.values() if j.source_id == source_id]

    def should_warn(self, club: Club) -> bool:
        """Hoechstens eine Warnung pro Verein und Tag."""
        return self.club_state(club).get("warned_on") != today()

    def mark_warned(self, club: Club) -> None:
        self.club_state(club)["warned_on"] = today()

    # -- Zusammenfuehren --------------------------------------------------
    def merge_source(self, club: Club, source: Source,
                     fetched: List[Job]) -> MergeResult:
        """Abrufergebnis einarbeiten und Aenderungen zurueckgeben."""
        stamp = now_iso()
        result = MergeResult(source_id=source.id, found=len(fetched))
        first_run = self.is_first_run(club, source)
        result.first_run = first_run

        seen_ids = set()
        for job in fetched:
            job.ensure_id()
            seen_ids.add(job.id)
            existing = self.jobs.get(job.id)
            if existing is None:
                job.first_seen = stamp
                job.last_seen = stamp
                job.status = "offen"
                job.initial = first_run
                self.jobs[job.id] = job
                result.new_jobs.append(job)
                continue

            # Bekannte Stelle: Felder auffrischen, Historie bewahren
            existing.last_seen = stamp
            if existing.status == "geschlossen":
                existing.status = "offen"
                existing.closed_at = None
            # "priority" fehlt hier absichtlich: eingestuft wird erst nach
            # dem Zusammenfuehren, wenn die gespeicherte Beschreibung vorliegt.
            for attr in ("title", "url", "location", "employment_type",
                         "department", "published_at", "deadline", "contact",
                         "apply_url", "source_label", "club", "club_short"):
                value = getattr(job, attr, None)
                if value:
                    setattr(existing, attr, value)
            if job.description and job.description != existing.description:
                existing.description = job.description
                existing.description_fetched = job.description_fetched
            result.updated += 1

        # Verschwundene Stellen schliessen (nur bei erfolgreichem Abruf)
        for job in self.jobs.values():
            if job.source_id != source.id:
                continue
            if job.id in seen_ids or job.status == "geschlossen":
                continue
            job.status = "geschlossen"
            job.closed_at = stamp
            result.closed.append(job)

        state = self.source_state(club, source)
        state["first_run_done"] = True
        state["last_success"] = stamp
        state["last_error"] = None
        state["last_count"] = len(fetched)
        self.club_state(club)["last_success"] = stamp
        self.club_state(club)["last_error"] = None
        return result

    def record_error(self, club: Club, source: Source, message: str) -> None:
        stamp = now_iso()
        state = self.source_state(club, source)
        state["last_error"] = {"at": stamp, "message": message}
        self.club_state(club)["last_error"] = {
            "at": stamp, "source": source.id, "message": message,
        }

    def refresh_counts(self) -> None:
        """Zaehler je Verein neu berechnen (fuer die Web-App)."""
        for short, state in self.clubs.items():
            open_jobs = [j for j in self.jobs.values()
                         if j.club_short == short and j.status == "offen"]
            state["open_total"] = len(open_jobs)
            state["open_sport"] = sum(1 for j in open_jobs if j.priority in ("A", "B"))
            state["open_glb"] = sum(1 for j in open_jobs if j.priority == "A")
