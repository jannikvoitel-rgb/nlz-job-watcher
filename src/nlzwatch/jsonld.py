"""Strukturierte Stellendaten aus einer HTML-Seite lesen.

Viele Portale (softgarden, Personio und zahlreiche Vereinsseiten) liefern
ein JSON-LD "JobPosting" mit. Das ist praeziser als jeder Selektor und
funktioniert portaluebergreifend.

SmartRecruiters - und damit RB Leipzig - nutzt stattdessen Microdata
(itemprop/itemtype direkt im Markup). Fehlt JSON-LD, wird deshalb auf
Microdata zurueckgegriffen.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Portale setzen "validThrough" oft automatisch Jahre in die Zukunft.
# Nur Fristen innerhalb dieses Fensters gelten als echte Bewerbungsfrist.
MAX_DEADLINE_DAYS = 365

EMPLOYMENT_TYPE_LABELS = {
    "FULL_TIME": "Vollzeit",
    "PART_TIME": "Teilzeit",
    "CONTRACTOR": "Freie Mitarbeit",
    "TEMPORARY": "Befristet",
    "INTERN": "Praktikum",
    "VOLUNTEER": "Ehrenamt",
    "PER_DIEM": "Aushilfe",
    "OTHER": None,          # nichts aussagend, lieber weglassen
}


def _iter_json_blocks(html: str) -> Iterable[Any]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            yield json.loads(raw)
        except json.JSONDecodeError:
            # Manche Seiten haengen mehrere Objekte aneinander
            for chunk in re.findall(r"\{.*?\}(?=\s*\{|\s*$)", raw, re.S):
                try:
                    yield json.loads(chunk)
                except json.JSONDecodeError:
                    continue


def _flatten(node: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(node, dict):
        if "@graph" in node:
            for item in node.get("@graph") or []:
                for found in _flatten(item):
                    yield found
        yield node
    elif isinstance(node, list):
        for item in node:
            for found in _flatten(item):
                yield found


def find_job_posting(html: str) -> Optional[Dict[str, Any]]:
    """Erstes JobPosting-Objekt der Seite zurueckgeben."""
    for block in _iter_json_blocks(html):
        for node in _flatten(block):
            types = node.get("@type") or node.get("type") or ""
            if isinstance(types, list):
                types = " ".join(str(t) for t in types)
            if "jobposting" in str(types).lower():
                return node
    return None


def _parse_date(value: Any) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    try:
        # fromisoformat kommt mit Offsets um, aber nicht mit "Z"
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except ValueError:
        pass
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    return m.group(0) if m else None


def _plausible_deadline(value: Any) -> Optional[str]:
    """Nur Fristen akzeptieren, die wie eine echte Frist aussehen."""
    iso = _parse_date(value)
    if not iso:
        return None
    try:
        day = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    if day < now - timedelta(days=1):
        return None
    if day > now + timedelta(days=MAX_DEADLINE_DAYS):
        return None    # Portal-Standardwert, keine echte Frist
    return iso


def _location(node: Any) -> Optional[str]:
    places: List[str] = []
    items = node if isinstance(node, list) else [node]
    for item in items:
        if not isinstance(item, dict):
            if isinstance(item, str) and item.strip():
                places.append(item.strip())
            continue
        address = item.get("address")
        if isinstance(address, dict):
            city = address.get("addressLocality") or address.get("addressRegion")
            if city and str(city).strip() not in ("-", ""):
                places.append(str(city).strip())
        elif isinstance(address, str) and address.strip():
            places.append(address.strip())
        elif item.get("name"):
            places.append(str(item["name"]).strip())
    seen = []
    for p in places:
        if p not in seen:
            seen.append(p)
    return ", ".join(seen) or None


def _employment_type(node: Any) -> Optional[str]:
    values = node if isinstance(node, list) else [node]
    labels = []
    for value in values:
        if not isinstance(value, str):
            continue
        label = EMPLOYMENT_TYPE_LABELS.get(value.strip().upper(), value.strip())
        if label:
            labels.append(label)
    return ", ".join(dict.fromkeys(labels)) or None


def _microdata_value(scope, prop: str) -> Optional[str]:
    """Wert einer Microdata-Eigenschaft lesen (meta-content oder Text)."""
    node = scope.select_one('[itemprop="{}"]'.format(prop))
    if node is None:
        return None
    if node.has_attr("content"):
        value = (node["content"] or "").strip()
        if value:
            return value
    text = node.get_text(" ", strip=True)
    return text or None


def extract_microdata(html: str) -> Dict[str, Any]:
    """JobPosting als Microdata lesen, wie SmartRecruiters es ausliefert."""
    soup = BeautifulSoup(html, "lxml")
    scope = soup.select_one('[itemtype*="JobPosting"]')
    if scope is None:
        return {}

    out: Dict[str, Any] = {}
    title = _microdata_value(scope, "title")
    if title:
        out["title"] = title

    description = scope.select_one('[itemprop="description"]')
    if description is not None:
        out["description_html"] = description.decode_contents()

    published = _parse_date(_microdata_value(scope, "datePosted"))
    if published:
        out["published_at"] = published
    deadline = _plausible_deadline(_microdata_value(scope, "validThrough"))
    if deadline:
        out["deadline"] = deadline

    city = (_microdata_value(scope, "addressLocality")
            or _microdata_value(scope, "jobLocation"))
    if city and city.strip() not in ("-", ""):
        out["location"] = city.strip()

    employment = _employment_type(_microdata_value(scope, "employmentType"))
    if employment:
        out["employment_type"] = employment
    return out


def extract(html: str) -> Dict[str, Any]:
    """Felder aus dem JobPosting der Seite ziehen. Leeres dict, wenn keins da ist."""
    node = find_job_posting(html)
    if not node:
        return extract_microdata(html)
    out: Dict[str, Any] = {}
    title = node.get("title")
    if isinstance(title, str) and title.strip():
        out["title"] = title.strip()
    if node.get("description"):
        out["description_html"] = str(node["description"])
    published = _parse_date(node.get("datePosted"))
    if published:
        out["published_at"] = published
    deadline = _plausible_deadline(node.get("validThrough"))
    if deadline:
        out["deadline"] = deadline
    location = _location(node.get("jobLocation"))
    if location:
        out["location"] = location
    employment = _employment_type(node.get("employmentType"))
    if employment:
        out["employment_type"] = employment
    apply_url = node.get("url") or node.get("directApplyUrl")
    if isinstance(apply_url, str) and apply_url.startswith("http"):
        out["apply_url"] = apply_url
    return out
