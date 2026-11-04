"""Adapter fuer HRworks-Stellenportale.

Genutzt von Mainz 05, SC Freiburg, Borussia Moenchengladbach und
Eintracht Frankfurt e.V. - teils unter jobapplication.hrworks.de, teils
unter einer eigenen Vereinsdomain. Das Markup ist identisch.

Besonderheiten:
- Die Element-IDs der Seite sind durchnummeriert und aendern sich bei jeder
  Aenderung am Portal. Hier wird daher ausschliesslich ueber Klassen gesucht.
- Die Meta-Zeile einer Stelle ("Berufseinsteiger - Festanstellung - Vollzeit")
  hat keine festen Positionen. Welcher Wert zu welchem Feld gehoert, verraten
  die Filter-Auswahllisten derselben Seite.
- Detailseiten liefern JSON-LD mit vollstaendiger Beschreibung.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set

from bs4 import BeautifulSoup, Tag

from .. import jsonld
from ..models import Job
from ..textclean import guess_employment_type, html_to_text
from .base import Adapter

log = logging.getLogger(__name__)

# Beschriftungen der Filterlisten, die wir auswerten.
LABEL_DEPARTMENT = "tätigkeitsbereich"
LABEL_CAREER = "karrierestufe"
LABEL_CONTRACT = "arbeitsverhältnis"
LABEL_WORKTIME = "arbeitszeit"

# Werte, die in keiner Zuordnung etwas beitragen.
VOCAB_NOISE = {"alle", "vor ort", "mobiles arbeiten", "hybrides arbeiten", ""}

def _contact_after(text: str) -> Optional[str]:
    """Namen hinter der Ueberschrift "Kontaktperson" lesen.

    Zeilenweise statt per Regex, weil HRworks den Block mal als fetten
    Absatz und mal als Ueberschrift auszeichnet.
    """
    lines = [ln.strip() for ln in (text or "").split("\n")]
    for index, line in enumerate(lines):
        if line.lstrip("# ").strip().lower() != "kontaktperson":
            continue
        for candidate in lines[index + 1:index + 5]:
            name = candidate.lstrip("# ").strip().rstrip(":").strip()
            if not name:
                continue
            if name.lower().startswith(("e-mail", "email", "bewerben",
                                        "telefon", "übersicht")):
                return None
            if 3 <= len(name) <= 60:
                return name
        return None
    return None


class HRworksAdapter(Adapter):
    name = "hrworks"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._vocab: Dict[str, Set[str]] = {}
        self._has_form = False

    # -- Vokabular der Filterlisten ---------------------------------------
    def _read_vocabulary(self, soup: BeautifulSoup) -> Dict[str, Set[str]]:
        """Auswahllisten der Seite lesen: welcher Wert gehoert zu welchem Feld?"""
        vocab: Dict[str, Set[str]] = {}
        for select in soup.select("select.form-control"):
            group = select.find_parent(class_="form-group")
            if group is None:
                continue
            label = group.find("label")
            if label is None:
                continue
            key = label.get_text(" ", strip=True).rstrip(":").strip().lower()
            values = set()
            for option in select.find_all("option"):
                text = option.get_text(" ", strip=True)
                if text.lower() not in VOCAB_NOISE:
                    values.add(text)
            if values:
                vocab[key] = values
        self._has_form = bool(vocab)
        log.debug("%s: Filterlisten erkannt: %s", self.source.id, sorted(vocab))
        return vocab

    def _assign_meta(self, job: Job, meta_text: str) -> None:
        """Meta-Zeile anhand des Seitenvokabulars den Feldern zuordnen."""
        if not meta_text:
            return
        tokens = [t.strip() for t in re.split(r"\s+-\s+|\n", meta_text) if t.strip()]
        departments: List[str] = []
        contract: List[str] = []
        audience: List[str] = []
        unmatched: List[str] = []

        for token in tokens:
            if token in self._vocab.get(LABEL_DEPARTMENT, set()):
                departments.append(token)
            elif token in self._vocab.get(LABEL_CONTRACT, set()) \
                    or token in self._vocab.get(LABEL_WORKTIME, set()):
                contract.append(token)
            elif token in self._vocab.get(LABEL_CAREER, set()):
                audience.append(token)
            else:
                unmatched.append(token)

        if departments:
            job.department = ", ".join(dict.fromkeys(departments))
        if contract:
            job.employment_type = ", ".join(dict.fromkeys(contract))
        if audience:
            job.audience = ", ".join(dict.fromkeys(audience))
        if unmatched:
            log.debug("%s: Meta-Werte ohne Zuordnung: %s",
                      self.source.id, unmatched)

    # -- Ort ---------------------------------------------------------------
    @staticmethod
    def _locations(block: Tag) -> Optional[str]:
        """Orte aus den Kartenlinks lesen und auf den Ortsnamen kuerzen."""
        cities: List[str] = []
        for link in block.select('a[href*="google.com/maps"]'):
            text = link.get_text(" ", strip=True)
            if not text:
                continue
            # "Mönchengladbach, Am Minto 3, Deutschland" -> "Mönchengladbach"
            city = text.split(",")[0].strip()
            if city and city not in cities:
                cities.append(city)
        return ", ".join(cities) or None

    # -- Stellenliste ------------------------------------------------------
    def list_jobs(self) -> List[Job]:
        self._list_html = self.fetcher.get_text(self.source.url)
        soup = BeautifulSoup(self._list_html, "lxml")
        self._vocab = self._read_vocabulary(soup)

        jobs: List[Job] = []
        seen: Set[str] = set()
        for block in soup.select("div.portlet"):
            link = block.select_one("a.job-offer-content[href]")
            if link is None:
                continue        # Filter-Portlet, keine Stelle

            heading = block.select_one("a.job-offer-content h2")
            title = (heading.get_text(" ", strip=True) if heading
                     else (link.get("title") or link.get_text(" ", strip=True)))
            url = self.absolute(link.get("href", ""))
            if not title or not url:
                continue
            key = url.split("id=")[-1]
            if key in seen:
                continue
            seen.add(key)

            job = self.new_job(title=title, url=url,
                               location=self._locations(block))
            meta = block.select_one("div.margin-top-10")
            self._assign_meta(job, meta.get_text(" ", strip=True) if meta else "")
            jobs.append(job)

        log.debug("%s: %d Stellen in der Liste", self.source.id, len(jobs))
        return jobs

    def looks_legitimately_empty(self, html: str) -> bool:
        """Filterformular da, aber keine Stellen: die Seite ist wirklich leer.

        Verlaesslicher als ein Textmuster, weil HRworks den Hinweistext je
        Mandant anders formuliert.
        """
        if self._has_form:
            return True
        return super().looks_legitimately_empty(html)

    # -- Detailseite -------------------------------------------------------
    def enrich(self, job: Job) -> None:
        html = self.fetcher.get_text(job.url)
        data = jsonld.extract(html)

        description = ""
        if data.get("description_html"):
            description = html_to_text(data["description_html"])
        if not description:
            description = html_to_text(html, root_selector="div.portlet-body, main")
        if description:
            job.description = description
            job.description_fetched = True

        if data.get("published_at"):
            job.published_at = data["published_at"]
        if data.get("deadline"):
            job.deadline = data["deadline"]
        if data.get("location") and not job.location:
            job.location = data["location"]
        if data.get("employment_type"):
            job.employment_type = data["employment_type"]
        elif not job.employment_type:
            job.employment_type = guess_employment_type(
                job.title + "\n" + (job.description or ""))

        soup = BeautifulSoup(html, "lxml")
        apply_link = soup.select_one('a[href*="apply?id="]')
        if apply_link is not None:
            job.apply_url = self.absolute(apply_link.get("href", ""))

        # Ansprechpartner. Die E-Mail steckt hinter einem Klick und bleibt dort.
        contact = _contact_after(html_to_text(html))
        if contact:
            job.contact = contact
