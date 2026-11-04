"""Text aus PDF-Stellenausschreibungen lesen.

Der VfB Stuttgart und Schalke 04 veroeffentlichen einzelne Ausschreibungen
nur als PDF. pdfminer liefert den Text zeilenweise, daher wird hier noch
etwas aufgeraeumt: harte Zeilenumbrueche innerhalb von Saetzen werden
zusammengezogen, Aufzaehlungszeichen vereinheitlicht.
"""
from __future__ import annotations

import io
import logging
import re
from typing import Optional

log = logging.getLogger(__name__)

# Aufzaehlungszeichen, wie sie in PDFs vorkommen
BULLETS = "•▪◦‣·–—‒*"


def _tidy(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("­", "")
    # Trennstriche am Zeilenende aufloesen: "Trai-\nner" -> "Trainer"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            lines.append("")
            continue
        # Aufzaehlungen auf "- " normieren
        if line[0] in BULLETS:
            line = "- " + line[1:].strip()
        lines.append(line)

    # Harte Umbrueche innerhalb eines Satzes zusammenziehen
    out = []
    for line in lines:
        if (out and out[-1] and line
                and not line.startswith("- ")
                and not out[-1].startswith("- ")
                and not re.search(r"[.:;!?]$", out[-1])
                and out[-1][-1:].islower()
                and line[:1].islower()):
            out[-1] = out[-1] + " " + line
        else:
            out.append(line)

    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def pdf_to_text(data: bytes, max_pages: int = 10) -> Optional[str]:
    """PDF-Bytes in Text umwandeln. None, wenn das nicht geht."""
    if not data:
        return None
    try:
        from pdfminer.high_level import extract_text
    except ImportError:
        log.warning("pdfminer.six ist nicht installiert, PDF wird übersprungen")
        return None
    try:
        raw = extract_text(io.BytesIO(data), maxpages=max_pages)
    except Exception as exc:
        log.warning("PDF nicht lesbar (%s)", exc.__class__.__name__)
        return None
    text = _tidy(raw or "")
    return text or None


def looks_like_pdf(url: str, content_type: str = "") -> bool:
    if "pdf" in (content_type or "").lower():
        return True
    return bool(re.search(r"\.pdf($|[?#])", (url or "").lower()))
