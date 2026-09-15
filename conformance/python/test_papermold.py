"""Behavioral tests for the independent Papermold reference."""

from __future__ import annotations

import copy
import unittest

try:
    from . import papermold as mold
except ImportError:  # Direct execution from this directory.
    import papermold as mold


def body(*, vessels=None, root="core"):
    return {"root": root, "vessels": vessels if vessels is not None else {"core": {}}}


def v1(profiles=None):
    return {"protocol": "papermold/v1", "profiles": profiles if profiles is not None else {}}


def v2(profiles=None, scene_profiles=None):
    return {
        "protocol": "papermold/v2",
        "profiles": profiles if profiles is not None else {},
        "sceneProfiles": scene_profiles if scene_profiles is not None else {},
    }


def scene(*, bodies=None, kinds=None, relations=None):
    return {
        "protocol": "paperchain/v1",
        "bodies": bodies if bodies is not None else {},
        "kinds": kinds if kinds is not None else {},
        "relations": relations if relations is not None else [],
    }


def paths(errors):
    return [error["path"] for error in errors]


class ProfileValidationTests(unittest.TestCase):
    def test_empty_v1_document_is_valid(self) -> None:
        """Catches rejecting the protocol's vacuously valid empty profile map."""

        self.assertEqual(mold.validate_profiles({"protocol": "papermold/v1", "profiles": {}}), [])

    def test_v1_rejects_unknown_keys_bad_ids_and_empty_demands(self) -> None:
        """Catches permissive object handling and missing identifier checks."""

        document = {
            "protocol": "papermold/v1",
            "profiles": {
                "Bad": {"surprise": 1},
                "ok": {"vessels": {"bad_id": {}, "head": {"mystery": True}}},
            },
            "extra": None,
        }
        got = paths(mold.validate_profiles(document))
        self.assertIn("$.extra", got)
        self.assertIn("$.profiles.Bad", got)
        self.assertIn("$.profiles.Bad.surprise", got)
        self.assertIn("$.profiles.ok.vessels.bad_id", got)
        self.assertIn("$.profiles.ok.vessels.bad_id", got)
        self.assertIn("$.profiles.ok.vessels.head.mystery", got)

    def test_v1_rejects_every_malformed_clause_shape_and_dangling_reference(self) -> None:
        """Catches skipped validation branches in the six-clause demand grammar."""

        profiles = {
            "broken": {
                "vessels": {
                    "a": {"exists": False},
                    "b": {"ports": {}},
                    "c": {"ports": {"up": {}, "left": {"vessel": "Bad", "side": "west"}}},
                    "d": {"acceptsAtLeast": []},
                    "e": {"containsAtLeast": [{"kind": "ok", "extra": 1}]},
                    "f": {"forbids": "no"},
                    "g": {"conformsTo": {"token": {"kind": "item"}, "profile": "missing"}},
                },
                "atLeast": {
                    "n": 3,
                    "of": [{"vessel": "a", "check": {"exists": True}}],
                },
            }
        }
        got = paths(mold.validate_profiles(v1(profiles)))
        expected = {
            "$.profiles.broken.vessels.a.exists",
            "$.profiles.broken.vessels.b.ports",
            "$.profiles.broken.vessels.c.ports.up",
            "$.profiles.broken.vessels.c.ports.left.vessel",
            "$.profiles.broken.vessels.c.ports.left.side",
            "$.profiles.broken.vessels.d.acceptsAtLeast",
            "$.profiles.broken.vessels.e.containsAtLeast.0.extra",
            "$.profiles.broken.vessels.f.forbids",
            "$.profiles.broken.vessels.g.conformsTo.profile",
            "$.profiles.broken.atLeast.n",
        }
        self.assertTrue(expected.issubset(got), expected - set(got))

    def test_at_least_checks_shape_n_and_nonempty_of(self) -> None:
        """Catches accepting invalid thresholds or malformed selector entries."""

        profiles = {
            "zero": {"atLeast": {"n": 0, "of": []}},
            "shape": {"atLeast": {"n": 1.5, "of": [{"vessel": "x"}, 4]}},
        }
        got = paths(mold.validate_profiles(v1(profiles)))
        self.assertIn("$.profiles.zero.atLeast.n", got)
        self.assertIn("$.profiles.zero.atLeast.of", got)
        self.assertIn("$.profiles.shape.atLeast.n", got)
        self.assertIn("$.profiles.shape.atLeast.of.0.check", got)
        self.assertIn("$.profiles.shape.atLeast.of.1", got)

    def test_constructor_is_an_ordinary_explicit_profile_and_vessel_id(self) -> None:
        """Catches host-object lookup leaking into protocol dictionary semantics."""

        document = v1({"constructor": {"vessels": {"constructor": {"exists": True}}}})
        subject = body(root="constructor", vessels={"constructor": {}})
        self.assertEqual(mold.validate_profiles(document), [])
        self.assertTrue(mold.conforms(subject, document, "constructor"))

    def test_v1_port_side_array_returns_an_error_instead_of_throwing(self) -> None:
        """Catches hashing an arbitrary finite-JSON port side during validation."""

        document = v1(
            {
                "unit": {
                    "vessels": {
                        "core": {
                            "ports": {"top": {"vessel": "other", "side": []}}
                        }
                    }
                }
            }
        )
        try:
            errors = mold.validate_profiles(document)
        except TypeError as error:
            self.fail(f"validator threw for a finite JSON side: {error}")
        self.assertIn("$.profiles.unit.vessels.core.ports.top.side", paths(errors))


class SceneProfileValidationTests(unittest.TestCase):
    def test_empty_v2_namespaces_are_valid(self) -> None:
        """Catches treating required empty namespaces as invalid."""

        self.assertEqual(mold.validate_scene_profiles(v2()), [])

    def test_v2_rejects_namespace_shape_and_invalid_body_kind_demands(self) -> None:
        """Catches missing strict validation in named body/kind selectors."""

        document = v2(
            {"unit": {}},
            {
                "fight": {
                    "bodies": {"Bad": {}, "red": {"exists": False, "conformsTo": "missing"}},
                    "kinds": {
                        "Bad": {},
                        "holds": {
                            "declared": False,
                            "declaration": {"symmetric": True, "toMax": 1, "extra": 0},
                        },
                    },
                }
            },
        )
        got = set(paths(mold.validate_scene_profiles(document)))
        expected = {
            "$.sceneProfiles.fight.bodies.Bad",
            "$.sceneProfiles.fight.bodies.red.exists",
            "$.sceneProfiles.fight.bodies.red.conformsTo",
            "$.sceneProfiles.fight.kinds.Bad",
            "$.sceneProfiles.fight.kinds.holds.declared",
            "$.sceneProfiles.fight.kinds.holds.declaration.toMax",
            "$.sceneProfiles.fight.kinds.holds.declaration.extra",
        }
        self.assertTrue(expected.issubset(got), expected - got)

    def test_scene_references_resolve_only_in_body_profile_namespace(self) -> None:
        """Catches incorrectly resolving conformsTo through sceneProfiles."""

        document = v2({}, {"unit": {"bodies": {"red": {"conformsTo": "unit"}}}})
        self.assertIn(
            "$.sceneProfiles.unit.bodies.red.conformsTo",
            paths(mold.validate_scene_profiles(document)),
        )

    def test_v2_body_profile_port_side_object_returns_an_error(self) -> None:
        """Catches the v2 body-profile validator sharing the unhashable-side crash."""

        document = v2(
            {
                "unit": {
                    "vessels": {
                        "core": {
                            "ports": {"left": {"vessel": "other", "side": {}}}
                        }
                    }
                }
            },
            {},
        )
        try:
            errors = mold.validate_scene_profiles(document)
        except TypeError as error:
            self.fail(f"validator threw for a finite JSON side: {error}")
        self.assertIn("$.profiles.unit.vessels.core.ports.left.side", paths(errors))


class BodyJudgmentTests(unittest.TestCase):
    def setUp(self) -> None:
        nested = body()
        self.subject = body(
            vessels={
                "core": {
                    "ports": {"right": {"vessel": "hand", "side": "left"}},
                    "accepts": [{"kind": "item"}, {"kind": "doll"}, {"kind": "status"}],
                    "contains": [
                        {"kind": "status", "type": "alive"},
                        {"kind": "item", "type": "sword"},
                        {"kind": "doll", "id": "child", "body": nested},
                    ],
                },
                "hand": {"ports": {"left": {"vessel": "core", "side": "right"}}},
            }
        )

    def test_all_vessel_clauses_can_conform(self) -> None:
        """Catches wrong exact/wildcard, port, forbids, or recursive clause semantics."""

        profiles = {
            "seed": {"vessels": {"core": {"exists": True}}},
            "unit": {
                "vessels": {
                    "core": {
                        "exists": True,
                        "ports": {"right": {"vessel": "hand", "side": "left"}},
                        "acceptsAtLeast": [{"kind": "item", "type": "sword"}],
                        "containsAtLeast": [
                            {"kind": "status"},
                            {"kind": "item", "type": "sword"},
                        ],
                        "forbids": [{"kind": "status", "type": "dead"}],
                        "conformsTo": {"token": {"kind": "doll"}, "profile": "seed"},
                    }
                }
            },
        }
        document = v1(profiles)
        self.assertEqual(mold.judge(self.subject, document, "unit"), [])
        self.assertTrue(mold.conforms(self.subject, document, "unit"))

    def test_open_accepts_everything_but_sealed_and_narrow_accepts_fail(self) -> None:
        """Catches confusing admission-set coverage with element matching."""

        document = v1(
            {
                "wide": {"vessels": {"core": {"acceptsAtLeast": [{"kind": "item"}]}}},
                "exact": {
                    "vessels": {
                        "core": {"acceptsAtLeast": [{"kind": "item", "type": "sword"}]}
                    }
                },
            }
        )
        open_body = body()
        sealed = body(vessels={"core": {"accepts": []}})
        narrow = body(vessels={"core": {"accepts": [{"kind": "item", "type": "sword"}]}})
        self.assertTrue(mold.conforms(open_body, document, "wide"))
        self.assertFalse(mold.conforms(sealed, document, "exact"))
        self.assertFalse(mold.conforms(narrow, document, "wide"))

    def test_absence_dominates_and_other_failures_use_clause_paths(self) -> None:
        """Catches per-clause absence noise and imprecise judgment paths."""

        profiles = {
            "seed": {"vessels": {"missing": {"exists": True}}},
            "broken": {
                "vessels": {
                    "missing": {"exists": True, "forbids": [{"kind": "x"}]},
                    "core": {
                        "ports": {"left": {"vessel": "hand", "side": "right"}},
                        "acceptsAtLeast": [{"kind": "tool"}],
                        "containsAtLeast": [{"kind": "status", "type": "dead"}],
                        "forbids": [{"kind": "status"}],
                        "conformsTo": {"token": {"kind": "doll"}, "profile": "seed"},
                    },
                }
            },
        }
        got = paths(mold.judge(self.subject, v1(profiles), "broken"))
        self.assertEqual(got.count("$.profiles.broken.vessels.missing"), 1)
        for path in (
            "$.profiles.broken.vessels.core.ports.left",
            "$.profiles.broken.vessels.core.acceptsAtLeast.0",
            "$.profiles.broken.vessels.core.containsAtLeast.0",
            "$.profiles.broken.vessels.core.forbids.0",
            "$.profiles.broken.vessels.core.conformsTo",
        ):
            self.assertIn(path, got)

    def test_threshold_suppresses_failed_candidates_until_minimum_missed(self) -> None:
        """Catches leaking selector failures or counting clauses instead of checks."""

        checks = [
            {"vessel": "core", "check": {"exists": True}},
            {"vessel": "hand", "check": {"exists": True}},
            {"vessel": "missing", "check": {"exists": True}},
        ]
        document = v1(
            {
                "passes": {"atLeast": {"n": 2, "of": checks}},
                "fails": {"atLeast": {"n": 3, "of": checks}},
            }
        )
        self.assertEqual(mold.judge(self.subject, document, "passes"), [])
        self.assertEqual(paths(mold.judge(self.subject, document, "fails")), ["$.profiles.fails.atLeast"])

    def test_self_recursive_profile_terminates_on_finite_nested_bodies(self) -> None:
        """Catches profile-cycle rejection or recursion that does not descend through bodies."""

        document = v1(
            {
                "nest": {
                    "vessels": {
                        "core": {
                            "conformsTo": {"token": {"kind": "doll"}, "profile": "nest"}
                        }
                    }
                }
            }
        )
        self.assertEqual(
            paths(mold.judge(self.subject, document, "nest")),
            ["$.profiles.nest.vessels.core.conformsTo"],
        )

    def test_judgment_throws_for_invalid_caller_domain(self) -> None:
        """Catches conflating malformed inputs and missing names with nonconformance."""

        document = v1({"unit": {}})
        with self.assertRaises(ValueError):
            mold.judge({"root": "missing", "vessels": {}}, document, "unit")
        with self.assertRaises(ValueError):
            mold.judge(body(), {"protocol": "papermold/v1", "profiles": []}, "unit")
        with self.assertRaises(ValueError):
            mold.judge(body(), document, "missing")

    def test_memo_is_invocation_local_and_observes_mutation(self) -> None:
        """Catches stale cross-call conformance caching after caller mutation."""

        document = v1({"unit": {"vessels": {"core": {"forbids": [{"kind": "dead"}]}}}})
        subject = body(vessels={"core": {"contains": []}})
        self.assertTrue(mold.conforms(subject, document, "unit"))
        subject["vessels"]["core"]["contains"].append({"kind": "dead"})
        self.assertFalse(mold.conforms(subject, document, "unit"))


class SceneJudgmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.unit = body()
        self.scene = scene(
            bodies={"green": body(), "red": body(), "blue": body()},
            kinds={"holds": {}, "linked": {"symmetric": True}, "loops": {}},
            relations=[
                {"kind": "holds", "from": "red/core", "to": "blue/core"},
                {"kind": "holds", "from": "red/core", "to": "green/core"},
                {"kind": "linked", "from": "blue/core", "to": "red/core"},
                {"kind": "loops", "from": "red/core", "to": "red/core"},
            ],
        )
        self.document = v2(
            {"unit": {"vessels": {"core": {"forbids": [{"kind": "dead"}]}}}},
            {},
        )

    def test_named_bodies_and_kinds_apply_absence_and_subset_semantics(self) -> None:
        """Catches missing-body noise, forwarded body errors, and declaration equality mistakes."""

        document = copy.deepcopy(self.document)
        document["sceneProfiles"] = {
            "good": {
                "bodies": {"red": {"exists": True, "conformsTo": "unit"}},
                "kinds": {
                    "holds": {"declared": True, "declaration": {"symmetric": False}},
                    "linked": {"declaration": {"symmetric": True, "irreflexive": False}},
                },
            },
            "bad": {
                "bodies": {"missing": {"exists": True, "conformsTo": "unit"}},
                "kinds": {
                    "missing": {"declared": True, "declaration": {"fromMax": 2}},
                    "holds": {"declaration": {"fromMax": 2}},
                },
            },
        }
        self.assertEqual(mold.judge_scene(self.scene, document, "good"), [])
        got = paths(mold.judge_scene(self.scene, document, "bad"))
        self.assertEqual(got.count("$.sceneProfiles.bad.bodies.missing"), 1)
        self.assertEqual(got.count("$.sceneProfiles.bad.kinds.missing"), 1)
        self.assertIn("$.sceneProfiles.bad.kinds.holds.declaration.fromMax", got)

    def test_relation_demands_count_subtrees_roles_filters_and_self_once(self) -> None:
        """Catches exact-only anchors, double-counted self-relations, and ignored filters."""

        document = copy.deepcopy(self.document)
        document["sceneProfiles"] = {
            "counts": {
                "relations": [
                    {"at": "red", "kind": "holds", "role": "from", "atLeast": 2, "atMost": 2},
                    {
                        "at": "red/core",
                        "kind": "holds",
                        "atLeast": 1,
                        "atMost": 1,
                        "otherEndpoint": {"prefix": "blue"},
                    },
                    {
                        "at": "red",
                        "kind": "holds",
                        "atLeast": 2,
                        "otherEndpoint": {"conformsTo": "unit"},
                    },
                    {"at": "red", "kind": "linked", "role": "from", "atLeast": 1},
                    {"at": "red", "kind": "loops", "atLeast": 1, "atMost": 1},
                ]
            }
        }
        self.assertEqual(mold.judge_scene(self.scene, document, "counts"), [])

    def test_relation_bounds_and_unresolvable_anchor_report_precisely(self) -> None:
        """Catches early exit across demands and evaluating bounds after anchor absence."""

        document = copy.deepcopy(self.document)
        document["sceneProfiles"] = {
            "bad": {
                "relations": [
                    {"at": "missing", "kind": "holds", "atLeast": 1, "atMost": 1},
                    {"at": "red", "kind": "holds", "atLeast": 3},
                    {"at": "red", "kind": "holds", "atMost": 1},
                ]
            }
        }
        got = paths(mold.judge_scene(self.scene, document, "bad"))
        self.assertEqual(got.count("$.sceneProfiles.bad.relations.0"), 1)
        self.assertNotIn("$.sceneProfiles.bad.relations.0.atLeast", got)
        self.assertNotIn("$.sceneProfiles.bad.relations.0.atMost", got)
        self.assertIn("$.sceneProfiles.bad.relations.1.atLeast", got)
        self.assertIn("$.sceneProfiles.bad.relations.2.atMost", got)

    def test_universal_reports_sorted_witnesses_and_honors_exclusions(self) -> None:
        """Catches existential quantification, unsorted witnesses, or ignored exclusions."""

        document = copy.deepcopy(self.document)
        document["profiles"]["missing-vessel"] = {"vessels": {"other": {"exists": True}}}
        document["sceneProfiles"] = {
            "all": {
                "forAllBodies": [
                    {"excluding": ["red"], "check": {"conformsTo": "missing-vessel"}}
                ]
            }
        }
        got = mold.judge_scene(self.scene, document, "all")
        self.assertEqual(
            [error["path"] for error in got],
            [
                "$.sceneProfiles.all.forAllBodies.0.check.conformsTo",
                "$.sceneProfiles.all.forAllBodies.0.check.conformsTo",
            ],
        )
        self.assertIn("blue", got[0]["message"])
        self.assertIn("green", got[1]["message"])

    def test_relation_bans_are_global_or_anchored_and_missing_anchor_is_vacuous(self) -> None:
        """Catches resolving ban anchors as required or checking only exact endpoints."""

        document = copy.deepcopy(self.document)
        document["sceneProfiles"] = {
            "bans": {
                "forbidsRelations": [
                    {"kind": "holds"},
                    {"kind": "linked", "at": "red"},
                    {"kind": "holds", "at": "missing"},
                ]
            }
        }
        self.assertEqual(
            paths(mold.judge_scene(self.scene, document, "bans")),
            [
                "$.sceneProfiles.bans.forbidsRelations.0",
                "$.sceneProfiles.bans.forbidsRelations.1",
            ],
        )

    def test_v2_body_entrypoints_share_v1_semantics(self) -> None:
        """Catches applying the v2 scene namespace when judging a body profile."""

        self.assertEqual(mold.judge_body(self.unit, self.document, "unit"), [])
        self.assertTrue(mold.conforms_body(self.unit, self.document, "unit"))
        self.assertTrue(mold.conforms_scene(self.scene, v2({}, {"empty": {}}), "empty"))

    def test_scene_judgment_throws_for_invalid_inputs_and_unknown_profile(self) -> None:
        """Catches returning nonconformance for scene caller-domain violations."""

        document = v2({}, {"empty": {}})
        with self.assertRaises(ValueError):
            mold.judge_scene({"protocol": "paperchain/v1"}, document, "empty")
        with self.assertRaises(ValueError):
            mold.judge_scene(scene(), v2({}, {"bad": {"relations": []}}), "bad")
        with self.assertRaises(ValueError):
            mold.judge_scene(scene(), document, "missing")

    def test_scene_body_memo_is_local_to_each_call(self) -> None:
        """Catches carrying embedded body verdicts across scene calls after mutation."""

        document = v2(
            {"unit": {"vessels": {"core": {"forbids": [{"kind": "dead"}]}}}},
            {"all": {"forAllBodies": [{"check": {"conformsTo": "unit"}}]}},
        )
        subject = scene(bodies={"red": body()})
        self.assertTrue(mold.conforms_scene(subject, document, "all"))
        subject["bodies"]["red"]["vessels"]["core"]["contains"] = [{"kind": "dead"}]
        self.assertFalse(mold.conforms_scene(subject, document, "all"))

    def test_constructor_is_an_ordinary_explicit_scene_dictionary_key(self) -> None:
        """Catches inherited host keys masquerading as bodies, kinds, or profiles."""

        constructor_body = body(root="constructor", vessels={"constructor": {}})
        subject = scene(
            bodies={"constructor": constructor_body},
            kinds={"constructor": {}},
        )
        document = v2(
            {"constructor": {"vessels": {"constructor": {"exists": True}}}},
            {
                "constructor": {
                    "bodies": {"constructor": {"conformsTo": "constructor"}},
                    "kinds": {"constructor": {"declared": True}},
                }
            },
        )
        self.assertEqual(mold.judge_scene(subject, document, "constructor"), [])


class FixtureProjectionTests(unittest.TestCase):
    def case(self, subject, operation, args):
        return {"subject": subject, "operation": operation, "input": {"args": args}}

    def test_validator_and_judge_projections_include_paths(self) -> None:
        """Catches leaking implementation error records across the fixture boundary."""

        invalid = v1({"bad": {"vessels": {"core": {}}}})
        self.assertEqual(
            mold.run_case(self.case("papermold/v1", "validateProfiles", [invalid])),
            {"outcome": "invalid", "errorPaths": ["$.profiles.bad.vessels.core"]},
        )
        document = v1({"unit": {"vessels": {"missing": {"exists": True}}}})
        self.assertEqual(
            mold.run_case(self.case("papermold/v1", "judge", [body(), document, "unit"])),
            {
                "outcome": "nonconforming",
                "errorPaths": ["$.profiles.unit.vessels.missing"],
            },
        )

    def test_conforms_projection_and_caller_errors_are_distinct(self) -> None:
        """Catches projecting booleans as verdict outcomes or swallowing caller errors."""

        document = v2({}, {"empty": {}})
        self.assertEqual(
            mold.run_case(self.case("papermold/v2", "conformsScene", [scene(), document, "empty"])),
            {"outcome": "ok", "value": True},
        )
        self.assertEqual(
            mold.run_case(self.case("papermold/v2", "judgeScene", [scene(), document, "missing"])),
            {"outcome": "error"},
        )

    def test_run_case_rejects_unknown_or_incompatible_operation(self) -> None:
        """Catches silently dispatching across protocol namespaces."""

        with self.assertRaises(ValueError):
            mold.run_case(self.case("papermold/v1", "judgeScene", []))

    def test_v2_rejects_malformed_relation_demands_filters_and_bounds(self) -> None:
        """Catches invalid anchor, role, bounds, and endpoint-filter acceptance."""

        document = v2(
            {"unit": {}},
            {
                "fight": {
                    "relations": [
                        {"at": "bad//anchor", "kind": "Bad", "role": "either"},
                        {"at": "red", "kind": "holds", "atLeast": 2, "atMost": 1},
                        {"at": "red", "kind": "holds", "atMost": -1, "otherEndpoint": {}},
                        {
                            "at": "red",
                            "kind": "holds",
                            "atLeast": 1,
                            "otherEndpoint": {"prefix": "bad/", "conformsTo": "missing"},
                        },
                    ]
                }
            },
        )
        got = set(paths(mold.validate_scene_profiles(document)))
        expected = {
            "$.sceneProfiles.fight.relations.0.at",
            "$.sceneProfiles.fight.relations.0.kind",
            "$.sceneProfiles.fight.relations.0.role",
            "$.sceneProfiles.fight.relations.0",
            "$.sceneProfiles.fight.relations.1.atLeast",
            "$.sceneProfiles.fight.relations.2.atMost",
            "$.sceneProfiles.fight.relations.2.otherEndpoint",
            "$.sceneProfiles.fight.relations.3.otherEndpoint.prefix",
            "$.sceneProfiles.fight.relations.3.otherEndpoint.conformsTo",
        }
        self.assertTrue(expected.issubset(got), expected - got)

    def test_v2_rejects_empty_quantifiers_and_malformed_bans(self) -> None:
        """Catches vacuous list clauses and loose universal/ban entries."""

        document = v2(
            {},
            {
                "broken": {"relations": [], "forAllBodies": [], "forbidsRelations": []},
                "more": {
                    "forAllBodies": [{"excluding": [], "check": {}}, {}],
                    "forbidsRelations": [{"kind": "Bad", "at": "bad//anchor"}, {}],
                },
            },
        )
        got = set(paths(mold.validate_scene_profiles(document)))
        expected = {
            "$.sceneProfiles.broken.relations",
            "$.sceneProfiles.broken.forAllBodies",
            "$.sceneProfiles.broken.forbidsRelations",
            "$.sceneProfiles.more.forAllBodies.0.excluding",
            "$.sceneProfiles.more.forAllBodies.0.check",
            "$.sceneProfiles.more.forAllBodies.1.check",
            "$.sceneProfiles.more.forbidsRelations.0.kind",
            "$.sceneProfiles.more.forbidsRelations.0.at",
            "$.sceneProfiles.more.forbidsRelations.1.kind",
        }
        self.assertTrue(expected.issubset(got), expected - got)


if __name__ == "__main__":
    unittest.main()
