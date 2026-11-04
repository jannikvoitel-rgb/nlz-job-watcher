"""Adaptertest gegen gespeichertes HTML - ohne Netzzugriff."""
from __future__ import annotations

import pytest

from conftest import FakeFetcher, fixture

from nlzwatch.models import Club, Source


LIST_URL = "https://bayer04.softgarden.io/de/vacancies"


def build(list_fixture: str = "softgarden_list.html", filters=None,
          detail: bool = True):
    from nlzwatch.adapters.softgarden import SoftgardenAdapter

    pages = {}
    if detail:
        pages["/job/"] = fixture("softgarden_detail.html")
    pages["/de/vacancies"] = fixture(list_fixture)
    fetcher = FakeFetcher(pages)
    club = Club(name="Bayer 04 Leverkusen", short="bayer04")
    source = Source(id="bayer04-softgarden", label="Karriere-Board",
                    adapter="softgarden", url=LIST_URL)
    return SoftgardenAdapter(fetcher, club, source, filters or {}), fetcher


# --- Stellenliste --------------------------------------------------------
def test_liste_wird_geparst():
    adapter, _ = build()
    jobs = adapter.list_jobs()
    assert len(jobs) == 12
    titles = [j.title for j in jobs]
    assert "Trainer Future Kids U8-U10 (m/w/d) - geringfügige Beschäftigung" in titles
    assert "Torwarttrainer in China (m/w/d)" in titles


def test_detail_url_ist_stabil():
    """Wechselnde Parameter duerfen die URL und damit die ID nicht aendern."""
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["Torwarttrainer in China (m/w/d)"]
    assert job.url == "https://bayer04.softgarden.io/job/68512697"
    assert "jobDbPVId" not in job.url
    assert "l=de" not in job.url


def test_felder_aus_der_liste():
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["Trainer Future Kids U8-U10 (m/w/d) - geringfügige Beschäftigung"]
    assert job.published_at == "2026-09-28"
    assert job.department == "Trainer"
    assert job.audience == "Berufseinsteiger"
    assert "Leverkusen" in (job.location or "")
    # Die Zielgruppe darf nicht als Beschaeftigungsart durchgehen
    assert job.employment_type != "Berufseinsteiger"


def test_ids_sind_eindeutig():
    adapter, _ = build()
    ids = [j.ensure_id() for j in adapter.list_jobs()]
    assert len(ids) == len(set(ids))


def test_liste_ohne_jobkategorie_spalte():
    """Schalke rendert kein Kategorie-Feld - darf nicht abstuerzen."""
    adapter, _ = build(list_fixture="softgarden_list_schalke.html", detail=False)
    jobs = adapter.list_jobs()
    assert len(jobs) == 18
    assert all(j.title and j.url for j in jobs)
    assert any(j.published_at for j in jobs)


# --- Leere Liste ---------------------------------------------------------
def test_leere_liste_ist_kein_fehler():
    adapter, _ = build(list_fixture="softgarden_list_empty.html", detail=False)
    result = adapter.fetch(detail_filter=lambda job: False)
    assert result.ok is True
    assert result.jobs == []
    assert result.legitimately_empty is True


# --- Dauer-Eintraege -----------------------------------------------------
def test_initiativbewerbung_ist_keine_stelle():
    filters = {
        "ignore_titles": ["initiativbewerbung"],
        "speculative_titles": ["initiativbewerbung"],
    }
    adapter, _ = build(filters=filters)
    result = adapter.fetch(detail_filter=lambda job: False)
    titles = [j.title for j in result.jobs]
    assert "Initiativbewerbung" not in titles
    assert len(result.jobs) == 11
    assert adapter.speculative_entry is not None
    assert adapter.speculative_entry.title == "Initiativbewerbung"


# --- Detailseite ---------------------------------------------------------
def test_detailseite_liefert_volltext():
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["Trainer Future Kids U8-U10 (m/w/d) - geringfügige Beschäftigung"]
    adapter.enrich(job)

    assert job.description_fetched is True
    assert len(job.description) > 800
    # Gliederung bleibt erhalten
    assert "Deine Aufgaben" in job.description
    assert "Dein Profil" in job.description
    # Listenpunkte bleiben Listenpunkte
    assert "- Vorbereitung, Durchführung und Nachbereitung" in job.description
    # Kein Rahmenwerk der Seite
    for noise in ("Impressum", "Datenschutzerklärung", "Powered by softgarden",
                  "Cookie"):
        assert noise not in job.description


def test_beschaeftigungsart_wird_erkannt():
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["Trainer Future Kids U8-U10 (m/w/d) - geringfügige Beschäftigung"]
    adapter.enrich(job)
    assert job.employment_type == "Geringfügige Beschäftigung"


def test_unplausible_frist_wird_verworfen():
    """softgarden setzt validThrough automatisch zwei Jahre in die Zukunft."""
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["Trainer Future Kids U8-U10 (m/w/d) - geringfügige Beschäftigung"]
    adapter.enrich(job)
    assert job.deadline is None


def test_einstufung_der_echten_anzeige(classifier):
    """Die gespeicherte Anzeige muss als GLB-Stelle erkannt werden."""
    adapter, _ = build()
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["Trainer Future Kids U8-U10 (m/w/d) - geringfügige Beschäftigung"]
    adapter.enrich(job)
    classifier.apply(job)
    assert job.priority == "A"
    assert "U8" in job.priority_reason


def test_detailabruf_nur_bei_bedarf():
    """detail_filter steuert, welche Detailseiten geholt werden."""
    adapter, fetcher = build()
    adapter.fetch(detail_filter=lambda job: False)
    assert sum(1 for c in fetcher.calls if "/job/" in c) == 0

    adapter2, fetcher2 = build()
    adapter2.fetch(detail_filter=lambda job: job.title.startswith("Torwarttrainer"))
    assert sum(1 for c in fetcher2.calls if "/job/" in c) == 1
