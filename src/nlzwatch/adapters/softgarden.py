"""Adapter fuer softgarden-Karriereboards.

Genutzt von Borussia Dortmund, Bayer 04, Schalke 04 und Werder Bremen.
Die Stellenliste ist serverseitig gerendert, die Klassennamen sind bei
allen Mandanten gleich.

Wichtig: die robots.txt von softgarden sperrt /api/, /rest/ und /widgets/.
Dieser Adapter liest deshalb ausschliesslich die normalen HTML-Seiten.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .. import jsonld
from ..dates import parse_date_de
from ..models import Job
from ..textclean import guess_employment_type, html_to_text
from .base import Adapter

log = logging.getLogger(__name__)

JOB_HREF = re.compile(r"/job/(\d+)")


class SoftgardenAdapter(Adapter):
    name = "softgarden"

    def _canonical_url(self, href: str) -> Optional[str]:
        """Stabile Detail-URL ohne wechselnde Parameter bauen."""
        absolute = self.absolute(href)
        m = JOB_HREF.search(absolute)
        if not m:
            return None
        parts = urlsplit(absolute)
        return "{}://{}/job/{}".format(parts.scheme or "https", parts.netloc,
                                       m.group(1))

    @staticmethod
    def _cell(row, *classes: str) -> str:
        for cls in classes:
            node = row.select_one(".matchValue.{}".format(cls))
            if node is not None:
                return node.get_text(" ", strip=True)
        return ""

    def list_jobs(self) -> List[Job]:
        self._list_html = self.fetcher.get_text(self.source.url)
        soup = BeautifulSoup(self._list_html, "lxml")

        rows = soup.select("div.outputContainer div.matchElement")
        if not rows:
            # Aeltere Mandanten rendern ohne outputContainer
            rows = [r for r in soup.select("div.matchElement")
                    if "matchHeadline" not in (r.get("class") or [])]

        jobs: List[Job] = []
        seen = set()
        for row in rows:
            if "matchHeadline" in (row.get("class") or []):
                continue
            link = row.select_one(".matchValue.title a[href]") or row.select_one("a[href*='/job/']")
            if link is None:
                continue
            title = link.get_text(" ", strip=True)
            url = self._canonical_url(link.get("href", ""))
            if not title or not url or url in seen:
                continue
            seen.add(url)

            location = self._cell(row, "ProjectGeoLocationCity", "location")
            location = re.sub(r"\s*,\s*", ", ", location).strip(" ,") or None

            jobs.append(self.new_job(
                title=title,
                url=url,
                published_at=parse_date_de(self._cell(row, "date")),
                department=self._cell(row, "jobcategory") or None,
                location=location,
                audience=self._cell(row, "audience") or None,
            ))

        log.debug("%s: %d Stellen in der Liste", self.source.id, len(jobs))
        return jobs

    def enrich(self, job: Job) -> None:
        html = self.fetcher.get_text(job.url)
        data = jsonld.extract(html)

        description = ""
        if data.get("description_html"):
            description = html_to_text(data["description_html"])
        if not description:
            # Rueckfall auf den Seiteninhalt
            description = html_to_text(html, root_selector=".view-job, #content, main")
        if description:
            job.description = description
            job.description_fetched = True

        if data.get("published_at") and not job.published_at:
            job.published_at = data["published_at"]
        if data.get("deadline"):
            job.deadline = data["deadline"]
        if data.get("location") and not job.location:
            job.location = data["location"]

        # Die Zielgruppe aus der Liste ("Student/in") ist keine Beschaeftigungsart,
        # daher aus JSON-LD, sonst aus Titel und Anzeigentext raten.
        employment = data.get("employment_type") or guess_employment_type(
            job.title + "\n" + (job.description or "")
        )
        if employment:
            job.employment_type = employment
