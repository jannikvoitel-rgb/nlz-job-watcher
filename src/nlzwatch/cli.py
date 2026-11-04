"""Kommandozeile des NLZ-Stellenwatchers."""
from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nlzwatch",
        description="Überwacht die Karriereseiten von Fußball-Nachwuchs"
                    "leistungszentren und meldet neue Sportstellen per Push.",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="alles ausführen, aber keine Pushes senden und "
                        "keine Dateien schreiben")
    p.add_argument("--club", action="append", dest="clubs", metavar="KURZNAME",
                   help="nur diesen Verein abrufen (mehrfach möglich), "
                        "z. B. --club bayer04")
    p.add_argument("--reclassify", action="store_true",
                   help="alle gespeicherten Stellen neu einstufen "
                        "(nach Änderungen an filters.yaml)")
    p.add_argument("--skip-details", action="store_true",
                   help="keine Detailseiten abrufen (schneller Test der Listen)")
    p.add_argument("--test-push", action="store_true",
                   help="eine Testnachricht mit hoher Priorität senden und beenden")
    p.add_argument("--report", action="store_true",
                   help="aktuellen Stand aus data/jobs.json als Markdown "
                        "ausgeben, ohne etwas abzurufen")
    p.add_argument("--fail-on-error", action="store_true",
                   help="mit Fehlercode enden, wenn eine Quelle nicht "
                        "abrufbar war (Standard: nein, damit ein einzelner "
                        "Verein den Lauf nicht rot färbt)")
    p.add_argument("-v", "--verbose", action="store_true", help="mehr Logausgaben")
    return p


def build_report() -> str:
    """Aktuellen Stand als Markdown, fuer die Zusammenfassung eines Laufs."""
    from .config import project_root
    from .store import Store

    store = Store(project_root() / "data" / "jobs.json")
    store.load()
    offen = [j for j in store.jobs.values() if j.status == "offen"]
    sport = [j for j in offen if j.priority in ("A", "B")]
    glb = [j for j in offen if j.priority == "A"]

    lines = [
        "### Stand der Stellensuche",
        "",
        "| | Anzahl |",
        "|---|---|",
        "| Stellen offen | {} |".format(len(offen)),
        "| davon im Sport | {} |".format(len(sport)),
        "| davon im Grundlagenbereich | {} |".format(len(glb)),
        "",
    ]
    if glb:
        lines.append("**Offen im Grundlagenbereich**")
        lines.append("")
        for job in sorted(glb, key=lambda j: (j.club, j.title)):
            lines.append("- {} – [{}]({})".format(job.club, job.title, job.url))
        lines.append("")

    probleme = []
    for short, state in sorted(store.clubs.items()):
        for sid, src in (state.get("sources") or {}).items():
            if src.get("manual"):
                probleme.append("- {}: {} wird manuell beobachtet".format(
                    state.get("name", short), src.get("label", sid)))
            elif src.get("last_error"):
                probleme.append("- {}: {} meldet einen Fehler".format(
                    state.get("name", short), src.get("label", sid)))
    if probleme:
        lines.append("**Hinweise**")
        lines.append("")
        lines.extend(probleme)
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
        stream=sys.stdout,
    )
    # Fremdbibliotheken nicht mitloggen lassen
    for noisy in ("urllib3", "requests", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # pdfminer warnt bei fast jedem Vereins-PDF ueber Farbdefinitionen.
    # Das sagt nichts ueber die Textqualitaet, daher ganz aus.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)

    from .notify import Notifier
    from .config import load_filters, project_root
    from .run import Runner
    from .store import Store

    if args.report:
        # Der Bericht geht in die Zusammenfassung eines Laufs, dort stoeren
        # Logzeilen auf der Standardausgabe.
        logging.getLogger().setLevel(logging.WARNING)
        print(build_report())
        return 0

    if args.test_push:
        notifier = Notifier(load_filters(), dry_run=args.dry_run)
        if not notifier.enabled and not args.dry_run:
            print("NTFY_TOPIC ist nicht gesetzt. Beispiel:\n"
                  "  export NTFY_TOPIC='dein-topic'\n"
                  "  python -m nlzwatch --test-push")
            return 2
        ok = notifier.push_test()
        print("Testnachricht gesendet." if ok else "Testnachricht nicht gesendet.")
        return 0 if ok else 1

    runner = Runner(dry_run=args.dry_run, only=args.clubs,
                    reclassify=args.reclassify, skip_details=args.skip_details)
    report = runner.execute()
    print("\n".join(report.summary_lines()))

    if report.errors:
        # Fehlerhafte Quellen melden sich per Warn-Push. Der Lauf selbst
        # gilt nur dann als fehlgeschlagen, wenn das ausdruecklich
        # gewuenscht ist - sonst waere jede Vereinsstoerung ein roter Lauf.
        for entry in report.errors:
            print("Fehler bei {} / {}: {}".format(
                entry.club, entry.label, entry.error))
        if args.fail_on_error:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
