"""Tests for input validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from security.validation import Bounds, InputValidator, StringRules, ValidationError


class TestInputValidator(unittest.TestCase):
    """Tests for input validation."""

    def test_string_valid(self):
        """Valid string passes."""
        result = InputValidator.string("hello")
        self.assertEqual(result, "hello")

    def test_string_not_string(self):
        """Non-string raises error."""
        with self.assertRaises(ValidationError) as ctx:
            InputValidator.string(123, "field")
        self.assertEqual(ctx.exception.field, "field")

    def test_string_empty_not_allowed(self):
        """Empty string rejected by default."""
        with self.assertRaises(ValidationError):
            InputValidator.string("")

    def test_string_empty_allowed(self):
        """Empty string allowed with flag."""
        result = InputValidator.string("", allow_empty=True)
        self.assertEqual(result, "")

    def test_string_min_length(self):
        """Min length enforced."""
        with self.assertRaises(ValidationError):
            InputValidator.string("ab", rules=StringRules(min_length=3))

    def test_string_max_length(self):
        """Max length enforced."""
        with self.assertRaises(ValidationError):
            InputValidator.string("a" * 1001)

    def test_string_pattern(self):
        """Pattern enforced."""
        result = InputValidator.string("abc_123", rules=StringRules(pattern=r"^[a-z0-9_]+$"))
        self.assertEqual(result, "abc_123")

    def test_string_pattern_fail(self):
        """Pattern mismatch raises."""
        with self.assertRaises(ValidationError):
            InputValidator.string("ABC", rules=StringRules(pattern=r"^[a-z]+$"))

    def test_symbol_valid(self):
        """Valid trading symbol."""
        self.assertEqual(InputValidator.symbol("AAPL"), "AAPL")
        self.assertEqual(InputValidator.symbol("BTC-USD"), "BTC-USD")

    def test_symbol_invalid(self):
        """Invalid symbol format."""
        with self.assertRaises(ValidationError):
            InputValidator.symbol("INVALID@SYMBOL")

    def test_number_valid(self):
        """Valid number."""
        self.assertEqual(InputValidator.number(42), 42.0)
        self.assertEqual(InputValidator.number("3.14"), 3.14)

    def test_number_bounds(self):
        """Bounds enforced."""
        self.assertEqual(InputValidator.number(50, bounds=Bounds(0, 100)), 50.0)
        with self.assertRaises(ValidationError):
            InputValidator.number(150, bounds=Bounds(0, 100))

    def test_number_no_zero(self):
        """Zero rejected when configured."""
        with self.assertRaises(ValidationError):
            InputValidator.number(0, allow_zero=False)

    def test_number_no_negative(self):
        """Negative rejected when configured."""
        with self.assertRaises(ValidationError):
            InputValidator.number(-1, allow_negative=False)

    def test_positive_int(self):
        """Positive integer validation."""
        self.assertEqual(InputValidator.positive_int(42), 42)
        with self.assertRaises(ValidationError):
            InputValidator.positive_int(0)
        with self.assertRaises(ValidationError):
            InputValidator.positive_int(-1)
        with self.assertRaises(ValidationError):
            InputValidator.positive_int(3.14)

    def test_quantity_valid(self):
        """Valid quantity."""
        q = InputValidator.quantity(100.5)
        self.assertEqual(float(q), 100.5)

    def test_quantity_positive(self):
        """Quantity must be positive."""
        with self.assertRaises(ValidationError):
            InputValidator.quantity(-1)

    def test_price_valid(self):
        """Valid price."""
        p = InputValidator.price(150.25)
        self.assertEqual(float(p), 150.25)

    def test_price_positive(self):
        """Price must be positive."""
        with self.assertRaises(ValidationError):
            InputValidator.price(0)

    def test_percentage(self):
        """Percentage bounds 0-1."""
        self.assertEqual(InputValidator.percentage(0.5), 0.5)
        with self.assertRaises(ValidationError):
            InputValidator.percentage(1.5)

    def test_uuid_valid(self):
        """Valid UUID."""
        uid = "550e8400-e29b-41d4-a716-446655440000"
        self.assertEqual(InputValidator.uuid(uid), uid)

    def test_uuid_invalid(self):
        """Invalid UUID format."""
        with self.assertRaises(ValidationError):
            InputValidator.uuid("not-a-uuid")

    def test_sanitize_string(self):
        """Dangerous characters removed."""
        result = InputValidator.sanitize_string("hello\x00world\x01")
        self.assertEqual(result, "helloworld")

    def test_validate_dict(self):
        """Dict schema validation."""
        data = {"name": "test", "count": 5}
        schema = {"name": (str, True), "count": (int, True)}
        result = InputValidator.validate_dict(data, schema)
        self.assertEqual(result["name"], "test")

    def test_validate_dict_missing_required(self):
        """Missing required field raises."""
        with self.assertRaises(ValidationError):
            InputValidator.validate_dict({}, {"name": (str, True)})

    def test_validate_dict_unexpected(self):
        """Unexpected field raises."""
        with self.assertRaises(ValidationError):
            InputValidator.validate_dict({"extra": 1}, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
