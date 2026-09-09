# kulturbytes-common

`kulturbytes-common` ist die gemeinsame Python-Bibliothek von `kulturbytes-social`,
der Open-Source-CLI für Content Publishing aus generischen JSON APIs auf Facebook,
Instagram und Mastodon. Sie richtet sich an Entwickler, die Quellen, Templates oder
Plattform-Publisher erweitern, ohne Datenextraktion, Medienabrufe und
Veröffentlichungszustand mehrfach zu implementieren.

[Projektübersicht](../README.md) · [Facebook](../facebook/README.md) · [Instagram](../instagram/README.md) · [Mastodon](../mastodon/README.md)

## Architektur und Aufgaben

- `SourceDefinition` beschreibt JSON-Listen- und optionale Detailabrufe in YAML.
  JMESPath bildet unterschiedliche Feldnamen und verschachtelte Strukturen auf
  das kanonische `ContentItem` ab; Pydantic validiert die Inhalte.
- Der zentrale Jinja2-Sandbox-Renderer erzeugt `RenderedPost` aus neutralen oder
  quellenspezifischen Templates. Plattformlimits bleiben außerhalb der Templates.
- httpx übernimmt öffentliche Quellen- und Medienabrufe. Separate Clients,
  quellengebundene Medienhosts und DNS-Pinning trennen sie von Social-Zugangsdaten.
- Gemeinsame Click-Helfer steuern Auswahl und Vorschau. SQLite speichert
  Duplikatschutz und das Journal bestätigter Veröffentlichungsversuche.
  Unklare Remote-Ergebnisse erfordern eine manuelle Auflösung.

Kulturbytes verwendet dieselbe generische JSON-Engine wie andere Quellen.
Seine Besonderheiten stehen in [YAML](src/kulturbytes_common/data/sources/kulturbytes.yaml)
und [Templates](src/kulturbytes_common/data/templates/kulturbytes/), nicht in einem
quellenspezifischen Python-Adapter. Die Plattformpakete übernehmen die eigentlichen
Facebook-, Instagram- und Mastodon-API-Aufrufe.

## Installation und lokale Befehle

Voraussetzungen sind Python 3.12 oder neuer und uv. Klone das Repository nach der
[Installationsanleitung](../README.md#schnellstart). Führe anschließend alle Befehle
im Repository-Hauptordner aus:

```bash
uv sync --all-packages --locked
uv run kulturbytes-social sources list
uv run kulturbytes-social sources show kulturbytes
uv run kulturbytes-social sources validate kulturbytes
```

Diese Quellenbefehle sind lokal und lesend. `kulturbytes-common` stellt keinen
eigenen öffentlichen CLI-Befehl bereit. Eine Vorschau über die gemeinsame CLI:

```bash
uv run kulturbytes-social publish --platform mastodon --source kulturbytes --limit 5
```

Die Vorschau benötigt Zugriff auf die JSON API und das öffentliche Instanzlimit,
aber keine Social-Zugangsdaten. `--publish` verlangt Zugangsdaten und eine
Einzelbestätigung; die CLI ist kein unbeaufsichtigter Veröffentlichungsdienst.

## Quellen, Templates und Konfiguration

Im Checkout verweisen `sources/` und `templates/` auf die Paketdaten unter
[`data/`](src/kulturbytes_common/data/). Für installierte Pakete gibt es deterministische
XDG-Konfigurationspfade; Konfiguration wird nicht aus dem aktuellen Arbeitsverzeichnis
gesucht. YAML definiert JMESPath-Mappings, Listen-/Detailschritte und
`media.allowed_hosts`. Optionale Pluto-Bildverarbeitung wird über `media.image`
aktiviert und verändert nur die Bild-URL, nicht lokal die Bilddatei.

- [Generische JSON-Quellen und vollständiges Mapping-Beispiel](../README.md#data-sources)
- [Quellenpfade und lokale Validierung](../README.md#quellen-verwalten-und-konfigurieren)
- [Jinja2-Templates und kanonische Felder](../README.md#jinja2-templates)
- [Pluto: Bildgröße, Seitenverhältnis und Format](../README.md#pluto-bildverarbeitung)
- [Zugangsdaten und `.env`](../README.md#konfiguration)

## Grenzen und Sicherheitsmodell

Generische Quellen unterstützen öffentliche HTTPS/443-GETs ohne Authentifizierung
und ohne Redirects. Die Medienrichtlinie erlaubt nur explizit freigegebene Hosts;
Redirect-Ziele werden erneut geprüft. Der Transport validiert DNS-Antworten und
bindet die Verbindung an eine geprüfte öffentliche IP, unter Beibehaltung von
Host, TLS-SNI und Zertifikatsprüfung. Social-Tokens gelangen nicht an Quellen-
oder Medienserver. Ungültige Quellenkonfiguration wird abgelehnt, Fehlerausgaben
verwenden zentrale Secret-Redaktion und Veröffentlichungs-POSTs werden nicht
blind wiederholt.

Der spätere Bildabruf durch Meta liegt außerhalb dieses Transports. Das Journal
bietet keine Exactly-once-Garantie über Netzwerk und Datenbank hinweg. Details:
[Sicherheitsmodell](../README.md#schutz-bei-api--medien--und-veröffentlichungsfehlern)
und [Wiederherstellung](../README.md#veröffentlichungsjournal-und-wiederherstellung).

## Entwicklung und Tests

Änderungen an dieser Bibliothek betreffen alle Publisher. Prüfe den ganzen Workspace:

```bash
uv sync --all-packages --locked
uv run --all-packages --locked python -m unittest discover -s tests -v
uv run --all-packages --locked ruff format --check .
uv run --all-packages --locked ruff check .
```

Die [Tests](../tests/) simulieren HTTP, DNS, Keyring und `.env` und prüfen Mapping,
Templates, Medienzugriff, Veröffentlichung und Wiederherstellung. Der
[Installationstest](../tests/test_package_assets.py) prüft Paketdaten außerhalb des
Checkouts. [GitHub Actions](../README.md#continuous-integration) führt die Suite
mit Python 3.12/3.13, Ruff sowie CodeQL mit `security-and-quality` aus.

## Lizenz

Open Source unter der [GNU Affero General Public License 3.0 (AGPL-3.0)](../LICENSE).
