"""Input validation and sanitization utilities.

Provides strict type checking, bounds validation, and pattern
matching for all external inputs to the trading system.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


class ValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(self, field: str, reason: str, value: Any | None = None):
        self.field = field
        self.reason = reason
        self.value = value
        super().__init__(f"Validation failed for '{field}': {reason}")


@dataclass(frozen=True)
class Bounds:
    """Numeric bounds for validation."""

    min_value: float | None = None
    max_value: float | None = None


@dataclass(frozen=True)
class StringRules:
    """String validation rules."""

    min_length: int = 0
    max_length: int = 1000
    pattern: str | None = None
    allowed_chars: str | None = None


class InputValidator:
    """Centralized input validation for trading system inputs.

    Validates order parameters, strategy configurations, API inputs,
    and any data crossing trust boundaries.
    """

    # Standard patterns
    SYMBOL_PATTERN = re.compile(r"^[A-Z0-9\-/]{1,20}$")
    UUID_PATTERN = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    ALPHANUM_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")

    @staticmethod
    def string(
        value: Any,
        name: str = "string",
        rules: StringRules | None = None,
        allow_empty: bool = False,
    ) -> str:
        """Validate a string input.

        Args:
            value: Input value.
            name: Field name for error messages.
            rules: Validation rules.
            allow_empty: Whether empty string is permitted.

        Returns:
            The validated string.

        Raises:
            ValidationError: If validation fails.
        """
        if not isinstance(value, str):
            raise ValidationError(name, f"Expected string, got {type(value).__name__}", value)

        if not allow_empty and len(value) == 0:
            raise ValidationError(name, "Empty string not allowed", value)

        rules = rules or StringRules()

        if len(value) < rules.min_length:
            raise ValidationError(name, f"Length {len(value)} < min {rules.min_length}", value)
        if len(value) > rules.max_length:
            raise ValidationError(name, f"Length {len(value)} > max {rules.max_length}", value)

        if rules.pattern and not re.match(rules.pattern, value):
            raise ValidationError(name, f"Pattern mismatch: {rules.pattern}", value)

        if rules.allowed_chars and any(c not in rules.allowed_chars for c in value):
            raise ValidationError(name, "Contains disallowed characters", value)

        return value

    @staticmethod
    def symbol(value: Any, name: str = "symbol") -> str:
        """Validate a trading symbol."""
        s = InputValidator.string(value, name, StringRules(min_length=1, max_length=20))
        if not InputValidator.SYMBOL_PATTERN.match(s):
            raise ValidationError(name, "Invalid symbol format", s)
        return s.upper()

    @staticmethod
    def number(
        value: Any,
        name: str = "number",
        bounds: Bounds | None = None,
        allow_zero: bool = True,
        allow_negative: bool = True,
    ) -> float:
        """Validate a numeric input.

        Args:
            value: Input value.
            name: Field name.
            bounds: Optional min/max bounds.
            allow_zero: Whether zero is permitted.
            allow_negative: Whether negative values are permitted.

        Returns:
            Validated float.
        """
        try:
            f = float(value)
        except (TypeError, ValueError):
            raise ValidationError(name, f"Not a number: {value!r}", value)

        if not allow_zero and f == 0:
            raise ValidationError(name, "Zero not allowed", value)
        if not allow_negative and f < 0:
            raise ValidationError(name, "Negative not allowed", value)

        bounds = bounds or Bounds()
        if bounds.min_value is not None and f < bounds.min_value:
            raise ValidationError(name, f"Value {f} < min {bounds.min_value}", value)
        if bounds.max_value is not None and f > bounds.max_value:
            raise ValidationError(name, f"Value {f} > max {bounds.max_value}", value)

        return f

    @staticmethod
    def positive_int(value: Any, name: str = "positive_int", max_value: int | None = None) -> int:
        """Validate a positive integer."""
        n = InputValidator.number(value, name, allow_zero=False, allow_negative=False)
        i = int(n)
        if i != n:
            raise ValidationError(name, f"Not an integer: {n}", value)
        if max_value is not None and i > max_value:
            raise ValidationError(name, f"Value {i} > max {max_value}", value)
        return i

    @staticmethod
    def quantity(value: Any, name: str = "quantity") -> Decimal:
        """Validate a trade quantity with Decimal precision."""
        try:
            d = Decimal(str(value))
        except Exception:
            raise ValidationError(name, f"Invalid quantity: {value!r}", value)
        if d <= 0:
            raise ValidationError(name, "Quantity must be positive", value)
        # Maximum 8 decimal places for crypto, 2 for equity
        if d.as_tuple().exponent < -8:
            raise ValidationError(name, "Too many decimal places", value)
        return d

    @staticmethod
    def price(value: Any, name: str = "price") -> Decimal:
        """Validate a price value."""
        try:
            d = Decimal(str(value))
        except Exception:
            raise ValidationError(name, f"Invalid price: {value!r}", value)
        if d <= 0:
            raise ValidationError(name, "Price must be positive", value)
        return d

    @staticmethod
    def percentage(value: Any, name: str = "percentage") -> float:
        """Validate a percentage (0.0 to 1.0)."""
        return InputValidator.number(value, name, bounds=Bounds(0.0, 1.0))

    @staticmethod
    def uuid(value: Any, name: str = "uuid") -> str:
        """Validate UUID format."""
        s = InputValidator.string(value, name, StringRules(min_length=36, max_length=36))
        if not InputValidator.UUID_PATTERN.match(s):
            raise ValidationError(name, "Invalid UUID format", s)
        return s

    @staticmethod
    def sanitize_string(value: str) -> str:
        """Remove potentially dangerous characters from a string.

        Strips control characters and null bytes.
        """
        return "".join(c for c in value if ord(c) >= 32 and c != "\x7f")

    @staticmethod
    def validate_dict(
        data: dict[str, Any],
        schema: dict[str, tuple[type, bool]],
    ) -> dict[str, Any]:
        """Validate a dictionary against a simple type schema.

        Args:
            data: Input dictionary.
            schema: Mapping of field name -> (expected_type, required).

        Returns:
            Validated data.

        Raises:
            ValidationError: If any field is invalid or missing.
        """
        validated: dict[str, Any] = {}
        for field, (expected_type, required) in schema.items():
            if field not in data:
                if required:
                    raise ValidationError(field, "Required field missing")
                continue
            val = data[field]
            if not isinstance(val, expected_type):
                raise ValidationError(
                    field,
                    f"Expected {expected_type.__name__}, got {type(val).__name__}",
                    val,
                )
            validated[field] = val
        # Check for unexpected fields
        for field in data:
            if field not in schema:
                raise ValidationError(field, "Unexpected field", data[field])
        return validated
