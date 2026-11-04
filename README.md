# NLZ-Stellenwatcher

Überwacht die Karriereseiten von 17 Fußball-Nachwuchsleistungszentren und meldet
neue Stellen im Sportbereich per Push aufs Handy. Stellen im Grundlagenbereich
(U8–U11) haben Vorrang. Alle gefundenen Stellen stehen mit vollständiger
Beschreibung in einer kleinen Web-App.

Privates Werkzeug für die eigene Stellensuche.

## Stand der Umsetzung

| Baustein | Stand |
|----------|-------|
| Untersuchungsbericht aller 17 Vereine | fertig, siehe [BERICHT.md](BERICHT.md) |
| Kern: Config, Datenmodell, Einstufung, Push, `jobs.json` | fertig |
| Adapter `softgarden` (Dortmund, Bayer 04, Schalke, Werder) | fertig, gegen die echten Seiten getestet |
| Adapter `hrworks` (Mainz, Freiburg, Gladbach, Eintracht e.V.) | fertig, gegen die echten Seiten getestet |
| Adapter `personio` (Köln, Hertha, HSV mit zwei Boards) | fertig, gegen die echten Seiten getestet |
| Adapter `generic_html` (VfB, Paderborn, Wolfsburg, HSV e.V., Eintracht AG, Gladbach-Minijobs, Schalke-Zusatz) | fertig, gegen die echten Seiten getestet |
| Adapter `js_generic` (Hoffenheim, RB Leipzig) | fertig, gegen die echten Seiten getestet |
| FC Bayern | **nicht scrapebar**, als manuelle Quelle geführt (siehe unten) |
| Web-App (`docs/`) | fertig, lokal geprüft |
| GitHub-Actions-Workflow | fertig |

Noch nicht gebaute Quellen stehen in `clubs.yaml` auf `enabled: false` und werden
übersprungen, ohne den Lauf zu stören. Stand jetzt: **16 von 17 Vereinen live**,
25 von 26 Quellen aktiv, 217 Stellen erfasst, davon 70 im Sport und 13 im
Grundlagenbereich. Nur der FC Bayern lässt sich nicht abrufen.

### FC Bayern: warum manuell

Das Jobportal des FC Bayern weist automatisierte Zugriffe ab – auch einem
echten Browser liefert es eine Fehlerseite statt der Stellen. Daran vorbei
zu kommen hieße, die Bot-Erkennung zu täuschen; das ist bewusst nicht
gebaut. Und selbst wenn es lokal ginge: GitHub Actions läuft headless,
genau das wird dort blockiert.

Stattdessen hat das Portal eine **eigene Benachrichtigungsfunktion**. Im
Portal auf „Benachrichtigung erstellen" gehen, E-Mail hinterlegen – dann
kommen neue Stellen direkt vom Verein. Zusätzlich lässt sich ein
Bewerberprofil für künftige Stellen anlegen. Die Quelle bleibt in
`clubs.yaml` dokumentiert und erscheint im Lauf als „manuell beobachten".

## Einrichtung auf GitHub

Danach läuft alles von allein: alle drei Stunden ein Lauf, Push aufs Handy
bei neuen Sportstellen, Web-App immer aktuell.

### 1. Repository anlegen

```bash
cd /Users/jannikvoitel/Desktop/Arbeit/nlz-job-watcher && git init -b main && git add . && git commit -m "NLZ-Stellenwatcher"
```

Dann auf GitHub ein Repository anlegen und verbinden:

```bash
git remote add origin git@github.com:DEIN-NAME/nlz-job-watcher.git && git push -u origin main
```

Das Repository muss **öffentlich** sein, sonst braucht GitHub Pages einen
bezahlten Plan. Damit sind auch die gesammelten Stellenbeschreibungen
öffentlich abrufbar – das ist bewusst so entschieden.

### 2. ntfy auf dem Handy einrichten

1. App installieren: **ntfy** für
   [iPhone](https://apps.apple.com/app/ntfy/id1625396347) oder
   [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy).
2. In der App auf **+** tippen und ein Topic abonnieren. Frei wählbar, aber
   wer es kennt, kann mitlesen – nimm etwas Langes und Unratbares, etwa
   `nlz-stellen-` plus eine zufällige Zeichenfolge.

### 3. Secret setzen

Im Repository unter **Settings → Secrets and variables → Actions → New
repository secret**:

| Name | Wert | Pflicht |
|------|------|---------|
| `NTFY_TOPIC` | dein Topic aus Schritt 2 | ja |
| `NTFY_SERVER` | eigener ntfy-Server, sonst weglassen | nein |
| `WATCHER_CONTACT` | Kontaktangabe im User-Agent | nein |

Das Topic steht dadurch nirgends im Code und wird auch nicht geloggt.

### 4. GitHub Pages aktivieren

**Settings → Pages → Source: Deploy from a branch**, Branch `main`, Ordner
`/docs`. Nach ein bis zwei Minuten liegt die App unter
`https://DEIN-NAME.github.io/nlz-job-watcher/`. Sie aktualisiert sich bei
jedem Lauf mit, weil der Workflow `docs/data/jobs.json` mit zurückschreibt.

Die Seite auf dem Handy öffnen und auf den Homescreen legen: iPhone über
„Teilen → Zum Home-Bildschirm", Android über das Browser-Menü
„App installieren".

### 5. Ersten Lauf starten

Unter **Actions → Stellen prüfen → Run workflow**. Beim allerersten Lauf
einer Quelle werden die vorhandenen Stellen nur als Bestand gespeichert;
statt einer Push-Flut kommt eine einzige Startübersicht.

> Im Repo liegt bereits ein Datenstand vom ersten Lauf. Wenn du die
> Startübersicht trotzdem einmal sehen willst, lösche `data/jobs.json` und
> starte den Workflow neu.

## Der Workflow

`.github/workflows/watch.yml` läuft alle drei Stunden (`cron: 0 */3 * * *`)
und lässt sich jederzeit von Hand starten, auf Wunsch als Trockenlauf.

Reihenfolge: Abhängigkeiten installieren, Chromium aus dem Cache holen,
**pytest**, dann der Scraper. Schlagen die Tests fehl, wird gar nicht erst
gescrapt. Danach werden `data/jobs.json` und `docs/data/jobs.json`
zurückcommittet, und die Zusammenfassung des Laufs zeigt die offenen
GLB-Stellen direkt in der Actions-Oberfläche.

Ein einzelner Verein, der klemmt, färbt den Lauf **nicht** rot – dafür gibt
es die Warn-Push. Lokal erzwingt `--fail-on-error` das andere Verhalten.

## Lokal ausführen

Für GitHub ist nichts davon nötig – das hier ist zum Ausprobieren und
Weiterbauen auf dem eigenen Rechner.

### 1. Abhängigkeiten installieren

```bash
python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements-dev.txt
```

Zwei Quellen (TSG Hoffenheim und RB Leipzig) laden ihre Stellen per
JavaScript nach und brauchen zusätzlich einen Browser:

```bash
./.venv/bin/python -m pip install -r requirements-playwright.txt && ./.venv/bin/python -m playwright install chromium
```

Ohne Playwright laufen alle übrigen 23 Quellen normal weiter – die beiden
JavaScript-Quellen melden dann einen Fehler und werden übersprungen. Der
Browser startet nur, wenn eine dieser Quellen ihn wirklich anfordert, und
lädt keine Bilder, Videos oder Schriften.

### 2. Topic in die Umgebung legen

Dasselbe Topic wie in der ntfy-App (siehe Einrichtung, Schritt 2):

```bash
export NTFY_TOPIC='dein-langes-geheimes-topic'
```

Ohne diese Variable läuft alles normal, es werden nur keine Pushes
verschickt.

### 3. Test-Push auslösen

```bash
NTFY_TOPIC='dein-topic' PYTHONPATH=src ./.venv/bin/python -m nlzwatch --test-push
```

Auf dem Handy muss eine Nachricht mit hoher Priorität ankommen
(„⚽ GLB-Stelle: Testverein"). Antippen öffnet einen Link.

### 4. Trockenlauf

Ruft die Seiten ab, stuft ein, sendet aber nichts und schreibt nichts:

```bash
PYTHONPATH=src ./.venv/bin/python -m nlzwatch --dry-run
```

Nur ein Verein:

```bash
PYTHONPATH=src ./.venv/bin/python -m nlzwatch --dry-run --club bayer04
```

### 5. Echter Lauf

```bash
NTFY_TOPIC='dein-topic' PYTHONPATH=src ./.venv/bin/python -m nlzwatch
```

Beim **ersten** Lauf einer Quelle werden alle vorhandenen Stellen nur als
Bestand gespeichert. Statt einer Push-Flut kommt eine einzige Startübersicht
(„X Sportstellen offen, davon Y im GLB").

## Web-App

Die App liegt in `docs/` und braucht keinen Build-Schritt: reines HTML, CSS
und JavaScript. Sie liest `docs/data/jobs.json`, das der Scraper bei jedem
Lauf aus `data/jobs.json` spiegelt.

**Lokal ansehen** (ein Server ist nötig, `file://` darf die JSON nicht laden):

```bash
cd /Users/jannikvoitel/Desktop/Arbeit/nlz-job-watcher/docs && python3 -m http.server 8787
```

Dann <http://localhost:8787> öffnen.

**Was die App kann**

- Reiter **GLB**, **Sport**, **Sonstige**, **Geschlossen** und **Vereine**,
  mit Anzahl je Bereich
- Karten mit Verein, Prioritäts-Badge, „NEU" für die letzten 7 Tage,
  Fundtag, Veröffentlichungsdatum, Ort, Vertragsart und Bewerbungsfrist
- Antippen klappt die vollständige Beschreibung auf, darunter die Buttons
  „Zur Originalanzeige" und, wo vorhanden, „Direkt bewerben"
- Unten an jeder Karte steht, **warum** die Stelle so eingestuft wurde
- Volltextsuche über Titel und Beschreibung, Filter nach Verein
- Reiter **Vereine**: letzter erfolgreicher Abruf, Zahl der offenen Stellen
  je Quelle, Initiativbewerbungs-Hinweis und -Link, Fehler und manuell
  beobachtete Quellen
- Hell und dunkel automatisch nach Systemeinstellung
- Installierbar auf dem Homescreen (Manifest + Service Worker); die zuletzt
  geladene Liste bleibt offline verfügbar

**Auf dem Homescreen**: Seite im Browser öffnen, auf iPhone über „Teilen →
Zum Home-Bildschirm", auf Android über das Browser-Menü „App installieren".

## Kommandozeile

| Option | Wirkung |
|--------|---------|
| `--dry-run` | alles ausführen, nichts senden, nichts schreiben |
| `--club KURZNAME` | nur diesen Verein (mehrfach möglich), z. B. `--club werder` |
| `--reclassify` | alle gespeicherten Stellen neu einstufen, nach Änderungen an `filters.yaml` |
| `--skip-details` | keine Detailseiten laden, schneller Test der Listen |
| `--test-push` | eine Testnachricht mit hoher Priorität senden |
| `--report` | aktuellen Stand als Markdown ausgeben, ohne etwas abzurufen |
| `--fail-on-error` | mit Fehlercode enden, wenn eine Quelle klemmt |
| `-v` | ausführlichere Logausgaben |

## Einstufung anpassen

Alles steckt in `filters.yaml`, nicht im Code:

- **Priorität A (GLB):** Schlagwörter und Altersklassen `u8`–`u11`.
- **Priorität B (Sport):** alle übrigen Sportstellen.
- **Priorität C:** ohne Sportbezug, wird gespeichert aber nicht gepusht.
- `ignore_titles`: Dauer-Einträge der Portale wie „Initiativbewerbung", die
  keine Stelle sind.

Für Eigennamen, die nur ein Verein benutzt, gibt es zusätzlich
vereinsspezifische Schlagwörter direkt in `clubs.yaml`:

```yaml
    keywords:
      priority_b:
        - fohlenstall      # Gladbachs NLZ-Internat
      priority_c:
        - fohlensportsbar
```

Sie werden vor den globalen Listen geprüft. Ohne sie wäre Gladbachs
Betreuungsstelle im NLZ-Internat nur über das Sicherheitsnetz in B gelandet.

Umlaute bitte normal schreiben (`förderkader`, `übungsleiter`). Groß- und
Kleinschreibung ist egal, `Fussballschule` und `Fußballschule` treffen beide.

Die Prüfung läuft von oben nach unten: Vereinsschlagwörter, dann A, dann B,
dann C. Greift nichts, wird
die Stelle **als B** eingestuft – unsichere Fälle landen bewusst zu hoch, damit
nichts durchrutscht. Welches Schlagwort getroffen hat, steht in `jobs.json`
unter `priority_reason`.

Nach einer Änderung:

```bash
PYTHONPATH=src ./.venv/bin/python -m nlzwatch --reclassify --dry-run
```

## Verein oder Quelle hinzufügen

Ein neuer Verein braucht in der Regel nur einen Eintrag in `clubs.yaml`:

```yaml
  - name: Neuer Verein
    short: neu
    sources:
      - id: neu-softgarden          # stabil lassen, steckt in den Job-IDs
        label: Karriere-Board
        adapter: softgarden         # vorhandenen Adapter wiederverwenden
        url: https://neu.softgarden.io/de/vacancies
        enabled: true
    speculative:
      allowed: unknown
      url: https://www.neu.de/jobs
```

Nur wenn der Verein ein Portal nutzt, für das es noch keinen Adapter gibt, kommt
ein kleiner Adapter in `src/nlzwatch/adapters/` dazu und wird in
`adapters/__init__.py` registriert.

### Vereinsseiten ohne Portal

Für Seiten ohne Bewerberportal gibt es `generic_html`. Der Adapter wird
vollständig über CSS-Selektoren gesteuert, inklusive `:has()` und
Geschwister-Selektoren:

```yaml
        adapter: generic_html
        params:
          item: "li.job"               # Container je Stelle (Pflicht)
          title: "h3"                  # fehlt er: Containertext ohne Linktext
          link: "a.detail"             # Standard: erstes a[href] im Container
          description: ".text"         # Volltext schon auf der Listenseite
          meta: ".meta-item"           # mehrere Werte, werden zugeordnet
          group_title: "h2"            # Überschrift des Abschnitts
          group_as: employment_type    # auto | employment_type | department
          detail_is_pdf: true          # Ausschreibung ist ein PDF
```

Zwei Dinge nimmt der Adapter von selbst in die Hand: Ist `description`
gesetzt, werden Links **innerhalb** der Beschreibung nicht als Stellenlink
verwendet. Und wenn mehrere Stellen eine URL teilen, bildet er die ID aus
Quelle und Titel statt aus der URL.

## Tests

```bash
./.venv/bin/python -m pytest
```

Die Adaptertests laufen gegen gespeichertes HTML in `tests/fixtures/` und
brauchen kein Netz. Die Einstufung wird mit mindestens zehn echten deutschen
Stellentiteln je Priorität geprüft.

## Fehlersuche

| Symptom | Ursache und Abhilfe |
|---------|---------------------|
| „NTFY_TOPIC ist nicht gesetzt" | `export NTFY_TOPIC='…'` vor dem Aufruf |
| Push kommt nicht an | Topic in App und Umgebung vergleichen, Groß-/Kleinschreibung beachten |
| Warnung „Scraper für X prüfen" | Die Quelle liefert plötzlich 0 Stellen oder ist nicht erreichbar. `--club X -v` zeigt den Grund. Höchstens eine Warnung pro Verein und Tag. |
| Warnung „liefert nur noch N statt M Stellen" | Teilausfall, etwa ein ausgefallener XML-Feed mit unvollständigem HTML-Rückfall. Schwelle in `filters.yaml` unter `monitoring.warn_on_drop_ratio`. |
| Quelle wird „übersprungen" | `enabled: false` in `clubs.yaml`, der Adapter ist noch nicht gebaut |
| Eine Stelle ist falsch eingestuft | Schlagwort in `filters.yaml` ergänzen, dann `--reclassify` |
| `robots.txt verbietet den Abruf` | Absicht. Die Quelle bleibt gesperrt, bitte manuell beobachten. |
| „Diese Ausschreibung liegt nur als Bild-PDF vor" | Der VfB veröffentlicht einen Teil seiner Ausschreibungen als Grafik ohne Textschicht. Titel, Einstufung und Link stimmen, nur der Volltext fehlt. Nicht reparierbar ohne Texterkennung. |

## Rücksicht beim Abrufen

- `robots.txt` wird vor jedem Abruf geprüft und beachtet.
- 1,5 Sekunden Pause pro Host, Timeouts, Wiederholungen mit wachsendem Abstand.
- Detailseiten werden nur geholt, wenn noch kein Text gespeichert ist.
- Klarer User-Agent. Die Kontaktangabe darin lässt sich über die
  Umgebungsvariable `WATCHER_CONTACT` setzen.
