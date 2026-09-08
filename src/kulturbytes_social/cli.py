"""Public CLI; platform implementations remain in their workspace packages."""

import click

from kulturbytes_facebook import facebook_command
from kulturbytes_instagram import instagram_command
from kulturbytes_mastodon import mastodon_command


@click.group()
def cli() -> None:
    """Kulturbytes-Veranstaltungen auf sozialen Plattformen veröffentlichen."""


cli.add_command(facebook_command)
cli.add_command(mastodon_command)
cli.add_command(instagram_command)
