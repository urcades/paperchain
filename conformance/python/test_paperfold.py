"""Behavioral tests for the independent Paperfold reference."""

from __future__ import annotations

import copy
import importlib.util
import unittest

from conformance.python import paperfold


def empty_body(root: str = "root") -> dict:
    return {"root": root, "vessels": {root: {}}}


def connected_body() -> dict:
    return {
        "root": "root",
        "vessels": {
            "root": {"ports": {"right": {"vessel": "arm", "side": "left"}}},
            "arm": {"ports": {"left": {"vessel": "root", "side": "right"}}},
        },
    }


def patch(*entries: dict) -> dict:
    return {"protocol": "paperfold/v1", "patch": list(entries)}


def scene_patch(*entries: dict) -> dict:
    return {"protocol": "paperfold/v2", "patch": list(entries)}


class PublicModuleTests(unittest.TestCase):
    def test_reference_module_and_complete_surface_are_public(self) -> None:
        """Removing any contracted entry point must fail the packaging surface."""

        self.assertIsNotNone(importlib.util.find_spec("conformance.python.paperfold"))
        names = {
            "validate_patch", "apply_patch", "invert_patch", "compose_patches",
            "canonicalize_body", "diff_bodies", "validate_scene_patch",
            "apply_scene_patch", "invert_scene_patch", "compose_scene_patches",
            "canonicalize_scene", "diff_scenes", "run_case",
        }
        self.assertFalse(names.difference(vars(paperfold)))


class ValidationTests(unittest.TestCase):
    def test_validators_return_op_errors_for_every_finite_json_type(self) -> None:
        """An unhashable operation value must be invalid rather than crash validation."""

        malformed_ops = [None, False, 0, 1.5, [], {}, ["connect"], {"name": "connect"}]
        for malformed_op in malformed_ops:
            with self.subTest(protocol="paperfold/v1", op=malformed_op):
                errors = paperfold.validate_patch(
                    {"protocol": "paperfold/v1", "patch": [{"op": malformed_op}]}
                )
                self.assertIn("$.patch.0.op", {error["path"] for error in errors})
            with self.subTest(protocol="paperfold/v2", op=malformed_op):
                errors = paperfold.validate_scene_patch(
                    {"protocol": "paperfold/v2", "patch": [{"op": malformed_op}]}
                )
                self.assertIn("$.patch.0.op", {error["path"] for error in errors})

    def test_v2_rejects_odd_nested_body_path_segments(self) -> None:
        """A nested body path must contain complete vessel/element pairs."""

        document = scene_patch({
            "op": "insertElement", "body": "alice", "path": "outer/child/inner",
            "vesselId": "slot", "element": {"kind": "item"}, "index": 0,
        })
        errors = paperfold.validate_scene_patch(document)
        self.assertIn("$.patch.0.path", {error["path"] for error in errors})

    def test_v1_accepts_every_entry_shape(self) -> None:
        """Dropping one of the seven v1 variants must fail structural validation."""

        element = {"kind": "item", "id": "coin"}
        vessel = {"accepts": [{"kind": "item"}], "contains": [element]}
        entries = [
            {"op": "connect", "from": {"vessel": "a", "side": "right"},
             "to": {"vessel": "b", "side": "left"}, "displaced": []},
            {"op": "disconnect", "endpoint": {"vessel": "a", "side": "right"},
             "removed": {"from": {"vessel": "a", "side": "right"},
                         "to": {"vessel": "b", "side": "left"}}},
            {"op": "insertVessel", "vesselId": "a", "vessel": {}, "bridged": None},
            {"op": "deleteVessel", "vesselId": "a", "vessel": vessel,
             "collapsed": None, "collapseOppositeNeighbors": False},
            {"op": "insertElement", "vesselId": "a", "element": element, "index": 0},
            {"op": "removeElement", "vesselId": "a", "index": 0, "element": element},
            {"op": "moveElement", "from": "a", "index": 0, "to": "b",
             "element": element, "toIndex": 0},
        ]
        self.assertEqual(paperfold.validate_patch(patch(*entries)), [])

    def test_v2_accepts_kernel_targets_and_all_scene_entry_shapes(self) -> None:
        """Losing a targeted or scene variant must fail the complete v2 vocabulary."""

        target = {
            "op": "insertElement", "body": "alice", "path": "pocket/bag",
            "vesselId": "inside", "element": {"kind": "item"}, "index": 0,
        }
        body = empty_body()
        relation = {"kind": "link", "from": "alice/root", "to": "bob/root"}
        entries = [
            target,
            {"op": "declareKind", "kindId": "link", "declaration": {"symmetric": True}},
            {"op": "deleteKind", "kindId": "link", "declaration": {"symmetric": True}},
            {"op": "insertBody", "name": "alice", "body": body},
            {"op": "deleteBody", "name": "alice", "body": body},
            {"op": "addRelation", "relation": relation},
            {"op": "removeRelation", "relation": relation},
        ]
        self.assertEqual(paperfold.validate_scene_patch(scene_patch(*entries)), [])

    def test_validators_collect_paths_for_unknown_missing_and_malformed_fields(self) -> None:
        """Weakening strict shape checks must expose the exact bad member paths."""

        invalid = {
            "protocol": "paperfold/v1", "extra": True,
            "patch": [
                {"op": "disconnect", "endpoint": {"vessel": "Bad", "side": "north"},
                 "removed": None, "surprise": 1},
                {"op": "insertVessel", "vesselId": "new", "vessel": {"ports": {}},
                 "bridged": None},
                {"op": "unknown"},
            ],
        }
        paths = {error["path"] for error in paperfold.validate_patch(invalid)}
        self.assertTrue({
            "$.extra", "$.patch.0.surprise", "$.patch.0.endpoint.vessel",
            "$.patch.0.endpoint.side", "$.patch.0.removed", "$.patch.1.vessel.ports",
            "$.patch.2.op",
        }.issubset(paths))

        scene_paths = {error["path"] for error in paperfold.validate_scene_patch({
            "protocol": "paperfold/v2",
            "patch": [
                {"op": "declareKind", "kindId": "k",
                 "declaration": {"symmetric": True, "toMax": 1}},
                {"op": "addRelation", "relation": {"kind": "k", "from": "bare", "to": "x/root"}},
                {"op": "insertElement", "body": "Bad", "path": "one",
                 "vesselId": "root", "element": {"kind": "item"}, "index": 0},
            ],
        })}
        self.assertTrue({
            "$.patch.0.declaration.toMax", "$.patch.1.relation.from",
            "$.patch.2.body", "$.patch.2.path",
        }.issubset(scene_paths))

    def test_invert_and_compose_throw_for_invalid_protocol_documents(self) -> None:
        """Treating malformed documents as trusted patches must remain impossible."""

        invalid = {"protocol": "paperfold/v1", "patch": [{"op": "wat"}]}
        with self.assertRaises(ValueError):
            paperfold.invert_patch(invalid)
        with self.assertRaises(ValueError):
            paperfold.compose_patches(patch(), {"protocol": "paperfold/v2", "patch": []})
        with self.assertRaises(ValueError):
            paperfold.invert_scene_patch({"protocol": "paperfold/v2", "patch": [{"op": "wat"}]})


class BodyPatchTests(unittest.TestCase):
    def assert_applies(self, before: dict, entry: dict, after: dict) -> None:
        original_body = copy.deepcopy(before)
        document = patch(entry)
        original_patch = copy.deepcopy(document)
        result = paperfold.apply_patch(before, document)
        self.assertEqual(result, {"ok": True, "value": paperfold.canonicalize_body(after)})
        self.assertEqual(before, original_body)
        self.assertEqual(document, original_patch)

    def test_integral_float_move_indices_apply_and_invert(self) -> None:
        # A direct json.loads caller retains the spelling 0.0 as float. It is
        # still a valid integer index under the protocol's numeric equality.
        before = {"root": "root", "vessels": {"root": {"contains": [{"kind": "item"}]}, "free": {}}}
        after = {"root": "root", "vessels": {"root": {}, "free": {"contains": [{"kind": "item"}]}}}
        entry = {"op": "moveElement", "from": "root", "index": 0.0, "to": "free", "element": {"kind": "item"}, "toIndex": 0.0}
        for scene in (False, True):
            with self.subTest(scene=scene):
                source = {"protocol": "paperchain/v1", "bodies": {"actor": before}, "kinds": {}, "relations": []} if scene else before
                target = {"protocol": "paperchain/v1", "bodies": {"actor": after}, "kinds": {}, "relations": []} if scene else after
                document = scene_patch(dict(entry, body="actor")) if scene else patch(entry)
                validate = paperfold.validate_scene_patch if scene else paperfold.validate_patch
                apply = paperfold.apply_scene_patch if scene else paperfold.apply_patch
                invert = paperfold.invert_scene_patch if scene else paperfold.invert_patch
                canonicalize = paperfold.canonicalize_scene if scene else paperfold.canonicalize_body
                original_source, original_document = copy.deepcopy(source), copy.deepcopy(document)
                self.assertEqual(validate(document), [])
                applied = apply(source, document)
                self.assertEqual(applied, {"ok": True, "value": canonicalize(target)})
                self.assertEqual(apply(applied["value"], invert(document)), {"ok": True, "value": canonicalize(source)})
                self.assertEqual(source, original_source)
                self.assertEqual(document, original_document)

    def test_apply_executes_all_seven_entry_types(self) -> None:
        """Routing any v1 op to the wrong edit must change one literal result."""

        base = {"root": "root", "vessels": {"root": {}, "arm": {}}}
        linked = connected_body()
        self.assert_applies(base, {
            "op": "connect", "from": {"vessel": "root", "side": "right"},
            "to": {"vessel": "arm", "side": "left"}, "displaced": [],
        }, linked)
        self.assert_applies(linked, {
            "op": "disconnect", "endpoint": {"vessel": "root", "side": "right"},
            "removed": {"from": {"vessel": "root", "side": "right"},
                        "to": {"vessel": "arm", "side": "left"}},
        }, base)
        self.assert_applies(empty_body(), {
            "op": "insertVessel", "vesselId": "arm", "vessel": {}, "bridged": None,
        }, base)
        self.assert_applies(base, {
            "op": "deleteVessel", "vesselId": "arm", "vessel": {}, "collapsed": None,
        }, empty_body())
        coin = {"kind": "item", "id": "coin"}
        holding = {"root": "root", "vessels": {"root": {"contains": [coin]}}}
        self.assert_applies(empty_body(), {
            "op": "insertElement", "vesselId": "root", "element": coin, "index": 0,
        }, holding)
        self.assert_applies(holding, {
            "op": "removeElement", "vesselId": "root", "index": 0, "element": coin,
        }, empty_body())
        before_move = {"root": "root", "vessels": {"root": {"contains": [coin]}, "bag": {}}}
        after_move = {"root": "root", "vessels": {"root": {}, "bag": {"contains": [coin]}}}
        self.assert_applies(before_move, {
            "op": "moveElement", "from": "root", "index": 0, "to": "bag",
            "element": coin, "toIndex": 0,
        }, after_move)

    def test_stale_records_and_final_invalidity_fail_atomically(self) -> None:
        """Ignoring integrity records or partial mutation must be detected."""

        body = connected_body()
        original = copy.deepcopy(body)
        stale = patch({
            "op": "disconnect", "endpoint": {"vessel": "root", "side": "right"},
            "removed": {"from": {"vessel": "root", "side": "top"},
                        "to": {"vessel": "arm", "side": "bottom"}},
        })
        result = paperfold.apply_patch(body, stale)
        self.assertFalse(result["ok"])
        self.assertIn("$.patch.0.removed", {error["path"] for error in result["errors"]})
        self.assertEqual(body, original)

        invalid_final = paperfold.apply_patch(empty_body(), patch(
            {"op": "insertVessel", "vesselId": "free", "vessel": {}, "bridged": None},
            {"op": "insertVessel", "vesselId": "other", "vessel": {}, "bridged": None},
            {"op": "connect", "from": {"vessel": "free", "side": "right"},
             "to": {"vessel": "other", "side": "left"}, "displaced": []},
        ))
        self.assertFalse(invalid_final["ok"])

    def test_connection_staleness_ignores_orientation(self) -> None:
        """Connection records must compare as undirected endpoint pairs."""

        result = paperfold.apply_patch(connected_body(), patch({
            "op": "disconnect", "endpoint": {"vessel": "root", "side": "right"},
            "removed": {"from": {"vessel": "arm", "side": "left"},
                        "to": {"vessel": "root", "side": "right"}},
        }))
        self.assertEqual(result, {"ok": True, "value": {
            "root": "root", "vessels": {"root": {}, "arm": {}}
        }})

    def test_invert_covers_every_v1_variant_and_roundtrips(self) -> None:
        """Omitting an inverse expansion must break op coverage or roundtrip."""

        coin = {"kind": "item", "id": "coin"}
        all_ops = patch(
            {"op": "connect", "from": {"vessel": "a", "side": "right"},
             "to": {"vessel": "b", "side": "left"}, "displaced": []},
            {"op": "disconnect", "endpoint": {"vessel": "a", "side": "right"},
             "removed": {"from": {"vessel": "a", "side": "right"},
                         "to": {"vessel": "b", "side": "left"}}},
            {"op": "insertVessel", "vesselId": "v", "vessel": {}, "bridged": None},
            {"op": "deleteVessel", "vesselId": "v", "vessel": {}, "collapsed": None},
            {"op": "insertElement", "vesselId": "a", "element": coin, "index": 0},
            {"op": "removeElement", "vesselId": "a", "index": 0, "element": coin},
            {"op": "moveElement", "from": "a", "index": 0, "to": "b",
             "element": coin, "toIndex": 0},
        )
        inverse = paperfold.invert_patch(all_ops)
        self.assertEqual(
            [entry["op"] for entry in inverse["patch"]],
            ["removeElement", "insertElement", "insertElement", "removeElement",
             "insertVessel", "deleteVessel", "connect", "disconnect"],
        )
        forward = patch({
            "op": "insertElement", "vesselId": "root", "element": coin, "index": 0,
        })
        applied = paperfold.apply_patch(empty_body(), forward)
        self.assertTrue(applied["ok"])
        restored = paperfold.apply_patch(applied["value"], paperfold.invert_patch(forward))
        self.assertEqual(restored, {"ok": True, "value": empty_body()})

    def test_compose_concatenates_deep_copies(self) -> None:
        """Composition must preserve order without aliasing either source."""

        first = patch({"op": "insertVessel", "vesselId": "arm", "vessel": {}, "bridged": None})
        second = patch({"op": "deleteVessel", "vesselId": "arm", "vessel": {}, "collapsed": None})
        composed = paperfold.compose_patches(first, second)
        first["patch"].clear()
        second["patch"].clear()
        self.assertEqual([entry["op"] for entry in composed["patch"]], ["insertVessel", "deleteVessel"])
        self.assertEqual(paperfold.apply_patch(empty_body(), composed), {"ok": True, "value": empty_body()})


class ScenePatchTests(unittest.TestCase):
    def test_apply_executes_all_six_scene_entries(self) -> None:
        """Every chain operation must be reified with its public field names."""

        alice = empty_body()
        bob = empty_body()
        initial = {"protocol": "paperchain/v1", "bodies": {"alice": alice}, "kinds": {}, "relations": []}
        relation = {"kind": "link", "from": "alice/root", "to": "bob/root"}
        transaction = scene_patch(
            {"op": "declareKind", "kindId": "link", "declaration": {"symmetric": True}},
            {"op": "insertBody", "name": "bob", "body": bob},
            {"op": "addRelation", "relation": relation},
            {"op": "removeRelation", "relation": relation},
            {"op": "deleteBody", "name": "bob", "body": bob},
            {"op": "deleteKind", "kindId": "link", "declaration": {"symmetric": True}},
        )
        self.assertEqual(paperfold.apply_scene_patch(initial, transaction), {
            "ok": True, "value": initial,
        })

    def test_nested_body_path_applies_and_reembeds_without_touching_siblings(self) -> None:
        """Resolving a path at the wrong level must visibly alter the wrong body."""

        inner = {"root": "inside", "vessels": {"inside": {}, "sibling": {}}}
        outer = {
            "root": "pocket",
            "vessels": {"pocket": {"contains": [{"kind": "bag", "id": "bag", "body": inner}]}},
        }
        scene = {"protocol": "paperchain/v1", "bodies": {"alice": outer}, "kinds": {}, "relations": []}
        target_patch = scene_patch({
            "op": "insertElement", "body": "alice", "path": "pocket/bag",
            "vesselId": "inside", "element": {"kind": "item", "id": "coin"}, "index": 0,
        })
        result = paperfold.apply_scene_patch(scene, target_patch)
        self.assertTrue(result["ok"])
        embedded = result["value"]["bodies"]["alice"]["vessels"]["pocket"]["contains"][0]["body"]
        self.assertEqual(embedded["vessels"]["inside"]["contains"], [{"kind": "item", "id": "coin"}])
        self.assertEqual(embedded["vessels"]["sibling"], {})

    def test_missing_nested_path_and_dangling_relation_fail_atomically(self) -> None:
        """A stale target or orphaned endpoint must refuse the whole transaction."""

        scene = {
            "protocol": "paperchain/v1",
            "bodies": {"alice": {"root": "root", "vessels": {"root": {"contains": [{"kind": "item", "id": "coin"}]}}}},
            "kinds": {"points": {}},
            "relations": [{"kind": "points", "from": "alice/root", "to": "alice/root/coin"}],
        }
        original = copy.deepcopy(scene)
        stale = paperfold.apply_scene_patch(scene, scene_patch({
            "op": "insertElement", "body": "alice", "path": "root/missing",
            "vesselId": "inside", "element": {"kind": "item"}, "index": 0,
        }))
        self.assertFalse(stale["ok"])
        self.assertEqual(scene, original)
        dangling = paperfold.apply_scene_patch(scene, scene_patch({
            "op": "removeElement", "body": "alice", "vesselId": "root", "index": 0,
            "element": {"kind": "item", "id": "coin"},
        }))
        self.assertFalse(dangling["ok"])
        self.assertEqual(scene, original)

    def test_symmetric_remove_requires_true_stored_orientation(self) -> None:
        """Relation equivalence must not weaken destruction-record exactness."""

        scene = {
            "protocol": "paperchain/v1",
            "bodies": {"alice": empty_body(), "bob": empty_body()},
            "kinds": {"link": {"symmetric": True}},
            "relations": [{"kind": "link", "from": "bob/root", "to": "alice/root"}],
        }
        stale = scene_patch({
            "op": "removeRelation",
            "relation": {"kind": "link", "from": "alice/root", "to": "bob/root"},
        })
        result = paperfold.apply_scene_patch(scene, stale)
        self.assertFalse(result["ok"])
        self.assertIn("$.patch.0.relation", {error["path"] for error in result["errors"]})
        exact = scene_patch({"op": "removeRelation", "relation": scene["relations"][0]})
        self.assertTrue(paperfold.apply_scene_patch(scene, exact)["ok"])

    def test_scene_invert_and_compose_preserve_targets_and_roundtrip(self) -> None:
        """Scene inversion must restamp body/path and reverse dependencies."""

        body = empty_body()
        base = {"protocol": "paperchain/v1", "bodies": {"alice": body}, "kinds": {}, "relations": []}
        forward = scene_patch(
            {"op": "declareKind", "kindId": "link", "declaration": {}},
            {"op": "insertElement", "body": "alice", "vesselId": "root",
             "element": {"kind": "item", "id": "coin"}, "index": 0},
        )
        combined = paperfold.compose_scene_patches(scene_patch(), forward)
        applied = paperfold.apply_scene_patch(base, combined)
        self.assertTrue(applied["ok"])
        inverse = paperfold.invert_scene_patch(forward)
        self.assertEqual(inverse["patch"][0]["body"], "alice")
        self.assertEqual([entry["op"] for entry in inverse["patch"]], ["removeElement", "deleteKind"])
        self.assertEqual(paperfold.apply_scene_patch(applied["value"], inverse), {"ok": True, "value": base})


class CanonicalAndDiffTests(unittest.TestCase):
    def test_canonicalization_is_recursive_and_scene_sort_keeps_orientation(self) -> None:
        """Empty residue and relation order normalize without endpoint swapping."""

        nested = empty_body("inner")
        nested["vessels"]["inner"] = {"contains": [], "ports": {}}
        body = {
            "root": "root", "vessels": {
                "root": {"ports": {}, "contains": [{"kind": "bag", "id": "bag", "body": nested}]}
            },
        }
        canonical = paperfold.canonicalize_body(body)
        self.assertNotIn("ports", canonical["vessels"]["root"])
        self.assertNotIn("contains", canonical["vessels"]["root"]["contains"][0]["body"]["vessels"]["inner"])
        reversed_relation = {"kind": "link", "from": "bob/root", "to": "alice/root"}
        earlier = {"kind": "a", "from": "bob/root", "to": "alice/root"}
        scene = {
            "protocol": "paperchain/v1", "bodies": {"alice": empty_body(), "bob": empty_body()},
            "kinds": {"link": {"symmetric": True}, "a": {}},
            "relations": [reversed_relation, earlier],
        }
        canonical_scene = paperfold.canonicalize_scene(scene)
        self.assertEqual(canonical_scene["relations"], [earlier, reversed_relation])
        self.assertEqual(canonical_scene["relations"][1]["from"], "bob/root")

    def test_body_diff_is_sound_invertible_and_checks_partial_domain(self) -> None:
        """A diff may be coarse but must reach and restore exact canonical bodies."""

        source = connected_body()
        source["vessels"]["root"]["contains"] = [{"kind": "item", "id": "old"}]
        target = {
            "root": "root",
            "vessels": {
                "root": {"contains": [{"kind": "item", "id": "new"}]},
                "leg": {},
            },
        }
        difference = paperfold.diff_bodies(source, target)
        self.assertTrue(difference["ok"])
        applied = paperfold.apply_patch(source, difference["value"])
        self.assertEqual(applied, {"ok": True, "value": paperfold.canonicalize_body(target)})
        self.assertEqual(
            paperfold.apply_patch(applied["value"], paperfold.invert_patch(difference["value"])),
            {"ok": True, "value": paperfold.canonicalize_body(source)},
        )
        self.assertFalse(paperfold.diff_bodies(empty_body("a"), empty_body("b"))["ok"])
        changed_accepts = empty_body()
        changed_accepts["vessels"]["root"]["accepts"] = []
        self.assertFalse(paperfold.diff_bodies(empty_body(), changed_accepts)["ok"])

    def test_scene_diff_handles_body_kind_and_true_orientation_changes(self) -> None:
        """Symmetric endpoint reversal must survive as stored scene state."""

        source = {
            "protocol": "paperchain/v1", "bodies": {"alice": empty_body(), "bob": empty_body()},
            "kinds": {"link": {"symmetric": True}},
            "relations": [{"kind": "link", "from": "alice/root", "to": "bob/root"}],
        }
        target = copy.deepcopy(source)
        target["bodies"]["alice"]["vessels"]["root"]["contains"] = [{"kind": "item", "id": "coin"}]
        target["relations"] = [{"kind": "link", "from": "bob/root", "to": "alice/root"}]
        difference = paperfold.diff_scenes(source, target)
        self.assertTrue(difference["ok"])
        self.assertEqual(paperfold.apply_scene_patch(source, difference["value"]), {
            "ok": True, "value": paperfold.canonicalize_scene(target),
        })
        ops = [entry["op"] for entry in difference["value"]["patch"]]
        self.assertIn("removeRelation", ops)
        self.assertIn("addRelation", ops)

    def test_run_case_projects_results_errors_and_diff_laws(self) -> None:
        """Fixture dispatch must preserve all contract outcome channels."""

        valid_case = {"subject": "paperfold/v1", "operation": "validatePatch", "input": {"args": [patch()]}}
        self.assertEqual(paperfold.run_case(valid_case), {"outcome": "valid"})
        invalid_case = {
            "subject": "paperfold/v1", "operation": "applyPatch",
            "input": {"args": [empty_body(), patch({"op": "wat"})]},
        }
        projected = paperfold.run_case(invalid_case)
        self.assertEqual(projected["outcome"], "invalid")
        self.assertIn("$.patch.0.op", projected["errorPaths"])
        laws_case = {
            "subject": "paperfold/v1", "operation": "diffLaws",
            "input": {"args": [empty_body(), {"root": "root", "vessels": {"root": {}, "free": {}}}]},
        }
        self.assertEqual(paperfold.run_case(laws_case), {
            "outcome": "ok",
            "value": {"applied": {"root": "root", "vessels": {"root": {}, "free": {}}}, "restored": empty_body()},
        })
        with self.assertRaises(ValueError):
            paperfold.run_case({"subject": "paperfold/v1", "operation": "wat", "input": {"args": []}})


if __name__ == "__main__":
    unittest.main()
