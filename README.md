# Kulturbytes Publisher

Teile Kulturbytes-Veranstaltungen auf Facebook, Mastodon und Instagram. Du wählst die
gewünschten Termine im Terminal aus, siehst eine Vorschau und bestätigst jeden
Beitrag vor der Veröffentlichung. So behältst du die Kontrolle darüber, was
auf deiner Seite oder deinem Konto erscheint.

Wähle die Anleitung für deine Plattform:

| Plattform | Wofür du sie verwendest |
|---|---|
| [Facebook](facebook/README.md) | Veranstaltungsbeiträge auf einer Facebook-Seite veröffentlichen |
| [Mastodon](mastodon/README.md) | Veranstaltungsbeiträge auf einem Mastodon-Konto veröffentlichen |
| [Instagram](instagram/README.md) | Veranstaltungsbilder auf einem Instagram-Professional-Konto veröffentlichen |

## Voraussetzungen

Du brauchst Python 3.12 oder neuer, `uv` und eine Internetverbindung.
Für Veröffentlichungen und den Zugangstest benötigst du außerdem die in der
jeweiligen Anleitung beschriebenen Zugangsdaten. Vorschau und Hilfe funktionieren ohne Tokens. Behalte den gesamten Repository-Ordner, da alle
Publisher das Paket in `common/` verwenden.

## Schnellstart

Öffne ein Terminal im Repository-Hauptordner und installiere die Abhängigkeiten:

```bash
uv sync --all-packages
```

Öffne danach die [Facebook-Anleitung](facebook/README.md#schnellstart),
[Mastodon-Anleitung](mastodon/README.md#schnellstart) oder
[Instagram-Anleitung](instagram/README.md#schnellstart). Dort findest du die
Befehle zum Setzen deiner Zugangsdaten und für deine erste Vorschau.
Die Installation ist für alle Plattformen gemeinsam und muss nur einmal
ausgeführt werden.

Bei der ersten Auswahl gibst du beispielsweise `1` oder `1,3-5` ein.
`all` wählt alle angezeigten Termine; eine leere Eingabe beendet die Auswahl.
Der Standardmodus zeigt nur eine Vorschau.

## Konfiguration

Alle Publisher lesen ihre Einstellungen aus Umgebungsvariablen. Die
plattformabhängigen Variablen und ihre Standardwerte stehen in den Anleitungen:

- [Facebook konfigurieren](facebook/README.md#konfiguration)
- [Mastodon konfigurieren](mastodon/README.md#konfiguration)
- [Instagram konfigurieren](instagram/README.md#zugangsdaten-und-veröffentlichung)

Alle drei Publisher benötigen Zugangsdaten nur für `--publish` und `--check-auth`.
Import, Vorschau (`--dry-run`) und Befehlshilfe (`--help`) funktionieren ohne Tokens. `.env`-Dateien werden nicht automatisch geladen.
Echte Tokens gehören außerhalb der versionierten Dateien aufbewahrt.

## Zugang prüfen

Im jeweiligen Ordner `facebook/`, `mastodon/` oder `instagram/`:

```bash
uv run main.py --check-auth
```

Der Check liest ausschließlich das konfigurierte Plattformkonto bzw. die Facebook-Seite.
Er zeigt bei Erfolg den Namen und beendet sich mit Exitcode 0; bei fehlenden oder
ungültigen Zugangsdaten erscheint eine Fehlermeldung mit Exitcode 1, beispielsweise
`Error: Facebook Access Token ist abgelaufen.` Tokens werden niemals angezeigt;
auch von der API zurückgegebene Tokenwerte werden entfernt.

`--check-auth` hat Vorrang vor `--publish`, `--dry-run` und allen Auswahloptionen.
Es gibt keine Event-Abfrage, Auswahl, Bildverarbeitung, Veröffentlichung oder
Datenbankänderung. Ein erfolgreicher Lesezugriff bestätigt den Kontozugriff;
er garantiert keine Veröffentlichungsrechte. Zum Veröffentlichen bleiben
passende Zugangsdaten und die Bestätigung pro Termin erforderlich.

## Termine auswählen und veröffentlichen

Nach der Konfiguration startest du den gewünschten Publisher in seinem Ordner.
Für Facebook, ausgehend vom Repository-Hauptordner:

```bash
cd facebook
uv run main.py --dry-run --limit 10
```

Für Mastodon, ebenfalls ausgehend vom Repository-Hauptordner:

```bash
cd mastodon
uv run main.py --dry-run --limit 10
```

Für Instagram, ebenfalls ausgehend vom Repository-Hauptordner:

```bash
cd instagram
uv run main.py --dry-run --limit 10
```

Die Liste enthält freigegebene Termine ab dem heutigen Datum, chronologisch
sortiert. Bereits gespeicherte Veröffentlichungen werden ausgeblendet.
Wähle die gewünschten Nummern aus, um ihre Vorschau zu sehen.

Wenn du veröffentlichen möchtest, starte im jeweiligen Plattformordner:

```bash
uv run main.py --publish --limit 10
```

Vor jedem Beitrag fragt das Programm nach einer Bestätigung. `--limit` begrenzt
die angebotene Liste; du entscheidest, wie viele Termine du daraus veröffentlichst.
Der Ablauf ist interaktiv und eignet sich derzeit nicht für unbeaufsichtigte
Timer-Läufe.

| Option | Wirkung | Standard |
|---|---|---|
| `--dry-run` | Vorschau der ausgewählten Beiträge anzeigen | aktiv |
| `--check-auth` | Nur Zugang prüfen, ohne Veröffentlichung oder Datenbankzugriff | aus |
| `--publish` | Beiträge nach einzelner Bestätigung veröffentlichen | aus |
| `--limit 10` | Höchstens zehn Termine zur Auswahl anbieten | `50` |
| `--limit 0` | Alle passenden Termine zur Auswahl anbieten | — |
| `--city Flensburg` | Nach Stadt filtern, unabhängig von Groß- und Kleinschreibung | alle Städte |
| `--include-published` | Bereits veröffentlichte Termine mit zusätzlicher Rückfrage anbieten | aus |
| `--help` | Hilfe zu den Befehlen anzeigen | — |

Alternativ zu `uv run main.py` funktionieren im jeweiligen Plattformordner
`uv run kulturbytes-facebook`, `uv run kulturbytes-mastodon` und
`uv run kulturbytes-instagram`.

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

Alle Publisher übernehmen Veranstaltungsinformationen aus der Kulturbytes-API
und verlinken auf den Termin bei Kulturbytes. Vorhandene Veranstaltungsbilder
und Hashtags ergänzen die Beiträge.

Facebook verwendet einen ausführlichen Beitrag und veröffentlicht vorhandene
Bilder als Fotopost. Mastodon verwendet einen auf das Instanzlimit (Fallback: 500 Zeichen)
gekürzten Text und öffentliche Beiträge mit Alt-Text für Bilder. Die Details
stehen unter [Facebook](facebook/README.md#inhalt-der-beiträge) und
[Mastodon](mastodon/README.md#inhalt-der-beiträge). Instagram benötigt ein JPEG-Hauptbild
und verwendet bis zu 2.200 Zeichen sowie höchstens fünf erzeugte Hashtags; siehe
[Instagram](instagram/README.md#bild-und-beitragstext).

## Lokale Daten

Jede Plattform speichert erfolgreiche Veröffentlichungen in ihrer eigenen
SQLite-Datenbank. Die Termin-ID (`date_uuid`) dient dazu, bekannte Termine beim
nächsten Lauf auszublenden. Eine Vorschau kann die Datenbank anlegen, speichert
aber keine Veröffentlichung.

Standardmäßig entstehen `facebook_posts.sqlite3`, `mastodon_posts.sqlite3` beziehungsweise
`instagram_posts.sqlite3` im aktuellen Arbeitsverzeichnis. Behalte bestehende
Datenbanken bei einem Umzug oder Update. Nutze das bisherige Arbeitsverzeichnis
oder setze `DATABASE_PATH` auf einen absoluten Pfad. Verwende für alle
Plattformen getrennte Datenbanken.

Virtuelle Umgebungen, Caches, `.env`-Dateien und lokale Datenbanken werden durch
[`.gitignore`](.gitignore) aus Git ausgeschlossen. Die gemeinsame `uv.lock`
gehört zum Repository und hält die Abhängigkeitsversionen fest.

## Hilfe bei Problemen

| Problem | Was du prüfen kannst |
|---|---|
| `uv` wird nicht gefunden | Prüfe, ob `uv` installiert und im Suchpfad deines Terminals verfügbar ist. |
| Beim Start fehlt eine Umgebungsvariable | Setze die Zugangsdaten im selben Terminal, in dem du den Publisher startest. |
| Ein lokales Python-Paket wird nicht gefunden | Führe `uv sync --all-packages` im Repository-Hauptordner aus und behalte alle vier Paketordner. |
| Es stehen keine Termine zur Auswahl | Prüfe Stadtfilter und bereits veröffentlichte Termine. |
| Die Veröffentlichung schlägt fehl | Lies die API-Fehlermeldung und die Hinweise für deine Plattform. |

Weitere Hilfe findest du bei [Facebook](facebook/README.md#hilfe-bei-problemen)
und [Mastodon](mastodon/README.md#hilfe-bei-problemen).

## Entwicklung

Die vier Pakete bilden einen `uv`-Workspace mit einer gemeinsamen `uv.lock`.
Das Paket `kulturbytes-common` wird lokal eingebunden. Änderungen an gemeinsamen
Funktionen wirken auf alle Publisher.

```text
common/src/kulturbytes_common/
  events.py       API-Abfragen und Veranstaltungsinformationen
  media.py        Bildadressen und Bilddownloads
  formatting.py   Gemeinsame Markdown-Bereinigung
  selection.py    Terminliste und interaktive Auswahl
  database.py     Prüfung auf bereits veröffentlichte Termine
  workflow.py     Laden, Filtern, Sortieren und Veröffentlichen
facebook/src/kulturbytes_facebook/cli.py
mastodon/src/kulturbytes_mastodon/cli.py
instagram/src/kulturbytes_instagram/cli.py
tests/test_publishers.py
tests/test_instagram.py
```

Die Plattformpakete enthalten ihre Konfiguration, Postformatierung, API-Aufrufe
und Datenbankschemata. Führe die gemeinsamen Tests im Repository-Hauptordner aus:

```bash
uv run --all-packages python -m unittest discover -s tests -v
```

Die Tests verwenden simulierte HTTP-Antworten und temporäre Datenbanken.

## Lizenz

[AGPL-3.0](LICENSE)
