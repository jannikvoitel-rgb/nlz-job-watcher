"""Adapter fuer Personio-Stellenboersen.

Genutzt von 1. FC Koeln, Hertha BSC und dem HSV (zwei Boards).

Personio bietet zwei Wege:

1. Den XML-Feed unter ``/xml``. Er liefert alle Stellen samt vollstaendiger,
   nach Abschnitten gegliederter Beschreibung in einem einzigen Abruf -
   dazu Abteilung und Einstiegsart. Nicht jedes Board hat ihn aktiviert:
   bei Hertha und dem HSV-Aushilfenboard kommt er leer zurueck.
2. Die HTML-Seite des Boards. Dort stehen Titel, Ort und Vertragsart,
   die Beschreibung aber erst auf der Detailseite.

Der Adapter nimmt den Feed, wenn er etwas liefert, und faellt sonst
automatisch auf HTML zurueck.

Das ``createdAt`` des Feeds ist NICHT das Veroeffentlichungsdatum, sondern
der Anlagezeitpunkt des Datensatzes - bei Daueranzeigen Jahre alt. Das
echte Datum steht als ``datePosted`` im JSON-LD der Detailseite.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from .. import jsonld
from ..models import Job, make_job_id
from ..textclean import guess_employment_type, html_to_text
from .base import Adapter

log = logging.getLogger(__name__)

# Personio liefert englische Schluesselwoerter.
EMPLOYMENT_DE = {
    "permanent": "Festanstellung",
    "temporary": "Befristet",
    "intern": "Praktikum",
    "internship": "Praktikum",
    "trainee": "Trainee",
    "freelance": "Freie Mitarbeit",
    "working_student": "Werkstudium",
    "apprenticeship": "Ausbildung",
    "volunteer": "Ehrenamt",
}
SCHEDULE_DE = {
    "full-time": "Vollzeit",
    "part-time": "Teilzeit",
    "full_time": "Vollzeit",
    "part_time": "Teilzeit",
}
SENIORITY_DE = {
    "entry-level": "Berufseinsteiger",
    "entry_level": "Berufseinsteiger",
    "experienced": "mit Berufserfahrung",
    "student": "Studium",
    "lead": "Führungskraft",
    "executive": "Führungskraft",
}


def _text(node: Optional[ET.Element]) -> str:
    return (node.text or "").strip() if node is not None else ""


# Manche Personio-Boards liefern kein JSON-LD (beim HSV ist das so), haben die
# Stellendaten aber als eingebettetes JSON in der Seite. Dort steht neben
# created_at auch das echte published_at. Anfuehrungszeichen koennen escaped
# sein, weil das JSON in einem JavaScript-String steckt.
EMBEDDED_PUBLISHED_RE = re.compile(
    r'\\?"published_at\\?"\s*:\s*\\?"(\d{4}-\d{2}-\d{2})')
EMBEDDED_SLUG_RE = {
    "employment": re.compile(r'\\?"employment_type_slug\\?"\s*:\s*\\?"([a-z_]+)'),
    "schedule": re.compile(r'\\?"schedule_slug\\?"\s*:\s*\\?"([a-z-]+)'),
}


def _embedded_fields(html: str) -> Dict[str, str]:
    """Datum und Vertragsart aus dem eingebetteten JSON der Seite lesen.

    Rueckfall fuer Boards ohne JSON-LD. Faellt das Muster weg, fehlt nur das
    Datum - die Stelle selbst wird weiter erfasst.
    """
    out: Dict[str, str] = {}
    match = EMBEDDED_PUBLISHED_RE.search(html)
    if match:
        out["published_at"] = match.group(1)
    employment = EMBEDDED_SLUG_RE["employment"].search(html)
    schedule = EMBEDDED_SLUG_RE["schedule"].search(html)
    parts = []
    if schedule:
        parts.append(SCHEDULE_DE.get(schedule.group(1), schedule.group(1)))
    if employment:
        parts.append(EMPLOYMENT_DE.get(employment.group(1), employment.group(1)))
    if parts:
        out["employment_type"] = ", ".join(dict.fromkeys(p for p in parts if p))
    return out


class PersonioAdapter(Adapter):
    name = "personio"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._used_xml = False
        self._board_has_content = False

    # -- Basis-URL ---------------------------------------------------------
    def _base(self) -> str:
        parts = urlsplit(self.source.url)
        return "{}://{}".format(parts.scheme or "https", parts.netloc)

    def _job_url(self, job_id: str) -> str:
        return "{}/job/{}".format(self._base(), job_id)

    def _stable_id(self, job: Job, job_id: str) -> None:
        """Identitaet an die Personio-Nummer binden, nicht an die Board-URL.

        Ein Verein kann mehrere Boards auf denselben Mandanten schalten
        (beim HSV war das so). Dieselbe Stelle haette dann je Board eine
        andere URL und waere doppelt gemeldet worden.
        """
        job.id = make_job_id(self.club.short, "personio-job:{}".format(job_id))

    # -- XML-Feed ----------------------------------------------------------
    def _parse_xml(self, raw: str) -> List[Job]:
        try:
            root = ET.fromstring(raw.strip())
        except ET.ParseError as exc:
            log.warning("%s: XML-Feed nicht lesbar (%s)", self.source.id, exc)
            return []

        jobs: List[Job] = []
        for position in root.iter("position"):
            job_id = _text(position.find("id"))
            title = _text(position.find("name"))
            if not job_id or not title:
                continue

            employment = EMPLOYMENT_DE.get(
                _text(position.find("employmentType")).lower(),
                _text(position.find("employmentType")))
            schedule = SCHEDULE_DE.get(
                _text(position.find("schedule")).lower(),
                _text(position.find("schedule")))
            parts = [p for p in (schedule, employment) if p]

            seniority = _text(position.find("seniority")).lower()
            audience = SENIORITY_DE.get(seniority, _text(position.find("seniority")))
            category = _text(position.find("recruitingCategory"))
            if category:
                audience = ", ".join(p for p in (audience, category) if p)

            job = self.new_job(
                title=title,
                url=self._job_url(job_id),
                department=_text(position.find("department")) or None,
                location=_text(position.find("office")) or None,
                employment_type=", ".join(dict.fromkeys(parts)) or None,
                audience=audience or None,
            )
            self._stable_id(job, job_id)
            description = self._xml_description(position)
            if description:
                job.description = description
                job.description_fetched = True
            jobs.append(job)
        return jobs

    @staticmethod
    def _xml_description(position: ET.Element) -> str:
        """Abschnitte des Feeds zu gegliedertem Text zusammensetzen."""
        chunks: List[str] = []
        for section in position.iter("jobDescription"):
            heading = _text(section.find("name"))
            body_html = _text(section.find("value"))
            body = html_to_text(body_html) if body_html else ""
            if heading and body:
                chunks.append("## {}\n\n{}".format(heading, body))
            elif body:
                chunks.append(body)
        return "\n\n".join(chunks).strip()

    # -- HTML-Board --------------------------------------------------------
    def _parse_html(self, html: str) -> List[Job]:
        soup = BeautifulSoup(html, "lxml")
        self._board_has_content = bool(soup.select_one(".jb-groups, [data-test-id]"))

        jobs: List[Job] = []
        seen = set()
        for link in soup.select("a.job-box[href], a[href*='/job/']"):
            href = link.get("href") or ""
            if "/job/" not in href:
                continue
            title_node = link.select_one(".jb-title, h3")
            title = (title_node.get_text(" ", strip=True) if title_node
                     else link.get_text(" ", strip=True))
            url = self.absolute(href)
            if not title or url in seen:
                continue
            seen.add(url)

            job = self.new_job(title=title, url=url)
            match = re.search(r"/job/(\d+)", href)
            if match:
                self._stable_id(job, match.group(1))
            self._assign_html_meta(job, link)
            self._assign_group(job, link)
            jobs.append(job)
        return jobs

    @staticmethod
    def _assign_html_meta(job: Job, link: Tag) -> None:
        """Ort und Vertragsart aus der Meta-Zeile der Kachel lesen."""
        meta = link.select_one(".jb-description")
        if meta is None:
            return
        items = [t.strip() for t in meta.stripped_strings if t.strip()]
        contract: List[str] = []
        location: List[str] = []
        for item in items:
            if guess_employment_type(item, limit=len(item) + 1):
                contract.append(item)
            else:
                location.append(item)
        if contract:
            job.employment_type = ", ".join(dict.fromkeys(contract))
        if location:
            job.location = ", ".join(dict.fromkeys(location))

    @staticmethod
    def _assign_group(job: Job, link: Tag) -> None:
        """Gruppentitel auswerten.

        Personio gruppiert je Board unterschiedlich: der HSV nach Abteilung
        ("Sport NLZ"), Hertha nach Vertragsart ("Minijob"). Deshalb wird
        geprueft, was der Titel ueberhaupt ist.
        """
        group = link.find_parent(class_="jobs-group")
        if group is None:
            return
        heading = group.select_one(".jobs-group-header, h2")
        if heading is None:
            return
        name = heading.get_text(" ", strip=True)
        # "Minijob - 2 Positionen" -> "Minijob"
        name = re.split(r"\s+-\s+\d+\s+Position", name)[0].strip()
        if not name:
            return
        if guess_employment_type(name, limit=len(name) + 1):
            if not job.employment_type:
                job.employment_type = name
        elif not job.department:
            job.department = name

    # -- Ablauf ------------------------------------------------------------
    def list_jobs(self) -> List[Job]:
        prefer_xml = bool(self.params.get("prefer_xml", True))
        jobs: List[Job] = []

        if prefer_xml:
            feed_url = "{}/xml".format(self._base())
            try:
                raw = self.fetcher.get_text(feed_url)
                jobs = self._parse_xml(raw)
                self._used_xml = bool(jobs)
            except Exception as exc:
                log.warning("%s: XML-Feed nicht abrufbar (%s), nutze HTML",
                            self.source.id, exc.__class__.__name__)
            if not jobs:
                log.info("  XML-Feed ist leer, Rückfall auf die HTML-Seite")

        # HTML nur laden, wenn der Feed nichts hergab. Sonst waere es ein
        # zusaetzlicher Abruf pro Board und Lauf ohne Mehrwert.
        if not jobs:
            self._list_html = self.fetcher.get_text(self.source.url)
            jobs = self._parse_html(self._list_html)

        log.debug("%s: %d Stellen (%s)", self.source.id, len(jobs),
                  "XML" if self._used_xml else "HTML")
        return jobs

    def looks_legitimately_empty(self, html: str) -> bool:
        """Board geladen, aber keine Stellen: wirklich nichts offen."""
        if self._board_has_content:
            return True
        return super().looks_legitimately_empty(html)

    def enrich(self, job: Job) -> None:
        """Detailseite holen: genaues Datum, bei HTML auch die Beschreibung."""
        html = self.fetcher.get_text(job.url)
        data = jsonld.extract(html)

        if not job.description:
            description = ""
            if data.get("description_html"):
                description = html_to_text(data["description_html"])
            if not description:
                description = html_to_text(html, root_selector="main, article")
            if description:
                job.description = description
                job.description_fetched = True

        # Das echte Veroeffentlichungsdatum, nicht das createdAt des Feeds.
        # Ohne JSON-LD aus dem eingebetteten JSON der Seite.
        embedded = _embedded_fields(html) if not data.get("published_at") else {}
        if data.get("published_at"):
            job.published_at = data["published_at"]
        elif embedded.get("published_at"):
            job.published_at = embedded["published_at"]
        if data.get("deadline"):
            job.deadline = data["deadline"]
        if data.get("location") and not job.location:
            job.location = data["location"]
        if data.get("employment_type") and not job.employment_type:
            job.employment_type = data["employment_type"]
        elif embedded.get("employment_type") and not job.employment_type:
            job.employment_type = embedded["employment_type"]

        soup = BeautifulSoup(html, "lxml")
        apply_link = soup.select_one('a[href*="/apply"], a[href*="apply/"]')
        if apply_link is not None:
            job.apply_url = self.absolute(apply_link.get("href", ""))
