"""Tests der Prioritaets-Einstufung.

Je Stufe mindestens zehn echte deutsche Stellentitel, mit m/w/d-Zusaetzen,
Umlauten und wechselnder Gross-/Kleinschreibung.
"""
from __future__ import annotations

import pytest

# --- Prioritaet A: Grundlagenbereich ------------------------------------
TITLES_A = [
    "Trainer Future Kids U8-U10 (m/w/d) - geringfügige Beschäftigung",
    "MINI JOB: Kinderfußball-Trainer (U7-U11) im Partnerverein (m/w/d)",
    "Honorartrainer*in (m/w/d) Werder Fußballschule",
    "Trainer*in (m/w/d) Fußballschule",
    "TRAINER/IN FÜR DIE SCP07 FUSSBALLSCHULE (M/W/D)",
    "Trainer (m|w|d) - FC Bayern Campus Training",
    "Übungsleiter Grundlagenbereich (m/w/d)",
    "Nachwuchstrainer im Grundlagentraining (m/w/d)",
    "Trainer U9 / U10 (m/w/d) im Nachwuchsleistungszentrum",
    "Bambini-Trainer (m/w/d) gesucht",
    "Co-Trainer (m/w/d) F-Jugend",
    "Pflichtpraktikant*in (m/w/d) in der WERDER Fußballschule",
    "Trainer:in Talentförderung (m/w/d)",
    "Camptrainer (m/w/d) für unsere Fußballcamps",
]

# --- Prioritaet B: Sport allgemein --------------------------------------
TITLES_B = [
    "Torwarttrainer in China (m/w/d)",
    "Torwarttrainer U12/U13 (all genders)",
    "Physiotherapeut (m/w/d) Fußball der Frauen",
    "Mitarbeiter/-in (m/w/d) Sportpsychologie Nachwuchsleistungszentrum",
    "Pflichtpraktikant/-in (m/w/d) Videoanalyse",
    "Athletiktrainer (m/w/d) für die U19",
    "Teammanager (m/w/d) BVB-Mädchen U16 als Aushilfe",
    "Scout (m/w/d) für den Nachwuchsbereich",
    "Sporttherapeut (m/w/d) für die Reha-Welt",
    "Individualtrainer (m/w/d) im Leistungszentrum",
    "Jugendtrainer (m/w/d)",
    "Co-Trainer:innen (m/w/d) Nachwuchsfußball weiblich",
    "Übungsleiter:in (m/w/d) Sportkurse",
    "Pädagogische Fachkraft (m/w/d) im Fußballinternat",
]

# --- Prioritaet C: ohne Sportbezug --------------------------------------
TITLES_C = [
    "Koch (m/w/d) SIGNAL IDUNA PARK",
    "Aushilfe (m/w/d) im Arenaverkauf",
    "Sicherheitsmitarbeiter (m/w/d) Objektschutz",
    "Data Architect (m/w/d)",
    "Controller (m/w/d) - Schwerpunkt Power BI",
    "Pflichtpraktikant Grafikdesign (m/w/d)",
    "Digital Media Manager International (m/w/d)",
    "Mitarbeiter (m/w/d) Ticketing",
    "Verkäufer (m/w/d) im Fanshop in Teilzeit",
    "Rechtsreferendar (m/w/d)",
    "Greenkeeper (m/w/d)",
    "Mitarbeiter (m/w/d) Payroll/Accounting",
    "Werkstudent (m/w/d) Film",
    "Aushilfe als Darsteller*in (m/w/d) Maskottchen",
    "Chef de Partie (m/w/d) Bistro 09",
]


@pytest.mark.parametrize("title", TITLES_A)
def test_priority_a(classifier, title):
    priority, reason = classifier.classify(title)
    assert priority == "A", "{} -> {} ({})".format(title, priority, reason)
    assert reason


@pytest.mark.parametrize("title", TITLES_B)
def test_priority_b(classifier, title):
    priority, reason = classifier.classify(title)
    assert priority == "B", "{} -> {} ({})".format(title, priority, reason)
    assert reason


@pytest.mark.parametrize("title", TITLES_C)
def test_priority_c(classifier, title):
    priority, reason = classifier.classify(title)
    assert priority == "C", "{} -> {} ({})".format(title, priority, reason)
    assert reason


def test_mindestens_zehn_beispiele_je_stufe():
    """Die Vorgabe aus der Aufgabenstellung festschreiben."""
    assert len(TITLES_A) >= 10
    assert len(TITLES_B) >= 10
    assert len(TITLES_C) >= 10


# --- Sonderfaelle --------------------------------------------------------
def test_a_aus_beschreibung_bei_neutralem_titel(classifier):
    """Nur "Trainer Nachwuchs/NLZ", Altersklassen erst in der Beschreibung."""
    priority, reason = classifier.classify(
        "Nachwuchstrainer (m/w/d) im NLZ",
        description="Du trainierst unsere Teams der Altersklassen U9 bis U11.",
        department="Sport",
    )
    assert priority == "A"
    assert "U9" in reason or "U11" in reason


def test_a_aus_beschreibung_nur_mit_sportbezug_im_titel(classifier):
    """Eine Marketingstelle wird nicht A, weil im Text ein U10-Turnier steht."""
    priority, _ = classifier.classify(
        "Manager (m/w/d) Brand Activation & Events",
        description="Du betreust unser U10-Turnier und weitere Veranstaltungen.",
        department="Marketing und Kommunikation",
    )
    assert priority == "C"


def test_umlaute_und_schreibweisen_egal(classifier):
    """Fussballschule ohne Umlaut und in Grossschreibung trifft genauso."""
    for variant in ("Trainer Fußballschule", "TRAINER FUSSBALLSCHULE",
                    "trainer fussballschule", "Trainer Fussballschule (m/w/d)"):
        assert classifier.classify(variant)[0] == "A", variant


def test_altersklasse_u16_loest_kein_a_aus(classifier):
    """U16 liegt ausserhalb des Grundlagenbereichs."""
    priority, _ = classifier.classify("Trainer (m/w/d) U16")
    assert priority == "B"


def test_kurzes_schlagwort_trifft_nicht_in_fremdwort(classifier):
    """"it" darf nicht in "Sicherheit" treffen."""
    priority, reason = classifier.classify(
        "Mitarbeiter (m/w/d) Veranstaltungssicherheit")
    assert priority == "C"
    assert "it" != reason


def test_unklarer_titel_wird_b_nicht_c(classifier):
    """Unsichere Faelle bewusst hoeher einstufen."""
    priority, reason = classifier.classify("Mitarbeiter (m/w/d) Erlebnisformate")
    assert priority == "B"
    assert "vorsorglich" in reason


def test_bereich_aus_dem_portal_zaehlt(classifier):
    """Die Jobkategorie des Portals ist ein gueltiges Signal."""
    priority, reason = classifier.classify(
        "Pflichtpraktikant (m/w/d)", department="Sport NLZ")
    assert priority == "B"
    assert "nlz" in reason.lower() or "sport" in reason.lower()


# --- Vereinsspezifische Schlagwoerter ------------------------------------
def test_vereinsschlagwort_hebt_nach_b(classifier):
    """"Fohlenstall" ist Gladbachs NLZ-Internat, global aber unbekannt."""
    titel = "PÄDAGOGISCHE BETREUUNGSKRAFT (M/W/D) IN TEILZEIT IM FOHLENSTALL"
    # Ohne Vereinsschlagwort greift nur das Sicherheitsnetz
    priority, reason = classifier.classify(titel)
    assert priority == "B"
    assert "vorsorglich" in reason

    club = classifier.compile_club("bmg", {"priority_b": ["fohlenstall"]})
    priority, reason = classifier.classify(titel, club_keywords=club)
    assert priority == "B"
    assert "fohlenstall" in reason.lower()
    assert "vorsorglich" not in reason


def test_vereinsschlagwort_kann_nach_a_heben(classifier):
    club = classifier.compile_club("test", {"priority_a": ["knappenkicker"]})
    priority, reason = classifier.classify(
        "Trainer (m/w/d) Knappenkicker", club_keywords=club)
    assert priority == "A"
    assert "knappenkicker" in reason.lower()


def test_vereinsschlagwort_kann_nach_c_senken(classifier):
    club = classifier.compile_club("test2", {"priority_c": ["fohlensportsbar"]})
    priority, reason = classifier.classify(
        "Aushilfe (m/w/d) FohlenSportsbar", club_keywords=club)
    assert priority == "C"


def test_ohne_vereinsschlagwoerter_unveraendert(classifier):
    """Ein Verein ohne eigene Liste wird genau wie vorher eingestuft."""
    titel = "Torwarttrainer (m/w/d)"
    assert classifier.classify(titel) == classifier.classify(
        titel, club_keywords=classifier.compile_club("leer", {}))


# --- Titel sticht Abteilung ---------------------------------------------
def test_eindeutiger_titel_sticht_abteilungssignal(classifier):
    """HSV: "Köchin/Koch" in der Abteilung "Ernährung" ist Gastronomie."""
    priority, reason = classifier.classify("Köchin/Koch (m/w/d)",
                                           department="Ernährung")
    assert priority == "C"
    assert "Titel" in reason


def test_abteilungssignal_greift_weiter_ohne_c_titel(classifier):
    """Ohne Nicht-Sport-Wort im Titel zaehlt der Bereich weiter."""
    priority, reason = classifier.classify("Pflichtpraktikant/-in (m/w/d)",
                                           department="Sport NLZ")
    assert priority == "B"


def test_sportberuf_im_titel_bleibt_b_trotz_c_abteilung(classifier):
    """Ein Sport-Schlagwort im Titel wird vor allem anderen geprueft."""
    priority, reason = classifier.classify(
        "Physiotherapeut (m/w/d) Fußball der Frauen", department="Marketing")
    assert priority == "B"
    assert "physiotherapeut" in reason.lower()


def test_nicht_sport_titel_blockt_a_aus_der_beschreibung(classifier):
    """Werder: ein Fahrdienst wird keine GLB-Meldung.

    Im Fliesstext der Anzeige steht "Talentförderung", der Titel nennt das
    Leistungszentrum - ohne Sperre waere das Prioritaet A geworden.
    """
    priority, reason = classifier.classify(
        "Aushilfe (m/w/d) Fahrdienst im Leistungszentrum",
        description="Du unterstützt unsere Talentförderung bei Fahrten zu Spielen.",
    )
    assert priority == "B"
    assert "leistungszentrum" in reason.lower()


def test_a_aus_der_beschreibung_bleibt_bei_echter_trainerstelle(classifier):
    """Die Sperre darf echte GLB-Stellen nicht verhindern."""
    priority, _ = classifier.classify(
        "Pflichtpraktikant Athletik und Rehabilitation im Leistungszentrum (m/w/d)",
        description="Unterstützung des Athletiktrainings im Grundlagen- "
                    "und Aufbaubereich (U11-U15).",
    )
    assert priority == "A"
