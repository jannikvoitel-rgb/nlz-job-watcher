"""Gerenderte Seiten ueber einen echten Browser holen.

Drei Quellen laden ihre Stellen erst per JavaScript nach und sind mit
requests nicht zu lesen. Nur fuer diese wird Chromium gestartet - einmal
pro Lauf, nicht pro Seite.

Zurueckhaltung wie beim normalen Abruf: Pause je Host, Timeouts, und
Bilder, Videos und Schriften werden gar nicht geladen.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional
from urllib.parse import urlsplit

from .http import USER_AGENT

log = logging.getLogger(__name__)

# Ressourcen, die fuer das Auslesen von Text nichts beitragen
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


class BrowserUnavailable(Exception):
    """Playwright oder Chromium fehlt oder laesst sich nicht starten."""


class BrowserSession:
    """Haelt einen Chromium offen und liefert gerenderte Seiten."""

    def __init__(self, timeout_seconds: int = 30, delay: float = 1.5,
                 viewport_width: int = 1280, viewport_height: int = 1600):
        self.timeout_ms = int(timeout_seconds * 1000)
        self.delay = float(delay)
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self._playwright = None
        self._browser = None
        self._context = None
        self._last_request: Dict[str, float] = {}
        self.page_count = 0

    # -- Start und Ende ----------------------------------------------------
    def _ensure_started(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailable(
                "Playwright ist nicht installiert. "
                "pip install -r requirements-playwright.txt "
                "&& python -m playwright install chromium"
            ) from exc
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._context = self._browser.new_context(
                user_agent=USER_AGENT,
                viewport=self.viewport,
                locale="de-DE",
            )
            self._context.set_default_timeout(self.timeout_ms)
            self._context.route("**/*", self._filter_requests)
        except Exception as exc:
            self.close()
            raise BrowserUnavailable(
                "Chromium liess sich nicht starten: {}".format(exc)) from exc
        log.info("Browser gestartet (nur für JavaScript-Seiten)")

    @staticmethod
    def _filter_requests(route, request) -> None:
        if request.resource_type in BLOCKED_RESOURCE_TYPES:
            route.abort()
        else:
            route.continue_()

    def close(self) -> None:
        for name in ("_context", "_browser"):
            obj = getattr(self, name, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
                setattr(self, name, None)
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- Pausen ------------------------------------------------------------
    def _wait_turn(self, url: str) -> None:
        host = urlsplit(url).netloc.lower()
        last = self._last_request.get(host)
        if last is not None:
            pause = self.delay - (time.monotonic() - last)
            if pause > 0:
                time.sleep(pause)
        self._last_request[host] = time.monotonic()

    # -- Abruf -------------------------------------------------------------
    def get_html(self, url: str, wait_for: Optional[str] = None,
                 settle_ms: int = 1200) -> str:
        """Seite rendern und das fertige HTML zurueckgeben.

        wait_for ist ein CSS-Selektor, auf den gewartet wird. Fehlt er oder
        erscheint er nicht, wird nach kurzer Beruhigungszeit gelesen - eine
        Seite ohne Stellen soll keinen Fehler erzeugen.
        """
        self._ensure_started()
        self._wait_turn(url)
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded",
                      timeout=self.timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            except Exception:
                log.debug("networkidle bei %s nicht erreicht, lese trotzdem", url)
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=8000)
                except Exception:
                    log.info("  Selektor '%s' erschien nicht - die Seite hat "
                             "vermutlich keine Stellen", wait_for)
            if settle_ms:
                page.wait_for_timeout(settle_ms)
            self.page_count += 1
            return page.content()
        finally:
            try:
                page.close()
            except Exception:
                pass
