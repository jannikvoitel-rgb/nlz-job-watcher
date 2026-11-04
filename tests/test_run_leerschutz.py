"""Ein leeres Abrufergebnis darf den Bestand nicht loeschen.

Hintergrund: Beim ersten Lauf auf GitHub lud die Angular-Seite der TSG
Hoffenheim nicht fertig. Die Quelle lieferte 0 Stellen, und der Lauf
markierte daraufhin alle 16 bekannten Stellen als geschlossen - darunter
drei aus der Fußballschule. Geantwortet hatte die Quelle aber nie.
"""
from nlzwatch.run import empty_result_is_suspect


def test_null_trotz_bestand_ist_verdaechtig():
    assert empty_result_is_suspect(found=0, previous=16,
                                   legitimately_empty=False) is True


def test_seite_meldet_selbst_nichts_offen():
    # Sagt die Seite "derzeit keine offenen Stellen", ist das eine Antwort.
    assert empty_result_is_suspect(found=0, previous=16,
                                   legitimately_empty=True) is False


def test_erstlauf_ohne_bestand_ist_kein_verdacht():
    assert empty_result_is_suspect(found=0, previous=0,
                                   legitimately_empty=False) is False


def test_gefundene_stellen_sind_kein_verdacht():
    assert empty_result_is_suspect(found=5, previous=16,
                                   legitimately_empty=False) is False


def test_rueckgang_ohne_null_bleibt_der_quotenregel():
    # Deutlicher Rueckgang, aber nicht leer: darum kuemmert sich die
    # Quotenpruefung im Lauf, nicht dieser Schutz.
    assert empty_result_is_suspect(found=1, previous=16,
                                   legitimately_empty=False) is False
