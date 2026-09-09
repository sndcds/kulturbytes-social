"""Central sandboxed presentation and safe re-rendering under platform constraints."""

import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from jinja2 import StrictUndefined, TemplateError, meta, nodes
from jinja2.sandbox import SandboxedEnvironment

from kulturbytes_common.events import normalize_hashtag
from kulturbytes_common.formatting import strip_markdown
from kulturbytes_common.sources.errors import TemplateRenderingError
from kulturbytes_common.sources.loader import NAME
from kulturbytes_common.sources.models import RenderedPost, SocialItem
from kulturbytes_common.sources.paths import config_roots


def hashtags(
    values: list[str], *, city: str | None = None, priority=(), limit: int | None = None
) -> str:
    tags = []
    seen = set()
    for value in [*values, city]:
        tag = normalize_hashtag(value or "")
        if tag and tag.casefold() not in seen:
            tags.append(tag)
            seen.add(tag.casefold())
    required = [normalize_hashtag(value or "") for value in priority]
    ordered = [
        tag
        for required_tag in required
        if required_tag
        for tag in tags
        if tag.casefold() == required_tag.casefold()
    ]
    ordered += [tag for tag in tags if tag not in ordered]
    return " ".join(ordered[:limit] if limit else ordered)


def trim_summary(summary: str, available: int) -> str:
    if len(summary) <= available:
        return summary
    end = 0
    for word in re.finditer(r"\S+", summary):
        if word.end() + 1 > available:
            break
        end = word.end()
    return summary[:end] + "…" if end else ""


class ContentSandbox(SandboxedEnvironment):
    def is_safe_attribute(self, obj, attr, value):
        return False

    def is_safe_callable(self, obj):
        return False


class TemplateRenderer:
    def __init__(self, roots: list[Path] | None = None):
        self.roots = config_roots("templates") if roots is None else roots
        self.environment = ContentSandbox(
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.environment.globals.clear()
        filters = self.environment.filters
        defaults = {
            name: filters[name]
            for name in ("default", "join", "trim", "lower", "upper")
        }
        filters.clear()
        filters.update(
            defaults,
            hashtags=hashtags,
            plain=strip_markdown,
            dateformat=lambda value: date.fromisoformat(value).strftime("%d.%m.%Y"),
        )
        self.environment.tests.clear()
        self.environment.tests["none"] = lambda value: value is None

    def template(self, source: str, platform: str):
        if not NAME.fullmatch(source) or platform not in (
            "facebook",
            "instagram",
            "mastodon",
        ):
            raise TemplateRenderingError("Ungültige Template-Auswahl.")
        for name in (source, "default"):
            for root in self.roots:
                path = root / name / f"{platform}.j2"
                if not path.exists():
                    continue
                if not path.resolve().is_relative_to(root.resolve()):
                    raise TemplateRenderingError(
                        "Template außerhalb des Konfigurationsverzeichnisses."
                    )
                try:
                    code = path.read_text(encoding="utf-8")
                    tree = self.environment.parse(code)
                    if (
                        meta.find_undeclared_variables(tree)
                        - SocialItem.model_fields.keys()
                    ):
                        raise TemplateRenderingError(
                            "Template enthält unbekannte Variablen."
                        )
                    if any(
                        tree.find_all(
                            (
                                nodes.Include,
                                nodes.Import,
                                nodes.FromImport,
                                nodes.Extends,
                            )
                        )
                    ):
                        raise TemplateRenderingError(
                            "Template-Includes und Imports sind nicht erlaubt."
                        )
                    return self.environment.from_string(code)
                except (OSError, UnicodeError, TemplateError):
                    raise TemplateRenderingError(
                        f"Quelle {source}: ungültiges {platform}-Template."
                    ) from None
        raise TemplateRenderingError(
            f"Quelle {source}: kein {platform}-Template oder Default vorhanden."
        )

    def validate(self, source: str) -> None:
        for platform in ("facebook", "instagram", "mastodon"):
            self.template(source, platform)

    def render(
        self,
        item: SocialItem,
        platform: str,
        *,
        source: str = "kulturbytes",
        max_length: int | None = None,
    ) -> RenderedPost:
        template = self.template(source, platform)
        values = item.model_dump()
        if platform != "facebook":
            for field in (
                "title",
                "subtitle",
                "text",
                "venue",
                "city",
                "address",
                "organizer",
            ):
                values[field] = strip_markdown(values[field] or "")

        def compose(context: dict) -> str:
            try:
                return template.render(**context).strip()
            except (TemplateError, ValueError, TypeError, OverflowError):
                raise TemplateRenderingError(
                    f"Quelle {source}: {platform}-Template konnte nicht gerendert werden."
                ) from None

        limit = (
            2200
            if platform == "instagram"
            else (max_length or 500)
            if platform == "mastodon"
            else None
        )
        if limit is None:
            text = compose(values)
        else:
            context = {**values, "text": None}
            optional = (
                ("subtitle", "price", "ticket_link", "organizer")
                if platform == "mastodon"
                else ()
            )
            for field in optional:
                context[field] = None
            fixed = compose(context)
            if len(fixed) > limit:
                raise TemplateRenderingError(
                    f"{platform.title()}: Titel/Metadaten ohne Beschreibung überschreiten das Instanzlimit von {limit} Zeichen."
                )
            for field in optional:
                candidate = {**context, field: values[field]}
                rendered = compose(candidate)
                if len(rendered) <= limit:
                    context, fixed = candidate, rendered
            available = limit - len(fixed) - 2
            summary = values.get("text") or ""
            text = fixed
            while summary and available > 1:
                shortened = (
                    trim_summary(summary, available)
                    if platform == "mastodon"
                    else (
                        summary
                        if len(summary) <= available
                        else summary[: available - 1].rstrip() + "…"
                    )
                )
                if not shortened:
                    break
                candidate = compose({**context, "text": shortened})
                if len(candidate) <= limit:
                    text = candidate
                    break
                available -= max(1, len(candidate) - limit)
            # Custom templates remain responsible for including protected content.
            priority = (
                ["Kulturbytes", values["city"]] if platform == "instagram" else []
            )
            protected_tags = hashtags(
                values["tags"],
                city=values["city"],
                priority=priority,
                limit=5 if platform == "instagram" else None,
            ).split()
            if item.link and item.link not in text:
                raise TemplateRenderingError(
                    f"{platform.title()}: Pflicht-Link fehlt im Template."
                )
            tokens = set(re.findall(r"(?<!\w)#[\w]+", text))
            if not set(protected_tags).issubset(tokens):
                raise TemplateRenderingError(
                    f"{platform.title()}: vollständige Hashtags fehlen im Template."
                )
            if platform == "instagram" and len(tokens) > 5:
                raise TemplateRenderingError(
                    "Instagram: maximal fünf Hashtags erlaubt."
                )
        return RenderedPost(
            text=text,
            image_url=item.image_url,
            image_alt=item.image_alt or f"Bild zu {item.title}",
            image_name=item.image_name or "image",
        )


@lru_cache(maxsize=8)
def _renderer(roots: tuple[Path, ...]) -> TemplateRenderer:
    return TemplateRenderer(list(roots))


def render_post(
    item: SocialItem, platform: str, *, max_length: int | None = None
) -> RenderedPost:
    source = item._origin.source if item._origin else "default"
    return _renderer(tuple(config_roots("templates"))).render(
        item, platform, source=source, max_length=max_length
    )
