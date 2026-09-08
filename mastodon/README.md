# Kulturbytes Mastodon Publisher

Teile Kulturbytes-Veranstaltungen auf deinem Mastodon-Konto: Du wählst Termine
im Terminal aus, prüfst die Vorschau und bestätigst die Veröffentlichung.
Beim normalen Start bleibt es bei einer Vorschau.

[Projektübersicht](../README.md) · [Facebook](../facebook/README.md) · [Mastodon](../mastodon/README.md)

## Voraussetzungen

Du brauchst Python 3.12 oder neuer, `uv` und eine Internetverbindung.
Zum Veröffentlichen benötigst du zusätzlich
die Adresse deiner Mastodon-Instanz und einen Access Token für dein Konto, der Beiträge veröffentlichen und Medien hochladen darf.
Behalte den gesamten Repository-Ordner: Der Publisher nutzt das gemeinsame
Paket in `common/`.

## Schnellstart

Öffne ein Terminal im Repository-Hauptordner. Installiere die Abhängigkeiten,
wechsle zum Publisher und starte die Vorschau ohne Zugangsdaten:

```bash
uv sync --all-packages
cd mastodon
uv run main.py --dry-run --limit 10
```

Das Programm zeigt bis zu zehn Termine. Gib beispielsweise `1` oder `1,3-5`
ein und drücke Enter, um die Vorschau zu sehen. `all` wählt alle angezeigten
Termine; eine leere Eingabe beendet die Auswahl. Es wird nichts veröffentlicht.

Alle weiteren Startbefehle auf dieser Seite führst du im Ordner `mastodon/` aus.

## Konfiguration

Die Einstellungen werden aus den Umgebungsvariablen gelesen:

| Variable | Bedeutung | Standard |
|---|---|---|
| `MASTODON_BASE_URL` | Adresse deiner Mastodon-Instanz | `https://norden.social` |
| `MASTODON_ACCESS_TOKEN` | Access Token für dein Konto auf dieser Instanz | für `--publish` und `--check-auth` erforderlich |
| `DATABASE_PATH` | Pfad zur lokalen Datenbank | `mastodon_posts.sqlite3` |

Zugangsdaten werden erst für `--publish` und `--check-auth` geladen.
`--dry-run`, `--help` und Modulimporte funktionieren ohne Zugangsdaten.
Die Vorschau lädt Veranstaltungsdaten aus der Kulturbytes-API.

Setze die Zugangsdaten vor dem Zugangstest oder einer Veröffentlichung:

```bash
export MASTODON_BASE_URL="https://norden.social"
export MASTODON_ACCESS_TOKEN="DEIN_ACCESS_TOKEN"
```

Die `export`-Befehle gelten für die aktuelle Terminal-Sitzung. Eine `.env`-Datei
wird vom Programm nicht automatisch geladen. Bewahre echte Tokens außerhalb
der versionierten Dateien auf; `.env` und lokale Datenbanken sind bereits in
[`.gitignore`](../.gitignore) ausgeschlossen.

## Optionaler OS-Keyring

Tokens werden zuerst aus der jeweiligen Umgebungsvariable, sonst aus dem
OS-Keyring geladen. Eine vorhandene, aber leere Variable verhindert ebenfalls
den Keyring-Zugriff und zählt als fehlend. Hilfe und Dry-Run lesen keine Tokens.
`--publish` und `--check-auth` verwenden beide dieselbe Auflösung.

Im Ordner `mastodon/`:

```bash
uv run main.py --credentials status
uv run main.py --credentials set
uv run main.py --credentials delete
```

Beim Speichern wird der Token verdeckt abgefragt. Status zeigt ausschließlich
vorhanden/nicht vorhanden; weder Werte, Teile, Längen noch Hashes werden ausgegeben.
Löschen verlangt eine Bestätigung und betrifft nur den Keyring, nicht die Umgebung.
Die Verwaltung führt keine Netzwerk- oder Datenbankoperationen aus. Kombinationen
mit `--publish` oder `--check-auth` sind nicht zulässig; Auswahloptionen werden ignoriert.
Die Paketbefehle akzeptieren dieselben Optionen.

Service: `kulturbytes-social/mastodon`, Benutzername: `access-token`.
Instanz-/Kontokonfiguration wird weiterhin über Umgebungsvariablen gesetzt.

Keyring ist optional. Auf Ubuntu können `sudo apt install gnome-keyring libsecret-tools`
und eine entsperrte Secret-Service-Sitzung benötigt werden. Die Python-Abhängigkeit
`keyring` wird über `uv sync --all-packages` installiert; die Anwendung ruft kein
`secret-tool` auf und verwendet keine Klartext-Dateiablage. Backend-Fehler werden
als bereinigte Click-Fehler angezeigt. Umgebungsvariablen funktionieren auch bei
kaputtem Keyring. Server können extern bereitgestellte Systemd-Credentials bevorzugen;
eine automatische Provisionierung ist nicht enthalten. Details und unterstützte
OS-Backends: [Projektübersicht](../README.md#tokens-optional-im-os-keyring-speichern).

## Zugang ohne Veröffentlichung prüfen

Im Ordner `mastodon/`, nach dem Setzen der Zugangsdaten:

```bash
uv run main.py --check-auth
```

Beispiel einer erfolgreichen Prüfung (Exitcode 0):

```text
✓ Mastodon Token gültig
✓ Konto: @kulturbytes@norden.social
```

Bei Fehlern endet der Check mit Exitcode 1, zum Beispiel `Error: Mastodon-Zugangsdaten ungültig oder abgelaufen.`
API-Fehler können zusätzlich HTTP-Status und bereinigte Details enthalten.
Tokens werden niemals angezeigt, auch wenn die API sie zurückgibt.

`--check-auth` hat Vorrang vor `--publish`, `--dry-run` und Auswahloptionen.
Es werden keine Kulturbytes-Termine geladen, keine Bilder oder Mediencontainer
erzeugt und keine Beiträge oder Datenbankeinträge geschrieben. Der Check verwendet
nur `GET /api/v1/accounts/verify_credentials`. Ein erfolgreicher Lesezugriff bestätigt den Kontozugriff,
aber nicht sämtliche Veröffentlichungsrechte. Siehe [Mastodon-Kontoprüfung](https://docs.joinmastodon.org/methods/accounts/#verify_credentials).

`MASTODON_BASE_URL` muss eine HTTP(S)-Instanzadresse ohne eingebettete
Zugangsdaten, Pfad, Query oder Fragment sein. Fehlende Zugangsdaten beenden
`--publish` vor der Event-Abfrage.

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

Alternativ zu `uv run main.py` kannst du `uv run kulturbytes-mastodon` mit
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

Der Publisher erstellt öffentliche Mastodon-Beiträge. Er bereinigt Markdown
und berücksichtigt das Zeichenlimit der Zielinstanz. Je nach verfügbaren Daten
enthält der Beitrag Veranstaltungsinformationen, einen Kulturbytes-Link und
Hashtags. Ein vorhandenes Veranstaltungsbild wird mit Alt-Text hochgeladen.
Ohne hinterlegtes Bild entsteht ein Textbeitrag.

Das Limit wird beim ersten gültigen ausgewählten Termin über die öffentliche
`GET /api/v2/instance`-Abfrage aus `configuration.statuses.max_characters` gelesen
und im gesamten Lauf wiederverwendet, auch im Dry-Run ohne Token. Fehlt ein gültiger
positiver Ganzzahlwert oder scheitert die Abfrage, verwendet das Programm mit einem
Hinweis 500 Zeichen. `--check-auth` führt diese Abfrage nicht aus. Siehe die
[Mastodon-Instanzdokumentation](https://docs.joinmastodon.org/entities/Instance/).

Titel, Datum/Zeit, Ort, Kulturbytes-Link und sämtliche erzeugten Hashtags bleiben
vollständig. Die Beschreibung wird zuerst an Wortgrenzen gekürzt oder weggelassen.
Optionale Metadaten werden nur ganz übernommen, in dieser Priorität: Untertitel,
Preis, Ticket-Link, Veranstalter; die Beschreibung erhält den verbleibenden Platz.
Ein Ticket-Link wird niemals teilweise übernommen. Passen bereits die Pflichtangaben
nicht, wird der Termin vor Bild-Upload und Veröffentlichung mit einer Fehlermeldung
abgebrochen; der bestehende Datenbankeintrag bleibt unverändert.

Die Vorschau zeigt `Zeichen: verwendete/erlaubte`, etwa `Zeichen: 611/750`.
Exakt dieser Vorschautext wird veröffentlicht. Gezählt wird mit Python `len()`;
eine besondere URL- oder Graphemzählung der Instanz wird nicht nachgebildet.
Die Sichtbarkeit bleibt fest auf öffentlich eingestellt.

## Lokale Daten

Der Publisher legt standardmäßig `mastodon_posts.sqlite3` im aktuellen
Arbeitsverzeichnis an, auch beim ersten Vorschau-Lauf. Erst nach einer
erfolgreichen Veröffentlichung speichert er die Termin-ID (`date_uuid`),
Veranstaltungsdaten und die Mastodon-Status-ID und gegebenenfalls die Status-URL.
So erkennt er beim nächsten Lauf bereits veröffentlichte Termine.

Behalte diese Datenbank bei einem Umzug oder Update. Mit `DATABASE_PATH` kannst
du einen anderen Pfad festlegen; ein absoluter Pfad bleibt auch bei einem
Wechsel des Arbeitsverzeichnisses eindeutig. Facebook und Mastodon benötigen
jeweils eine eigene Datenbank.

`--include-published` erlaubt nach zusätzlichen Bestätigungen auch eine erneute
Veröffentlichung eines bekannten Termins. Nach erfolgreicher Veröffentlichung
ersetzt der neue Eintrag die gespeicherte Mastodon-Status-ID und die Status-URL
für dieselbe `date_uuid` und aktualisiert Veranstaltungsdaten und `published_at`.
Es wird nur die letzte Veröffentlichung gespeichert. Schlägt die Veröffentlichung
auf der Plattform fehl, bleibt der bisherige Datenbankeintrag unverändert.

## Hilfe bei Problemen

| Problem | Was du prüfen kannst |
|---|---|
| `uv` wird nicht gefunden | Prüfe, ob `uv` installiert und im Suchpfad deines Terminals verfügbar ist. |
| Eine Zugangsdaten-Variable fehlt | Setze die erforderlichen Variablen unter „Konfiguration“ im selben Terminal. |
| Es stehen keine Termine zur Auswahl | Prüfe den Stadtfilter. Bereits veröffentlichte Termine siehst du mit `--include-published`; vergangene oder nicht freigegebene Termine werden ausgefiltert. |
| Mastodon lehnt die Veröffentlichung ab | Prüfe die ausgegebene API-Antwort und ob der Access Token zur eingestellten Instanz gehört und Beiträge veröffentlichen darf. |
| Der Bild-Upload schlägt fehl | Prüfe die Bildadresse aus der Vorschau und ob der Token Medien hochladen darf. |
| Die Datenbank lässt sich nicht öffnen | Prüfe, ob der übergeordnete Ordner von `DATABASE_PATH` existiert und beschreibbar ist. |

Die verfügbaren Optionen zeigt `uv run main.py --help` auch ohne Zugangsdaten.

## Entwicklung

Der Plattformcode liegt in [`src/kulturbytes_mastodon/cli.py`](src/kulturbytes_mastodon/cli.py).
Gemeinsame API-Abfragen, Terminauswahl und Bilddownloads liegen in
[`common/`](../common/). Hinweise zur Struktur und zum Testlauf findest du in
der [Projektübersicht](../README.md#entwicklung).

## Lizenz

[AGPL-3.0](../LICENSE)
