"""Tests for the independent Python Paperdoll/Paperchain edit reference."""

from __future__ import annotations

import copy
import unittest

try:
    from . import paper_edits
except ImportError:  # Supports direct execution from this directory.
    try:
        import paper_edits  # type: ignore[no-redef]
    except ImportError:
        paper_edits = None  # type: ignore[assignment]


def empty_body(*vessel_ids: str) -> dict:
    return {
        "root": vessel_ids[0],
        "vessels": {vessel_id: {} for vessel_id in vessel_ids},
    }


def empty_scene(*body_names: str) -> dict:
    return {
        "protocol": "paperchain/v1",
        "bodies": {name: empty_body("root") for name in body_names},
        "kinds": {},
        "relations": [],
    }


class DollEditTests(unittest.TestCase):
    def test_connect_installs_reciprocal_ports_without_aliasing_input(self) -> None:
        self.assertIsNotNone(paper_edits, "paper_edits module is not implemented")
        body = empty_body("torso", "hand")
        before = copy.deepcopy(body)

        result = paper_edits.connect(
            body,
            {"vessel": "torso", "side": "right"},
            {"vessel": "hand", "side": "left"},
        )

        self.assertEqual(body, before)
        self.assertEqual(result["displaced"], [])
        self.assertEqual(
            result["body"],
            {
                "root": "torso",
                "vessels": {
                    "torso": {"ports": {"right": {"vessel": "hand", "side": "left"}}},
                    "hand": {"ports": {"left": {"vessel": "torso", "side": "right"}}},
                },
            },
        )
        result["body"]["vessels"]["torso"]["ports"]["right"]["vessel"] = "changed"
        self.assertEqual(body, before)

    def test_connect_returns_each_displaced_connection_once(self) -> None:
        body = empty_body("a", "b", "c", "d")
        body["vessels"]["a"] = {"ports": {"right": {"vessel": "b", "side": "left"}}}
        body["vessels"]["b"] = {"ports": {"left": {"vessel": "a", "side": "right"}}}
        body["vessels"]["c"] = {"ports": {"right": {"vessel": "d", "side": "left"}}}
        body["vessels"]["d"] = {"ports": {"left": {"vessel": "c", "side": "right"}}}

        result = paper_edits.connect(
            body,
            {"vessel": "a", "side": "right"},
            {"vessel": "d", "side": "left"},
        )

        self.assertEqual(
            result["displaced"],
            [
                {
                    "from": {"vessel": "a", "side": "right"},
                    "to": {"vessel": "b", "side": "left"},
                },
                {
                    "from": {"vessel": "d", "side": "left"},
                    "to": {"vessel": "c", "side": "right"},
                },
            ],
        )
        self.assertEqual(result["body"]["vessels"]["b"]["ports"], {})
        self.assertEqual(result["body"]["vessels"]["c"]["ports"], {})

    def test_connect_rejects_only_its_checked_endpoint_preconditions(self) -> None:
        body = empty_body("a", "b")
        invalid_calls = [
            ({"vessel": "missing", "side": "right"}, {"vessel": "b", "side": "left"}),
            ({"vessel": "a", "side": "diagonal"}, {"vessel": "b", "side": "left"}),
            ({"vessel": "a", "side": "right"}, {"vessel": "a", "side": "left"}),
            ({"vessel": "a", "side": "right"}, {"vessel": "b", "side": "top"}),
        ]
        for from_endpoint, to_endpoint in invalid_calls:
            with self.subTest(from_endpoint=from_endpoint, to_endpoint=to_endpoint):
                with self.assertRaises(ValueError):
                    paper_edits.connect(body, from_endpoint, to_endpoint)

    def test_disconnect_returns_removed_connection_and_empty_noop(self) -> None:
        body = empty_body("a", "b", "free")
        body["vessels"]["a"] = {"ports": {"right": {"vessel": "b", "side": "left"}}}
        body["vessels"]["b"] = {"ports": {"left": {"vessel": "a", "side": "right"}}}
        before = copy.deepcopy(body)

        removed = paper_edits.disconnect(body, {"vessel": "a", "side": "right"})
        noop = paper_edits.disconnect(body, {"vessel": "free", "side": "top"})

        self.assertEqual(body, before)
        self.assertEqual(
            removed,
            {
                "body": {
                    "root": "a",
                    "vessels": {"a": {"ports": {}}, "b": {"ports": {}}, "free": {}},
                },
                "removed": {
                    "from": {"vessel": "a", "side": "right"},
                    "to": {"vessel": "b", "side": "left"},
                },
            },
        )
        self.assertEqual(noop, {"body": body, "removed": None})
        self.assertIsNot(noop["body"], body)

    def test_disconnect_rejects_missing_vessel_and_invalid_side(self) -> None:
        body = empty_body("a")
        for endpoint in (
            {"vessel": "missing", "side": "top"},
            {"vessel": "a", "side": "diagonal"},
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    paper_edits.disconnect(body, endpoint)

    def test_insert_vessel_generates_first_free_id_and_copies_arguments(self) -> None:
        body = empty_body("root", "vessel-1", "vessel-3")
        vessel = {"accepts": [{"kind": "item"}]}
        result = paper_edits.insert_vessel(body, vessel)

        self.assertEqual(result["vesselId"], "vessel-2")
        self.assertIsNone(result["bridged"])
        self.assertEqual(result["body"]["vessels"]["vessel-2"], vessel)
        result["body"]["vessels"]["vessel-2"]["accepts"][0]["kind"] = "changed"
        self.assertEqual(vessel, {"accepts": [{"kind": "item"}]})
        self.assertNotIn("vessel-2", body["vessels"])

    def test_insert_vessel_bridges_an_occupied_endpoint(self) -> None:
        body = empty_body("a", "b")
        body["vessels"]["a"] = {"ports": {"right": {"vessel": "b", "side": "left"}}}
        body["vessels"]["b"] = {"ports": {"left": {"vessel": "a", "side": "right"}}}

        result = paper_edits.insert_vessel(
            body,
            {},
            {"id": "middle", "at": {"vessel": "a", "side": "right"}},
        )

        self.assertEqual(
            result["bridged"],
            {
                "from": {"vessel": "a", "side": "right"},
                "to": {"vessel": "b", "side": "left"},
            },
        )
        self.assertEqual(
            result["body"]["vessels"],
            {
                "a": {"ports": {"right": {"vessel": "middle", "side": "left"}}},
                "b": {"ports": {"left": {"vessel": "middle", "side": "right"}}},
                "middle": {
                    "ports": {
                        "right": {"vessel": "b", "side": "left"},
                        "left": {"vessel": "a", "side": "right"},
                    }
                },
            },
        )

    def test_insert_vessel_checks_requested_id_and_attachment_endpoint(self) -> None:
        body = empty_body("root")
        invalid_options = [
            {"id": "Not-An-Id"},
            {"id": "root"},
            {"at": {"vessel": "missing", "side": "top"}},
            {"at": {"vessel": "root", "side": "diagonal"}},
        ]
        for options in invalid_options:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    paper_edits.insert_vessel(body, {}, options)

    def test_delete_vessel_returns_exact_vessel_and_removes_incident_ports(self) -> None:
        body = empty_body("root", "limb")
        body["vessels"]["root"] = {
            "ports": {"right": {"vessel": "limb", "side": "left"}}
        }
        body["vessels"]["limb"] = {
            "contains": [{"kind": "item", "id": "ring"}],
            "ports": {"left": {"vessel": "root", "side": "right"}},
        }
        before = copy.deepcopy(body)

        result = paper_edits.delete_vessel(body, "limb")

        self.assertEqual(body, before)
        self.assertEqual(result["vessel"], before["vessels"]["limb"])
        self.assertIsNone(result["collapsed"])
        self.assertEqual(result["body"], {"root": "root", "vessels": {"root": {"ports": {}}}})
        result["vessel"]["contains"][0]["id"] = "changed"
        self.assertEqual(body, before)

    def test_delete_vessel_can_collapse_two_opposite_neighbors(self) -> None:
        body = empty_body("left", "middle", "right")
        body["vessels"]["left"] = {
            "ports": {"right": {"vessel": "middle", "side": "left"}}
        }
        body["vessels"]["middle"] = {
            "ports": {
                "left": {"vessel": "left", "side": "right"},
                "right": {"vessel": "right", "side": "left"},
            }
        }
        body["vessels"]["right"] = {
            "ports": {"left": {"vessel": "middle", "side": "right"}}
        }

        result = paper_edits.delete_vessel(
            body, "middle", {"collapseOppositeNeighbors": True}
        )

        self.assertEqual(
            result["collapsed"],
            {
                "from": {"vessel": "left", "side": "right"},
                "to": {"vessel": "right", "side": "left"},
            },
        )
        self.assertEqual(
            result["body"]["vessels"],
            {
                "left": {"ports": {"right": {"vessel": "right", "side": "left"}}},
                "right": {"ports": {"left": {"vessel": "left", "side": "right"}}},
            },
        )

    def test_delete_vessel_rejects_missing_and_root_vessels(self) -> None:
        body = empty_body("root", "other")
        for vessel_id in ("missing", "root"):
            with self.subTest(vessel_id=vessel_id):
                with self.assertRaises(ValueError):
                    paper_edits.delete_vessel(body, vessel_id)

    def test_insert_element_checks_compatibility_identity_and_position(self) -> None:
        body = {
            "root": "bag",
            "vessels": {
                "bag": {
                    "accepts": [{"kind": "item", "type": "tool"}],
                    "contains": [{"kind": "item", "type": "tool", "id": "saw"}],
                }
            },
        }
        element = {"kind": "item", "type": "tool", "id": "hammer", "data": {"mass": 2}}
        result = paper_edits.insert_element(body, "bag", element, 0)

        self.assertEqual(
            result["vessels"]["bag"]["contains"],
            [element, {"kind": "item", "type": "tool", "id": "saw"}],
        )
        result["vessels"]["bag"]["contains"][0]["data"]["mass"] = 99
        self.assertEqual(element["data"], {"mass": 2})
        self.assertEqual(body["vessels"]["bag"]["contains"][0]["id"], "saw")

        invalid_elements = [
            {"kind": "Bad"},
            {"kind": "item", "type": "Bad"},
            {"kind": "item", "id": "Bad"},
            {"kind": "item", "type": "tool", "id": "saw"},
            {"kind": "item", "type": "hat", "id": "cap"},
            {"kind": "item", "type": "tool", "body": {"root": "gone", "vessels": {}}},
        ]
        for invalid in invalid_elements:
            with self.subTest(element=invalid):
                with self.assertRaises(ValueError):
                    paper_edits.insert_element(body, "bag", invalid)
        for at in (-1, 3, True):
            with self.subTest(at=at):
                with self.assertRaises(ValueError):
                    paper_edits.insert_element(body, "bag", element, at)
        with self.assertRaises(ValueError):
            paper_edits.insert_element(body, "missing", element)

    def test_insert_element_does_not_add_unlisted_schema_checks(self) -> None:
        body = empty_body("open")
        unusual = {"kind": "item", "extra": {"consumer": True}}

        result = paper_edits.insert_element(body, "open", unusual)

        self.assertEqual(result["vessels"]["open"]["contains"], [unusual])

    def test_remove_element_returns_exact_record_and_checks_index(self) -> None:
        element = {"kind": "item", "id": "nested", "data": {"values": [1, 2]}}
        body = empty_body("root", "empty")
        body["vessels"]["root"] = {"contains": [element, {"kind": "item"}]}
        before = copy.deepcopy(body)

        result = paper_edits.remove_element(body, "root", 0)

        self.assertEqual(result["element"], element)
        self.assertEqual(result["body"]["vessels"]["root"]["contains"], [{"kind": "item"}])
        result["element"]["data"]["values"].append(3)
        self.assertEqual(body, before)
        for vessel_id, index in (("missing", 0), ("empty", 0), ("root", -1), ("root", 2), ("root", True)):
            with self.subTest(vessel_id=vessel_id, index=index):
                with self.assertRaises(ValueError):
                    paper_edits.remove_element(body, vessel_id, index)

    def test_move_element_checks_destination_before_removal_and_copies(self) -> None:
        body = {
            "root": "source",
            "vessels": {
                "source": {
                    "contains": [
                        {"kind": "item", "type": "tool", "id": "hammer", "data": [1]},
                        {"kind": "item", "id": "stay"},
                    ]
                },
                "tools": {"accepts": [{"kind": "item", "type": "tool"}]},
                "sealed": {"accepts": []},
                "collision": {"contains": [{"kind": "item", "id": "hammer"}]},
            },
        }
        before = copy.deepcopy(body)

        moved = paper_edits.move_element(body, "source", 0, "tools")

        self.assertEqual(body, before)
        self.assertEqual(moved["vessels"]["source"]["contains"], [{"kind": "item", "id": "stay"}])
        self.assertEqual(
            moved["vessels"]["tools"]["contains"],
            [{"kind": "item", "type": "tool", "id": "hammer", "data": [1]}],
        )
        moved["vessels"]["tools"]["contains"][0]["data"].append(2)
        self.assertEqual(body, before)

        for destination in ("sealed", "collision", "missing"):
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    paper_edits.move_element(body, "source", 0, destination)
                self.assertEqual(body, before)

    def test_move_element_within_one_vessel_moves_to_end(self) -> None:
        body = empty_body("root")
        body["vessels"]["root"] = {
            "contains": [
                {"kind": "item", "id": "first"},
                {"kind": "item", "id": "second"},
            ]
        }

        moved = paper_edits.move_element(body, "root", 0, "root")

        self.assertEqual(
            moved["vessels"]["root"]["contains"],
            [{"kind": "item", "id": "second"}, {"kind": "item", "id": "first"}],
        )


class ChainEditTests(unittest.TestCase):
    def test_declare_kind_defaults_to_fresh_empty_declaration(self) -> None:
        scene = empty_scene("alice")
        try:
            first = paper_edits.declare_kind(scene, "plain")
            second = paper_edits.declare_kind(scene, "other")
        except TypeError:
            first = second = None

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first["kinds"]["plain"], {})
        self.assertEqual(second["kinds"]["other"], {})
        first["kinds"]["plain"]["symmetric"] = True
        self.assertEqual(second["kinds"]["other"], {})
        self.assertEqual(scene["kinds"], {})
        with self.assertRaises(ValueError):
            paper_edits.declare_kind(scene, "null-kind", None)

    def test_declare_kind_accepts_constructor_key_and_large_integer_without_aliasing(self) -> None:
        scene = empty_scene("alice")
        declaration = {"symmetric": False, "fromMax": 2**80}

        result = paper_edits.declare_kind(scene, "constructor", declaration)

        self.assertEqual(result["kinds"]["constructor"], declaration)
        self.assertNotIn("constructor", scene["kinds"])
        result["kinds"]["constructor"]["fromMax"] = 0
        self.assertEqual(declaration["fromMax"], 2**80)

    def test_declare_kind_checks_id_uniqueness_and_declaration_shape(self) -> None:
        scene = empty_scene("alice")
        scene["kinds"]["used"] = {}
        invalid_calls = [
            ("Bad", {}),
            ("used", {}),
            ("new", {"symmetric": True, "toMax": 1}),
            ("new", {"fromMax": -1}),
            ("new", {"extra": True}),
        ]
        for kind_id, declaration in invalid_calls:
            with self.subTest(kind_id=kind_id, declaration=declaration):
                with self.assertRaises(ValueError):
                    paper_edits.declare_kind(scene, kind_id, declaration)

    def test_delete_kind_returns_declaration_and_rejects_live_relations(self) -> None:
        scene = empty_scene("alice", "bob")
        scene["kinds"] = {"holds": {"symmetric": True}, "unused": {"fromMax": 2}}
        scene["relations"] = [
            {"kind": "holds", "from": "alice/root", "to": "bob/root"}
        ]
        before = copy.deepcopy(scene)

        result = paper_edits.delete_kind(scene, "unused")

        self.assertEqual(scene, before)
        self.assertEqual(result["declaration"], {"fromMax": 2})
        self.assertEqual(result["scene"]["kinds"], {"holds": {"symmetric": True}})
        result["declaration"]["fromMax"] = 0
        self.assertEqual(scene, before)
        for kind_id in ("missing", "holds"):
            with self.subTest(kind_id=kind_id):
                with self.assertRaises(ValueError):
                    paper_edits.delete_kind(scene, kind_id)

    def test_insert_and_delete_body_return_copies_and_check_preconditions(self) -> None:
        scene = empty_scene("alice")
        body = empty_body("constructor")

        inserted = paper_edits.insert_body(scene, "constructor", body)

        self.assertEqual(inserted["bodies"]["constructor"], body)
        inserted["bodies"]["constructor"]["root"] = "changed"
        self.assertEqual(body["root"], "constructor")
        self.assertNotIn("constructor", scene["bodies"])
        for name, candidate in (
            ("Bad", body),
            ("alice", body),
            ("new", {"root": "missing", "vessels": {}}),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    paper_edits.insert_body(scene, name, candidate)

        deletable = paper_edits.insert_body(scene, "bob", empty_body("root"))
        deleted = paper_edits.delete_body(deletable, "bob")
        self.assertEqual(deleted["body"], empty_body("root"))
        self.assertNotIn("bob", deleted["scene"]["bodies"])
        deleted["body"]["root"] = "changed"
        self.assertEqual(deletable["bodies"]["bob"]["root"], "root")

    def test_delete_body_rejects_missing_and_referenced_bodies(self) -> None:
        scene = empty_scene("alice", "bob")
        scene["kinds"]["holds"] = {}
        scene["relations"].append(
            {"kind": "holds", "from": "alice/root", "to": "bob/root"}
        )
        for name in ("missing", "alice", "bob"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    paper_edits.delete_body(scene, name)

    def test_add_relation_preserves_orientation_and_checks_symmetric_duplicate(self) -> None:
        scene = empty_scene("alice", "bob")
        scene["kinds"]["holds"] = {"symmetric": True}
        relation = {"kind": "holds", "from": "bob/root", "to": "alice/root"}

        result = paper_edits.add_relation(scene, relation)

        self.assertEqual(result["relations"], [relation])
        self.assertEqual(scene["relations"], [])
        result["relations"][0]["from"] = "changed/root"
        self.assertEqual(relation["from"], "bob/root")
        with self.assertRaises(ValueError):
            paper_edits.add_relation(
                paper_edits.add_relation(scene, relation),
                {"kind": "holds", "from": "alice/root", "to": "bob/root"},
            )

    def test_add_relation_checks_existence_irreflexivity_and_multiplicity(self) -> None:
        scene = empty_scene("alice", "bob", "carol")
        scene["kinds"] = {
            "follows": {"irreflexive": True, "fromMax": 1, "toMax": 1},
            "touches": {"symmetric": True, "fromMax": 1},
        }
        invalid_first_relations = [
            {"kind": "missing", "from": "alice/root", "to": "bob/root"},
            {"kind": "follows", "from": "alice/missing", "to": "bob/root"},
            {"kind": "follows", "from": "alice/root", "to": "alice/root"},
            {"kind": "touches", "from": "alice/root", "to": "alice/root"},
        ]
        for relation in invalid_first_relations:
            with self.subTest(relation=relation):
                with self.assertRaises(ValueError):
                    paper_edits.add_relation(scene, relation)

        occupied = paper_edits.add_relation(
            scene,
            {"kind": "follows", "from": "alice/root", "to": "bob/root"},
        )
        for relation in (
            {"kind": "follows", "from": "alice/root", "to": "carol/root"},
            {"kind": "follows", "from": "carol/root", "to": "bob/root"},
        ):
            with self.subTest(relation=relation):
                with self.assertRaises(ValueError):
                    paper_edits.add_relation(occupied, relation)

    def test_remove_relation_uses_symmetric_equivalence_and_returns_stored_record(self) -> None:
        scene = empty_scene("alice", "bob")
        scene["kinds"] = {"holds": {"symmetric": True}, "follows": {}}
        stored = {"kind": "holds", "from": "bob/root", "to": "alice/root"}
        scene["relations"] = [stored]

        result = paper_edits.remove_relation(
            scene,
            {"kind": "holds", "from": "alice/root", "to": "bob/root"},
        )

        self.assertEqual(result, {"scene": {**scene, "relations": []}, "relation": stored})
        result["relation"]["from"] = "changed/root"
        self.assertEqual(scene["relations"], [stored])
        with self.assertRaises(ValueError):
            paper_edits.remove_relation(
                {**scene, "kinds": {"holds": {}}},
                {"kind": "holds", "from": "alice/root", "to": "bob/root"},
            )

    def test_relations_at_matches_both_positions_and_returns_copies(self) -> None:
        scene = empty_scene("alice", "bob", "carol")
        scene["kinds"] = {"holds": {"symmetric": True}, "follows": {}}
        scene["relations"] = [
            {"kind": "holds", "from": "alice/root", "to": "bob/root"},
            {"kind": "follows", "from": "carol/root", "to": "alice/root"},
        ]
        before = copy.deepcopy(scene)

        found = paper_edits.relations_at(scene, "alice/root")

        self.assertEqual(found, scene["relations"])
        found[0]["from"] = "changed/root"
        self.assertEqual(scene, before)
        self.assertEqual(paper_edits.relations_at(scene, "ghost/root"), [])
        for malformed in ("alice", "/alice/root", "alice//root"):
            with self.subTest(address=malformed):
                with self.assertRaises(ValueError):
                    paper_edits.relations_at(scene, malformed)


class RunCaseTests(unittest.TestCase):
    def test_run_case_dispatches_camel_case_and_normalizes_doll_connections(self) -> None:
        body = empty_body("a", "b", "c", "d")
        body["vessels"]["a"] = {"ports": {"right": {"vessel": "b", "side": "left"}}}
        body["vessels"]["b"] = {"ports": {"left": {"vessel": "a", "side": "right"}}}
        body["vessels"]["c"] = {"ports": {"right": {"vessel": "d", "side": "left"}}}
        body["vessels"]["d"] = {"ports": {"left": {"vessel": "c", "side": "right"}}}

        projection = paper_edits.run_case(
            {
                "subject": "paper-doll/v3",
                "operation": "connect",
                "input": {
                    "args": [
                        body,
                        {"vessel": "d", "side": "left"},
                        {"vessel": "a", "side": "right"},
                    ]
                },
            }
        )

        self.assertEqual(projection["outcome"], "ok")
        self.assertEqual(
            projection["value"]["displaced"],
            [
                {
                    "from": {"vessel": "a", "side": "right"},
                    "to": {"vessel": "b", "side": "left"},
                },
                {
                    "from": {"vessel": "c", "side": "right"},
                    "to": {"vessel": "d", "side": "left"},
                },
            ],
        )

    def test_run_case_projects_checked_errors(self) -> None:
        projection = paper_edits.run_case(
            {
                "subject": "paper-doll/v3",
                "operation": "deleteVessel",
                "input": {"args": [empty_body("root"), "root"]},
            }
        )
        self.assertEqual(projection, {"outcome": "error"})

    def test_run_case_preserves_stored_chain_relation_orientation(self) -> None:
        scene = empty_scene("alice", "bob")
        scene["kinds"]["holds"] = {"symmetric": True}
        stored = {"kind": "holds", "from": "bob/root", "to": "alice/root"}
        scene["relations"] = [stored]

        projection = paper_edits.run_case(
            {
                "subject": "paperchain/v1",
                "operation": "removeRelation",
                "input": {
                    "args": [
                        scene,
                        {"kind": "holds", "from": "alice/root", "to": "bob/root"},
                    ]
                },
            }
        )

        self.assertEqual(projection["outcome"], "ok")
        self.assertEqual(projection["value"]["relation"], stored)

    def test_run_case_rejects_unknown_or_malformed_dispatch(self) -> None:
        invalid_cases = [
            {"subject": "paper-doll/v3", "operation": "unknown", "input": {"args": []}},
            {"subject": "paperchain/v1", "operation": "connect", "input": {"args": []}},
            {"subject": "paper-doll/v3", "operation": "connect", "input": {}},
        ]
        for case in invalid_cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    paper_edits.run_case(case)


if __name__ == "__main__":
    unittest.main()
