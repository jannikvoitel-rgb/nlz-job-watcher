"""HTML in sauberen, strukturierten Text verwandeln.

Behaelt Gliederungen wie "Deine Aufgaben" / "Dein Profil" / "Wir bieten",
entfernt Navigation, Footer, Cookie-Banner und Skripte.
"""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

# Container, die niemals Teil der Stellenbeschreibung sind.
DROP_TAGS = ("script", "style", "noscript", "svg", "iframe", "form",
             "nav", "footer", "header", "aside", "template", "button", "select")

# Klassen-/ID-Muster von Rahmenelementen und Consent-Bannern.
DROP_PATTERN = re.compile(
    r"(cookie|consent|gdpr|dsgvo|usercentric|onetrust|borlabs|klaro|"
    r"navbar|navigation|mainmenu|megamenu|breadcrumb|"
    r"site-?header|site-?footer|page-?footer|skip-?link|"
    r"social|share|sharing|newsletter|banner|advert|werbung|"
    r"sidebar|offcanvas|modal|popup|overlay|toolbar|searchform)",
    re.I,
)

BLOCK_TAGS = {"p", "div", "section", "article", "tr", "br", "figure", "blockquote"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _should_drop(tag: Tag) -> bool:
    if tag.name in DROP_TAGS:
        return True
    ident = " ".join(filter(None, [
        " ".join(tag.get("class", []) or []),
        tag.get("id") or "",
        tag.get("role") or "",
        tag.get("data-testid") or "",
    ]))
    return bool(ident and DROP_PATTERN.search(ident))


def _strip_chrome(node: Tag) -> None:
    for tag in list(node.find_all(True)):
        if tag.parent is None:
            continue
        if _should_drop(tag):
            tag.decompose()


def _is_bold_heading(tag: Tag) -> bool:
    """Absatz, der nur aus fettem Text besteht und kurz genug ist."""
    text = tag.get_text(" ", strip=True)
    if not text or len(text) > 90:
        return False
    bold = tag.find_all(["strong", "b"], recursive=True)
    if not bold:
        return False
    bold_text = " ".join(b.get_text(" ", strip=True) for b in bold).strip()
    if not bold_text:
        return False
    # Der fette Teil muss praktisch den ganzen Absatz ausmachen
    return len(bold_text) >= len(text) - 2


def _render(node: Tag, out: list) -> None:
    """Knoten rekursiv in Textzeilen umwandeln."""
    for child in node.children:
        if isinstance(child, NavigableString):
            text = re.sub(r"[ \t\r\n\xa0​﻿]+", " ", str(child))
            if text.strip():
                out.append(text)
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name
        if name in HEADING_TAGS:
            heading = child.get_text(" ", strip=True)
            if heading:
                out.append("\n\n## " + heading + "\n")
            continue
        if name == "li":
            item = child.get_text(" ", strip=True)
            if item:
                out.append("\n- " + item)
            continue
        if name == "br":
            out.append("\n")
            continue
        if name in ("p", "div") and _is_bold_heading(child):
            # Viele Anzeigen setzen Zwischenueberschriften als fetten
            # Absatz statt als <h*>. Fuer die App ist das eine Ueberschrift.
            heading = child.get_text(" ", strip=True)
            if heading:
                out.append("\n\n## " + heading.rstrip(":") + "\n")
            continue
        if name in BLOCK_TAGS or name in ("ul", "ol", "table"):
            out.append("\n")
            _render(child, out)
            out.append("\n")
            continue
        _render(child, out)


def _tidy(text: str) -> str:
    text = text.replace("­", "")                      # weiches Trennzeichen
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Doppelte Leerzeichen vor Satzzeichen glaetten
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    lines = [ln.rstrip() for ln in text.split("\n")]
    # Aufeinanderfolgende identische Zeilen entfernen (Portal-Wiederholungen)
    cleaned = []
    for line in lines:
        if cleaned and line and line == cleaned[-1]:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def html_to_text(html: str, root_selector: Optional[str] = None) -> str:
    """HTML-Fragment oder -Dokument in bereinigten Text umwandeln."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    root: Optional[Tag] = None
    if root_selector:
        root = soup.select_one(root_selector)
    if root is None:
        for candidate in ("main", "article", '[role="main"]', "body"):
            root = soup.select_one(candidate)
            if root is not None:
                break
    if root is None:
        root = soup
    _strip_chrome(root)
    out: list = []
    _render(root, out)
    return _tidy("".join(out))


def collapse(text: str) -> str:
    """Text zu einer Zeile zusammenziehen (fuer Suche und Einstufung)."""
    return re.sub(r"\s+", " ", text or "").strip()


# Beschaeftigungsarten, wie deutsche Portale sie schreiben.
_EMPLOYMENT_TERMS = [
    ("geringfügige beschäftigung", "Geringfügige Beschäftigung"),
    ("geringfugige beschaftigung", "Geringfügige Beschäftigung"),
    ("kurzfristige beschäftigung", "Kurzfristige Beschäftigung"),
    ("vollzeit und teilzeit", "Vollzeit und Teilzeit"),
    ("vollzeit", "Vollzeit"),
    ("teilzeit", "Teilzeit"),
    ("minijob", "Minijob"),
    ("werkstudent", "Werkstudium"),
    ("werkstudium", "Werkstudium"),
    ("pflichtpraktikum", "Pflichtpraktikum"),
    ("praktikum", "Praktikum"),
    ("ausbildung", "Ausbildung"),
    ("duales studium", "Duales Studium"),
    ("befristet", "Befristet"),
    ("unbefristet", "Unbefristet"),
    ("festanstellung", "Festanstellung"),
    ("honorarbasis", "Honorarbasis"),
    ("honorartätigkeit", "Honorartätigkeit"),
    ("ehrenamt", "Ehrenamt"),
    ("übungsleiterpauschale", "Übungsleiterpauschale"),
    ("aushilfe", "Aushilfe"),
    ("freiwilliges soziales jahr", "FSJ"),
    ("bundesfreiwilligendienst", "Bundesfreiwilligendienst"),
]


def guess_employment_type(text: str, limit: int = 600) -> Optional[str]:
    """Beschaeftigungsart aus dem Anfang eines Stellentexts ablesen."""
    if not text:
        return None
    head = text[:limit].lower()
    for needle, label in _EMPLOYMENT_TERMS:
        if needle in head:
            return label
    return None
