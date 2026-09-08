"""Explicit local recovery; never creates, deletes or queries remote content."""
from importlib import import_module

import click

from kulturbytes_common.publications import describe_attempt, get_attempt, list_attempts, resolve_attempt, STATES

PLATFORMS = click.Choice(['facebook', 'instagram', 'mastodon'])


@click.group('attempts')
def attempts_command() -> None:
    """Veröffentlichungsjournal prüfen und ungeklärte Versuche auflösen."""


@attempts_command.command('list')
@click.option('--platform', type=PLATFORMS, required=True)
@click.option('--state', type=click.Choice(STATES), default=None, help='Nach Zustand filtern.')
@click.option('--active', is_flag=True, help='Nur reserved, publishing und remote_succeeded.')
@click.option('--date-uuid', default=None, help='Nur Versuche dieses Termins.')
@click.option('--limit', type=click.IntRange(min=0), default=50, show_default=True, help='Neueste N Versuche; 0 zeigt alle.')
def show_attempts(platform: str, state: str | None, active: bool, date_uuid: str | None, limit: int) -> None:
    """Versuche einschließlich Remote-IDs anzeigen (nur lokale Daten)."""
    module = import_module(f'kulturbytes_{platform}.cli')
    conn = module.init_database()
    try:
        rows = list_attempts(conn, state=state, active=active, date_uuid=date_uuid, limit=limit)
        for row in rows:
            click.echo(describe_attempt(row))
        if not rows:
            click.echo('Keine Veröffentlichungsversuche vorhanden.')
    finally:
        conn.close()


@attempts_command.command('resolve')
@click.option('--platform', type=PLATFORMS, required=True)
@click.argument('attempt_uuid')
@click.option('--outcome', type=click.Choice(['published', 'failed']), required=True)
@click.option('--remote-id', default=None, help='Bereits vorhandene Post-ID nach manueller Plattformprüfung.')
@click.option('--remote-url', default=None, help='Optionale vorhandene Mastodon-Status-URL.')
def resolve(platform: str, attempt_uuid: str, outcome: str, remote_id: str | None, remote_url: str | None) -> None:
    """Erst laufenden Publisher stoppen und Ergebnis auf der Plattform prüfen.

    published repariert lokale Daten für einen bestehenden Post. failed gibt
    einen Versuch nur frei, wenn sicher kein Post erstellt wurde.
    """
    module = import_module(f'kulturbytes_{platform}.cli')
    conn = module.init_database()
    try:
        attempt = get_attempt(conn, attempt_uuid)
        click.echo(describe_attempt(attempt))
        if not click.confirm('Publisher gestoppt, Plattform manuell geprüft und dieses Ergebnis sicher bestätigt?', default=False):
            click.echo('Unverändert.')
            return

        def finalize(event: dict, post_id: str, post_url: str | None) -> None:
            if platform == 'mastodon':
                module.remember_post(conn, event, post_id, post_url, commit=False)
            else:
                module.remember_post(conn, event, post_id, commit=False)

        resolve_attempt(conn, attempt_uuid, outcome, finalize, remote_id=remote_id, remote_url=remote_url)
        click.echo('Versuch aufgelöst; keine Remote-Anfrage ausgeführt.')
    finally:
        conn.close()
