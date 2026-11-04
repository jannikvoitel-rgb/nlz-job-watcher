"""Relevanz-Einstufung einer Stelle in Prioritaet A, B oder C.

Regeln und Schlagwoerter stehen in filters.yaml, nicht hier im Code.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Einstiegsstellen-Begriffe, die allein noch keinen Sportbezug belegen.
_CONDITIONAL_EXTRA = {
    "fsj", "freiwilliges soziales jahr", "bundesfreiwilligendienst", "bfd",
}

_UMLAUT_MAP = str.maketrans({
    "ä": "a", "ö": "o", "ü": "u", "Ä": "a", "Ö": "o", "Ü": "u",
    "ß": "ss", "é": "e", "è": "e", "á": "a", "à": "a", "â": "a", "ç": "c",
})

# Verschiedene Bindestrich- und Anfuehrungsvarianten vereinheitlichen.
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")


def normalize(text: str) -> str:
    """Kleinschreibung, Umlaute aufgeloest, Bindestriche vereinheitlicht."""
    if not text:
        return ""
    text = text.translate(_DASHES).translate(_UMLAUT_MAP).lower()
    # "ß" kann nach translate noch als Mehrzeichen auftreten, daher erneut
    text = text.replace("ß", "ss")
    text = re.sub(r"[­​﻿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _keyword_regex(keyword: str) -> "re.Pattern[str]":
    """Schlagwortsuche, abgestuft nach Laenge.

    Deutsche Komposita stellen das Schlagwort vorn ODER hinten an:
    "Nachwuchstrainer" und "Trainerfortbildung" sollen beide auf "trainer"
    treffen, "Arenaverkauf" auf "verkauf". Lange Schlagwoerter werden daher
    an jeder Stelle im Wort gesucht.

    Kurze Schlagwoerter brauchen Grenzen, sonst trifft "it" in "Sicherheit"
    und "reha" waere zu unscharf.
    """
    kw = normalize(keyword)
    escaped = re.escape(kw)
    length = len(kw.replace(" ", "").replace("-", ""))
    if length <= 3:
        # Nur als eigenstaendiges Wort: it, fsj, bfd, nlz
        return re.compile(r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])")
    if length == 4:
        # Nur am Wortanfang: koch, reha
        return re.compile(r"(?<![a-z0-9])" + escaped)
    # Ab fuenf Zeichen an jeder Stelle, fuer Komposita
    return re.compile(escaped)


class Classifier:
    """Stuft Stellen anhand der Konfiguration aus filters.yaml ein."""

    def __init__(self, filters: Dict[str, Any]):
        self.filters = filters or {}
        a = self.filters.get("priority_a", {}) or {}
        b = self.filters.get("priority_b", {}) or {}
        c = self.filters.get("priority_c", {}) or {}
        dept = self.filters.get("department_signals", {}) or {}

        self.a_keywords = self._compile(a.get("keywords", []))
        self.a_title_signals = self._compile(a.get("description_requires_title_signal", []))
        self.age_regex = self._build_age_regex(a.get("age_groups", []))
        self.a_age_names = self._compile(a.get("age_names", []))
        self.a_nlz_signals = self._compile(a.get("nlz_signals", []))
        self.a_excludes = self._compile(a.get("excludes", []))

        entry = [normalize(x) for x in (b.get("entry_level_terms", []) or [])]
        self.conditional = self._compile(
            list(entry) + sorted(_CONDITIONAL_EXTRA)
        )
        strong = [
            k for k in (b.get("keywords", []) or [])
            if normalize(k) not in _CONDITIONAL_EXTRA
        ]
        self.b_keywords = self._compile(strong)
        self.c_keywords = self._compile(c.get("keywords", []))

        self._club_cache: Dict[str, Dict[str, List[Tuple[str, "re.Pattern[str]"]]]] = {}

        self.dept_a = self._compile(dept.get("priority_a", []))
        self.dept_b = self._compile(dept.get("priority_b", []))
        self.dept_c = self._compile(dept.get("priority_c", []))

    # -- Hilfsfunktionen ---------------------------------------------------
    @staticmethod
    def _compile(keywords: Iterable[str]) -> List[Tuple[str, "re.Pattern[str]"]]:
        out = []
        for kw in keywords or []:
            kw = (kw or "").strip()
            if kw:
                out.append((kw, _keyword_regex(kw)))
        # Laengere Schlagwoerter zuerst pruefen, damit der Grund praeziser ist
        out.sort(key=lambda pair: len(pair[0]), reverse=True)
        return out

    def compile_club(self, club_short: str,
                     keywords: Optional[Dict[str, Any]]) -> Dict[str, List[Tuple[str, "re.Pattern[str]"]]]:
        """Vereinsspezifische Schlagwoerter uebersetzen und zwischenspeichern."""
        if not keywords:
            return {}
        if club_short in self._club_cache:
            return self._club_cache[club_short]
        compiled = {
            level: self._compile(keywords.get(level, []) or [])
            for level in ("priority_a", "priority_b", "priority_c")
        }
        self._club_cache[club_short] = compiled
        return compiled

    @staticmethod
    def _build_age_regex(groups: Iterable[str]) -> Optional["re.Pattern[str]"]:
        numbers = []
        for g in groups or []:
            m = re.search(r"\d+", str(g))
            if m:
                numbers.append(m.group(0))
        if not numbers:
            return None
        # Laengste Zahlen zuerst, damit "11" vor "1" greift
        numbers.sort(key=lambda n: (-len(n), n))
        alt = "|".join(numbers)
        return re.compile(
            r"(?<![a-z0-9])u\s*-?\s*(" + alt + r")(?![0-9])"
        )

    @staticmethod
    def _first_match(text: str, patterns: List[Tuple[str, "re.Pattern[str]"]]) -> Optional[str]:
        if not text:
            return None
        for keyword, rx in patterns:
            if rx.search(text):
                return keyword
        return None

    def _age_match(self, text: str) -> Optional[str]:
        if not (text and self.age_regex):
            return None
        m = self.age_regex.search(text)
        return ("U" + m.group(1)) if m else None

    def _age_signal(self, text: str) -> Optional[str]:
        """Altersangabe des Grundlagenbereichs, als U-Zahl oder Jahrgang."""
        hit = self._age_match(text)
        if hit:
            return "Altersklasse {}".format(hit)
        name = self._first_match(text, self.a_age_names)
        if name:
            return "Jahrgang {}".format(name)
        return None

    # -- Grundlagenbereich -------------------------------------------------
    def _classify_glb(self, head: str, title_n: str, dept_n: str, desc_n: str,
                      club: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """Ist das eine NLZ-Mannschaft im Grundlagenbereich (U9-U11)?

        Der Grundlagenbereich ist eng gefasst: NLZ-Mannschaften der
        Altersklassen U9 bis U11. Eine Fussballschule, ein Feriencamp oder
        ein Partnerverein ist das nicht, auch wenn dort Kinder desselben
        Alters trainieren. Solche Stellen bleiben Sport (B).
        """
        # Breitenfussball schliesst A aus, auch mit passender Altersangabe.
        if self._first_match(head, self.a_excludes):
            return None

        # a) Das Wort benennt den Bereich selbst - der NLZ-Beleg steckt drin.
        hit = self._first_match(head, self.a_keywords)
        if hit:
            return "A", 'Schlagwort "{}" im Titel'.format(hit)
        hit = self._first_match(dept_n, self.dept_a)
        if hit:
            return "A", 'Bereich "{}"'.format(hit)

        # b) Altersangabe im Titel, NLZ-Beleg irgendwo im Text.
        whole = " | ".join(x for x in (head, desc_n) if x)
        age = self._age_signal(head)
        if age:
            nlz = self._first_match(whole, self.a_nlz_signals)
            if nlz:
                return "A", '{} im Titel, NLZ-Beleg "{}"'.format(age, nlz)
            # Altersangabe ohne NLZ-Bezug: Kinderfussball irgendeiner Art,
            # aber kein Grundlagenbereich.
            return None

        # c) Altersangabe erst in der Beschreibung. Dann muss der Titel eine
        #    Trainerrolle nennen und darf kein Nicht-Sport-Wort enthalten -
        #    sonst wird Werders "Aushilfe Fahrdienst im Leistungszentrum"
        #    zur GLB-Meldung, nur weil im Fliesstext eine U10 vorkommt.
        title_signal = self._first_match(title_n, self.a_title_signals)
        title_blocker = (self._first_match(title_n, club.get("priority_c", []))
                         or self._first_match(title_n, self.c_keywords))
        if title_signal and not title_blocker:
            age = self._age_signal(desc_n)
            if age:
                nlz = self._first_match(whole, self.a_nlz_signals)
                if nlz:
                    return "A", '{} in der Beschreibung, NLZ-Beleg "{}"'.format(
                        age, nlz)
        return None

    # -- Einstufung --------------------------------------------------------
    def classify(self, title: str, description: str = "", department: str = "",
                 club_keywords: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        """Gibt (Prioritaet, Begruendung) zurueck.

        club_keywords sind bereits uebersetzte vereinsspezifische Schlagwoerter
        aus compile_club(). Sie werden vor den globalen Listen geprueft.
        """
        club = club_keywords or {}
        title_n = normalize(title)
        dept_n = normalize(department)
        desc_n = normalize(description)
        head = (title_n + " | " + dept_n).strip(" |")

        # 0) Vereinsspezifische Schlagwoerter gehen vor
        hit = self._first_match(head, club.get("priority_a", []))
        if hit:
            return "A", 'Vereinsschlagwort "{}"'.format(hit)

        # 1) Prioritaet A: Grundlagenbereich, eng gefasst
        verdict = self._classify_glb(head, title_n, dept_n, desc_n, club)
        if verdict:
            return verdict

        # 3) Prioritaet B: klarer Sportbezug
        hit = self._first_match(head, club.get("priority_b", []))
        if hit:
            return "B", 'Vereinsschlagwort "{}"'.format(hit)
        hit = self._first_match(head, self.b_keywords)
        if hit:
            return "B", 'Schlagwort "{}"'.format(hit)

        # 3b) Eindeutiger Nicht-Sport-Titel sticht den Abteilungs-Hinweis.
        #     Beispiel HSV: "Köchin/Koch" in der Abteilung "Ernährung" ist
        #     Gastronomie, auch wenn Ernährung sonst ein Sportsignal ist.
        hit = self._first_match(title_n, club.get("priority_c", []))
        if hit:
            return "C", 'Vereinsschlagwort "{}" im Titel'.format(hit)
        hit = self._first_match(title_n, self.c_keywords)
        if hit:
            return "C", 'Schlagwort "{}" im Titel'.format(hit)

        hit = self._first_match(dept_n, self.dept_b)
        if hit:
            return "B", 'Bereich "{}"'.format(hit)

        # 4) Einstiegsstelle (Praktikum, FSJ, Aushilfe) mit Sport-Bereich.
        #    Die Beschreibung wird hier absichtlich NICHT geprueft: fast jede
        #    Vereinsstelle erwaehnt im Einleitungstext "Fussball".
        cond = self._first_match(head, self.conditional)
        if cond:
            dept_hit = self._first_match(dept_n, self.dept_b)
            if dept_hit:
                return "B", '{} im Bereich "{}"'.format(cond, dept_hit)

        # 5) Prioritaet C: klar ohne Sportbezug
        hit = self._first_match(head, club.get("priority_c", []))
        if hit:
            return "C", 'Vereinsschlagwort "{}"'.format(hit)
        hit = self._first_match(head, self.c_keywords)
        if hit:
            return "C", 'Schlagwort "{}"'.format(hit)
        hit = self._first_match(dept_n, self.dept_c)
        if hit:
            return "C", 'Bereich "{}"'.format(hit)

        # 6) Unklar: bewusst als Sport einstufen, damit nichts durchrutscht
        return "B", "kein klares Schlagwort, vorsorglich als Sport eingestuft"

    def apply(self, job, club_keywords: Optional[Dict[str, Any]] = None) -> None:
        """Einstufung in das Job-Objekt schreiben."""
        priority, reason = self.classify(
            job.title, job.description or "", job.department or "",
            club_keywords=club_keywords,
        )
        job.priority = priority
        job.priority_reason = reason
