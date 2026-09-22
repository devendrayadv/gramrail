import hashlib
import json
import math
import re
import uuid
from typing import Any

from .errors import InvalidInput

SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def ident() -> str:
    return uuid.uuid4().hex


def canonical(value: Any, limit: int = 262144) -> str:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InvalidInput("Value must be finite, JSON-compatible data.") from exc
    if len(text.encode()) > limit:
        raise InvalidInput(f"JSON exceeds the {limit}-byte limit.")
    return text


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def finite(value: float, name: str) -> float:
    if not math.isfinite(value):
        raise InvalidInput(f"{name} must be a finite number.")
    return value


def slug(value: str) -> str:
    if not SLUG.fullmatch(value):
        raise InvalidInput("Use a lowercase name starting with a letter (up to 64 characters).")
    return value
