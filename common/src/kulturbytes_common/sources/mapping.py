from jmespath.parser import ParsedResult
from pydantic import ValidationError

from .errors import SourceMappingError, SourceValidationError
from .models import ContentItem
from .rules import evaluate


def map_item(
    name: str,
    expressions: dict[str, ParsedResult],
    raw: object,
    *,
    derived: dict | None = None,
) -> ContentItem:
    values = {}
    for field, expression in expressions.items():
        values[field] = evaluate(name, field, expression, raw)
    for field, parts in (derived or {}).items():
        chunks = [
            part if isinstance(part, str) else evaluate(name, field, part, raw)
            for part in parts
        ]
        if any(not isinstance(chunk, str) for chunk in chunks):
            raise SourceMappingError(
                f"Quelle {name}: concat für {field} benötigt Zeichenketten."
            )
        values[field] = "".join(chunks)
    try:
        return ContentItem.model_validate(values)
    except ValidationError as exc:
        # Only field names chosen from the fixed canonical schema, never Pydantic input values.
        fields = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors()}))
        raise SourceValidationError(
            f"Quelle {name}: ungültige Felder: {fields}."
        ) from None
