# Untersuchungsbericht: Karriereseiten der 17 NLZ-Vereine

Stand: 4. November 2026. Alle Angaben selbst geprüft (robots.txt, HTTP-Status, Seiteninhalt).

## 1. Kurzfassung

- **16 von 17 Vereinen sind zuverlässig scrapebar.** Ein Verein (FC Bayern) blockiert automatisierte Zugriffe aktiv — siehe Abschnitt 5.
- **Kein einziger Verein verbietet das Scraping per robots.txt.** Keine der geprüften Karriereseiten ist dort gesperrt.
- **Fünf Adapter genügen für 15 Vereine**, weil sich die Portale wiederholen:
  - **HRworks** → Mainz 05, SC Freiburg, Gladbach, Eintracht e.V. (4 Vereine)
  - **softgarden** → BVB, Werder, Schalke (3 Vereine)
  - **Personio** → 1. FC Köln, Hertha BSC, HSV (3 Vereine, 4 Boards)
  - **generic_html** → VfB, Bayer 04, Paderborn, Wolfsburg, HSV e.V., Eintracht AG, Gladbach-Minijobs
  - **SuccessFactors** → FC Bayern, TSG Hoffenheim
- **Aktuell 6 Stellen im Grundlagenbereich (Prio A)** über alle Vereine — siehe Abschnitt 4.
  *Nachtrag 04.11.2026: Diese Zahl galt unter der ersten, zu weiten Auslegung
  des Grundlagenbereichs. Maßgeblich ist jetzt: NLZ-Mannschaften U9 bis U11.
  Damit ist keine dieser sechs Stellen mehr Prio A — siehe Abschnitt 4.*
- *Nachtrag 04.11.2026: Die TSG Hoffenheim antwortet den GitHub-Rechnern mit
  „403 Forbidden“ und wird wie der FC Bayern als manuelle Quelle geführt. Vom
  eigenen Rechner aus ist sie normal abrufbar — siehe README.*
- Aktuell insgesamt rund **190 offene Stellen**, davon ca. **40 im Sportbereich**.

## 2. Haupttabelle

| # | Verein | Offizielle Quelle(n) | Technik | robots.txt erlaubt | Offene Stellen (ges.) | davon Sport | Initiativbewerbung | Geplanter Adapter | Schwierigkeit |
|---|--------|----------------------|---------|--------------------|----------------------|-------------|--------------------|-------------------|---------------|
| 1 | Borussia Dortmund | `karriere.bvb.de` → `bvb.softgarden.io/de/vacancies` | softgarden, serverseitig gerendert | ja (nur `/api/`, `/rest/`, `/widgets/` gesperrt) | 23 | 4 | kein Hinweis; Job-Abo vorhanden | `softgarden` | leicht |
| 2 | FSV Mainz 05 | `mainz05.de/jobs` → `jobapplication.hrworks.de/de?companyId=ba8e529b` | HRworks, serverseitig | ja (keine Sperren) | 12 | 1 | **nein**, ausdrücklich abgelehnt | `hrworks` | leicht |
| 3 | FC Bayern München | `fcbayern.com/de/jobs` → `careers.fcbayern.com` | SAP SuccessFactors | robots.txt nicht abrufbar (403) | 32 | 5–7 | ja, Talent-Pool-Profil | `playwright` + `successfactors` | **schwer** (siehe 5.1) |
| 4 | TSG Hoffenheim | `tsg-hoffenheim.de/tsg/karriere/stellenangebote` | JS-gerendert, Bewerbung über SuccessFactors | ja (Karrierebereich frei) | **0** | 0 | möglich, aber "geringe Aussicht"; Ansprechpartner Nachwuchs + Fußballschule genannt | `playwright` | mittel (siehe 5.2) |
| 5 | VfB Stuttgart | `vfb.de/de/1893/aktuell/jobs/jobs/` (+ `/praktikum/`, `/aushilfen-und-werkstudenten/`) | statisches HTML, **Beschreibungen als PDF** | ja (`/fileadmin/` gesperrt, PDFs liegen woanders) | 6 (+ Unterseiten) | 3 | kein Hinweis | `generic_html` + PDF-Parser | mittel (siehe 5.3) |
| 6 | SC Freiburg | `scfreiburg.com/verein/jobs/` → `jobs.scfreiburg.com/de` | HRworks, serverseitig | ja (keine robots.txt am Portal) | 12 | 0 | kein Hinweis | `hrworks` | leicht |
| 7 | Bayer 04 Leverkusen | `bayer04.de/de-de/page/stellenangebote` | statisches HTML | ja (`Allow: /`) | 11 | 3 (**1× A**) | kein Hinweis | `generic_html` | leicht |
| 8 | Borussia Mönchengladbach | `job.borussia.de/de` (HRworks) + `minijobs.borussia.de` | HRworks + statische Minijob-Seite | ja (keine robots.txt) | 8 + 5 Minijobs | 3 | **nein**, ausdrücklich abgelehnt | `hrworks` + `generic_html` | leicht |
| 9 | 1. FC Köln | `fc.de/jobs` → `effzeh.jobs.personio.de` | Personio, **XML-Feed mit Volltext** | ja (`Allow: /`) | 8 | 2 (**1× A**) | **nein**, ausdrücklich abgelehnt | `personio` | leicht |
| 10 | FC Schalke 04 | `schalke04.de/verein/karriere/jobangebote/` → `schalke04.softgarden.io/de/vacancies` | softgarden-Widget; Board serverseitig | ja (keine robots.txt auf Hauptdomain) | 18 (+1 statisch) | 2 | kein Hinweis | `softgarden` + `generic_html` | leicht |
| 11 | VfL Wolfsburg | `vfl-wolfsburg.de/der-vfl/jobs` + `/direkteinstieg`, `/aushilfsjobs`, `/praktikum` | statisches HTML (TYPO3), 3 Unterseiten | ja (keine robots.txt) | 5 | 1 | **nein**, ausdrücklich abgelehnt | `generic_html` (3 URLs) | leicht |
| 12 | SV Werder Bremen | `karriere.werder.de` → `werder.softgarden.io/de/vacancies` | softgarden, **mit Veröffentlichungsdatum** | ja (`Allow: /`) | 18 | 3 (**1× A**) | **nein**, ausdrücklich abgelehnt | `softgarden` | leicht |
| 13 | Hamburger SV | `hsv.de/karriere` → `hsv-fussball-ag.jobs.personio.de` (Festanstellung), `hsv-fussball-ag-ap.jobs.personio.de` (Aushilfen/Praktika), `hsv.de/jobs-beim-e-v` (e.V.), HSV-Stiftung als PDF | Personio (2 Boards) + statisches HTML | ja (`Allow: /`, nur `/api/` gesperrt) | 12 + 9 + 7 | ca. 8 | **nein**, ausdrücklich abgelehnt | `personio` (2×) + `generic_html` | leicht–mittel |
| 14 | Hertha BSC | `herthabsc.com/de/club/jobs` → `herthabsc.jobs.personio.com` | Personio (XML-Feed **leer**, HTML gefüllt) | ja (`Allow: /`) | 3 | 1 (**1× A**) | kein Hinweis | `personio` (HTML-Modus) | leicht |
| 15 | RB Leipzig | `rbleipzig.com/de/club-teamwork-karriere` | JS-gerendert; Detailseiten bei SmartRecruiters (nicht-indexiert) | ja (`Allow: /`) | 5 | 1 | kein Hinweis | `playwright` | mittel (siehe 5.4) |
| 16 | Eintracht Frankfurt | `klub.eintracht.de/jobs/ag/` (AG) + `jobapplication.hrworks.de/de?companyId=aq915e9c` (e.V.) | statisches HTML + HRworks | ja (Jobbereich frei) | 5 + 3 | 3 (andere Sportarten) | **nein**, ausdrücklich abgelehnt | `generic_html` + `hrworks` | leicht |
| 17 | SC Paderborn 07 | `scp07.de/SCP07/Die-KGaA/Jobs/` | statisches HTML, Stellen inkl. Volltext auf einer Seite | ja (robots.txt ohne Regeln) | 8 | 3 (**1× A**) | **nein**, ausdrücklich abgelehnt | `generic_html` | leicht |

## 3. Adapter-Übersicht

| Adapter | Vereine | Besonderheit |
|---------|---------|--------------|
| `hrworks` | Mainz 05, SC Freiburg, Gladbach, Eintracht e.V. | Stabile Detail-IDs `?companyId=<x>&id=<6-hex>`; Liste und Detailtext serverseitig |
| `softgarden` | BVB, Werder, Schalke | Board unter `<verein>.softgarden.io/de/vacancies`, Detail `../job/<id>/<slug>`; Werder und Schalke liefern Datum. **`/api/`, `/rest/`, `/widgets/` per robots.txt gesperrt → nur HTML nutzen** |
| `personio` | Köln, Hertha, HSV (2 Boards) | Köln + HSV-AG liefern einen **XML-Feed mit vollständiger Beschreibung** (`/xml`) — ideal. Hertha und HSV-Aushilfen haben leeren Feed → dort HTML parsen |
| `generic_html` | VfB, Bayer 04, Paderborn, Wolfsburg, HSV e.V., Eintracht AG, Gladbach-Minijobs | Selektoren je Quelle in `clubs.yaml` |
| `playwright` | FC Bayern, TSG Hoffenheim, RB Leipzig | Nur diese drei brauchen einen echten Browser |

Damit ist das Ziel erfüllt, dass ein neuer Verein in der Regel nur einen Eintrag in `clubs.yaml` braucht.

## 4. Prio-A-Treffer (Grundlagenbereich), Stand heute

> **Nachtrag 04.11.2026.** Die Tabelle zeigt den Stand der ersten Auslegung,
> die den Grundlagenbereich zu weit fasste. Maßgeblich ist jetzt: GLB sind
> **NLZ-Mannschaften der Altersklassen U9 bis U11**. Fußballschulen,
> Feriencamps, Kinderfußball und Partnervereine sind Breitenfußball und
> zählen als Sport (B) — sie werden weiter gemeldet, nur nicht als GLB-Fund.
> Damit ist **keine** der sechs Stellen unten Prio A, und aktuell ist in
> keinem der 17 NLZ eine U9-U11-Mannschaftsstelle ausgeschrieben. Die Regel
> steht in `filters.yaml` unter `priority_a` und ist im README erklärt.

| Verein | Stelle | Einordnung (erste, zu weite Auslegung) |
|--------|--------|------------|
| Bayer 04 Leverkusen | **Trainer Future Kids U8-U10 (m/w/d)** – geringfügige Beschäftigung | A, Altersklasse explizit |
| 1. FC Köln | **MINI JOB: Kinderfußball-Trainer (U7-U11) im Partnerverein des 1. FC Köln (m/w/d)** | A, Altersklasse explizit |
| SV Werder Bremen | **Honorartrainer\*in (m/w/d) Werder Fußballschule** | A, Schlagwort Fußballschule |
| Hertha BSC | **Trainer\*in (m/w/d) Fußballschule**, Teilzeit, befristet | A, Schlagwort Fußballschule |
| SC Paderborn 07 | **TRAINER/IN FÜR DIE SCP07 FUSSBALLSCHULE (M/W/D)** | A, Schlagwort Fußballschule |
| FC Bayern München | **Trainer (m\|w\|d) – FC Bayern Campus Training** (+ Praktikant Camptrainer) | A zu prüfen, Altersklassen erst in der Beschreibung |

Weitere klare Sport-B-Stellen gibt es u. a. bei HSV (Sportpsychologie NLZ, Videoanalyse, Co-Trainerinnen Nachwuchs weiblich), BVB (Teammanager Mädchen U16, Praktikant Fußballakademie), Wolfsburg (Torwarttrainer U12/U13), Gladbach (Physiotherapeut Frauen- und Juniorinnenfußball), Schalke und RB Leipzig (je Physiotherapie im Frauen-/Nachwuchsbereich), VfB (2× Physiotherapeut, 1× Sporttherapeut).

## 5. Problemfälle — hier brauche ich deine Entscheidung

### 5.1 FC Bayern München: aktive Bot-Sperre
`careers.fcbayern.com` liefert jedem automatisierten Client **HTTP 403**, auch die `robots.txt` selbst ist nicht abrufbar. Im echten Browser lädt die Seite normal (32 Stellen, SuccessFactors). Es gibt also **kein robots.txt-Verbot**, aber eine technische Schutzschicht, die automatisierte Abrufe gezielt abweist.

Drei Optionen:
1. **Playwright mit echtem Browser** — funktioniert technisch, umgeht aber bewusst die Sperre. Würde ich nicht ohne deine ausdrückliche Zustimmung bauen.
2. **Nicht scrapen, stattdessen Bayerns eigenen Job-Alert nutzen.** SuccessFactors hat eine eingebaute Benachrichtigungsfunktion ("Benachrichtigung erstellen") plus Talent-Pool-Profil. Du bekommst die Mails direkt vom Verein, das Tool listet Bayern dann nur als "manuell beobachtet".
3. **Kompromiss:** Im Tool als `manual`-Quelle führen, mit Link und dem Hinweis in der Web-App.

**Meine Empfehlung: Option 2.** Du verlierst nichts an Information und das Tool bleibt sauber.

### 5.2 TSG Hoffenheim: leere Seite ohne Textmuster
Aktuell **null offene Stellen**. Die Seite schreibt das aber **nicht hin** — sie zeigt einfach nur Ansprechpartner. Damit kann der Scraper "legitim leer" nicht von "kaputt" unterscheiden, so wie du es in Punkt 6 der Fehlerüberwachung vorgesehen hattest. Vorschlag: Für Hoffenheim das Kriterium umdrehen — Warnung nur, wenn die Seite nicht erreichbar ist oder der Ansprechpartner-Block fehlt (der ist der Marker dafür, dass die Seite korrekt geladen wurde).

Nebenbei: Die genannten Ansprechpartner sind für dich relevant — **Matilde Florentino und Noelle Herbst (Nachwuchsbereich), Robin Wenzel (Fußballschule)**. Initiativbewerbungen haben laut FAQ "geringe Aussicht", sind aber nicht ausgeschlossen.

### 5.3 VfB Stuttgart: Beschreibungen nur als PDF
Die Übersichtsseite nennt Titel und Bereich, die vollständige Beschreibung steckt je Stelle in einem PDF (`/?proxy=redaktion/downloads/verein/jobs/2026/...pdf`). Für "vollständige Beschreibung als bereinigter Text" brauche ich dort einen PDF-Parser (`pdfminer.six` oder `pypdf`). Ist in Ordnung, nur eine zusätzliche Abhängigkeit. Praktikums- und Aushilfenstellen liegen auf zwei weiteren Unterseiten, die ich als eigene Quellen aufnehme.

### 5.4 RB Leipzig: nicht-indexierte SmartRecruiters-Anzeigen
Die Stellen liegen bei `jobs.smartrecruiters.com/ni/RedBull/...`. Das `/ni/` steht für "not indexed": Die offene SmartRecruiters-API (`api.smartrecruiters.com/v1/companies/RedBull/postings`) listet sie **nicht** — ich habe es geprüft, für Leipzig kommt dort nur eine Red-Bull-Marketingstelle zurück, nicht die Vereinsstellen. Also: Vereinsseite per Playwright rendern. Funktioniert, ist aber die aufwendigere Variante. `rbleipzig.com` erlaubt alles per robots.txt.

### 5.5 Kleinere Hinweise
- **werder.de** antwortet auf schnelle Abrufe mit **HTTP 429** (Rate Limit). `karriere.werder.de` und das softgarden-Board sind unproblematisch — ich nutze nur diese. Pausen zwischen Requests sind hier Pflicht.
- **Hertha und HSV-Aushilfen**: Personio-XML-Feed ist leer, obwohl die HTML-Seite Stellen zeigt. Der Adapter braucht deshalb beide Modi mit automatischem Rückfall auf HTML.
- **Drittanbieter bewusst ausgeschlossen**: Bayer 04 (SPORTFIVE VIP-Host, Aramark-Gastro), RB Leipzig (Cuisinevent, Löwensicherheit, Velvet), VfB (Aramark, Clubrestaurant), Gladbach (Partner-Jobportal), HSV (jobs-im-stadion.de). Das sind keine Vereinsstellen.
- **BVB** betreibt zusätzlich thematische Landingpages (`nebenjobs-bvb`, `expertinnen-bvb`, `ausbildung-bvb`, `leben-bvb` auf `career.softgarden.de`). Die zeigen Teilmengen desselben Boards — eine Quelle genügt.
- **Initiativbewerbung**: 9 Vereine lehnen sie ausdrücklich ab (Mainz, Köln, Gladbach, Wolfsburg, Werder, HSV, Eintracht, Paderborn, dazu Hoffenheim mit Einschränkung). Das wird so in `clubs.yaml` und der Web-App hinterlegt — ersparst dir sinnlose Bewerbungen.

## 6. Technischer Hinweis zur Umgebung

Auf diesem Mac läuft als System-Python nur **3.9.6**. Dein Zielstand ist 3.12. Für GitHub Actions ist das irrelevant (dort wird 3.12 gesetzt), für lokale Tests brauche ich 3.12 per Homebrew oder pyenv. Sag mir, ob ich das einrichten soll oder ob du lokal mit 3.9 testen willst — der Code bleibt in beiden Fällen 3.12-kompatibel.

Außerdem ist `/Users/jannikvoitel/Desktop/Arbeit/nlz-job-watcher` noch **kein Git-Repository**. Das lege ich im nächsten Schritt mit an.
