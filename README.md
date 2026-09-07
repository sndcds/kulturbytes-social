# Kulturbytes Publisher

Facebook und Mastodon teilen sich ein Python-Paket. Änderungen an API-Abfragen,
Terminauswahl, Hashtags oder Bilddownloads wirken dadurch auf beide Publisher.

```text
common/src/kulturbytes_common/
  events.py       Kulturbytes-API, Datum, Adresse, Preise und Hashtags
  media.py        Bild-URL und Bilddownload
  selection.py    Terminliste und interaktive Auswahl
  database.py     Prüfung auf bereits veröffentlichte Termine
  workflow.py     Laden, Filtern, Sortieren und Veröffentlichen der Auswahl
facebook/src/kulturbytes_facebook/cli.py
mastodon/src/kulturbytes_mastodon/cli.py
```

Die Plattformpakete enthalten ihre Konfiguration, Postformatierung, API-Aufrufe
und SQLite-Schemata. Vorhandene Datenbanken können weiterverwendet werden.
Facebook und Mastodon verwenden jeweils eine eigene Datenbank.

## Installation

Python 3.12 oder neuer und `uv` werden benötigt. Im Repository-Hauptordner:

```bash
uv sync --all-packages
```

Die drei Pakete bilden einen `uv`-Workspace mit einer gemeinsamen `uv.lock`.
Das Paket `kulturbytes-common` wird lokal eingebunden; es muss nicht separat
veröffentlicht oder kopiert werden. Für Installation und Betrieb den gesamten
Repository-Ordner behalten.

## Starten

Die Zugangsdaten wie in [Facebook](facebook/README.md) beziehungsweise
[Mastodon](mastodon/README.md) beschrieben setzen. Danach im jeweiligen Ordner:

```bash
cd facebook
uv run main.py --dry-run --limit 10
```

Oder für Mastodon, ausgehend vom Repository-Hauptordner:

```bash
cd mastodon
uv run main.py --dry-run --limit 10
```

Alternativ funktionieren dort `uv run kulturbytes-facebook` bzw.
`uv run kulturbytes-mastodon`. Der Standard ist eine Vorschau. `--publish`
aktiviert die Veröffentlichung mit einer Bestätigung pro Termin.

Weitere Optionen: `--city Flensburg`, `--limit 0` (alle Termine) und
`--include-published`. Die Datenbankpfade sind relativ zum Arbeitsverzeichnis;
beim Umstellen bestehender Aufrufe das bisherige Arbeitsverzeichnis beibehalten
oder `DATABASE_PATH` auf den absoluten Pfad der bisherigen Datenbank setzen.

## Tests

Im Repository-Hauptordner:

```bash
uv run --all-packages python -m unittest discover -s tests -v
```

Die Tests verwenden simulierte HTTP-Antworten und temporäre Datenbanken.
