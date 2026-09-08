# Mastodon

Kulturbytes-Termine über die Click-CLI auswählen und vom FastAPI-Backend veröffentlichen.
Das Journal liegt ausschließlich in der gemeinsamen PostgreSQL-Datenbank.
[Backend einrichten](../README.md#installation-und-start).

```bash
uv run kulturbytes-social mastodon
uv run kulturbytes-social mastodon --city Flensburg --publish
uv run kulturbytes-social mastodon --event-uuid EVENT_UUID --date-identifier DATE_UUID
uv run kulturbytes-social mastodon --check-auth
```

Standard ist die Vorschau; je Veröffentlichung wird lokal bestätigt. `--include-published`
fordert eine zusätzliche Bestätigung auch in der Vorschau. Bereits bestehende aktive oder
ungeklärte Versuche bleiben gesperrt. Wiederholungen erhalten die bisherige Historie.

## Server-Konfiguration

```dotenv
MASTODON_BASE_URL=https://norden.social
MASTODON_ACCESS_TOKEN=
```

Die Standard-Instanz ist `https://norden.social`. Alternative Instanzen werden als HTTP(S)-Origin
ohne Pfad, Query, Fragment oder Zugangsdaten konfiguriert. `.env` hat Vorrang vor Environment;
für das Secret folgt der OS-Keyring. Die CLI braucht bei Fernzugriff nur Backend-Adresse
und API-Token. Der Server fragt nicht interaktiv nach Zugangsdaten.

Der Mastodon-Token benötigt `write:statuses` und für Bilder `write:media` oder umfassendere
Scopes. `--check-auth` führt serverseitig `GET /api/v1/accounts/verify_credentials` aus,
ohne Posts, Medien oder Publikationsdaten anzulegen.
[Mastodon Status API](https://docs.joinmastodon.org/methods/statuses/),
[Media API](https://docs.joinmastodon.org/methods/media/).

## Text und Bild

Details werden nach Auswahl aus `/api/events` nachgeladen. Eine nichtleere Listen-Summary
hat Vorrang vor der Detail-Description, Detail-Summary wird ignoriert. Der Adapter normalisiert
Markdown und ergänzt Datum, Ort, Kulturbytes-Link und Hashtags einschließlich Kulturbytes
und Stadt. Veranstaltungszeiten verwenden `Europe/Berlin`.

Der Server fragt `/api/v2/instance` für das Zeichenlimit ab, mit 500 als Fallback.
Die bestehende Komposition kürzt zuerst die Summary, entfernt optionale Metadaten/Tags
nur vollständig und schützt Kulturbytes-URL sowie Pflicht-Hashtags. Zu lange Pflichtdaten
werden abgelehnt. Die Zählung verwendet weiterhin Python-`len()`; serverseitige URL-Gewichtung
wird nicht modelliert. Dadurch kann der Text konservativer gekürzt werden als nötig.

Ein Detail-Hauptbild wird mit DNS-Pinning, HTTPS-Allowlist und erneuter Redirect-Prüfung
heruntergeladen und mit Alt-Text via `/api/v2/media` hochgeladen (`mastodon_media`).
Alt-Text stammt aus `images.main.alt`, ersatzweise „Veranstaltungsbild zu {title}“.
Das bestehende Medien-Polling prüft bis zu zehnmal und warnt bei ausbleibender Bereitschaft;
es fährt danach fort. Diese Plattformgrenze bleibt bestehen. Der Status-POST an
`/api/v1/statuses` verwendet `public` und die Phase `mastodon_status`.

## Journal

Die Sperre gilt je `mastodon + date_uuid`. Post-ID und bereinigte optionale Status-URL werden
nach Remote-Erfolg vor der atomaren Finalisierung gespeichert. Unklare POST-Ergebnisse
bleiben gesperrt und werden nicht automatisch wiederholt.

```bash
uv run kulturbytes-social attempts list --platform mastodon --active
uv run kulturbytes-social attempts resolve ATTEMPT_UUID --platform mastodon --outcome published --remote-id STATUS_ID --remote-url https://norden.social/@konto/STATUS_ID
```

Vor Auflösung Publisher stoppen und Konto manuell prüfen. Eine bereits bestätigte Remote-ID
wird nicht überschrieben; Auflösung führt keine Social-Anfrage aus.
[Zentrale Betriebs- und Testdokumentation](../README.md).
