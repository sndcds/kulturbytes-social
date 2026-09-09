from jmespath.exceptions import JMESPathError
from jmespath.parser import ParsedResult
from pydantic import ValidationError

from .errors import SourceMappingError, SourceValidationError
from .models import ContentItem


def map_item(
    name: str, expressions: dict[str, ParsedResult], raw: object
) -> ContentItem:
    values = {}
    for field, expression in expressions.items():
        try:
            values[field] = expression.search(raw)
        except JMESPathError:
            raise SourceMappingError(
                f"Quelle {name}: Mapping für {field} fehlgeschlagen."
            ) from None
    try:
        return ContentItem.model_validate(values)
    except ValidationError as exc:
        # Only field names chosen from the fixed canonical schema, never Pydantic input values.
        fields = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors()}))
        raise SourceValidationError(
            f"Quelle {name}: ungültige Felder: {fields}."
        ) from None
