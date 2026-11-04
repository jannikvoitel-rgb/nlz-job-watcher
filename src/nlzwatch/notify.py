"""Push-Nachrichten ueber ntfy.sh.

Das Topic kommt ausschliesslich aus der Umgebung (GitHub-Secret NTFY_TOPIC)
und wird nie geloggt oder in eine Datei geschrieben.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

from .models import Job

log = logging.getLogger(__name__)

DEFAULT_SERVER = "https://ntfy.sh"

# ntfy: 1 = min, 3 = default, 4 = high, 5 = urgent
PRIORITY_MAP = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5, "max": 5}


class NotifierError(Exception):
    pass


class Notifier:
    """Verschickt Push-Nachrichten, optional als Trockenlauf."""

    def __init__(self, filters: Dict[str, Any], dry_run: bool = False,
                 timeout: int = 15):
        self.push_config = (filters or {}).get("push", {}) or {}
        self.dry_run = dry_run
        self.timeout = timeout
        self.sent = 0
        self.failed = 0

        self.server = (os.environ.get("NTFY_SERVER") or DEFAULT_SERVER).rstrip("/")
        self._topic = os.environ.get("NTFY_TOPIC") or ""
        self.enabled = bool(self._topic)
        if not self.enabled and not dry_run:
            log.warning("NTFY_TOPIC ist nicht gesetzt - es werden keine Pushes "
                        "verschickt. Siehe README.")

    # -- intern ------------------------------------------------------------
    def _config_for(self, priority: str) -> Dict[str, Any]:
        key = "priority_{}".format((priority or "b").lower())
        return self.push_config.get(key, {}) or {}

    def _post(self, payload: Dict[str, Any], label: str) -> bool:
        """Nachricht senden. Loggt nur die Art, niemals das Topic."""
        if self.dry_run:
            log.info("[dry-run] Push unterdrueckt: %s | %s",
                     payload.get("title"), payload.get("message", "")[:80])
            return True
        if not self.enabled:
            log.info("Kein Topic gesetzt, Push uebersprungen: %s", label)
            return False
        payload = dict(payload)
        payload["topic"] = self._topic
        try:
            resp = requests.post(self.server, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            # Fehlertext kann die URL mit Topic enthalten, daher nur die Klasse
            self.failed += 1
            log.error("Push fehlgeschlagen (%s): %s", label, exc.__class__.__name__)
            return False
        self.sent += 1
        log.info("Push gesendet: %s", label)
        return True

    # -- oeffentliche Methoden --------------------------------------------
    def push_job(self, job: Job) -> bool:
        """Eine einzelne Stelle melden (immer fuer Prioritaet A)."""
        cfg = self._config_for(job.priority)
        if cfg.get("push") is False:
            return False
        title_tpl = cfg.get("title_template") or "Neue Stelle: {club}"
        payload = {
            "title": title_tpl.format(club=job.club),
            "message": job.title,
            "priority": PRIORITY_MAP.get(str(cfg.get("ntfy_priority", "default")), 3),
            "tags": list(cfg.get("tags") or []),
            "click": job.url or "",
        }
        if job.location:
            payload["message"] += "\n{}".format(job.location)
        return self._post(payload, "Prio {} / {}".format(job.priority, job.club))

    def push_bundle(self, jobs: List[Job], priority: str = "B") -> bool:
        """Mehrere Stellen eines Laufs in einer Nachricht zusammenfassen."""
        if not jobs:
            return False
        if len(jobs) == 1:
            return self.push_job(jobs[0])
        cfg = self._config_for(priority)
        if cfg.get("push") is False:
            return False
        clubs = []
        for job in jobs:
            if job.club not in clubs:
                clubs.append(job.club)
        if len(clubs) == 1:
            title = (cfg.get("title_template") or "Neue Stellen: {club}").format(
                club=clubs[0])
        else:
            title = "{} neue Sportstellen".format(len(jobs))
        lines = ["• {} ({})".format(j.title, j.club) for j in jobs]
        payload = {
            "title": title,
            "message": "\n".join(lines),
            "priority": PRIORITY_MAP.get(str(cfg.get("ntfy_priority", "default")), 3),
            "tags": list(cfg.get("tags") or []),
            "click": jobs[0].url or "",
        }
        return self._post(payload, "Sammelmeldung Prio {} ({} Stellen)".format(
            priority, len(jobs)))

    def push_startup_summary(self, sport_count: int, glb_count: int,
                             club_count: int, app_url: Optional[str] = None) -> bool:
        """Einmalige Startuebersicht statt einer Push-Flut beim ersten Lauf."""
        payload = {
            "title": "Startübersicht",
            "message": "{} Sportstellen offen, davon {} im GLB "
                       "({} Vereine erfasst)".format(sport_count, glb_count, club_count),
            "priority": 3,
            "tags": ["clipboard"],
        }
        if app_url:
            payload["click"] = app_url
        return self._post(payload, "Startuebersicht")

    def push_warning(self, club_name: str, detail: str,
                     url: Optional[str] = None) -> bool:
        """Warnung, wenn eine Quelle verdaechtig aussieht."""
        payload = {
            "title": "Scraper für {} prüfen".format(club_name),
            "message": detail,
            "priority": PRIORITY_MAP["default"],
            "tags": ["warning"],
        }
        if url:
            payload["click"] = url
        return self._post(payload, "Warnung / {}".format(club_name))

    def push_test(self) -> bool:
        """Testnachricht mit hoher Prioritaet, wie eine GLB-Meldung."""
        payload = {
            "title": "⚽ GLB-Stelle: Testverein",
            "message": "Testnachricht des NLZ-Stellenwatchers.\n"
                       "Antippen öffnet die DFB-Seite.",
            "priority": PRIORITY_MAP["high"],
            "tags": ["soccer"],
            "click": "https://www.dfb.de/trainer/",
        }
        return self._post(payload, "Testnachricht (Prio A)")
