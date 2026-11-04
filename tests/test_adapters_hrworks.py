"""Adaptertest HRworks gegen gespeichertes HTML - ohne Netzzugriff."""
from __future__ import annotations

import pytest

from conftest import FakeFetcher, fixture

from nlzwatch.models import Club, Source


def build(list_fixture: str = "hrworks_list_gladbach.html",
          url: str = "https://job.borussia.de/de",
          club_name: str = "Borussia Mönchengladbach", short: str = "bmg",
          filters=None, detail: bool = True):
    from nlzwatch.adapters.hrworks import HRworksAdapter

    # Detail-Muster zuerst: die Listen-URL steckt als Teilstring in der
    # Detail-URL ("/de" in "/de?id=c2d4df").
    pages = {}
    if detail:
        pages["?id="] = fixture("hrworks_detail.html")
    pages[url] = fixture(list_fixture)
    fetcher = FakeFetcher(pages)
    club = Club(name=club_name, short=short)
    source = Source(id=short + "-hrworks", label="Stellenportal",
                    adapter="hrworks", url=url)
    return HRworksAdapter(fetcher, club, source, filters or {}), fetcher


# --- Stellenliste --------------------------------------------------------
def test_liste_gladbach():
    adapter, _ = build(detail=False)
    jobs = adapter.list_jobs()
    assert len(jobs) == 8
    titles = [j.title for j in jobs]
    assert "PHYSIOTHERAPEUT IM FRAUEN- UND JUNIORINNENFUSSBALL (M/W/D)" in titles


def test_liste_mainz():
    adapter, _ = build(list_fixture="hrworks_list_mainz.html",
                       url="https://jobapplication.hrworks.de/de?companyId=ba8e529b",
                       club_name="FSV Mainz 05", short="mainz05", detail=False)
    jobs = adapter.list_jobs()
    assert len(jobs) == 12
    assert any("Spiel- & Videoanalyse" in j.title for j in jobs)


def test_filterportlet_ist_keine_stelle():
    """Die Seite hat ein Portlet mehr als Stellen: das Suchformular."""
    adapter, _ = build(detail=False)
    html = fixture("hrworks_list_gladbach.html")
    assert html.count("class='portlet light bordered'") == 9
    assert len(adapter.list_jobs()) == 8


def test_detail_url_traegt_die_id():
    adapter, _ = build(detail=False)
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["PHYSIOTHERAPEUT IM FRAUEN- UND JUNIORINNENFUSSBALL (M/W/D)"]
    assert job.url == "https://job.borussia.de/de?id=c2d4df"


def test_ids_sind_eindeutig():
    adapter, _ = build(detail=False)
    ids = [j.ensure_id() for j in adapter.list_jobs()]
    assert len(ids) == len(set(ids))


# --- Meta-Zeile ----------------------------------------------------------
def test_meta_wird_ueber_das_seitenvokabular_zugeordnet():
    """"Festanstellung - Teilzeit" darf nicht als Bereich durchgehen."""
    adapter, _ = build(detail=False)
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["PHYSIOTHERAPEUT IM FRAUEN- UND JUNIORINNENFUSSBALL (M/W/D)"]
    assert job.employment_type == "Festanstellung, Teilzeit"
    assert job.audience == "Berufseinsteiger"


def test_taetigkeitsbereich_wird_erkannt():
    """Mainz hat eine Bereichsliste, Gladbach nicht - beides muss gehen."""
    adapter, _ = build(list_fixture="hrworks_list_mainz.html",
                       url="https://jobapplication.hrworks.de/de?companyId=ba8e529b",
                       club_name="FSV Mainz 05", short="mainz05", detail=False)
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "Digitaler Vertrieb" in t][0]
    assert job.department == "Marketing und Werbung"
    assert job.employment_type == "Praktikum, Vollzeit"


def test_ort_wird_auf_den_ortsnamen_gekuerzt():
    adapter, _ = build(detail=False)
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["MITARBEITENDE VERKAUF IM FOHLENSHOP MINTO (M/W/D)"]
    assert job.location == "Mönchengladbach"
    assert "Am Minto" not in (job.location or "")


# --- Leere Liste ---------------------------------------------------------
def test_leere_liste_am_formular_erkannt():
    """Kein Hinweistext noetig: Formular da, Stellen weg -> legitim leer."""
    adapter, _ = build(list_fixture="hrworks_list_empty.html", detail=False)
    result = adapter.fetch(detail_filter=lambda job: False)
    assert result.ok is True
    assert result.jobs == []
    assert result.legitimately_empty is True


# --- Detailseite ---------------------------------------------------------
def test_detailseite_liefert_volltext():
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["PHYSIOTHERAPEUT IM FRAUEN- UND JUNIORINNENFUSSBALL (M/W/D)"]
    adapter.enrich(job)

    assert job.description_fetched is True
    assert len(job.description) > 1500
    assert "DEIN SPIELFELD" in job.description
    assert "WER DU BIST" in job.description
    for noise in ("bereitgestellt von", "Cross-Sitetracking", "Impressum",
                  "Datenschutzerklärung"):
        assert noise not in job.description


def test_detailseite_liefert_datum_und_vertragsart():
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["PHYSIOTHERAPEUT IM FRAUEN- UND JUNIORINNENFUSSBALL (M/W/D)"]
    adapter.enrich(job)
    assert job.published_at == "2026-10-21"
    assert job.employment_type == "Teilzeit"      # PART_TIME aus JSON-LD
    assert job.deadline is None                   # kein validThrough gesetzt


def test_bewerbungslink_und_ansprechpartner():
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["PHYSIOTHERAPEUT IM FRAUEN- UND JUNIORINNENFUSSBALL (M/W/D)"]
    adapter.enrich(job)
    assert job.apply_url and "apply?id=c2d4df" in job.apply_url
    assert job.contact == "Katharina Siegmann"


def test_einstufung_der_echten_anzeige(classifier):
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["PHYSIOTHERAPEUT IM FRAUEN- UND JUNIORINNENFUSSBALL (M/W/D)"]
    adapter.enrich(job)
    classifier.apply(job)
    assert job.priority == "B"
    assert "physiotherapeut" in job.priority_reason.lower()


def test_detailabruf_nur_bei_bedarf():
    adapter, fetcher = build()
    adapter.fetch(detail_filter=lambda job: False)
    assert sum(1 for c in fetcher.calls if "?id=" in c) == 0
