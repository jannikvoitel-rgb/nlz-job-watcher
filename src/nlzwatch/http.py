"""Hoeflicher HTTP-Client: robots.txt, Pausen, Timeouts, Retries.

Haelt sich bewusst zurueck: eine Anfrage pro 1,5 Sekunden je Host,
Wiederholungen mit wachsendem Abstand, klarer User-Agent.
"""
from __future__ import annotations

import logging
import os
import random
import time
import urllib.robotparser as robotparser
from typing import Dict, Optional
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

# Kontaktangabe im User-Agent. Bewusst ueber eine Umgebungsvariable, damit
# keine private Adresse im Repo landet.
DEFAULT_CONTACT = os.environ.get(
    "WATCHER_CONTACT", "privates Stellen-Monitoring, Kontakt auf Anfrage"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 "
    "NLZ-Stellenwatcher/1.0 (+{})".format(DEFAULT_CONTACT)
)

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class RobotsDisallowed(Exception):
    """Die robots.txt der Seite verbietet diesen Pfad."""


class Fetcher:
    """Teilt sich eine Session, cached robots.txt und bremst pro Host."""

    def __init__(self, delay: float = 1.5, timeout: int = 25, retries: int = 3,
                 respect_robots: bool = True):
        self.delay = float(delay)
        self.timeout = int(timeout)
        self.retries = int(retries)
        self.respect_robots = bool(respect_robots)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
        })
        self._last_request: Dict[str, float] = {}
        self._robots: Dict[str, Optional[robotparser.RobotFileParser]] = {}
        self.request_count = 0

    # -- robots.txt --------------------------------------------------------
    def _robots_for(self, url: str) -> Optional[robotparser.RobotFileParser]:
        host = urlsplit(url).netloc.lower()
        if host in self._robots:
            return self._robots[host]
        robots_url = "{}://{}/robots.txt".format(urlsplit(url).scheme or "https", host)
        parser: Optional[robotparser.RobotFileParser] = None
        try:
            resp = self.session.get(robots_url, timeout=self.timeout)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if resp.status_code == 200 and "text/plain" in ctype:
                parser = robotparser.RobotFileParser()
                parser.parse(resp.text.splitlines())
            else:
                # Keine verwertbare robots.txt: nach Konvention nicht gesperrt.
                log.debug("robots.txt von %s nicht verwertbar (%s, %s)",
                          host, resp.status_code, ctype or "ohne Typ")
        except requests.RequestException as exc:
            log.debug("robots.txt von %s nicht abrufbar: %s", host, exc)
        self._robots[host] = parser
        return parser

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parser = self._robots_for(url)
        if parser is None:
            return True
        try:
            return parser.can_fetch(USER_AGENT, url) or parser.can_fetch("*", url)
        except Exception:
            return True

    # -- Pausen ------------------------------------------------------------
    def _wait(self, url: str) -> None:
        host = urlsplit(url).netloc.lower()
        last = self._last_request.get(host)
        if last is not None:
            elapsed = time.monotonic() - last
            pause = self.delay - elapsed
            if pause > 0:
                time.sleep(pause)
        self._last_request[host] = time.monotonic()

    # -- Abruf -------------------------------------------------------------
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET mit robots-Pruefung, Pause, Timeout und Backoff."""
        if not self.allowed(url):
            raise RobotsDisallowed("robots.txt verbietet {}".format(url))

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            self._wait(url)
            try:
                self.request_count += 1
                resp = self.session.get(url, timeout=self.timeout,
                                        allow_redirects=True, **kwargs)
                if resp.status_code in RETRY_STATUS and attempt < self.retries:
                    backoff = self.delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    log.warning("HTTP %s bei %s, neuer Versuch in %.1fs",
                                resp.status_code, url, backoff)
                    time.sleep(backoff)
                    continue
                resp.raise_for_status()
                return resp
            except requests.HTTPError as exc:
                # Dauerhafte Client-Fehler (404, 403, 410) nicht wiederholen:
                # weitere Versuche aendern daran nichts.
                status = exc.response.status_code if exc.response is not None else None
                if status is not None and 400 <= status < 500 \
                        and status not in RETRY_STATUS:
                    raise RuntimeError(
                        "Abruf von {} fehlgeschlagen: HTTP {}".format(url, status))
                last_error = exc
                if attempt >= self.retries:
                    break
                backoff = self.delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                log.warning("Fehler bei %s (HTTP %s), neuer Versuch in %.1fs",
                            url, status, backoff)
                time.sleep(backoff)
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                backoff = self.delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                log.warning("Fehler bei %s (%s), neuer Versuch in %.1fs",
                            url, exc.__class__.__name__, backoff)
                time.sleep(backoff)
        raise RuntimeError("Abruf von {} fehlgeschlagen: {}".format(url, last_error))

    def get_text(self, url: str) -> str:
        resp = self.get(url)
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def get_bytes(self, url: str) -> bytes:
        """Rohdaten abrufen, etwa fuer PDF-Stellenausschreibungen."""
        return self.get(url).content

    def close(self) -> None:
        self.session.close()
