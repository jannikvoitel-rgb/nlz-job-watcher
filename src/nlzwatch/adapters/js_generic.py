"""Adapter fuer Seiten, die ihre Stellen per JavaScript nachladen.

Genutzt von TSG Hoffenheim und RB Leipzig. Die Stellenliste wird in einem
echten Browser gerendert, danach greift dieselbe Selektor-Logik wie bei
generic_html.

Die Detailseiten brauchen meist keinen Browser: bei RB Leipzig liegen sie
bei SmartRecruiters und sind normal abrufbar. Nur wenn
``detail_needs_browser: true`` gesetzt ist, wird auch dafuer gerendert.

Zusaetzliche Parameter:
  wait_for              CSS-Selektor, auf den vor dem Auslesen gewartet wird
  loaded_marker         Text, der belegt, dass die Seite fertig geladen ist.
                        Steht er da und es gibt trotzdem keine Stellen, ist
                        die Seite legitim leer - wichtig bei Hoffenheim, die
                        das nicht hinschreiben.
  detail_needs_browser  true, wenn auch die Detailseite gerendert werden muss
  exclude_link_hosts    Hosts von Dienstleistern, die nicht zum Verein zaehlen
"""
from __future__ import annotations

import logging

from ..models import Job
from .generic_html import GenericHtmlAdapter

log = logging.getLogger(__name__)


class JsGenericAdapter(GenericHtmlAdapter):
    name = "js_generic"

    def _load_list_html(self) -> str:
        browser = self.require_browser()
        return browser.get_html(self.source.url,
                                wait_for=self.params.get("wait_for"))

    def looks_legitimately_empty(self, html: str) -> bool:
        """Geladene Seite ohne Stellen ist kein Fehler.

        Hoffenheim schreibt bei null offenen Stellen keinen Hinweis hin.
        Beleg fuer das korrekte Laden ist deshalb ein Textbaustein, der
        immer da ist - bei Hoffenheim der Ansprechpartner-Block.
        """
        marker = self.params.get("loaded_marker")
        if marker and html and str(marker).lower() in html.lower():
            log.info("  Seite ist geladen (Marker '%s' gefunden), aber ohne "
                     "Stellen - kein Fehler", marker)
            return True
        return super().looks_legitimately_empty(html)

    def enrich(self, job: Job) -> None:
        if not self.params.get("detail_needs_browser"):
            return super().enrich(job)

        if job.description or not job.url or job.url == self.source.url:
            return
        from .. import jsonld
        from ..textclean import html_to_text

        browser = self.require_browser()
        html = browser.get_html(job.url)
        data = jsonld.extract(html)
        text = ""
        if data.get("description_html"):
            text = html_to_text(data["description_html"])
        if not text:
            text = html_to_text(html, root_selector=self.params.get("detail_root"))
        if text:
            job.description = text
            job.description_fetched = True
        if data.get("published_at") and not job.published_at:
            job.published_at = data["published_at"]
        if data.get("location") and not job.location:
            job.location = data["location"]
        if data.get("employment_type") and not job.employment_type:
            job.employment_type = data["employment_type"]
