"""Generic entry point delegating to the existing authenticated platform flows."""

import click

from kulturbytes_common.sources.cli import DEFAULT_SOURCE
from kulturbytes_facebook import facebook_command
from kulturbytes_instagram import instagram_command
from kulturbytes_mastodon import mastodon_command

PLATFORMS = {
    "facebook": facebook_command,
    "instagram": instagram_command,
    "mastodon": mastodon_command,
}


@click.command("publish")
@click.option("--platform", type=click.Choice(tuple(PLATFORMS)), required=True)
@click.option("--source", default=DEFAULT_SOURCE, show_default=True)
@click.option("--item-id", default=None)
@click.option("--city", default=None)
@click.option("--limit", type=click.IntRange(min=0), default=50, show_default=True)
@click.option(
    "--dry-run/--publish",
    default=True,
    help="Vorschau oder nach Einzelbestätigung veröffentlichen.",
)
@click.option("--include-published", is_flag=True)
@click.pass_context
def publish_command(ctx: click.Context, platform: str, **options) -> None:
    """Konfigurierte Inhalte auf einer sozialen Plattform veröffentlichen."""
    ctx.invoke(PLATFORMS[platform], **options)
