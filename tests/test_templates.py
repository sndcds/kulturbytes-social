import json
import tempfile
from pathlib import Path

from canonical_support import canonical as from_kulturbytes
from dotenv_support import IsolatedEnvironmentTestCase

from kulturbytes_common.rendering import TemplateRenderer
from kulturbytes_common.sources.errors import TemplateRenderingError
from kulturbytes_common.sources.models import ContentItem


class TemplateTests(IsolatedEnvironmentTestCase):
    def test_kulturbytes_golden_outputs(self):
        cases = json.loads(
            (Path(__file__).parent / "fixtures/kulturbytes_rendering.json").read_text()
        )
        renderer = TemplateRenderer()
        for case in cases:
            for platform in ("facebook", "instagram", "mastodon"):
                with self.subTest(case=case["name"], platform=platform):
                    self.assertEqual(
                        renderer.render(from_kulturbytes(case["event"]), platform).text,
                        case[platform],
                    )

    def test_minimal_optional_fields_and_canonical_context(self):
        for platform in ("facebook", "instagram", "mastodon"):
            rendered = TemplateRenderer().render(
                ContentItem(title="Minimal"), platform, source="arbitrary"
            )
            self.assertEqual(rendered.text, "Minimal")
            self.assertNotIn("None", rendered.text)

    def test_source_override_then_default_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ("special", "default"):
                (root / folder).mkdir()
            (root / "default/facebook.j2").write_text("Default: {{ title }}")
            (root / "special/facebook.j2").write_text("Special: {{ title | upper }}")
            renderer = TemplateRenderer([root])
            self.assertEqual(
                renderer.render(
                    ContentItem(title="Title"), "facebook", source="special"
                ).text,
                "Special: TITLE",
            )
            self.assertEqual(
                renderer.render(
                    ContentItem(title="Title"), "facebook", source="other"
                ).text,
                "Default: Title",
            )
            with self.assertRaises(TemplateRenderingError):
                renderer.render(ContentItem(title="Title"), "instagram")

    def test_unsafe_globals_attributes_and_includes_are_unavailable(self):
        cases = [
            "{{ os.environ }}",
            "{{ environment }}",
            "{{ cycler.__init__.__globals__ }}",
            "{{ title.__class__.__mro__ }}",
            "{{ _source_context }}",
            '{% include "/etc/passwd" %}',
            '{% import "secret.j2" as secret %}',
            "{{ title.upper() }}",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "default").mkdir()
            path = root / "default/facebook.j2"
            renderer = TemplateRenderer([root])
            for code in cases:
                path.write_text(code)
                with (
                    self.subTest(code=code),
                    self.assertRaises(TemplateRenderingError) as error,
                ):
                    renderer.render(ContentItem(title="sensitive-content"), "facebook")
                self.assertNotIn("sensitive-content", str(error.exception))
            with self.assertRaises(TemplateRenderingError):
                renderer.template("../outside", "facebook")

    def test_template_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "templates/default").mkdir(parents=True)
            (root / "secret.j2").write_text("secret")
            (root / "templates/default/facebook.j2").symlink_to(root / "secret.j2")
            with self.assertRaises(TemplateRenderingError):
                TemplateRenderer([root / "templates"]).template("default", "facebook")

    def test_custom_template_limits_rerender_text_and_preserve_footer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "default").mkdir()
            (root / "default/mastodon.j2").write_text(
                '{{ title }}\n{{ (text or "") }} {{ (text or "") }}\n{{ link }}\n{{ tags | hashtags }}'
            )
            item = ContentItem(
                title="Title",
                text="long words " * 1000,
                link="https://example.org/event",
                tags=["WholeTag"],
            )
            result = TemplateRenderer([root]).render(item, "mastodon", max_length=120)
            self.assertLessEqual(len(result.text), 120)
            self.assertIn(item.link, result.text)
            self.assertTrue(result.text.endswith("#WholeTag"))
            (root / "default/mastodon.j2").write_text("{{ title }}")
            with self.assertRaises(TemplateRenderingError):
                TemplateRenderer([root]).render(item, "mastodon")

    def test_fixed_content_overflow_fails_instead_of_slicing(self):
        for platform in ("instagram", "mastodon"):
            with self.assertRaises(TemplateRenderingError):
                TemplateRenderer().render(
                    ContentItem(title="X" * 2400, link="https://example.org/full"),
                    platform,
                )

    def test_data_is_not_reinterpreted_as_jinja(self):
        text = "{{ os.environ }}"
        result = TemplateRenderer().render(ContentItem(title=text), "facebook")
        self.assertIn(text, result.text)
