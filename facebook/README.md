# Facebook Pages

Der Facebook-Adapter veröffentlicht Page-Beiträge aus Kulturbytes-Terminen. Bedienung erfolgt
über die HTTP-CLI; FastAPI übernimmt Veröffentlichung und PostgreSQL-Journal.
[Backend einrichten](../README.md#installation-und-start).

```bash
uv run kulturbytes-social facebook
uv run kulturbytes-social facebook --city Flensburg --publish
uv run kulturbytes-social facebook --event-uuid EVENT_UUID --date-identifier DATE_UUID
uv run kulturbytes-social facebook --check-auth
```

Die Vorschau benötigt auf dem Server keine Facebook-Zugangsdaten. `--publish` verlangt
pro Termin Bestätigung. `--include-published` benötigt eine weitere Bestätigung und
schreibt bei Erfolg einen neuen Eintrag in die gemeinsame PostgreSQL-Historie.

## Server-Konfiguration

```dotenv
META_SYSTEM_USER_ACCESS_TOKEN=
FACEBOOK_PAGE_ID=
FACEBOOK_GRAPH_API_VERSION=v26.0
```

`FACEBOOK_PAGE_ID` ist die numerische Page-ID. Die Versionsangabe ist der Projektstandard,
keine Aussage über die neueste Meta-Version. Ein passender System User muss Zugriff auf die
Page und die benötigten Berechtigungen haben. Für Page-Posts gehören dazu je nach App/Flow
`pages_show_list`, `pages_read_engagement` und `pages_manage_posts`.
[Meta Page Posts](https://developers.facebook.com/docs/pages-api/posts/).

Der gemeinsame Meta-Zugang hat Vorrang vor den weiterhin unterstützten Plattform-Credentials
`FACEBOOK_PAGE_ACCESS_TOKEN` und `FACEBOOK_USER_ACCESS_TOKEN`. `.env` hat Vorrang vor
Environment, danach folgt der OS-Keyring. Der Server fragt nie interaktiv nach Tokens.
Ein fehlender/abgelaufener Page-Zugang kann über den verfügbaren User-/System-Zugang
und `/me/accounts` exakt für die konfigurierte Page aufgelöst werden. Pagination verwendet
validierte Cursor. Fehler bei einem konfigurierten System-Zugang wechseln nicht still auf
einen anderen Zugang. Erfolgreich validierte Meta-Credentials aus Environment/Keyring können
in der serverseitigen `.env` gespeichert werden.

`--check-auth` und `--resolve-page-token` rufen den Backend-Check auf. Dieser führt nur
lesende Social-Anfragen aus und erstellt keine Versuche oder Publikationen. Lokale
`--credentials status|set|delete`-Befehle verwalten nur den OS-Keyring des ausführenden Rechners.

## Text und Bilder

Die Liste `/api/events` dient der Auswahl. Detaildaten werden immer nachgeladen. Die
nichtleere Listen-Summary hat Vorrang vor der Detail-Description; Detail-Summary wird ignoriert.
Datum, Ort, Veranstalter, Preis, Ticket-Link, Kulturbytes-Link und ganze Hashtags werden wie
bisher formatiert. Facebook übernimmt derzeit Markdown im Text; dessen Normalisierung
ist eine bestehende Formatierungsgrenze.

Mit `images.main.url` aus den Details wird das Bild über den gemeinsamen abgesicherten
Downloader geholt und über `/{PAGE_ID}/photos` mit Caption veröffentlicht. Ohne Hauptbild
wird `/{PAGE_ID}/feed` verwendet. Ein Fehler beim Bildabruf/Upload führt nicht zu einem
Text-Fallback. Es werden keine Facebook Events angelegt.

## Journal und Fehler

PostgreSQL sperrt je `facebook + date_uuid`. Die Phasen heißen `facebook_photo` und
`facebook_feed`. Der bestätigte Post-Identifier wird vor dem Abschluss dauerhaft gespeichert.
Ein Timeout nach einem POST bleibt ungeklärt; nicht ungeprüft erneut veröffentlichen.

```bash
uv run kulturbytes-social attempts list --platform facebook --active
uv run kulturbytes-social attempts resolve ATTEMPT_UUID --platform facebook --outcome published --remote-id POST_ID
```

Vor der Auflösung Publisher stoppen und Page manuell prüfen. Details zu API-Sicherheit,
Transaktionen und Cutover stehen in der [zentralen Dokumentation](../README.md).
