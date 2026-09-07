# Kulturbytes Facebook Publisher

Teil des gemeinsamen [uv-Workspaces](../README.md). Geteilte Funktionen liegen
in `common/src/kulturbytes_common`, Facebook-Code in `src/kulturbytes_facebook/cli.py`.
Alle folgenden `uv`-Aufrufe erfolgen im Ordner `facebook/`.
Die Veröffentlichung wird mit `--publish` und einer Bestätigung pro Termin aktiviert;
`DRY_RUN` und `MAX_POSTS_PER_RUN` werden nicht als Umgebungsvariablen ausgewertet.

Ein kleines Python-Tool, das veröffentlichte Veranstaltungen aus der Kulturbytes-API lädt und automatisch auf der Facebook-Seite von Kulturbytes veröffentlicht.

Das Projekt verwendet:

- Python
- `httpx`
- `uv`
- SQLite zur Deduplizierung
- Meta Graph API
- Eventbilder direkt aus der Kulturbytes-API

## Datenquelle

Die Veranstaltungen werden aus der Kulturbytes-API geladen:

```text
https://api.kulturbytes.de/api/events
```

Die öffentliche Veranstaltungsseite wird aus `uuid` und `date_slug` aufgebaut:

```text
https://kulturbytes.de/de/veranstaltung/{uuid}/{date_slug}
```

Beispiel:

```text
https://kulturbytes.de/de/veranstaltung/019f4608-8996-72e3-9d34-0544db82c659/202609071830
```

## Funktionsweise

Das Script:

1. lädt alle Kulturbytes-Termine,
2. filtert auf veröffentlichte Veranstaltungen,
3. ignoriert vergangene Termine,
4. sortiert die Termine chronologisch,
5. prüft anhand der `date_uuid`, ob ein Termin bereits veröffentlicht wurde,
6. lädt das Eventbild über `image_path`,
7. veröffentlicht einen Facebook-Fotopost,
8. fällt bei fehlendem Bild auf einen Textpost zurück,
9. speichert die Facebook-Post-ID in einer lokalen SQLite-Datenbank.

## Voraussetzungen

Benötigt werden:

- Python 3.12 oder neuer
- `uv`
- Zugriff auf die Facebook-Seite von Kulturbytes
- eine Meta Developer App
- ein Facebook Page Access Token mit den benötigten Berechtigungen

Für das Posten auf einer Facebook-Seite werden insbesondere folgende Berechtigungen benötigt:

```text
pages_show_list
pages_read_engagement
pages_manage_posts
```

## Installation

Repository klonen:

```bash
git clone <REPOSITORY-URL>
cd kulturbytes-facebook/facebook
```

Abhängigkeiten installieren:

```bash
uv sync
```

Das Projekt verwendet kein manuell verwaltetes Virtual Environment. `uv` übernimmt die Python-Umgebung und das Dependency-Management.

## Konfiguration

Die Anwendung wird über Umgebungsvariablen konfiguriert.

Beispiel:

```bash
export FACEBOOK_PAGE_ID="1173614782497494"
export FACEBOOK_PAGE_ACCESS_TOKEN="DEIN_PAGE_ACCESS_TOKEN"
export FACEBOOK_GRAPH_API_VERSION="v26.0"

# Vorschau mit --dry-run, Auswahlgröße mit --limit steuern.
```

Optional kann der Pfad zur SQLite-Datenbank geändert werden:

```bash
export DATABASE_PATH="facebook_posts.sqlite3"
```

## Umgebungsvariablen

| Variable | Beschreibung | Standard |
|---|---|---|
| `FACEBOOK_PAGE_ID` | Numerische ID der Facebook-Seite | erforderlich |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Facebook Page Access Token | erforderlich |
| `FACEBOOK_GRAPH_API_VERSION` | Meta Graph API Version | `v26.0` |
| `DATABASE_PATH` | Pfad zur SQLite-Datenbank | `facebook_posts.sqlite3` |

## Beispiel für eine Environment-Datei

Für den produktiven Betrieb kann eine Datei wie

```text
/etc/kulturbytes/facebook.env
```

verwendet werden.

Inhalt:

```env
FACEBOOK_PAGE_ID=1173614782497494
FACEBOOK_PAGE_ACCESS_TOKEN=DEIN_PAGE_ACCESS_TOKEN
FACEBOOK_GRAPH_API_VERSION=v26.0

DATABASE_PATH=facebook_posts.sqlite3
```

Die Datei sollte geschützt werden:

```bash
sudo chmod 600 /etc/kulturbytes/facebook.env
sudo chown root:root /etc/kulturbytes/facebook.env
```

## Sicherheit

Der Facebook Access Token darf niemals ins Git-Repository committed werden.

Empfohlene `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
*.pyo

# uv / virtual environments
.venv/

# Local environment / secrets
.env
.env.*
!.env.example

# SQLite
*.sqlite
*.sqlite3
*.db

# IDE
.vscode/
.idea/

# OS
.DS_Store
```

## Dry Run

Vor dem ersten echten Posting sollte das Script immer im Dry-Run-Modus gestartet werden.

```bash
uv run main.py --dry-run
```

Das Script zeigt dann beispielsweise:

```text
488 Kulturbytes-Termine gefunden

================================================================================
📅 Arne Semsrott: Gegenmacht

Universitäten gegen die Gefahr rechter Machtübernahme verteidigen

🗓 07.09.2026 · 18:30 Uhr
📍 Tallinn
Mitscherlich-Nielsen Straße 1, 24943 Flensburg

Autor Arne Semsrott liest aus seinem neuen Buch "Gegenmacht:
Die Zivilgesellschaft schlägt zurück".

...

👉 Mehr Informationen:
https://kulturbytes.de/de/veranstaltung/019f4608-8996-72e3-9d34-0544db82c659/202609071830

🖼 https://api.kulturbytes.de/api/image/019f4641-c789-783d-a426-50ba86c061b7
================================================================================

DRY RUN: kein Facebook-Post veröffentlicht.
```

## Veröffentlichung aktivieren

Wenn die Vorschau korrekt aussieht:

```bash
uv run main.py --publish --limit 1
```

Standardmäßig sollte maximal ein neuer Termin pro Lauf veröffentlicht werden.

Das verhindert, dass bei einer neuen Installation plötzlich eine große Anzahl bereits vorhandener Veranstaltungen gleichzeitig auf Facebook veröffentlicht wird.

## Deduplizierung

Jeder konkrete Veranstaltungstermin besitzt eine eindeutige:

```text
date_uuid
```

Diese wird als Primärschlüssel in der SQLite-Datenbank gespeichert.

Dadurch wird derselbe Termin nicht mehrfach veröffentlicht.

Beispiel:

```text
uuid:
019f4608-8996-72e3-9d34-0544db82c659

date_uuid:
019f5b53-5a9c-76e8-ad1c-fdf261c50090

date_slug:
202609071830
```

Dabei gilt:

```text
uuid
```

identifiziert die Veranstaltung selbst.

```text
date_uuid
```

identifiziert den konkreten Termin intern.

```text
date_slug
```

wird zusammen mit der `uuid` für den öffentlichen Frontend-Link verwendet.

Der resultierende Link lautet:

```text
https://kulturbytes.de/de/veranstaltung/019f4608-8996-72e3-9d34-0544db82c659/202609071830
```

## Eventbild

Wenn ein Event ein `image_path` besitzt, wird dieses Bild vor dem Facebook-Posting direkt über die Kulturbytes-API geladen.

Beispiel:

```text
https://api.kulturbytes.de/api/image/019f4641-c789-783d-a426-50ba86c061b7
```

Das Bild wird anschließend über den Facebook-Photos-Endpoint veröffentlicht.

Wenn kein Eventbild vorhanden ist, fällt das Script auf einen Textpost zurück.

## Inhalt eines Facebook-Posts

Ein Facebook-Post enthält unter anderem:

- Titel
- Untertitel
- Datum
- Uhrzeit
- Veranstaltungsort
- Adresse
- Beschreibung
- Veranstalter
- Eintrittsinformationen
- Link zur Veranstaltung auf Kulturbytes
- Hashtags

Beispiel:

```text
📅 Arne Semsrott: Gegenmacht

Universitäten gegen die Gefahr rechter Machtübernahme verteidigen

🗓 07.09.2026 · 18:30 Uhr
📍 Tallinn
Mitscherlich-Nielsen Straße 1, 24943 Flensburg

Autor Arne Semsrott liest aus seinem neuen Buch "Gegenmacht:
Die Zivilgesellschaft schlägt zurück".

Veranstalter: Carl-von-Ossietzky-Buchhandlung

Eintritt frei

👉 Mehr Informationen:
https://kulturbytes.de/de/veranstaltung/019f4608-8996-72e3-9d34-0544db82c659/202609071830

#Kulturbytes #Flensburg #Kultur
```

## Facebook API

Für Fotoposts wird folgender Endpoint verwendet:

```text
POST /{PAGE_ID}/photos
```

Für Textposts ohne Bild:

```text
POST /{PAGE_ID}/feed
```

Die Graph-API-Version kann über folgende Variable konfiguriert werden:

```bash
export FACEBOOK_GRAPH_API_VERSION="v26.0"
```

## Facebook Events

Das Projekt erstellt aktuell keine eigenständigen Facebook-Veranstaltungen.

Die aktuelle Meta Graph API stellt das Erstellen echter Page Events nicht als allgemein verfügbaren Write-Flow für jede App bereit.

Das Projekt veröffentlicht deshalb Facebook-Posts mit:

- Eventbild
- Veranstaltungsdaten
- Link zurück zu Kulturbytes

Kulturbytes bleibt damit die zentrale Datenquelle für die eigentliche Veranstaltung.

## SQLite-Datenbank

Standardmäßig verwendet das Script:

```text
facebook_posts.sqlite3
```

Darin werden unter anderem folgende Werte gespeichert:

```text
date_uuid
event_uuid
facebook_post_id
title
start_date
start_time
published_at
```

Die Datenbank ist Laufzeitstatus und gehört nicht ins Git-Repository.

## Fehlerdiagnose

Facebook-API-Fehler werden inklusive HTTP-Statuscode und Meta-API-Antwort ausgegeben.

Beispiel:

```text
Facebook API error:
Status: 403
```

Typische Ursachen sind:

- fehlende `pages_manage_posts`-Berechtigung
- fehlende `pages_read_engagement`-Berechtigung
- falscher Token-Typ
- abgelaufener Access Token
- unzureichende Seitenrechte
- falsche Page-ID
- falsche Graph-API-Version

## Meta Graph API Explorer

Zum Testen der Berechtigungen kann der Meta Graph API Explorer verwendet werden.

Mit einem User Access Token kann beispielsweise geprüft werden:

```text
GET /me/permissions
```

Erwartet werden unter anderem:

```json
{
  "permission": "pages_show_list",
  "status": "granted"
}
```

```json
{
  "permission": "pages_read_engagement",
  "status": "granted"
}
```

```json
{
  "permission": "pages_manage_posts",
  "status": "granted"
}
```

Die verfügbaren Seiten können geprüft werden mit:

```text
GET /me/accounts
```

Dort sollte die Kulturbytes-Seite enthalten sein.

## Automatisierter Betrieb mit systemd

Für den produktiven Betrieb kann das Script über einen systemd-Service und einen systemd-Timer gestartet werden.

### Service

Beispiel:

```ini
[Unit]
Description=Kulturbytes Facebook Publisher
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot

User=oklab
Group=oklab

WorkingDirectory=/opt/kulturbytes-facebook/facebook

EnvironmentFile=/etc/kulturbytes/facebook.env

ExecStart=/usr/local/bin/uv run main.py

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Je nach Installation kann `uv` unter einem anderen Pfad liegen.

Den Pfad erhältst du mit:

```bash
which uv
```

### Timer

Beispiel:

```ini
[Unit]
Description=Run Kulturbytes Facebook Publisher hourly

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

Service und Timer neu laden:

```bash
sudo systemctl daemon-reload
```

Timer aktivieren:

```bash
sudo systemctl enable --now kulturbytes-facebook.timer
```

Status prüfen:

```bash
systemctl status kulturbytes-facebook.timer
```

Timer anzeigen:

```bash
systemctl list-timers kulturbytes-facebook.timer
```

Logs anzeigen:

```bash
journalctl -u kulturbytes-facebook.service
```

Logs live verfolgen:

```bash
journalctl -fu kulturbytes-facebook.service
```

## Entwicklung

Abhängigkeiten synchronisieren:

```bash
uv sync
```

Script starten:

```bash
uv run main.py
```

Python-Version prüfen:

```bash
uv run python --version
```

Projektstatus prüfen:

```bash
git status
```

## Projektstruktur

Die Paketstruktur und das gemeinsame Dependency-Management sind in der
[Workspace-Anleitung](../README.md) beschrieben.

## Geplante Erweiterungen

Mögliche zukünftige Erweiterungen:

- Bluesky
- Instagram
- konfigurierbare Veröffentlichungszeiträume
- Event-Reminder
- Retry-Mechanismus
- strukturiertes Logging
- Post-Updates bei geänderten Events
- Löschen von Posts bei abgesagten Veranstaltungen
- PostgreSQL statt SQLite
- zentrale Social-Publishing-Queue
- systemd-Deployment
- Tests mit `pytest`
- automatische Healthchecks

## Kulturbytes

Kulturbytes ist ein Veranstaltungskalender für Kulturveranstaltungen.

Website:

```text
https://kulturbytes.de
```

Event-API:

```text
https://api.kulturbytes.de/api/events
```

Bild-API:

```text
https://api.kulturbytes.de/api/image/{image_uuid}
```

Facebook:

```text
https://www.facebook.com/kulturbytes
```

## Lizenz
AGPL-3.0
