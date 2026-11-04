"""Adaptertest js_generic gegen gespeicherte, gerenderte Seiten.

Die Tests starten keinen Browser: statt der echten Browsersitzung wird eine
Attrappe eingesetzt, die das gespeicherte HTML liefert.
"""
from __future__ import annotations

import pytest
import yaml

from conftest import FakeFetcher, fixture

from nlzwatch.models import Club, Source


TSG_URL = "https://www.tsg-hoffenheim.de/tsg/karriere/stellenangebote"
RBL_URL = "https://rbleipzig.com/de/club-teamwork-karriere"


class FakeBrowser:
    """Liefert gespeichertes HTML statt eine Seite zu rendern."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.calls = []
        self.page_count = 0

    def get_html(self, url: str, wait_for=None, settle_ms=0) -> str:
        self.calls.append(url)
        self.page_count += 1
        for needle, content in self.pages.items():
            if needle in url:
                return content
        raise AssertionError("Unerwarteter Browserabruf: {}".format(url))


def params_from_clubs_yaml(source_id: str) -> dict:
    from conftest import ROOT
    data = yaml.safe_load((ROOT / "clubs.yaml").read_text(encoding="utf-8"))
    for club in data["clubs"]:
        for source in club["sources"]:
            if source["id"] == source_id:
                return source.get("params") or {}
    raise AssertionError("Quelle {} fehlt in clubs.yaml".format(source_id))


def build(source_id, url, club_name, short, list_fixture,
          detail_fixture=None, detail_key=None, browser_pages=None):
    from nlzwatch.adapters.js_generic import JsGenericAdapter

    pages = dict(browser_pages or {})
    pages.setdefault(url, fixture(list_fixture))
    browser = FakeBrowser(pages)

    http_pages = {}
    if detail_fixture:
        # Der Schluessel muss in der echten Detail-URL vorkommen
        http_pages[detail_key or "/"] = fixture(detail_fixture)
    fetcher = FakeFetcher(http_pages)

    source = Source(id=source_id, label="Stellen", adapter="js_generic",
                    url=url, params=params_from_clubs_yaml(source_id))
    adapter = JsGenericAdapter(fetcher, Club(name=club_name, short=short),
                               source, {}, browser_factory=lambda: browser)
    return adapter, browser, fetcher


# --- TSG Hoffenheim: AngularJS-Liste ------------------------------------
def test_tsg_alle_sechzehn_stellen():
    adapter, browser, _ = build("tsg-stellenangebote", TSG_URL,
                                "TSG Hoffenheim", "tsg", "js_tsg_list.html")
    jobs = adapter.list_jobs()
    assert len(jobs) == 16
    assert browser.page_count == 1


def test_tsg_titel_ohne_badges_und_ort():
    """Die Kachel enthaelt "Neu", die Vertragsart und den Ort.

    Ohne eigene Selektoren stand das alles im Titel.
    """
    adapter, _, _ = build("tsg-stellenangebote", TSG_URL,
                          "TSG Hoffenheim", "tsg", "js_tsg_list.html")
    jobs = {j.title: j for j in adapter.list_jobs()}
    assert "Praktikant TSG-Fußballschule (m/w/d)" in jobs
    job = jobs["Praktikant TSG-Fußballschule (m/w/d)"]
    assert job.employment_type == "Vollzeit"
    assert job.location == "Hoffenheim"
    for title in jobs:
        assert not title.startswith("Neu")
        assert "Hoffenheim" not in title or "TSG" in title


def test_tsg_links_gegen_die_seitenwurzel():
    """Angular liefert "./tsg/karriere/..." - sonst entsteht ein 403."""
    adapter, _, _ = build("tsg-stellenangebote", TSG_URL,
                          "TSG Hoffenheim", "tsg", "js_tsg_list.html")
    for job in adapter.list_jobs():
        assert job.url.startswith(
            "https://www.tsg-hoffenheim.de/tsg/karriere/stellenangebote/detail/")
        assert "karriere/./" not in job.url
        assert "/karriere/tsg/" not in job.url


def test_tsg_fussballschule_ist_kein_glb(classifier):
    """Die drei Fussballschul-Stellen sind Sport, aber kein GLB.

    Sie waren der Anlass fuer die engere Definition: GLB sind nur
    NLZ-Mannschaften der Altersklassen U9 bis U11. In dieser Liste
    steht keine solche Stelle.
    """
    adapter, _, _ = build("tsg-stellenangebote", TSG_URL,
                          "TSG Hoffenheim", "tsg", "js_tsg_list.html")
    jobs = adapter.list_jobs()
    for job in jobs:
        classifier.apply(job)
    schule = [j for j in jobs if "Fußballschule" in j.title]
    assert len(schule) == 3
    assert all(j.priority == "B" for j in schule)
    assert [j for j in jobs if j.priority == "A"] == []


def test_tsg_detailseite_ohne_browser():
    """Die Detailseiten sind normal abrufbar, dafuer braucht es keinen Browser."""
    adapter, browser, fetcher = build("tsg-stellenangebote", TSG_URL,
                                      "TSG Hoffenheim", "tsg",
                                      "js_tsg_list.html", "js_tsg_detail.html",
                                      detail_key="/stellenangebote/detail/")
    job = adapter.list_jobs()[0]
    adapter.enrich(job)
    assert job.description_fetched is True
    assert "DIESE AUFGABEN ERWARTEN DICH" in job.description
    assert browser.page_count == 1          # nur die Liste
    assert len(fetcher.calls) == 1          # Detail per HTTP


def test_tsg_leere_liste_am_marker_erkannt():
    """Hoffenheim schreibt bei null Stellen keinen Hinweis hin."""
    adapter, _, _ = build("tsg-stellenangebote", TSG_URL,
                          "TSG Hoffenheim", "tsg", "js_tsg_list_empty.html")
    result = adapter.fetch(detail_filter=lambda job: False)
    assert result.ok is True
    assert result.jobs == []
    assert result.legitimately_empty is True


# --- RB Leipzig: Links auf SmartRecruiters -------------------------------
def test_rbl_nur_vereinsstellen():
    """Neben den Vereinsstellen stehen dort Caterer und Sicherheitsfirmen."""
    adapter, _, _ = build("rbl-karriere", RBL_URL, "RB Leipzig", "rbl",
                          "js_rbl_list.html")
    jobs = adapter.list_jobs()
    assert len(jobs) == 5
    for job in jobs:
        assert "jobs.smartrecruiters.com" in job.url
    titles = " ".join(j.title for j in jobs).lower()
    assert "physiotherapeut" in titles
    for fremd in ("kandidatenportal", "loewensicherheit", "velvet-jobs"):
        assert fremd not in " ".join(j.url for j in jobs)


def test_rbl_container_ist_selbst_der_link():
    adapter, _, _ = build("rbl-karriere", RBL_URL, "RB Leipzig", "rbl",
                          "js_rbl_list.html")
    jobs = adapter.list_jobs()
    assert all(j.title for j in jobs)
    assert len({j.id for j in jobs}) == 5


def test_rbl_detail_als_microdata():
    """SmartRecruiters liefert kein JSON-LD, sondern Microdata."""
    adapter, browser, fetcher = build("rbl-karriere", RBL_URL, "RB Leipzig",
                                      "rbl", "js_rbl_list.html",
                                      "js_rbl_detail.html",
                                      detail_key="smartrecruiters")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "PHYSIOTHERAPEUT" in t.upper()][0]
    adapter.enrich(job)
    assert job.description_fetched is True
    assert job.published_at == "2026-10-27"
    assert job.location == "Leipzig"
    assert "Unternehmensbeschreibung" in job.description
    assert browser.page_count == 1          # Detail lief ohne Browser


def test_rbl_einstufung(classifier):
    adapter, _, fetcher = build("rbl-karriere", RBL_URL, "RB Leipzig", "rbl",
                                "js_rbl_list.html", "js_rbl_detail.html",
                                detail_key="smartrecruiters")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "PHYSIOTHERAPEUT" in t.upper()][0]
    classifier.apply(job)
    assert job.priority == "B"


# --- Fehlender Browser ---------------------------------------------------
def test_ohne_browser_scheitert_nur_diese_quelle():
    from nlzwatch.adapters.js_generic import JsGenericAdapter

    source = Source(id="tsg-stellenangebote", label="Stellen",
                    adapter="js_generic", url=TSG_URL,
                    params=params_from_clubs_yaml("tsg-stellenangebote"))
    adapter = JsGenericAdapter(FakeFetcher({}), Club(name="TSG", short="tsg"),
                               source, {}, browser_factory=None)
    result = adapter.fetch()
    assert result.ok is False
    assert "Browser" in (result.error or "")
