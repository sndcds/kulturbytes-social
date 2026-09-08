# Kulturbytes Facebook Publisher

Teile Kulturbytes-Veranstaltungen auf deiner Facebook-Seite: Du wählst Termine
im Terminal aus, prüfst die Vorschau und bestätigst die Veröffentlichung.
Beim normalen Start bleibt es bei einer Vorschau.

[Projektübersicht](../README.md) · [Facebook](../facebook/README.md) · [Mastodon](../mastodon/README.md)

## Voraussetzungen

Du brauchst Python 3.12 oder neuer, `uv` und eine Internetverbindung.
Zum Veröffentlichen benötigst du zusätzlich
eine Facebook-Seiten-ID und einen Page Access Token, der Beiträge auf dieser Seite veröffentlichen darf.
Behalte den gesamten Repository-Ordner: Der Publisher nutzt das gemeinsame
Paket in `common/`.

## Schnellstart

Öffne ein Terminal im Repository-Hauptordner. Installiere die Abhängigkeiten,
wechsle zum Publisher und starte die Vorschau ohne Zugangsdaten:

```bash
uv sync --all-packages
cd facebook
uv run main.py --dry-run --limit 10
```

Das Programm zeigt bis zu zehn Termine. Gib beispielsweise `1` oder `1,3-5`
ein und drücke Enter, um die Vorschau zu sehen. `all` wählt alle angezeigten
Termine; eine leere Eingabe beendet die Auswahl. Es wird nichts veröffentlicht.

Alle weiteren Startbefehle auf dieser Seite führst du im Ordner `facebook/` aus.

## Konfiguration

Die Einstellungen werden aus den Umgebungsvariablen gelesen:

| Variable | Bedeutung | Standard |
|---|---|---|
| `FACEBOOK_PAGE_ID` | ID der Zielseite | für `--publish` und `--check-auth` erforderlich |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Page Access Token für die Zielseite | für `--publish` und `--check-auth` erforderlich |
| `FACEBOOK_GRAPH_API_VERSION` | Verwendete Graph-API-Version | `v26.0` |
| `DATABASE_PATH` | Pfad zur lokalen Datenbank | `facebook_posts.sqlite3` |

Zugangsdaten werden erst für `--publish` und `--check-auth` geladen.
`--dry-run`, `--help` und Modulimporte funktionieren ohne Zugangsdaten.
Die Vorschau lädt Veranstaltungsdaten aus der Kulturbytes-API.

Setze die Zugangsdaten vor dem Zugangstest oder einer Veröffentlichung:

```bash
export FACEBOOK_PAGE_ID="DEINE_NUMERISCHE_SEITEN_ID"
export FACEBOOK_PAGE_ACCESS_TOKEN="DEIN_PAGE_ACCESS_TOKEN"
```

Die `export`-Befehle gelten für die aktuelle Terminal-Sitzung. Eine `.env`-Datei
wird vom Programm nicht automatisch geladen. Bewahre echte Tokens außerhalb
der versionierten Dateien auf; `.env` und lokale Datenbanken sind bereits in
[`.gitignore`](../.gitignore) ausgeschlossen.

## Zugang ohne Veröffentlichung prüfen

Im Ordner `facebook/`, nach dem Setzen der Zugangsdaten:

```bash
uv run main.py --check-auth
```

Beispiel einer erfolgreichen Prüfung (Exitcode 0):

```text
✓ Facebook Token gültig
✓ Seite erreichbar: Kulturbytes (1173614782497494)
```

Bei Fehlern endet der Check mit Exitcode 1, zum Beispiel `Error: Facebook Access Token ist abgelaufen.`
API-Fehler können zusätzlich HTTP-Status und bereinigte Details enthalten.
Tokens werden niemals angezeigt, auch wenn die API sie zurückgibt.

`--check-auth` hat Vorrang vor `--publish`, `--dry-run` und Auswahloptionen.
Es werden keine Kulturbytes-Termine geladen, keine Bilder oder Mediencontainer
erzeugt und keine Beiträge oder Datenbankeinträge geschrieben. Der Check verwendet
nur `GET /{version}/{page_id}?fields=id,name`. Ein erfolgreicher Lesezugriff bestätigt den Kontozugriff,
aber nicht sämtliche Veröffentlichungsrechte. Siehe [Meta Pages API](https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api).

Die zurückgegebene Seiten-ID muss mit `FACEBOOK_PAGE_ID` übereinstimmen.
Seiten-IDs müssen numerisch sein; die API-Version hat das Format `v26.0`.
Fehlende Zugangsdaten beenden `--publish` vor der Event-Abfrage.

## Termine auswählen und veröffentlichen

Starte mit einer kleinen Auswahl:

```bash
uv run main.py --publish --limit 10 --city Flensburg
```

Das Programm bietet freigegebene Termine ab dem heutigen Datum chronologisch
an und blendet bereits gespeicherte Veröffentlichungen aus. Wähle Nummern wie
`1,3-5` oder `all`. Vor jedem Beitrag erscheinen eine Vorschau und eine eigene
Bestätigungsfrage. Ohne Zustimmung wird dieser Termin übersprungen.

`--limit` begrenzt die angebotene Terminliste. Wie viele Beiträge entstehen,
entscheidest du mit deiner Auswahl und den Bestätigungen. Der Ablauf ist
interaktiv und eignet sich derzeit nicht für unbeaufsichtigte Timer-Läufe.

| Option | Wirkung | Standard |
|---|---|---|
| `--dry-run` | Vorschau der ausgewählten Beiträge anzeigen | aktiv |
| `--check-auth` | Nur Zugang prüfen, ohne Veröffentlichung | aus |
| `--publish` | Beiträge nach einzelner Bestätigung veröffentlichen | aus |
| `--limit 10` | Höchstens zehn Termine zur Auswahl anbieten | `50` |
| `--limit 0` | Alle passenden Termine zur Auswahl anbieten | — |
| `--city Flensburg` | Nach Stadt filtern, unabhängig von Groß- und Kleinschreibung | alle Städte |
| `--include-published` | Bereits veröffentlichte Termine mit zusätzlicher Rückfrage anbieten | aus |
| `--help` | Hilfe zu den Befehlen anzeigen | — |

Alternativ zu `uv run main.py` kannst du `uv run kulturbytes-facebook` mit
denselben Optionen verwenden. `DRY_RUN` und `MAX_POSTS_PER_RUN` werden nicht
als Umgebungsvariablen ausgewertet.

## Einzelnen Termin direkt auswählen

Im jeweiligen Plattformordner kannst du die nummerierte Auswahl überspringen:

```bash
uv run main.py --publish --event-uuid "EVENT_UUID" --date-identifier "202609101830"
```

Ersetze `EVENT_UUID` durch die Veranstaltungs-UUID. `--date-identifier` akzeptiert
entweder den `date_slug` (wie im Beispiel) oder die `date_uuid`. Beide Optionen
müssen zusammen angegeben werden. Ohne `--publish` erscheint nur die Vorschau.
Vor dem Veröffentlichen bleibt die Bestätigungsfrage bestehen.

Der Termin wird über `/api/events` aufgelöst; die Liste liefert auch die bevorzugte
`summary`. Die Detailantwort liefert die übrigen Daten und bei leerer Zusammenfassung
die `description`. Freigabe-, Datums-, Stadt- und Duplikatfilter gelten weiterhin.
`--limit` schließt den direkt gewählten Termin nicht aus. Nicht eindeutig gefundene
oder ausgefilterte Termine führen zu einer Fehlermeldung und einem Fehler-Exitcode.

## Inhalt der Beiträge

Der Publisher erstellt einen Fotobeitrag mit dem Veranstaltungsbild. Ist kein
Bild hinterlegt, erstellt er einen Textbeitrag. Der Text enthält je nach
verfügbaren Daten Titel, Untertitel, Datum, Uhrzeit, Ort, Adresse, Beschreibung,
Veranstalter, Eintrittsinformationen, Kulturbytes-Link und Hashtags.

Es entstehen Beiträge auf deiner Seite; eigenständige Facebook-Veranstaltungen
werden vom Programm nicht angelegt.

## Lokale Daten

Der Publisher legt standardmäßig `facebook_posts.sqlite3` im aktuellen
Arbeitsverzeichnis an, auch beim ersten Vorschau-Lauf. Erst nach einer
erfolgreichen Veröffentlichung speichert er die Termin-ID (`date_uuid`),
Veranstaltungsdaten und die Facebook-Post-ID.
So erkennt er beim nächsten Lauf bereits veröffentlichte Termine.

Behalte diese Datenbank bei einem Umzug oder Update. Mit `DATABASE_PATH` kannst
du einen anderen Pfad festlegen; ein absoluter Pfad bleibt auch bei einem
Wechsel des Arbeitsverzeichnisses eindeutig. Facebook und Mastodon benötigen
jeweils eine eigene Datenbank.

`--include-published` erlaubt nach zusätzlichen Bestätigungen auch eine erneute
Veröffentlichung eines bekannten Termins. Nach erfolgreicher Veröffentlichung
ersetzt der neue Eintrag die gespeicherte Facebook-Post-ID
für dieselbe `date_uuid` und aktualisiert Veranstaltungsdaten und `published_at`.
Es wird nur die letzte Veröffentlichung gespeichert. Schlägt die Veröffentlichung
auf der Plattform fehl, bleibt der bisherige Datenbankeintrag unverändert.

## Hilfe bei Problemen

| Problem | Was du prüfen kannst |
|---|---|
| `uv` wird nicht gefunden | Prüfe, ob `uv` installiert und im Suchpfad deines Terminals verfügbar ist. |
| Eine Zugangsdaten-Variable fehlt | Setze die erforderlichen Variablen unter „Konfiguration“ im selben Terminal. |
| Es stehen keine Termine zur Auswahl | Prüfe den Stadtfilter. Bereits veröffentlichte Termine siehst du mit `--include-published`; vergangene oder nicht freigegebene Termine werden ausgefiltert. |
| Facebook lehnt die Veröffentlichung ab | Prüfe die ausgegebene API-Antwort, die Seiten-ID sowie Gültigkeit und Veröffentlichungsrechte des Page Access Tokens. |
| Ein Fotobeitrag schlägt fehl | Prüfe die Bildadresse aus der Vorschau und die API-Fehlermeldung. Bei einem fehlerhaften Bild erfolgt kein automatischer Wechsel zum Textbeitrag. |
| Die Datenbank lässt sich nicht öffnen | Prüfe, ob der übergeordnete Ordner von `DATABASE_PATH` existiert und beschreibbar ist. |

Die verfügbaren Optionen zeigt `uv run main.py --help` auch ohne Zugangsdaten.

## Entwicklung

Der Plattformcode liegt in [`src/kulturbytes_facebook/cli.py`](src/kulturbytes_facebook/cli.py).
Gemeinsame API-Abfragen, Terminauswahl und Bilddownloads liegen in
[`common/`](../common/). Hinweise zur Struktur und zum Testlauf findest du in
der [Projektübersicht](../README.md#entwicklung).

## Lizenz

[AGPL-3.0](../LICENSE)
