"""Contract tests for the independent portable-JSON profile."""

from __future__ import annotations

import importlib.util
import math
import unittest

from conformance.python import portable_json


class PublicModuleTests(unittest.TestCase):
    def test_portable_json_module_is_importable(self) -> None:
        """Deleting the profile module must break its public import boundary."""

        self.assertIsNotNone(
            importlib.util.find_spec("conformance.python.portable_json")
        )

    def test_profile_exposes_the_raw_loader_and_numeric_callback(self) -> None:
        """Removing a public integration seam must break loader wiring."""

        self.assertEqual(
            getattr(portable_json, "MAX_PORTABLE_INTEGER", None),
            9_007_199_254_740_991,
        )
        error_type = getattr(portable_json, "PortableJSONError", None)
        self.assertIsInstance(error_type, type)
        self.assertTrue(issubclass(error_type, ValueError))
        self.assertTrue(callable(getattr(portable_json, "parse_portable_number", None)))
        self.assertTrue(callable(getattr(portable_json, "loads_portable_json", None)))
        self.assertTrue(callable(getattr(portable_json, "normalize_portable_json", None)))


_HAS_PUBLIC_API = all(
    hasattr(portable_json, name)
    for name in (
        "MAX_PORTABLE_INTEGER",
        "PortableJSONError",
        "parse_portable_number",
        "loads_portable_json",
        "normalize_portable_json",
    )
)


@unittest.skipUnless(_HAS_PUBLIC_API, "portable JSON public API is not implemented")
class NumberTokenTests(unittest.TestCase):
    def test_safe_integer_boundaries_survive_binary64_normalization(self) -> None:
        """Using a smaller inclusive range must reject valid boundary values."""

        self.assertEqual(
            portable_json.parse_portable_number("9007199254740991"),
            9_007_199_254_740_991,
        )
        self.assertEqual(
            portable_json.parse_portable_number("-9007199254740991"),
            -9_007_199_254_740_991,
        )

    def test_unsafe_integers_are_rejected_after_binary64_rounding(self) -> None:
        """Checking the decimal token instead of the rounded value must fail here."""

        for token in (
            "9007199254740992",
            "9007199254740993",
            "-9007199254740992",
            "-9007199254740993",
        ):
            with self.subTest(token=token):
                with self.assertRaises(portable_json.PortableJSONError):
                    portable_json.parse_portable_number(token)

    def test_exponent_spellings_use_the_same_binary64_integer_contract(self) -> None:
        """Treating exponent tokens as an unvalidated float path must fail here."""

        self.assertEqual(portable_json.parse_portable_number("1e3"), 1000)
        self.assertEqual(
            portable_json.parse_portable_number("9.007199254740991e15"),
            9_007_199_254_740_991,
        )
        with self.assertRaises(portable_json.PortableJSONError):
            portable_json.parse_portable_number("9.007199254740992e15")

    def test_fractions_remain_binary64_floats(self) -> None:
        """Converting every numeric token to int must fail on ordinary fractions."""

        tenth = portable_json.parse_portable_number("0.1")
        self.assertIs(type(tenth), float)
        self.assertEqual(tenth, 0.1)
        self.assertEqual(portable_json.parse_portable_number("-2.5"), -2.5)

    def test_negative_zero_compares_as_integer_zero(self) -> None:
        """Keeping a separate signed-zero identity must fail portable equality."""

        for token in ("-0", "-0.0", "-0e20"):
            with self.subTest(token=token):
                result = portable_json.parse_portable_number(token)
                self.assertIs(type(result), int)
                self.assertEqual(result, 0)

    def test_binary64_underflow_to_zero_is_allowed(self) -> None:
        """Rejecting finite underflow must fail the documented binary64 behavior."""

        self.assertEqual(portable_json.parse_portable_number("1e-4000"), 0)
        smallest = portable_json.parse_portable_number("5e-324")
        self.assertIs(type(smallest), float)
        self.assertGreater(smallest, 0.0)

    def test_overflow_and_non_json_number_spellings_are_rejected(self) -> None:
        """Relying on float() alone must not admit infinities or Python spellings."""

        for token in ("1e400", "NaN", "Infinity", "-Infinity", "+1", "01", " 1"):
            with self.subTest(token=token):
                with self.assertRaises(portable_json.PortableJSONError):
                    portable_json.parse_portable_number(token)


@unittest.skipUnless(_HAS_PUBLIC_API, "portable JSON public API is not implemented")
class RawJSONTests(unittest.TestCase):
    def test_nested_document_is_normalized_without_treating_booleans_as_numbers(self) -> None:
        """Visiting bool through Python's int branch must fail the type assertions."""

        result = portable_json.loads_portable_json(
            b'{"enabled":true,"values":[1.0,0.25,-0,1e2],"missing":null}'
        )
        self.assertEqual(
            result,
            {"enabled": True, "values": [1, 0.25, 0, 100], "missing": None},
        )
        self.assertIs(result["enabled"], True)
        self.assertIs(type(result["values"][0]), int)
        self.assertIs(type(result["values"][1]), float)
        self.assertEqual(result["values"], [1, 0.25, 0, 100])
        self.assertIsNone(result["missing"])

    def test_duplicate_keys_are_rejected_at_the_nested_object_path(self) -> None:
        """Letting json.loads silently keep the last duplicate must fail here."""

        with self.assertRaisesRegex(
            portable_json.PortableJSONError, r"\$\.outer.*duplicate.*x"
        ):
            portable_json.loads_portable_json('{"outer":{"x":1,"x":2}}')

    def test_nonfinite_literals_and_binary64_overflow_are_rejected(self) -> None:
        """Python json's permissive constants and float overflow must fail here."""

        for source in ("NaN", "Infinity", "-Infinity", "1e400"):
            with self.subTest(source=source):
                with self.assertRaises(portable_json.PortableJSONError):
                    portable_json.loads_portable_json(source)

    def test_unsafe_nested_number_reports_its_location(self) -> None:
        """Losing traversal context must fail this diagnostic boundary."""

        with self.assertRaisesRegex(
            portable_json.PortableJSONError, r"\$\.outer\[1\]"
        ):
            portable_json.loads_portable_json(
                '{"outer":[0,9007199254740993]}'
            )

    def test_exact_decimal_strings_are_preserved_verbatim(self) -> None:
        """Coercing numeric-looking strings must break the exact-decimal escape hatch."""

        self.assertEqual(
            portable_json.loads_portable_json(
                '{"exact":"9007199254740993.0000000000000001"}'
            ),
            {"exact": "9007199254740993.0000000000000001"},
        )


@unittest.skipUnless(_HAS_PUBLIC_API, "portable JSON public API is not implemented")
class ParsedValueTests(unittest.TestCase):
    def test_nested_values_are_normalized_with_paths(self) -> None:
        """Validating only the root must miss unsafe numbers in containers."""

        value = {"items": [True, 3.0, 0.125]}
        result = portable_json.normalize_portable_json(value)
        self.assertIs(result["items"][0], True)
        self.assertIs(type(result["items"][1]), int)
        self.assertIs(type(result["items"][2]), float)
        self.assertEqual(result, {"items": [True, 3, 0.125]})

        with self.assertRaisesRegex(
            portable_json.PortableJSONError, r"\$\.items\[1\]"
        ):
            portable_json.normalize_portable_json(
                {"items": [0, 9_007_199_254_740_992]}
            )

    def test_nonfinite_parsed_floats_are_rejected(self) -> None:
        """Accepting Python floats without finiteness checks must fail here."""

        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaises(portable_json.PortableJSONError):
                    portable_json.normalize_portable_json({"value": value})

    def test_non_json_values_and_object_keys_are_rejected(self) -> None:
        """Silently accepting Python-only container values must fail here."""

        for value in ({"bad": (1, 2)}, {1: "numeric key"}, {"bad": object()}):
            with self.subTest(value=value):
                with self.assertRaises(portable_json.PortableJSONError):
                    portable_json.normalize_portable_json(value)

    def test_cycles_raise_profile_errors_instead_of_recursion_errors(self) -> None:
        """Traversing containers without an active-object guard must fail here."""

        cyclic_list: list[object] = []
        cyclic_list.append(cyclic_list)
        cyclic_dict: dict[str, object] = {}
        cyclic_dict["self"] = cyclic_dict

        for value in (cyclic_list, cyclic_dict):
            with self.subTest(container=type(value).__name__):
                with self.assertRaisesRegex(
                    portable_json.PortableJSONError, "cycle"
                ):
                    portable_json.normalize_portable_json(value)

    def test_shared_acyclic_values_are_allowed(self) -> None:
        """Treating all repeated identities as cycles must reject this JSON tree."""

        shared = [1.5]
        self.assertEqual(
            portable_json.normalize_portable_json({"a": shared, "b": shared}),
            {"a": [1.5], "b": [1.5]},
        )


if __name__ == "__main__":
    unittest.main()
