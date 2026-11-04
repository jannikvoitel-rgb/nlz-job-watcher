"""Adapter fuer Vereinsseiten ohne Bewerberportal.

Diese Seiten haben keine gemeinsame Technik, deshalb wird der Adapter
vollstaendig ueber CSS-Selektoren in clubs.yaml gesteuert. Unterstuetzt
werden auch :has() und Geschwister-Selektoren, damit auch Seiten ohne
sprechende Klassennamen abgebildet werden koennen.

Parameter unter params:
  item            Container je Stelle (Pflicht)
  title           Titel. Fehlt er, wird der Text des Containers ohne den
                  Linktext genommen, sonst der Linktext selbst.
  link            Detail-Link. Standard: erstes a[href] im Container.
  description     Volltext, wenn er schon auf der Listenseite steht
  meta            Mehrere Meta-Werte (Ort, Vertragsart) im Container
  location        Ort, wenn er einen eigenen Selektor hat
  employment_type Vertragsart, wenn sie einen eigenen Selektor hat
  group_title     Ueberschrift des umgebenden Abschnitts. Sieht sie wie eine
                  Vertragsart aus, wird sie als solche uebernommen, sonst
                  als Bereich.
  group_as        "auto" (Standard), "employment_type" oder "department" -
                  erzwingt, wie die Gruppenueberschrift gedeutet wird.
  detail_root     Container der Beschreibung auf der Detailseite
  detail_is_pdf   true, wenn die Ausschreibung ein PDF ist
  require_link    true, wenn Eintraege ohne Link uebersprungen werden sollen
  link_relative_to
                  "root", wenn Links wie "./a/b" gegen die Seitenwurzel
                  aufzuloesen sind statt gegen den aktuellen Pfad. Bei
                  Hoffenheim erzeugt die Angular-Oberflaeche solche Links.
  min_pdf_text    Mindestlaenge fuer brauchbaren PDF-Text (Standard 400).
                  Darunter gilt die Ausschreibung als Bild-PDF.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from .. import jsonld
from ..dates import parse_date_de
from ..models import Job, make_job_id
from ..pdftext import looks_like_pdf, pdf_to_text
from ..textclean import guess_employment_type, html_to_text
from .base import Adapter

log = logging.getLogger(__name__)


class GenericHtmlAdapter(Adapter):
    name = "generic_html"

    # -- kleine Helfer -----------------------------------------------------
    @staticmethod
    def _one(scope: Tag, css: Optional[str]) -> Optional[Tag]:
        if not css:
            return None
        try:
            return scope.select_one(css)
        except Exception as exc:
            log.warning("Selektor '%s' ist ungültig: %s", css, exc)
            return None

    @staticmethod
    def _text(node: Optional[Tag]) -> str:
        return node.get_text(" ", strip=True) if node is not None else ""

    def _group_title(self, item: Tag) -> str:
        """Ueberschrift des umgebenden Abschnitts suchen.

        Geht vom Container nach oben und nimmt die erste Ebene, die eine
        passende Ueberschrift enthaelt - das ist die des eigenen Abschnitts.
        """
        css = self.params.get("group_title")
        if not css:
            return ""
        for parent in item.parents:
            if not isinstance(parent, Tag):
                continue
            heading = self._one(parent, css)
            if heading is not None:
                return self._text(heading)
        return ""

    def _resolve_link(self, href: str) -> str:
        """Link aufloesen, bei Bedarf gegen die Seitenwurzel.

        Hoffenheims Oberflaeche liefert "./tsg/karriere/..." - gegen den
        aktuellen Pfad aufgeloest ergaebe das einen doppelten Pfad und
        damit eine 403-Seite.
        """
        href = (href or "").strip()
        if not href:
            return ""
        if (str(self.params.get("link_relative_to", "")).lower() == "root"
                and href.startswith("./")):
            parts = urlsplit(self.source.url)
            return "{}://{}/{}".format(parts.scheme or "https", parts.netloc,
                                       href[2:].lstrip("/"))
        return self.absolute(href)

    def _excluded_host(self, url: str) -> bool:
        """Stellen von Dienstleistern aussortieren.

        RB Leipzig listet neben den Vereinsstellen auch Caterer und
        Sicherheitsfirmen. Das sind keine Stellen des Vereins.
        """
        hosts = self.params.get("exclude_link_hosts") or []
        if not hosts:
            return False
        host = urlsplit(url).netloc.lower()
        return any(str(h).lower() in host for h in hosts)

    def _assign_meta_values(self, job: Job, values: List[str]) -> None:
        """Meta-Werte in Vertragsart und Ort aufteilen."""
        contract, other = [], []
        for value in values:
            value = value.strip()
            if not value:
                continue
            if guess_employment_type(value, limit=len(value) + 1):
                contract.append(value)
            else:
                other.append(value)
        if contract and not job.employment_type:
            job.employment_type = ", ".join(dict.fromkeys(contract))
        if other and not job.location:
            job.location = ", ".join(dict.fromkeys(other))

    def _title_for(self, item: Tag, link: Optional[Tag]) -> str:
        """Titel bestimmen, auch wenn die Seite ihn nicht sauber auszeichnet."""
        css = self.params.get("title")
        if css:
            node = self._one(item, css)
            if node is not None:
                return self._text(node)

        link_text = self._text(link)
        item_text = self._text(item)
        if link_text and item_text.endswith(link_text):
            # VfB: "Recht: Rechtsreferendar (m/w/d)Ausschreibung Rechtsreferendar"
            stripped = item_text[: -len(link_text)].strip(" ·|-–—:")
            if stripped:
                return stripped
        if link_text:
            return link_text
        return item_text

    # -- Stellenliste ------------------------------------------------------
    def _load_list_html(self) -> str:
        """Listenseite holen. Unterklassen rendern sie stattdessen."""
        return self.fetcher.get_text(self.source.url)

    def list_jobs(self) -> List[Job]:
        item_css = self.params.get("item")
        if not item_css:
            raise ValueError(
                "Quelle {}: params.item fehlt in clubs.yaml".format(self.source.id))

        self._list_html = self._load_list_html()
        soup = BeautifulSoup(self._list_html, "lxml")

        matches = soup.select(item_css)
        # Fehlerhaft verschachteltes HTML (beim VfB sind <p> ineinander
        # geschachtelt) liefert denselben Eintrag doppelt: einmal als
        # aeusseres, einmal als inneres Element. Das aeussere umfasst dann
        # mehrere Stellen und haette einen unbrauchbaren Titel. Deshalb nur
        # die innersten Treffer verwenden.
        match_set = set(id(m) for m in matches)
        items = [m for m in matches
                 if not any(id(d) in match_set for d in m.descendants
                            if isinstance(d, Tag))]
        if len(items) != len(matches):
            log.debug("%s: %d von %d Treffern waren verschachtelt",
                      self.source.id, len(matches) - len(items), len(matches))

        jobs: List[Job] = []
        seen = set()
        # Steht der Volltext schon auf der Listenseite, enthaelt der Container
        # Links aus der Beschreibung (bei Paderborn eine Bewerbungsadresse).
        # Die duerfen nicht als Stellen-Link gelten, sonst zeigt die Meldung
        # auf eine fremde Seite. Dann nur ein ausdruecklich gesetzter Link.
        auto_link = not self.params.get("description")

        for item in items:
            if self.params.get("link"):
                link = self._one(item, self.params["link"])
            elif auto_link:
                link = self._one(item, "a[href]")
                if link is None and item.name == "a" and item.get("href"):
                    # Der Container ist selbst der Link (RB Leipzig)
                    link = item
            else:
                link = None
            if link is not None and not link.get("href"):
                link = None
            if link is None and self.params.get("require_link"):
                continue

            title = self._title_for(item, link)
            if not title:
                continue

            url = self._resolve_link(link.get("href", "")) if link is not None else ""
            if url and self._excluded_host(url):
                continue
            job = self.new_job(title=title, url=url or self.source.url)

            if link is None:
                # Mehrere Stellen auf einer Seite (Paderborn, HSV e.V.):
                # ohne den Titel waeren alle IDs gleich.
                #
                # Die ID wird ueber den Titel gebildet, NICHT ueber die URL
                # mit angehaengtem "#titel": normalize_url() entfernt den
                # Fragment-Teil, dadurch waeren wieder alle IDs identisch.
                job.id = make_job_id(
                    self.club.short, "",
                    "{}|{}".format(self.source.id, title))

            if job.id in seen:
                continue
            seen.add(job.id)

            if self.params.get("meta"):
                values = [self._text(n) for n in item.select(self.params["meta"])]
                self._assign_meta_values(job, values)
            location = self._one(item, self.params.get("location"))
            if location is not None:
                job.location = self._text(location) or job.location
            employment = self._one(item, self.params.get("employment_type"))
            if employment is not None:
                job.employment_type = self._text(employment) or job.employment_type
            date_node = self._one(item, self.params.get("date"))
            if date_node is not None:
                job.published_at = parse_date_de(self._text(date_node))

            group = self._group_title(item)
            if group:
                mode = str(self.params.get("group_as", "auto")).lower()
                looks_like_contract = bool(
                    guess_employment_type(group, limit=len(group) + 1))
                if mode == "employment_type":
                    if looks_like_contract and not job.employment_type:
                        job.employment_type = group
                elif mode == "department":
                    if not job.department:
                        job.department = group
                elif looks_like_contract:
                    if not job.employment_type:
                        job.employment_type = group
                elif not job.department:
                    job.department = group

            description_node = self._one(item, self.params.get("description"))
            if description_node is not None:
                text = html_to_text(str(description_node))
                if text:
                    job.description = text
                    job.description_fetched = True

            if not job.employment_type:
                job.employment_type = guess_employment_type(
                    title + "\n" + (job.description or ""))

            jobs.append(job)

        log.debug("%s: %d Stellen in der Liste", self.source.id, len(jobs))
        return jobs

    # -- Detailseite -------------------------------------------------------
    def enrich(self, job: Job) -> None:
        if job.description:
            return          # Volltext stand schon auf der Listenseite
        if not job.url or job.url == self.source.url:
            return          # keine eigene Detailseite

        if self.params.get("detail_is_pdf") or looks_like_pdf(job.url):
            data = self.fetcher.get_bytes(job.url)
            text = pdf_to_text(data) or ""
            minimum = int(self.params.get("min_pdf_text", 400))
            if len(text) >= minimum:
                job.description = text
                job.description_fetched = True
            else:
                # Der VfB veroeffentlicht einen Teil seiner Ausschreibungen
                # als Bild-PDF. Da steht kein Text drin, den man auslesen
                # koennte. Das wird benannt statt stillschweigend leer
                # gelassen - der Link fuehrt ja zur Anzeige.
                log.info("  %s: Ausschreibung ist ein Bild-PDF (%d Zeichen "
                         "Text), nur Link verfügbar", job.title[:50], len(text))
                job.description = (
                    "Diese Ausschreibung liegt nur als Bild-PDF vor und lässt "
                    "sich nicht als Text auslesen. Bitte über den Button "
                    "„Zur Originalanzeige“ öffnen."
                )
                job.description_fetched = False
            return

        html = self.fetcher.get_text(job.url)
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
        if data.get("deadline"):
            job.deadline = data["deadline"]
        if data.get("location") and not job.location:
            job.location = data["location"]
        if data.get("employment_type") and not job.employment_type:
            job.employment_type = data["employment_type"]
