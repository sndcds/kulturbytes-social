# Kulturbytes Mastodon Publisher

Veröffentlicht ausgewählte Kulturbytes-Termine auf Mastodon. Gemeinsame
Funktionen liegen im Paket `common`, siehe [Workspace-Anleitung](../README.md).

## Installation und Konfiguration

Im Repository-Hauptordner `uv sync --all-packages` ausführen. Anschließend:

```bash
cd mastodon
export MASTODON_ACCESS_TOKEN="DEIN_ACCESS_TOKEN"
export MASTODON_BASE_URL="https://norden.social"
# Optional, Standard relativ zum Arbeitsverzeichnis:
export DATABASE_PATH="mastodon_posts.sqlite3"
```

Der Token muss das Veröffentlichen von Statusmeldungen und Hochladen von Medien
für das gewünschte Konto erlauben. `MASTODON_BASE_URL` verwendet standardmäßig
`https://norden.social`.

## Verwendung

```bash
uv run main.py --dry-run --limit 10
uv run main.py --publish --city Flensburg
# Alternativer Einstiegspunkt:
uv run kulturbytes-mastodon --dry-run
```

Das Programm zeigt eine nummerierte Liste. Einzelne Nummern, Kombinationen wie
`1,3-5` oder `all` wählen die Termine aus. Vor jeder echten Veröffentlichung
fragt es nach Bestätigung. `--include-published` zeigt auch bekannte Termine.

Mastodon verwendet einen gekürzten Text mit maximal 500 Zeichen, bereinigtem
Markdown sowie Eventbildern mit Alt-Text. Die Status-ID und gegebenenfalls die
Status-URL werden in einer eigenen SQLite-Datenbank gespeichert. Bestehende
Datenbanken bleiben verwendbar.
