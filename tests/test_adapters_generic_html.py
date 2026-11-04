"""Adaptertest generic_html gegen gespeichertes HTML - ohne Netzzugriff.

Die sieben Vereinsseiten haben keine gemeinsame Technik. Jeder Test prueft
daher eine Quelle mit den Selektoren, die auch in clubs.yaml stehen.
"""
from __future__ import annotations

import pytest
import yaml

from conftest import FakeFetcher, fixture

from nlzwatch.models import Club, Source


def build(url, params, list_fixture, club_name="Testverein", short="test",
          filters=None, detail=None, detail_bytes=None):
    from nlzwatch.adapters.generic_html import GenericHtmlAdapter

    pages = {}
    if detail:
        pages["DETAIL"] = fixture(detail)
    pages[url] = fixture(list_fixture)
    fetcher = FakeFetcher(pages)
    if detail_bytes is not None:
        fetcher.get_bytes = lambda u: detail_bytes
    source = Source(id=short + "-generic", label="Jobs",
                    adapter="generic_html", url=url, params=params)
    return GenericHtmlAdapter(fetcher, Club(name=club_name, short=short),
                              source, filters or {}), fetcher


def params_from_clubs_yaml(source_id: str) -> dict:
    """Selektoren aus der echten clubs.yaml holen.

    So kann der Test nicht mit der Konfiguration auseinanderlaufen.
    """
    from conftest import ROOT
    data = yaml.safe_load((ROOT / "clubs.yaml").read_text(encoding="utf-8"))
    for club in data["clubs"]:
        for source in club["sources"]:
            if source["id"] == source_id:
                return source.get("params") or {}
    raise AssertionError("Quelle {} fehlt in clubs.yaml".format(source_id))


# --- Paderborn: Aufklapp-Abschnitte ohne eigene URL ----------------------
PADERBORN_URL = "https://www.scp07.de/SCP07/Die-KGaA/Jobs/"


def test_paderborn_alle_acht_stellen():
    adapter, _ = build(PADERBORN_URL, params_from_clubs_yaml("scp-jobs"),
                       "generic_paderborn.html", "SC Paderborn 07", "scp")
    jobs = adapter.list_jobs()
    assert len(jobs) == 8
    assert any("SCP07 FUSSBALLSCHULE" in j.title for j in jobs)


def test_paderborn_ids_sind_eindeutig_trotz_gleicher_url():
    """Alle Stellen teilen eine URL - die ID muss am Titel haengen.

    normalize_url() entfernt Fragmente, ein "#titel" an der URL haette
    daher wieder identische IDs ergeben.
    """
    adapter, _ = build(PADERBORN_URL, params_from_clubs_yaml("scp-jobs"),
                       "generic_paderborn.html", "SC Paderborn 07", "scp")
    jobs = adapter.list_jobs()
    assert len({j.url for j in jobs}) == 1
    assert len({j.id for j in jobs}) == 8


def test_paderborn_volltext_steht_auf_der_listenseite():
    adapter, fetcher = build(PADERBORN_URL, params_from_clubs_yaml("scp-jobs"),
                             "generic_paderborn.html", "SC Paderborn 07", "scp")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "FUSSBALLSCHULE" in t][0]
    assert job.description_fetched is True
    assert "DEINE AUFGABEN" in job.description
    assert len(fetcher.calls) == 1          # nur die Listenseite


def test_paderborn_links_aus_der_beschreibung_werden_nicht_verwendet():
    """Eine Stelle verlinkt im Text einen Caterer - das ist kein Stellenlink."""
    adapter, _ = build(PADERBORN_URL, params_from_clubs_yaml("scp-jobs"),
                       "generic_paderborn.html", "SC Paderborn 07", "scp")
    for job in adapter.list_jobs():
        assert job.url == PADERBORN_URL
        assert "esslust" not in job.url


def test_paderborn_abschnittstitel_wird_vertragsart():
    adapter, _ = build(PADERBORN_URL, params_from_clubs_yaml("scp-jobs"),
                       "generic_paderborn.html", "SC Paderborn 07", "scp")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "FUSSBALLSCHULE" in t][0]
    assert job.employment_type == "Teilzeit/Geringfügige Beschäftigung"


def test_paderborn_einstufung(classifier):
    adapter, _ = build(PADERBORN_URL, params_from_clubs_yaml("scp-jobs"),
                       "generic_paderborn.html", "SC Paderborn 07", "scp")
    jobs = {j.title: j for j in adapter.list_jobs()}
    job = [j for t, j in jobs.items() if "FUSSBALLSCHULE" in t][0]
    classifier.apply(job)
    assert job.priority == "A"


def test_leere_seite_ohne_stellen():
    adapter, _ = build(PADERBORN_URL, params_from_clubs_yaml("scp-jobs"),
                       "generic_paderborn_empty.html", "SC Paderborn 07", "scp")
    jobs = adapter.list_jobs()
    assert jobs == []


# --- Eintracht AG: Liste mit Meta-Werten ---------------------------------
def test_eintracht_ag_liste_und_meta():
    adapter, _ = build("https://klub.eintracht.de/jobs/ag/",
                       params_from_clubs_yaml("sge-ag"),
                       "generic_eintracht_ag.html", "Eintracht Frankfurt", "sge")
    jobs = {j.title: j for j in adapter.list_jobs()}
    assert len(jobs) == 5
    job = jobs["Mitarbeiter Veranstaltungs- und Geländesicherheit (m/w/d)"]
    assert job.employment_type == "Festanstellung, Vollzeit"
    assert "Deutsche Bank Park" in (job.location or "")
    assert job.url.endswith("/jobs/mitarbeiter-veranstaltungs-und-gelandesicherheit-mwd/")


# --- Gladbach Minijobs: Volltext und Link --------------------------------
def test_gladbach_minijobs():
    adapter, _ = build("https://minijobs.borussia.de/",
                       params_from_clubs_yaml("bmg-minijobs"),
                       "generic_bmg_minijobs.html", "Borussia Mönchengladbach", "bmg")
    jobs = {j.title: j for j in adapter.list_jobs()}
    assert len(jobs) == 5
    job = jobs["Fahrdienst im NLZ (m/w/d)"]
    assert job.description_fetched is True
    assert "Nachwuchsleistungszentrums" in job.description
    assert job.url == "https://minijobs.borussia.de/jobs/fahrdienst-im-nlz-mwd/"


# --- HSV e.V.: Seite ohne sprechende Klassen ------------------------------
def test_hsv_ev_nur_stellen_kein_navigationsmenue():
    """Das Navigationsmenue nutzt dieselbe Aufklapp-Struktur."""
    adapter, _ = build("https://www.hsv.de/jobs-beim-e-v",
                       params_from_clubs_yaml("hsv-ev"),
                       "generic_hsv_ev.html", "Hamburger SV", "hsv")
    jobs = adapter.list_jobs()
    assert len(jobs) == 7
    titles = [j.title for j in jobs]
    assert "Menü" not in titles
    assert "Co-Trainer:innen (m/w/d) Nachwuchsfußball weiblich" in titles
    assert all(j.description for j in jobs)


# --- VfB: verschachteltes HTML und PDF-Ausschreibungen -------------------
VFB_URL = "https://www.vfb.de/de/1893/aktuell/jobs/jobs/"


def test_vfb_titel_ohne_linktext():
    """Der Titel steht im <p>, der Linktext ist "Ausschreibung ..."."""
    adapter, _ = build(VFB_URL, params_from_clubs_yaml("vfb-jobs"),
                       "generic_vfb_jobs.html", "VfB Stuttgart", "vfb")
    titles = [j.title for j in adapter.list_jobs()]
    assert "Recht: Rechtsreferendar (m/w/d)" in titles
    assert "Fanbetreuung: Mitarbeiter (m/w/d) Fan- und Zuschauermanagement" in titles
    assert not any(t.startswith("Ausschreibung") for t in titles)


def test_vfb_verschachtelte_treffer_werden_gefiltert():
    """Das VfB-HTML schachtelt <p> ineinander, das darf nicht doppeln."""
    adapter, _ = build(VFB_URL, params_from_clubs_yaml("vfb-jobs"),
                       "generic_vfb_jobs.html", "VfB Stuttgart", "vfb")
    jobs = adapter.list_jobs()
    assert len(jobs) == 6
    assert len({j.url for j in jobs}) == 6


def test_vfb_verlinkt_das_pdf():
    adapter, _ = build(VFB_URL, params_from_clubs_yaml("vfb-jobs"),
                       "generic_vfb_jobs.html", "VfB Stuttgart", "vfb")
    for job in adapter.list_jobs():
        assert job.url.endswith(".pdf")


def test_bild_pdf_wird_benannt_statt_leer_gelassen():
    """Ein Teil der VfB-Ausschreibungen sind Bild-PDFs ohne Textschicht."""
    adapter, _ = build(VFB_URL, params_from_clubs_yaml("vfb-jobs"),
                       "generic_vfb_jobs.html", "VfB Stuttgart", "vfb",
                       detail_bytes=b"")      # liefert keinen Text
    job = adapter.list_jobs()[0]
    adapter.enrich(job)
    assert job.description_fetched is False
    assert "Bild-PDF" in job.description
    assert "Originalanzeige" in job.description


# --- Schalke: Titel steckt im Linktext -----------------------------------
def test_schalke_titel_aus_dem_linktext():
    adapter, _ = build("https://schalke04.de/verein/karriere/jobangebote/",
                       params_from_clubs_yaml("s04-weitere"),
                       "generic_schalke_weitere.html", "FC Schalke 04", "s04")
    jobs = adapter.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].title == "Ehrenamtlicher Fahrdienst (m/w/d) im Fußball der Frauen"
    assert jobs[0].url.endswith(".pdf")


# --- Wolfsburg: Titel im ersten <p>, Datum nicht im Titel ----------------
def test_wolfsburg_titel_ohne_startdatum():
    adapter, _ = build("https://www.vfl-wolfsburg.de/der-vfl/jobs/praktikum",
                       params_from_clubs_yaml("vfl-praktikum"),
                       "generic_wolfsburg_praktikum.html", "VfL Wolfsburg", "vfl")
    jobs = adapter.list_jobs()
    assert len(jobs) == 3
    titles = [j.title for j in jobs]
    assert "Internationale Vermarktung (all genders)" in titles
    assert not any("01.02.2027" in t for t in titles)


# --- Fehlende Konfiguration ----------------------------------------------
def test_fehlender_item_selektor_wird_klar_gemeldet():
    adapter, _ = build(PADERBORN_URL, {}, "generic_paderborn.html")
    with pytest.raises(ValueError) as fehler:
        adapter.list_jobs()
    assert "params.item" in str(fehler.value)
