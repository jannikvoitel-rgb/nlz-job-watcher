"""Datumsangaben deutscher Stellenportale in ISO-Form bringen."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

MONTHS_DE = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3,
    "mrz": 3, "mar": 3, "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6,
    "juli": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9,
    "sept": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}


def _year(value: int) -> int:
    """Zweistellige Jahreszahl auf das passende Jahrhundert bringen."""
    if value >= 100:
        return value
    # Portale zeigen "26" fuer 2026. Werte deutlich in der Zukunft
    # gehoeren noch ins laufende Jahrhundert.
    return 2000 + value


def parse_date_de(text: str) -> Optional[str]:
    """Erkennt 03.11.26, 03.11.2026, 2026-11-03 und "3. November 2026"."""
    if not text:
        return None
    raw = text.strip()

    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None

    m = re.search(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{2,4})\b", raw)
    if m:
        try:
            return date(_year(int(m.group(3))), int(m.group(2)),
                        int(m.group(1))).isoformat()
        except ValueError:
            return None

    m = re.search(r"\b(\d{1,2})\.?\s+([A-Za-zÄÖÜäöüß]+)\s+(\d{4})\b", raw)
    if m:
        month = MONTHS_DE.get(m.group(2).strip(".").lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1))).isoformat()
            except ValueError:
                return None
    return None


def parse_deadline_de(text: str) -> Optional[str]:
    """Bewerbungsfrist aus einem Satz ziehen, etwa "Bewerbungsschluss: 30.11.2026"."""
    if not text:
        return None
    pattern = re.compile(
        r"(bewerbungsfrist|bewerbungsschluss|bewerbungen\s+bis|"
        r"bewerbung\s+bis|frist|bis\s+zum|einsendeschluss)"
        r"[^0-9]{0,40}([0-9][0-9.\s\-A-Za-zÄÖÜäöüß]{5,30})",
        re.I,
    )
    for m in pattern.finditer(text):
        iso = parse_date_de(m.group(2))
        if iso:
            return iso
    return None


def today_iso() -> str:
    return datetime.now().date().isoformat()
