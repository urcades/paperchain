"""Independent conformance tests for the Python paper-family runner."""

from __future__ import annotations

import importlib.util
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from conformance.python import paper_conformance


def doll_case(operation: str, input_value: dict, expected: dict | None = None) -> dict:
    """Build only the fixed corpus envelope fields; expectations stay literal."""

    return {
        "id": f"unit.doll.{operation}",
        "rule": "paper-doll/v3#document-grammar",
        "subject": "paper-doll/v3",
        "operation": operation,
        "input": input_value,
        "expected": expected or {"outcome": "valid"},
    }


def chain_case(operation: str, input_value: dict, expected: dict | None = None) -> dict:
    return {
        "id": f"unit.chain.{operation}",
        "rule": "paperchain/v1#law-1-structure",
        "subject": "paperchain/v1",
        "operation": operation,
        "input": input_value,
        "expected": expected or {"outcome": "valid"},
    }


def minimal_body() -> dict:
    return {"root": "root", "vessels": {"root": {}}}


def validation_paths(case: dict) -> set[str]:
    result = paper_conformance.run_case(case)
    if result["outcome"] != "invalid":
        raise AssertionError(f"expected invalid result, got {result!r}")
    return set(result["errorPaths"])


class PublicModuleTests(unittest.TestCase):
    def test_runner_module_is_importable(self) -> None:
        """Deleting the runner module must break the public Python entry point."""

        self.assertIsNotNone(
            importlib.util.find_spec("conformance.python.paper_conformance")
        )

    def test_runner_exposes_case_dispatch(self) -> None:
        """Removing run_case must break the shared-corpus contract."""

        self.assertTrue(hasattr(paper_conformance, "run_case"))

    def test_runner_exposes_fixture_boundary(self) -> None:
        """Removing fixture loading or comparison must break the runner contract."""

        self.assertTrue(hasattr(paper_conformance, "load_corpus"))
        self.assertTrue(hasattr(paper_conformance, "run_corpus_file"))


class PaperdollValidationTests(unittest.TestCase):
    def test_minimal_document_and_explicit_constructor_are_valid(self) -> None:
        for root in ("root", "constructor"):
            document = {
                "protocol": "paper-doll/v3",
                "body": {"root": root, "vessels": {root: {}}},
            }
            self.assertEqual(
                paper_conformance.run_case(
                    doll_case("validateDocument", {"document": document})
                ),
                {"outcome": "valid"},
            )

    def test_structure_rejects_unknown_keys_nonfinite_json_and_bad_arrays(self) -> None:
        bad_documents = [
            ({"protocol": "paper-doll/v3", "body": minimal_body(), "extra": 1}, "$"),
            (
                {
                    "protocol": "paper-doll/v3",
                    "body": {
                        "root": "root",
                        "vessels": {
                            "root": {"contains": [{"kind": "item", "data": math.nan}]}
                        },
                    },
                },
                "$.body.vessels.root.contains.0.data",
            ),
            (
                {
                    "protocol": "paper-doll/v3",
                    "body": {
                        "root": "root",
                        "vessels": {"root": {"accepts": {"kind": "item"}}},
                    },
                },
                "$.body.vessels.root.accepts",
            ),
        ]
        for document, expected_path in bad_documents:
            with self.subTest(expected_path=expected_path):
                self.assertIn(
                    expected_path,
                    validation_paths(
                        doll_case("validateDocument", {"document": document})
                    ),
                )

    def test_graph_laws_reject_missing_root_reciprocity_and_opposition(self) -> None:
        documents = [
            (
                {"protocol": "paper-doll/v3", "body": {"root": "gone", "vessels": {}}},
                "$.body.root",
            ),
            (
                {
                    "protocol": "paper-doll/v3",
                    "body": {
                        "root": "a",
                        "vessels": {
                            "a": {"ports": {"right": {"vessel": "b", "side": "left"}}},
                            "b": {},
                        },
                    },
                },
                "$.body.vessels.a.ports.right",
            ),
            (
                {
                    "protocol": "paper-doll/v3",
                    "body": {
                        "root": "a",
                        "vessels": {
                            "a": {"ports": {"right": {"vessel": "b", "side": "top"}}},
                            "b": {"ports": {"top": {"vessel": "a", "side": "right"}}},
                        },
                    },
                },
                "$.body.vessels.a.ports.right.side",
            ),
        ]
        for document, expected_path in documents:
            with self.subTest(expected_path=expected_path):
                self.assertIn(
                    expected_path,
                    validation_paths(doll_case("validateDocument", {"document": document})),
                )

    def test_planarity_collision_and_unreachable_ported_vessels_are_invalid(self) -> None:
        collision = {
            "protocol": "paper-doll/v3",
            "body": {
                "root": "a",
                "vessels": {
                    "a": {
                        "ports": {
                            "right": {"vessel": "b", "side": "left"},
                            "bottom": {"vessel": "c", "side": "top"},
                        }
                    },
                    "b": {
                        "ports": {
                            "left": {"vessel": "a", "side": "right"},
                            "bottom": {"vessel": "d", "side": "top"},
                        }
                    },
                    "c": {
                        "ports": {
                            "top": {"vessel": "a", "side": "bottom"},
                            "right": {"vessel": "e", "side": "left"},
                        }
                    },
                    "d": {"ports": {"top": {"vessel": "b", "side": "bottom"}}},
                    "e": {"ports": {"left": {"vessel": "c", "side": "right"}}},
                },
            },
        }
        collision_paths = validation_paths(
            doll_case("validateDocument", {"document": collision})
        )
        self.assertTrue(
            "$.body.vessels.b.ports.bottom" in collision_paths
            or "$.body.vessels.c.ports.right" in collision_paths
        )

        unreachable = {
            "protocol": "paper-doll/v3",
            "body": {
                "root": "a",
                "vessels": {
                    "a": {},
                    "b": {"ports": {"right": {"vessel": "c", "side": "left"}}},
                    "c": {"ports": {"left": {"vessel": "b", "side": "right"}}},
                },
            },
        }
        unreachable_paths = validation_paths(
            doll_case("validateDocument", {"document": unreachable})
        )
        self.assertIn("$.body.vessels.b.ports", unreachable_paths)
        self.assertIn("$.body.vessels.c.ports", unreachable_paths)

    def test_open_sealed_typed_and_recursive_compatibility(self) -> None:
        open_document = {
            "protocol": "paper-doll/v3",
            "body": {
                "root": "root",
                "vessels": {"root": {"contains": [{"kind": "item", "type": "hat"}]}},
            },
        }
        self.assertEqual(
            paper_conformance.run_case(
                doll_case("validateDocument", {"document": open_document})
            ),
            {"outcome": "valid"},
        )

        sealed = json.loads(json.dumps(open_document))
        sealed["body"]["vessels"]["root"]["accepts"] = []
        self.assertIn(
            "$.body.vessels.root.contains.0",
            validation_paths(doll_case("validateDocument", {"document": sealed})),
        )

        nested = json.loads(json.dumps(open_document))
        nested["body"]["vessels"]["root"]["contains"] = [
            {
                "kind": "item",
                "id": "pack",
                "body": {
                    "root": "pocket",
                    "vessels": {
                        "pocket": {
                            "contains": [
                                {"kind": "item", "id": "rope"},
                                {"kind": "item", "id": "rope"},
                            ]
                        }
                    },
                },
            }
        ]
        self.assertIn(
            "$.body.vessels.root.contains.0.body.vessels.pocket.contains.1.id",
            validation_paths(doll_case("validateDocument", {"document": nested})),
        )


class AddressAndLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = {
            "root": "torso",
            "vessels": {
                "torso": {
                    "ports": {"top": {"vessel": "head", "side": "bottom"}},
                    "contains": [
                        {
                            "kind": "item",
                            "id": "pack",
                            "body": {
                                "root": "pocket",
                                "vessels": {
                                    "pocket": {
                                        "contains": [{"kind": "item", "id": "rope"}]
                                    }
                                },
                            },
                        }
                    ],
                },
                "head": {"ports": {"bottom": {"vessel": "torso", "side": "top"}}},
                "cargo": {},
            },
        }

    def test_resolves_nested_elements_and_distinguishes_missing_from_malformed(self) -> None:
        resolved = paper_conformance.run_case(
            doll_case(
                "resolveAddress",
                {"body": self.body, "address": "torso/pack/pocket/rope"},
            )
        )
        self.assertEqual(
            resolved,
            {
                "outcome": "resolved",
                "value": {
                    "kind": "element",
                    "vesselId": "pocket",
                    "index": 0,
                    "element": {"kind": "item", "id": "rope"},
                },
            },
        )
        self.assertEqual(
            paper_conformance.run_case(
                doll_case("resolveAddress", {"body": self.body, "address": "torso/missing"})
            ),
            {"outcome": "unresolved"},
        )
        self.assertEqual(
            paper_conformance.run_case(
                doll_case("resolveAddress", {"body": self.body, "address": "torso//pack"})
            ),
            {"outcome": "error"},
        )

    def test_layout_has_rooted_coordinates_sorted_free_and_normalized_connections(self) -> None:
        self.assertEqual(
            paper_conformance.run_case(doll_case("deriveLayout", {"body": self.body})),
            {
                "outcome": "layout",
                "value": {
                    "figure": {"torso": {"x": 0, "y": 0}, "head": {"x": 0, "y": -1}},
                    "free": ["cargo"],
                    "connections": [
                        {
                            "from": {"vessel": "head", "side": "bottom"},
                            "to": {"vessel": "torso", "side": "top"},
                        }
                    ],
                },
            },
        )


class PaperchainValidationTests(unittest.TestCase):
    def scene(self, *, kinds: dict | None = None, relations: list | None = None) -> dict:
        return {
            "protocol": "paperchain/v1",
            "bodies": {"alice": minimal_body(), "bob": minimal_body()},
            "kinds": {} if kinds is None else kinds,
            "relations": [] if relations is None else relations,
        }

    def test_empty_scene_and_explicit_constructor_endpoint_are_valid(self) -> None:
        empty = {"protocol": "paperchain/v1", "bodies": {}, "kinds": {}, "relations": []}
        self.assertEqual(
            paper_conformance.run_case(chain_case("validateScene", {"scene": empty})),
            {"outcome": "valid"},
        )
        scene = self.scene(kinds={"holds": {}})
        scene["bodies"]["alice"] = {
            "root": "constructor",
            "vessels": {"constructor": {}},
        }
        scene["relations"] = [
            {"kind": "holds", "from": "alice/constructor", "to": "bob/root"}
        ]
        self.assertEqual(
            paper_conformance.run_case(chain_case("validateScene", {"scene": scene})),
            {"outcome": "valid"},
        )

    def test_structure_accepts_integral_float_budgets_but_rejects_nonintegers(self) -> None:
        integral = self.scene(kinds={"holds": {"fromMax": 1.0}})
        self.assertEqual(
            paper_conformance.run_case(chain_case("validateScene", {"scene": integral})),
            {"outcome": "valid"},
        )
        for value in (True, 1.5, -1):
            scene = self.scene(kinds={"holds": {"fromMax": value}})
            with self.subTest(value=value):
                self.assertIn(
                    "$.kinds.holds.fromMax",
                    validation_paths(chain_case("validateScene", {"scene": scene})),
                )
        scene = self.scene()
        scene["bodies"]["alice"] = {"root": "missing", "vessels": {}}
        self.assertIn(
            "$.bodies.alice.root",
            validation_paths(chain_case("validateScene", {"scene": scene})),
        )

    def test_declared_kind_existence_and_irreflexivity_laws(self) -> None:
        undeclared = self.scene(
            relations=[{"kind": "holds", "from": "alice/root", "to": "bob/root"}]
        )
        self.assertIn(
            "$.relations.0.kind",
            validation_paths(chain_case("validateScene", {"scene": undeclared})),
        )

        missing = self.scene(
            kinds={"holds": {}},
            relations=[
                {"kind": "holds", "from": "alice/constructor", "to": "bob/root"}
            ],
        )
        self.assertIn(
            "$.relations.0.from",
            validation_paths(chain_case("validateScene", {"scene": missing})),
        )

        reflexive = self.scene(
            kinds={"holds": {"irreflexive": True}},
            relations=[{"kind": "holds", "from": "alice/root", "to": "alice/root"}],
        )
        self.assertIn(
            "$.relations.0.to",
            validation_paths(chain_case("validateScene", {"scene": reflexive})),
        )

    def test_symmetric_duplicates_asymmetric_direction_and_budgets(self) -> None:
        symmetric = self.scene(
            kinds={"holds": {"symmetric": True}},
            relations=[
                {"kind": "holds", "from": "alice/root", "to": "bob/root"},
                {"kind": "holds", "from": "bob/root", "to": "alice/root"},
            ],
        )
        self.assertIn(
            "$.relations.1",
            validation_paths(chain_case("validateScene", {"scene": symmetric})),
        )

        asymmetric = self.scene(
            kinds={"follows": {}},
            relations=[
                {"kind": "follows", "from": "alice/root", "to": "bob/root"},
                {"kind": "follows", "from": "bob/root", "to": "alice/root"},
            ],
        )
        self.assertEqual(
            paper_conformance.run_case(chain_case("validateScene", {"scene": asymmetric})),
            {"outcome": "valid"},
        )

        reflexive_budget = self.scene(
            kinds={"near": {"symmetric": True, "fromMax": 1}},
            relations=[{"kind": "near", "from": "alice/root", "to": "alice/root"}],
        )
        self.assertIn(
            "$.relations.0",
            validation_paths(chain_case("validateScene", {"scene": reflexive_budget})),
        )

    def test_scene_resolution_uses_error_and_unresolved_channels(self) -> None:
        scene = self.scene()
        self.assertEqual(
            paper_conformance.run_case(
                chain_case(
                    "resolveSceneAddress", {"scene": scene, "address": "alice/root"}
                )
            ),
            {"outcome": "resolved", "value": {"kind": "vessel", "vesselId": "root"}},
        )
        self.assertEqual(
            paper_conformance.run_case(
                chain_case(
                    "resolveSceneAddress", {"scene": scene, "address": "nobody/root"}
                )
            ),
            {"outcome": "unresolved"},
        )
        self.assertEqual(
            paper_conformance.run_case(
                chain_case("resolveSceneAddress", {"scene": scene, "address": "alice"})
            ),
            {"outcome": "error"},
        )


class FixtureBoundaryTests(unittest.TestCase):
    def write(self, directory: str, text: str) -> str:
        path = Path(directory, "corpus.json")
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_loader_rejects_duplicate_object_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(
                directory,
                '{"corpus":"paper-family-conformance/v1","cases":[],"cases":[]}',
            )
            with self.assertRaises(ValueError):
                paper_conformance.load_corpus(path)

    def test_runner_detects_intentionally_flipped_expectation(self) -> None:
        document = {"protocol": "paper-doll/v3", "body": minimal_body()}
        good = {
            "corpus": "paper-family-conformance/v1",
            "cases": [
                doll_case("validateDocument", {"document": document}, {"outcome": "valid"})
            ],
        }
        flipped = json.loads(json.dumps(good))
        flipped["cases"][0]["expected"] = {
            "outcome": "invalid",
            "includesErrorPaths": ["$.body.root"],
        }
        with tempfile.TemporaryDirectory() as directory:
            good_path = self.write(directory, json.dumps(good))
            self.assertEqual(paper_conformance.run_corpus_file(good_path), [])
            flipped_path = self.write(directory, json.dumps(flipped))
            self.assertTrue(paper_conformance.run_corpus_file(flipped_path))

    def test_cli_rejects_duplicate_case_ids_across_selected_files(self) -> None:
        document = {"protocol": "paper-doll/v3", "body": minimal_body()}
        envelope = {
            "corpus": "paper-family-conformance/v1",
            "cases": [doll_case("validateDocument", {"document": document})],
        }
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory, "first.json")
            second = Path(directory, "second.json")
            first.write_text(json.dumps(envelope), encoding="utf-8")
            second.write_text(json.dumps(envelope), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                status = paper_conformance.main([str(first), str(second)])
            self.assertEqual(status, 1)
            self.assertIn("duplicate case id", output.getvalue())

    def test_loader_rejects_malformed_envelopes_unknown_operations_and_outcomes(self) -> None:
        malformed_cases = [
            {"corpus": "wrong", "cases": []},
            {"corpus": "paper-family-conformance/v1", "cases": [], "extra": True},
            {
                "corpus": "paper-family-conformance/v1",
                "cases": [
                    {
                        "id": "bad",
                        "rule": "paper-doll/v3#layout",
                        "subject": "paper-doll/v3",
                        "operation": "unknown",
                        "input": {},
                        "expected": {"outcome": "layout", "value": {}},
                    }
                ],
            },
            {
                "corpus": "paper-family-conformance/v1",
                "cases": [
                    doll_case(
                        "validateDocument",
                        {"document": {"protocol": "paper-doll/v3", "body": minimal_body()}},
                        {"outcome": "maybe"},
                    )
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, envelope in enumerate(malformed_cases):
                with self.subTest(index=index):
                    path = self.write(directory, json.dumps(envelope))
                    with self.assertRaises(ValueError):
                        paper_conformance.load_corpus(path)

    def test_loader_rejects_malformed_result_projections_and_duplicate_case_ids(self) -> None:
        document = {"protocol": "paper-doll/v3", "body": minimal_body()}
        bad_projection = {
            "corpus": "paper-family-conformance/v1",
            "cases": [
                doll_case(
                    "resolveAddress",
                    {"body": minimal_body(), "address": "root"},
                    {"outcome": "resolved", "value": {"kind": "vessel"}},
                )
            ],
        }
        duplicate = {
            "corpus": "paper-family-conformance/v1",
            "cases": [
                doll_case("validateDocument", {"document": document}),
                doll_case("validateDocument", {"document": document}),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            for envelope in (bad_projection, duplicate):
                path = self.write(directory, json.dumps(envelope))
                with self.assertRaises(ValueError):
                    paper_conformance.load_corpus(path)

    def test_loader_enforces_schema_patterns_nonempty_cases_and_rules(self) -> None:
        document = {"protocol": "paper-doll/v3", "body": minimal_body()}
        valid_case = doll_case("validateDocument", {"document": document})
        malformed = [
            {"corpus": "paper-family-conformance/v1", "cases": []},
            {
                "corpus": "paper-family-conformance/v1",
                "cases": [valid_case | {"id": "bad@id"}],
            },
            {
                "corpus": "paper-family-conformance/v1",
                "cases": [valid_case | {"rule": "anything"}],
            },
            {
                "corpus": "paper-family-conformance/v1",
                "cases": [valid_case | {"rule": "paperchain/v1#law-1-structure"}],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, envelope in enumerate(malformed):
                with self.subTest(index=index):
                    path = self.write(directory, json.dumps(envelope))
                    with self.assertRaises(ValueError):
                        paper_conformance.load_corpus(path)

    def test_loader_enforces_invalid_paths_and_operation_input_types(self) -> None:
        invalid_path_values = ([], [""], ["$.x", "$.x"])
        malformed = [
            {
                "corpus": "paper-family-conformance/v1",
                "cases": [
                    doll_case(
                        "validateDocument",
                        {"document": {}},
                        {"outcome": "invalid", "includesErrorPaths": paths},
                    )
                ],
            }
            for paths in invalid_path_values
        ]
        malformed.extend(
            [
                {
                    "corpus": "paper-family-conformance/v1",
                    "cases": [
                        doll_case(
                            "resolveAddress",
                            {"body": [], "address": "root"},
                            {"outcome": "unresolved"},
                        )
                    ],
                },
                {
                    "corpus": "paper-family-conformance/v1",
                    "cases": [
                        chain_case(
                            "resolveSceneAddress",
                            {"scene": {}, "address": 1},
                            {"outcome": "error"},
                        )
                    ],
                },
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, envelope in enumerate(malformed):
                with self.subTest(index=index):
                    path = self.write(directory, json.dumps(envelope))
                    with self.assertRaises(ValueError):
                        paper_conformance.load_corpus(path)

    def test_loader_accepts_json_integral_float_projection_numbers(self) -> None:
        resolved = doll_case(
            "resolveAddress",
            {"body": minimal_body(), "address": "root/item"},
            {
                "outcome": "resolved",
                "value": {
                    "kind": "element",
                    "vesselId": "root",
                    "index": 1.0,
                    "element": {},
                },
            },
        )
        layout = doll_case(
            "deriveLayout",
            {"body": minimal_body()},
            {
                "outcome": "layout",
                "value": {
                    "figure": {"root": {"x": 0.0, "y": -0.0}},
                    "free": [],
                    "connections": [],
                },
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(
                directory,
                json.dumps(
                    {"corpus": "paper-family-conformance/v1", "cases": [resolved, layout]}
                ),
            )
            paper_conformance.load_corpus(path)

    def test_loader_rejects_boolean_projection_numbers_and_overflow(self) -> None:
        boolean_index = doll_case(
            "resolveAddress",
            {"body": minimal_body(), "address": "root/item"},
            {
                "outcome": "resolved",
                "value": {
                    "kind": "element",
                    "vesselId": "root",
                    "index": True,
                    "element": {},
                },
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(
                directory,
                json.dumps({"corpus": "paper-family-conformance/v1", "cases": [boolean_index]}),
            )
            with self.assertRaises(ValueError):
                paper_conformance.load_corpus(path)

            overflow = (
                '{"corpus":"paper-family-conformance/v1","cases":['
                '{"id":"overflow","rule":"paper-doll/v3#document-grammar",'
                '"subject":"paper-doll/v3","operation":"validateDocument",'
                '"input":{"document":1e400},"expected":{"outcome":"valid"}}]}'
            )
            path = self.write(directory, overflow)
            with self.assertRaises(ValueError):
                paper_conformance.load_corpus(path)


class JsonEqualityTests(unittest.TestCase):
    def test_numbers_compare_by_value_including_integral_float_and_negative_zero(self) -> None:
        self.assertTrue(paper_conformance._json_equal(1, 1.0))
        self.assertTrue(paper_conformance._json_equal(-0.0, 0))

    def test_booleans_do_not_equal_numbers_even_when_nested(self) -> None:
        self.assertFalse(paper_conformance._json_equal(True, 1))
        self.assertFalse(
            paper_conformance._json_equal(
                {"outer": [False, {"value": True}]},
                {"outer": [0, {"value": 1}]},
            )
        )

    def test_result_matching_uses_json_structural_equality(self) -> None:
        actual = {
            "outcome": "resolved",
            "value": {
                "kind": "element",
                "vesselId": "root",
                "index": 0,
                "element": {"kind": "item", "data": True},
            },
        }
        expected = json.loads(json.dumps(actual))
        expected["value"]["element"]["data"] = 1
        self.assertFalse(paper_conformance._matches_expected(actual, expected))


if __name__ == "__main__":
    unittest.main()
