"""Interactive HTTP client; publication rules and persistence live on the server."""
from urllib.parse import quote
import click
from kulturbytes_common.credentials import credential_options
from kulturbytes_common.selection import select_events
from kulturbytes_social.client import APIClient
from kulturbytes_social.attempts import attempts_command


@click.group()
def cli() -> None:
    """Kulturbytes-Veranstaltungen über das Social-Backend veröffentlichen."""


def platform_command(platform: str) -> click.Command:
    @click.command(platform)
    @click.option('--dry-run/--publish', default=True, help='Vorschau (Standard) oder nach Bestätigung veröffentlichen.')
    @click.option('--city', default=None)
    @click.option('--limit', type=click.IntRange(0, 1000), default=50, show_default=True, help='0 zeigt alle Termine.')
    @click.option('--include-published', is_flag=True)
    @click.option('--event-uuid', default=None)
    @click.option('--date-identifier', default=None)
    @click.option('--check-auth', 'check_auth_only', is_flag=True, help='Plattformzugang auf dem Backend prüfen.')
    @credential_options(platform.title())
    def command(dry_run: bool, city: str | None, limit: int, include_published: bool,
                event_uuid: str | None, date_identifier: str | None, check_auth_only: bool,
                resolve_page_token: bool = False) -> None:
        if not (check_auth_only or resolve_page_token) and bool(event_uuid) != bool(date_identifier):
            raise click.UsageError('--event-uuid und --date-identifier müssen gemeinsam angegeben werden.')
        with APIClient() as api:
            if check_auth_only or resolve_page_token:
                api.post(f'platforms/{platform}/check-auth')
                click.echo(f'✓ {platform.title()}: Backend-Zugang gültig.')
                return
            filters = dict(platform=platform, city=city, include_published=include_published)
            if event_uuid:
                selected = [api.get(f'events/{quote(event_uuid, safe="")}/dates/{quote(date_identifier, safe="")}', **filters)['summary']]
            else:
                selected = select_events(api.get('events', limit=limit, **filters))
            failures = False
            for event in selected:
                try:
                    if event.get('published') and not click.confirm('Dieser Termin wurde bereits veröffentlicht. Trotzdem fortfahren?', default=False):
                        continue
                    body = dict(platform=platform, event_uuid=event['uuid'], date_identifier=event['date_slug'],
                                city=city, force_repeat=include_published)
                    preview = api.post('publications/preview', body)
                    click.echo('\n' + preview['text'])
                    click.echo('Bild: ' + (preview['image_url'] or 'kein Bild'))
                    click.echo(f"Termin: {event['date_uuid']} · {event['date_slug']}")
                    if dry_run:
                        click.echo('DRY RUN: Es wurde nichts veröffentlicht.')
                        continue
                    if not click.confirm(f'Diesen Termin jetzt auf {platform.title()} veröffentlichen?', default=False):
                        continue
                    result = api.post('publications', {**body, 'expected_content_sha256': preview['content_sha256']})
                    click.echo(f"✓ Veröffentlicht: {result['remote_id']} · Versuch {result['attempt_id']}")
                except click.ClickException as exc:
                    if event_uuid:
                        raise
                    exc.show()
                    failures = True
            if failures:
                raise click.ClickException('Mindestens ein ausgewählter Termin ist fehlgeschlagen.')
    if platform == 'facebook':
        command.params.append(click.Option(['--resolve-page-token'], is_flag=True,
            help='Facebook-Zugang auf dem Backend prüfen und bei Bedarf auflösen.'))
    return command


for _platform in ('facebook', 'instagram', 'mastodon'):
    cli.add_command(platform_command(_platform))
cli.add_command(attempts_command)
