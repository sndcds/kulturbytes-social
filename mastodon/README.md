# Kulturbytes Mastodon Publisher

Teile Kulturbytes-Veranstaltungen auf deinem Mastodon-Konto: Du wählst Termine
im Terminal aus, prüfst die Vorschau und bestätigst die Veröffentlichung.
Beim normalen Start bleibt es bei einer Vorschau.

[Projektübersicht](../README.md) · [Facebook](../facebook/README.md) · [Mastodon](../mastodon/README.md)

## Voraussetzungen

Du brauchst Python 3.12 oder neuer, `uv`, eine Internetverbindung und
die Adresse deiner Mastodon-Instanz und einen Access Token für dein Konto, der Beiträge veröffentlichen und Medien hochladen darf.
Behalte den gesamten Repository-Ordner: Der Publisher nutzt das gemeinsame
Paket in `common/`.

## Schnellstart

Öffne ein Terminal im Repository-Hauptordner. Installiere die Abhängigkeiten,
wechsle zum Publisher und ersetze die Platzhalter durch deine Zugangsdaten:

```bash
uv sync --all-packages
cd mastodon
export MASTODON_BASE_URL="https://norden.social"
export MASTODON_ACCESS_TOKEN="DEIN_ACCESS_TOKEN"
uv run main.py --dry-run --limit 10
```

Setze `MASTODON_BASE_URL` auf die Instanz, auf der dein Konto liegt.

Das Programm zeigt bis zu zehn Termine. Gib beispielsweise `1` oder `1,3-5`
ein und drücke Enter, um die Vorschau zu sehen. `all` wählt alle angezeigten
Termine; eine leere Eingabe beendet die Auswahl. Es wird nichts veröffentlicht.

Alle weiteren Startbefehle auf dieser Seite führst du im Ordner `mastodon/` aus.

## Konfiguration

Die Einstellungen werden aus den Umgebungsvariablen gelesen:

| Variable | Bedeutung | Standard |
|---|---|---|
| `MASTODON_BASE_URL` | Adresse deiner Mastodon-Instanz | `https://norden.social` |
| `MASTODON_ACCESS_TOKEN` | Access Token für dein Konto auf dieser Instanz | erforderlich |
| `DATABASE_PATH` | Pfad zur lokalen Datenbank | `mastodon_posts.sqlite3` |

Die erforderlichen Variablen müssen bereits beim Start gesetzt sein, auch für
`--dry-run` und `--help`. Die Vorschau veröffentlicht nichts auf Mastodon,
lädt aber Veranstaltungsdaten aus der Kulturbytes-API.

Die `export`-Befehle gelten für die aktuelle Terminal-Sitzung. Eine `.env`-Datei
wird vom Programm nicht automatisch geladen. Bewahre echte Tokens außerhalb
der versionierten Dateien auf; `.env` und lokale Datenbanken sind bereits in
[`.gitignore`](../.gitignore) ausgeschlossen.

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
| `--publish` | Beiträge nach einzelner Bestätigung veröffentlichen | aus |
| `--limit 10` | Höchstens zehn Termine zur Auswahl anbieten | `50` |
| `--limit 0` | Alle passenden Termine zur Auswahl anbieten | — |
| `--city Flensburg` | Nach Stadt filtern, unabhängig von Groß- und Kleinschreibung | alle Städte |
| `--include-published` | Bereits veröffentlichte Termine mit zusätzlicher Rückfrage anbieten | aus |
| `--help` | Hilfe zu den Befehlen anzeigen | — |

Alternativ zu `uv run main.py` kannst du `uv run kulturbytes-mastodon` mit
denselben Optionen verwenden. `DRY_RUN` und `MAX_POSTS_PER_RUN` werden nicht
als Umgebungsvariablen ausgewertet.

## Inhalt der Beiträge

Der Publisher erstellt öffentliche Mastodon-Beiträge. Er bereinigt Markdown
und kürzt den Beitragstext auf höchstens 500 Zeichen. Je nach verfügbaren Daten
enthält der Beitrag Veranstaltungsinformationen, einen Kulturbytes-Link und
Hashtags. Ein vorhandenes Veranstaltungsbild wird mit Alt-Text hochgeladen.
Ohne hinterlegtes Bild entsteht ein Textbeitrag.

Die Grenze von 500 Zeichen und die öffentliche Sichtbarkeit sind im Programm
festgelegt; sie lassen sich derzeit nicht über Umgebungsvariablen ändern.

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
Veröffentlichung eines bekannten Termins.

## Hilfe bei Problemen

| Problem | Was du prüfen kannst |
|---|---|
| `uv` wird nicht gefunden | Prüfe, ob `uv` installiert und im Suchpfad deines Terminals verfügbar ist. |
| Beim Start erscheint ein `KeyError` für eine Variable | Setze die erforderlichen Variablen unter „Konfiguration“ im selben Terminal. |
| Es stehen keine Termine zur Auswahl | Prüfe den Stadtfilter. Bereits veröffentlichte Termine siehst du mit `--include-published`; vergangene oder nicht freigegebene Termine werden ausgefiltert. |
| Mastodon lehnt die Veröffentlichung ab | Prüfe die ausgegebene API-Antwort und ob der Access Token zur eingestellten Instanz gehört und Beiträge veröffentlichen darf. |
| Der Bild-Upload schlägt fehl | Prüfe die Bildadresse aus der Vorschau und ob der Token Medien hochladen darf. |
| Die Datenbank lässt sich nicht öffnen | Prüfe, ob der übergeordnete Ordner von `DATABASE_PATH` existiert und beschreibbar ist. |

Die verfügbaren Optionen zeigt `uv run main.py --help`, nachdem die
erforderlichen Umgebungsvariablen gesetzt sind.

## Entwicklung

Der Plattformcode liegt in [`src/kulturbytes_mastodon/cli.py`](src/kulturbytes_mastodon/cli.py).
Gemeinsame API-Abfragen, Terminauswahl und Bilddownloads liegen in
[`common/`](../common/). Hinweise zur Struktur und zum Testlauf findest du in
der [Projektübersicht](../README.md#entwicklung).

## Lizenz

[AGPL-3.0](../LICENSE)
