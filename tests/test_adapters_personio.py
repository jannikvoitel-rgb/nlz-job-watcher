"""Adaptertest Personio gegen gespeicherte Dateien - ohne Netzzugriff."""
from __future__ import annotations

import pytest

from conftest import FakeFetcher, fixture

from nlzwatch.models import Club, Source


KOELN = "https://effzeh.jobs.personio.de/"
HERTHA = "https://herthabsc.jobs.personio.com/"
HSV_AP = "https://hsv-fussball-ag-ap.jobs.personio.de/"


def build(url=KOELN, club_name="1. FC Köln", short="fck", prefer_xml=True,
          feed=None, board=None, detail=None, filters=None):
    from nlzwatch.adapters.personio import PersonioAdapter

    # Spezifische Muster zuerst: "/job/" steckt nicht in "/xml", aber die
    # Board-URL ist Teilstring der Detail-URL.
    pages = {}
    if detail:
        pages["/job/"] = fixture(detail)
    if feed:
        pages["/xml"] = fixture(feed)
    if board:
        pages[url] = fixture(board)
    fetcher = FakeFetcher(pages)
    source = Source(id=short + "-personio", label="Stellenbörse",
                    adapter="personio", url=url,
                    params={"prefer_xml": prefer_xml})
    return PersonioAdapter(fetcher, Club(name=club_name, short=short),
                           source, filters or {}), fetcher


# --- XML-Feed ------------------------------------------------------------
def test_feed_wird_geparst():
    adapter, _ = build(feed="personio_feed_koeln.xml")
    jobs = adapter.list_jobs()
    assert len(jobs) == 8
    assert adapter._used_xml is True
    titles = [j.title for j in jobs]
    assert ("MINI JOB: Kinderfußball-Trainer (U7-U11) im Partnerverein "
            "des 1. FC Köln (m/w/d)") in titles


def test_feed_liefert_beschreibung_mit_abschnitten():
    """Ein Abruf genuegt: der Feed enthaelt den gegliederten Volltext."""
    adapter, fetcher = build(feed="personio_feed_koeln.xml")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "Kinderfußball-Trainer" in t][0]
    assert job.description_fetched is True
    assert len(job.description) > 1500
    assert "## MIT DIESEN AUFGABEN TRÄGST DU ZU UNSEREM ERFOLG BEI" in job.description
    assert "## DAS SOLLTEST DU MITBRINGEN" in job.description
    assert "- Du planst und führst die Trainingseinheiten" in job.description
    # Nur der Feed, keine Detailseiten
    assert len(fetcher.calls) == 1


def test_feld_zuordnung_aus_dem_feed():
    adapter, _ = build(feed="personio_feed_koeln.xml")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "Kinderfußball-Trainer" in t][0]
    assert job.department == "Kinderfußball"
    assert job.location == "Köln"
    assert job.employment_type == "Teilzeit, Befristet"
    assert "Aushilfen" in (job.audience or "")
    assert job.url == "https://effzeh.jobs.personio.de/job/2134837"


def test_englische_schluesselwoerter_werden_uebersetzt():
    adapter, _ = build(feed="personio_feed_hsv.xml", url="https://hsv-fussball-ag.jobs.personio.de/",
                       club_name="Hamburger SV", short="hsv")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "Sportpsychologie" in t][0]
    assert job.employment_type == "Vollzeit, Festanstellung"
    assert job.department == "Administration NLZ"


def test_createdat_wird_nicht_als_datum_benutzt():
    """Das createdAt des Feeds ist der Anlagezeitpunkt, nicht die Veröffentlichung.

    Kölns Trainerstelle traegt im Feed 2025-05-30, die Detailseite aber
    2026-10-14. Ohne Detailabruf bleibt das Datum daher leer.
    """
    adapter, _ = build(feed="personio_feed_koeln.xml")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "Kinderfußball-Trainer" in t][0]
    assert job.published_at is None
    assert "2025-05-30" in fixture("personio_feed_koeln.xml")


def test_datum_kommt_von_der_detailseite():
    adapter, _ = build(feed="personio_feed_koeln.xml",
                       detail="personio_detail_koeln.html")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "Kinderfußball-Trainer" in t][0]
    adapter.enrich(job)
    assert job.published_at == "2026-10-14"


def test_einstufung_der_echten_anzeige(classifier):
    """Kölns Kinderfußball-Trainerstelle muss Priorität A werden."""
    adapter, _ = build(feed="personio_feed_koeln.xml")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "Kinderfußball-Trainer" in t][0]
    classifier.apply(job)
    assert job.priority == "A"


# --- HTML-Rueckfall ------------------------------------------------------
def test_rueckfall_auf_html_wenn_feed_leer():
    adapter, fetcher = build(url=HERTHA, club_name="Hertha BSC", short="hertha",
                             prefer_xml=True, feed="personio_feed_empty.xml",
                             board="personio_board_hertha.html")
    jobs = adapter.list_jobs()
    assert adapter._used_xml is False
    assert len(jobs) == 3
    assert any("Fußballschule" in j.title for j in jobs)
    assert any("/xml" in c for c in fetcher.calls)


def test_html_modus_ohne_feedversuch():
    adapter, fetcher = build(url=HERTHA, club_name="Hertha BSC", short="hertha",
                             prefer_xml=False, board="personio_board_hertha.html")
    jobs = adapter.list_jobs()
    assert len(jobs) == 3
    assert not any("/xml" in c for c in fetcher.calls)


def test_html_meta_ort_und_vertragsart():
    adapter, _ = build(url=HERTHA, club_name="Hertha BSC", short="hertha",
                       prefer_xml=False, board="personio_board_hertha.html")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["Trainer*in (m/w/d) Fußballschule"]
    assert job.location == "Berlin"
    assert "Teilzeit" in (job.employment_type or "")


def test_gruppentitel_als_abteilung():
    """Der HSV gruppiert nach Abteilung - das ist ein wertvolles Signal."""
    adapter, _ = build(url=HSV_AP, club_name="Hamburger SV", short="hsv",
                       prefer_xml=False, board="personio_board_hsv_ap.html")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "Athletik" in t][0]
    assert job.department == "Sport NLZ"


def test_gruppentitel_der_eine_vertragsart_ist_wird_nicht_abteilung():
    """Hertha gruppiert nach Vertragsart - "Minijob" ist keine Abteilung."""
    adapter, _ = build(url=HERTHA, club_name="Hertha BSC", short="hertha",
                       prefer_xml=False, board="personio_board_hertha.html")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["Trainer*in (m/w/d) Fußballschule"]
    assert job.department is None


def test_html_modus_holt_beschreibung_von_der_detailseite():
    adapter, _ = build(url=HERTHA, club_name="Hertha BSC", short="hertha",
                       prefer_xml=False, board="personio_board_hertha.html",
                       detail="personio_detail_hertha.html")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = jobs["Trainer*in (m/w/d) Fußballschule"]
    assert job.description == ""
    adapter.enrich(job)
    assert job.description_fetched is True
    assert len(job.description) > 800
    assert job.published_at == "2026-10-16"


# --- Identitaet ----------------------------------------------------------
def test_id_haengt_an_der_personio_nummer_nicht_an_der_board_url():
    """Zwei Boards desselben Vereins duerfen eine Stelle nicht doppeln.

    Der HSV hatte die Praktikumsstelle 1926161 auf beiden Boards.
    """
    from nlzwatch.models import make_job_id
    erwartet = make_job_id("hsv", "personio-job:1926161")

    aus_feed, _ = build(feed="personio_feed_hsv.xml",
                        url="https://hsv-fussball-ag.jobs.personio.de/",
                        club_name="Hamburger SV", short="hsv")
    feed_jobs = {j.id: j for j in aus_feed.list_jobs()}

    aus_html, _ = build(url=HSV_AP, club_name="Hamburger SV", short="hsv",
                        prefer_xml=False, board="personio_board_hsv_ap.html")
    html_jobs = {j.id: j for j in aus_html.list_jobs()}

    assert erwartet in feed_jobs
    assert erwartet in html_jobs
    # Gleiche Stelle, unterschiedliche Board-URL, identische ID
    assert feed_jobs[erwartet].url != html_jobs[erwartet].url
    assert len(set(feed_jobs) & set(html_jobs)) == 9


# --- Leeres Board --------------------------------------------------------
def test_leeres_board_ist_kein_fehler():
    adapter, _ = build(url=HERTHA, club_name="Hertha BSC", short="hertha",
                       prefer_xml=False, board="personio_board_empty.html")
    result = adapter.fetch(detail_filter=lambda job: False)
    assert result.ok is True
    assert result.jobs == []
    assert result.legitimately_empty is True
