"""Operator recovery through the backend; never calls social platforms."""
from uuid import UUID
import click
from kulturbytes_social.client import APIClient

PLATFORMS = click.Choice(['facebook', 'instagram', 'mastodon'])
STATES = ['reserved', 'publishing', 'remote_succeeded', 'published', 'failed', 'cancelled']


def describe(attempt: dict) -> str:
    return ' · '.join(str(attempt.get(key) or '-') for key in
                     ('id', 'platform', 'state', 'date_uuid', 'mutation_stage', 'target_ref', 'content_sha256', 'remote_id', 'remote_url'))


@click.group('attempts')
def attempts_command() -> None:
    """Veröffentlichungsjournal auf dem Backend prüfen und auflösen."""


@attempts_command.command('list')
@click.option('--platform', type=PLATFORMS, required=True)
@click.option('--state', type=click.Choice(STATES))
@click.option('--active', is_flag=True)
@click.option('--date-uuid')
@click.option('--limit', type=click.IntRange(0, 1000), default=50, show_default=True)
def show_attempts(**params) -> None:
    with APIClient() as api:
        rows = api.get('publication-attempts', **params)
    for row in rows:
        click.echo(describe(row))
    if not rows:
        click.echo('Keine Veröffentlichungsversuche vorhanden.')


@attempts_command.command('resolve')
@click.option('--platform', type=PLATFORMS, required=True)
@click.argument('attempt_uuid', type=click.UUID)
@click.option('--outcome', type=click.Choice(['published', 'failed', 'cancelled']), required=True)
@click.option('--remote-id')
@click.option('--remote-url')
def resolve(platform: str, attempt_uuid: UUID, outcome: str, remote_id: str | None, remote_url: str | None) -> None:
    """Publisher zuerst stoppen und Ergebnis auf der Plattform manuell prüfen."""
    with APIClient() as api:
        attempt = api.get(f'publication-attempts/{attempt_uuid}')
        if attempt['platform'] != platform:
            raise click.ClickException('Der Versuch gehört zu einer anderen Plattform.')
        click.echo(describe(attempt))
        if not click.confirm('Publisher gestoppt, Plattform manuell geprüft und dieses Ergebnis sicher bestätigt?', default=False):
            click.echo('Unverändert.')
            return
        api.post(f'publication-attempts/{attempt_uuid}/resolve',
                 dict(outcome=outcome, remote_id=remote_id, remote_url=remote_url, confirmed=True))
        click.echo('Versuch aufgelöst; keine Anfrage an eine soziale Plattform ausgeführt.')
