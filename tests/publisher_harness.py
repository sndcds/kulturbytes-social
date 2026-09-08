"""Test-only entry point for isolated publisher/auth regression tests."""
import click
import httpx
from kulturbytes_common.credentials import credential_options
from kulturbytes_facebook import publisher as facebook
from kulturbytes_instagram import publisher as instagram
from kulturbytes_mastodon import publisher as mastodon

@click.group()
def cli():
    pass

def command(platform):

    @click.command(platform)
    @click.option('--check-auth', 'check_auth_only', is_flag=True)
    @click.option('--resolve-page-token', is_flag=True)
    @click.option('--dry-run/--publish', default=True)
    @click.option('--city')
    @click.option('--limit', type=int)
    @click.option('--include-published', is_flag=True)
    @click.option('--event-uuid')
    @click.option('--date-identifier')
    @credential_options(platform.title())
    def run(check_auth_only, resolve_page_token, dry_run, **kwargs):
        module = {'facebook': facebook, 'instagram': instagram, 'mastodon': mastodon}[platform]
        if platform == 'facebook':
            config = module.authenticate(force=resolve_page_token, allow_prompt=True)
        elif platform == 'instagram':
            config = module.authenticate()
        else:
            config = module.load_config()
            module.check_auth(config)
        if not dry_run and (not check_auth_only) and (not resolve_page_token):
            from test_publishers import EVENT
            from test_instagram import EVENT as IG_EVENT
            with httpx.Client() as client:
                if platform == 'facebook':
                    module.publish_text_post(client, EVENT, config=config)
                elif platform == 'instagram':
                    image = module.validate_image(client, IG_EVENT)
                    module.publish_instagram_photo(client, config, image, module.build_instagram_caption(IG_EVENT))
    return run
for platform in ('facebook', 'instagram', 'mastodon'):
    cli.add_command(command(platform))
