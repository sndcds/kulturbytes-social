"""Publisher adapters own platform details, never API routes or database state."""
from dataclasses import dataclass
from typing import Protocol, Any
import click
import httpx
from kulturbytes_common.errors import PlatformAuthenticationError, InvalidEvent
from kulturbytes_common.media import get_image_url
from kulturbytes_facebook import publisher as facebook
from kulturbytes_instagram import publisher as instagram
from kulturbytes_mastodon import publisher as mastodon


@dataclass(frozen=True)
class Prepared:
    text: str
    image_url: str | None


class Publisher(Protocol):
    def authenticate(self) -> Any: ...
    def prepare(self, client: httpx.Client, event: dict, *, config: Any = None) -> Prepared: ...
    def target(self, config: Any) -> str: ...
    def publish(self, client: httpx.Client, config: Any, event: dict, prepared: Prepared) -> tuple[str, str | None]: ...


class FacebookPublisher:
    def authenticate(self) -> facebook.FacebookConfig:
        return facebook.authenticate(allow_prompt=False)

    def prepare(self, client: httpx.Client, event: dict, *, config: facebook.FacebookConfig | None = None) -> Prepared:
        return Prepared(facebook.build_message(event), get_image_url(event))

    def target(self, config: facebook.FacebookConfig) -> str:
        return config.page_id

    def publish(self, client: httpx.Client, config: facebook.FacebookConfig, event: dict, prepared: Prepared) -> tuple[str, str | None]:
        publish = facebook.publish_facebook_photo if prepared.image_url else facebook.publish_text_post
        return publish(client, event, config=config, message=prepared.text), None


class InstagramPublisher:
    def authenticate(self) -> instagram.InstagramConfig:
        return instagram.authenticate()

    def prepare(self, client: httpx.Client, event: dict, *, config: instagram.InstagramConfig | None = None) -> Prepared:
        return Prepared(instagram.build_instagram_caption(event), instagram.validate_image(client, event))

    def target(self, config: instagram.InstagramConfig) -> str:
        return config.user_id

    def publish(self, client: httpx.Client, config: instagram.InstagramConfig, event: dict, prepared: Prepared) -> tuple[str, str | None]:
        return instagram.publish_instagram_photo(client, config, prepared.image_url, prepared.text), None


class MastodonPublisher:
    def authenticate(self) -> mastodon.MastodonConfig:
        config = mastodon.load_config()
        mastodon.check_auth(config)
        return config

    def prepare(self, client: httpx.Client, event: dict, *, config: mastodon.MastodonConfig | None = None) -> Prepared:
        limit = mastodon.get_status_limit(client, config.base_url if config else mastodon.load_base_url())
        return Prepared(mastodon.build_mastodon_message(event, max_length=limit), get_image_url(event))

    def target(self, config: mastodon.MastodonConfig) -> str:
        return config.base_url

    def publish(self, client: httpx.Client, config: mastodon.MastodonConfig, event: dict, prepared: Prepared) -> tuple[str, str | None]:
        return mastodon.publish_mastodon_status(client, event, message=prepared.text, config=config)


class PlatformService:
    def __init__(self, registry: dict[str, Publisher] | None = None) -> None:
        self.registry = registry if registry is not None else {
            'facebook': FacebookPublisher(), 'instagram': InstagramPublisher(), 'mastodon': MastodonPublisher()}

    def authenticate(self, platform: str) -> Any:
        try:
            return self.registry[platform].authenticate()
        except Exception:
            raise PlatformAuthenticationError() from None

    def prepare(self, platform: str, client: httpx.Client, event: dict, *, config: Any = None) -> Prepared:
        try:
            return self.registry[platform].prepare(client, event, config=config)
        except (click.ClickException, ValueError, httpx.HTTPError):
            raise InvalidEvent('Die Plattform-Vorschau konnte nicht erstellt werden. Metadaten und Bild prüfen.') from None
