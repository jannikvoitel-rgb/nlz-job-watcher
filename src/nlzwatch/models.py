"""Datenmodell fuer Stellen, Vereine und Quellen."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query-Parameter, die sich von Abruf zu Abruf aendern und daher nicht in die
# Job-ID einfliessen duerfen.
VOLATILE_QUERY_PARAMS = {
    "l", "lang", "language", "locale",
    "jobdbpvid", "jobdbpv", "sid", "session",
    "ref", "referrer", "source", "src",
    "fbclid", "gclid", "msclkid", "_ga", "_gl",
}


def normalize_url(url: str) -> str:
    """URL auf eine stabile Form bringen, damit IDs ueber Laeufe gleich bleiben."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in VOLATILE_QUERY_PARAMS and not k.lower().startswith("utm_")
    ]
    kept.sort()
    return urlunsplit((scheme, host, path, urlencode(kept), ""))


def make_job_id(club_short: str, url: str, title: str = "") -> str:
    """ID = Verein + normalisierte URL. Fallback: Verein + Titel."""
    basis = normalize_url(url)
    if not basis:
        basis = "title:" + re.sub(r"\s+", " ", (title or "").strip().lower())
    raw = "{}|{}".format(club_short.strip().lower(), basis)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class Job:
    """Eine Stellenanzeige."""

    id: str = ""
    club: str = ""
    club_short: str = ""
    source_id: str = ""
    source_label: str = ""

    title: str = ""
    url: str = ""
    apply_url: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    department: Optional[str] = None
    audience: Optional[str] = None       # Zielgruppe laut Portal
    published_at: Optional[str] = None     # ISO-Datum, falls die Quelle es liefert
    deadline: Optional[str] = None         # Bewerbungsfrist, falls vorhanden
    contact: Optional[str] = None          # Bewerbungs-Kontakt, falls vorhanden

    description: str = ""                  # bereinigter Volltext
    description_fetched: bool = False

    priority: str = "C"                    # A | B | C
    priority_reason: str = ""

    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    status: str = "offen"                  # offen | geschlossen
    closed_at: Optional[str] = None
    initial: bool = False                  # beim ersten Lauf vorgefunden ("Bestand")
    notified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def ensure_id(self) -> str:
        if not self.id:
            self.id = make_job_id(self.club_short, self.url, self.title)
        return self.id

    @property
    def search_text(self) -> str:
        """Alles, was fuer die Einstufung herangezogen wird."""
        return "\n".join(p for p in (self.title, self.department or "", self.description) if p)


@dataclass
class Source:
    """Eine Stellenquelle eines Vereins."""

    id: str
    label: str
    adapter: str
    url: str
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)
    empty_ok: List[str] = field(default_factory=list)
    # Quelle, die bewusst nicht abgerufen wird und die der Mensch selbst
    # im Blick behaelt. Erscheint so auch in der Web-App.
    manual: bool = False
    manual_reason: str = ""
    manual_hint: str = ""


@dataclass
class Club:
    """Ein Verein mit einer oder mehreren Quellen."""

    name: str
    short: str
    sources: List[Source] = field(default_factory=list)
    speculative: Dict[str, Any] = field(default_factory=dict)
    # Vereinsspezifische Schlagwoerter, z. B. "Fohlenstall" fuer das NLZ-Internat
    keywords: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class SourceResult:
    """Ergebnis eines Abrufs einer Quelle."""

    source_id: str
    jobs: List[Job] = field(default_factory=list)
    ok: bool = True
    error: Optional[str] = None
    legitimately_empty: bool = False
