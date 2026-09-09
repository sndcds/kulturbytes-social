"""Pluto processing is requested remotely through source-scoped image URLs."""

from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import click
import httpx
from canonical_support import canonical
from dotenv_support import IsolatedEnvironmentTestCase
from pydantic import ValidationError
from test_publishers import EVENT

from kulturbytes_common.image_urls import ImageSettings, image_url
from kulturbytes_common.media import download_post_image
from kulturbytes_common.network import MediaPolicy
from kulturbytes_common.rendering import render_post
from kulturbytes_common.sources.loader import load_source
from kulturbytes_common.sources.models import ContentItem


class ImageURLTests(TestCase):
    def test_strict_configuration(self):
        for value in (
            {"max_width": True},
            {"max_height": 0},
            {"max_width": "1920"},
            {"max_width": 65536},
            {"type": {"facebook": "gif"}},
            {"ratio": {"facebook": "0/5"}},
            {"ratio": {"facebook": "4/0"}},
            {"ratio": {"facebook": "nan"}},
            {"ratio": {"facebook": "1/99999"}},
            {"ratio": {"facebook": "4/5"}, "max_height": 1},
            {"ratio": {"facebook": "1200/630"}, "max_width": 1},
            {"unknown": True},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                MediaPolicy.model_validate({"image": value})
        for value in (0, -1, True, "100"):
            with self.assertRaises(ValidationError):
                ContentItem(title="Test", image_width=value)

    def test_platform_parameters_and_free_orientation(self):
        settings = load_source("kulturbytes").definition.media.image
        cases = [
            (
                "instagram",
                2400,
                1600,
                {"ratio": ["4:5"], "height": ["1920"], "type": ["jpg"]},
            ),
            (
                "facebook",
                2400,
                1600,
                {"ratio": ["1200:630"], "width": ["1920"], "type": ["webp"]},
            ),
            ("mastodon", 2400, 1600, {"width": ["1920"], "type": ["jpg"]}),
            ("mastodon", 1600, 2400, {"height": ["1920"], "type": ["jpg"]}),
        ]
        for platform, width, height, expected in cases:
            with self.subTest(platform=platform, width=width):
                result = image_url(
                    "https://example.org/image", settings, platform, width, height
                )
                self.assertEqual(parse_qs(urlsplit(result).query), expected)

    def test_query_replacement_and_opt_in(self):
        url = "https://example.org/image?width=5&width=6&height=7&ratio=1:1&fit=cover&type=png&quality=90&x=1&x=2"
        settings = ImageSettings(
            ratio={"test": "free"}, type={"test": "webp"}, max_width=100
        )
        result = image_url(url, settings, "test")
        self.assertEqual(
            parse_qs(urlsplit(result).query),
            {"width": ["100"], "type": ["webp"], "quality": ["90"], "x": ["1", "2"]},
        )
        self.assertEqual(image_url(url, None, "test"), url)
        self.assertEqual(image_url(url, ImageSettings(), "test"), url)
        self.assertIsNone(image_url(None, settings, "test"))
        with self.assertRaises(click.ClickException):
            image_url(url, ImageSettings(max_width=100, max_height=100), "test")


class ImageIntegrationTests(IsolatedEnvironmentTestCase):
    def test_render_download_and_private_policy(self):
        event = {
            **EVENT,
            "images": {
                "main": {
                    "url": "https://api.kulturbytes.de/image",
                    "width": 2400,
                    "height": 1600,
                }
            },
        }
        item = canonical(event)
        self.assertEqual((item.image_width, item.image_height), (2400, 1600))
        seen = []

        def respond(request):
            seen.append(request)
            return httpx.Response(
                200,
                content=b"remote-transformed-image",
                headers={"Content-Type": "image/jpg"},
            )

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            for platform in ("facebook", "mastodon", "instagram"):
                post = render_post(item, platform)
                self.assertNotIn("media_policy", post.model_dump())
                content, content_type, filename = download_post_image(client, post)
                self.assertEqual(content, b"remote-transformed-image")
                self.assertEqual(content_type, "image/jpeg")
                self.assertTrue(filename.endswith(".jpg"))
                self.assertEqual(str(seen[-1].url), post.image_url)
                self.assertNotIn("Authorization", seen[-1].headers)
                download_post_image(client, item, platform=platform)
                self.assertEqual(str(seen[-1].url), post.image_url)
        self.assertEqual(item.image_url, event["images"]["main"]["url"])
        with patch("kulturbytes_common.media.media_response") as response:
            bad = item.model_copy(update={"image_width": None})
            with httpx.Client() as client, self.assertRaises(click.ClickException):
                download_post_image(client, bad, platform="mastodon")
            response.assert_not_called()
