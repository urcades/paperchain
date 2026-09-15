"""Strict corpus-v2 transport for the independent optional Python references.

Run this file directly from an installed npm package, or import it as a module.
The dispatcher loads only the requested protocol; no JavaScript runtime is used.
"""
from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path
from typing import Any, Callable

try:
    from . import paper_conformance as core
    from .portable_json import loads_portable_json
except ImportError:  # Direct execution from a package's conformance directory.
    import paper_conformance as core
    from portable_json import loads_portable_json

OPERATIONS = {
    "paper-doll/v3": {"connect", "disconnect", "insertVessel", "deleteVessel", "insertElement", "removeElement", "moveElement"},
    "paperchain/v1": {"insertBody", "deleteBody", "declareKind", "deleteKind", "addRelation", "removeRelation", "relationsAt"},
    "paperfold/v1": {"validatePatch", "applyPatch", "invertPatch", "composePatches", "diffLaws"},
    "paperfold/v2": {"validateScenePatch", "applyScenePatch", "invertScenePatch", "composeScenePatches", "diffSceneLaws"},
    "papermold/v1": {"validateProfiles", "judge", "conforms"},
    "papermold/v2": {"validateSceneProfiles", "judgeBody", "conformsBody", "judgeScene", "conformsScene"},
}
# Arity is part of fixture validity, not a simulated API precondition failure.
# Optional arguments use ranges; JSON cannot encode an omitted middle argument.
ARITY = {
    "connect": (3, 3), "disconnect": (2, 2), "insertVessel": (1, 3),
    "deleteVessel": (2, 3), "insertElement": (3, 4), "removeElement": (3, 3), "moveElement": (4, 4),
    "insertBody": (3, 3), "deleteBody": (2, 2), "declareKind": (2, 3),
    "deleteKind": (2, 2), "addRelation": (2, 2), "removeRelation": (2, 2), "relationsAt": (2, 2),
    "validatePatch": (1, 1), "applyPatch": (2, 2), "invertPatch": (1, 1), "composePatches": (2, 2), "diffLaws": (2, 2),
    "validateScenePatch": (1, 1), "applyScenePatch": (2, 2), "invertScenePatch": (1, 1), "composeScenePatches": (2, 2), "diffSceneLaws": (2, 2),
    "validateProfiles": (1, 1), "judge": (3, 3), "conforms": (3, 3),
    "validateSceneProfiles": (1, 1), "judgeBody": (3, 3), "conformsBody": (3, 3), "judgeScene": (3, 3), "conformsScene": (3, 3),
}
RULE = re.compile(r"(paper-doll/v3|paperchain/v1|paperfold/v[12]|papermold/v[12])#[a-z0-9-]+\Z", re.ASCII)
MODULES = {"paper-doll/v3": "paper_edits", "paperchain/v1": "paper_edits",
           "paperfold/v1": "paperfold", "paperfold/v2": "paperfold",
           "papermold/v1": "papermold", "papermold/v2": "papermold"}


def _outcomes(operation: str) -> set[str]:
    if operation.startswith("validate"):
        return {"valid", "invalid"}
    if operation.startswith("judge"):
        return {"conforms", "nonconforming", "error"}
    if operation in {"applyPatch", "applyScenePatch", "diffLaws", "diffSceneLaws"}:
        return {"ok", "invalid", "error"}
    return {"ok", "error"}


def _check_case(case: Any, seen: set[str]) -> None:
    if type(case) is not dict or set(case) != {"id", "rule", "subject", "operation", "input", "expected"}:
        raise ValueError("case must have exactly id, rule, subject, operation, input, expected")
    case_id = case["id"]
    if not isinstance(case_id, str) or core.ASCII_CASE_ID_RE.fullmatch(case_id) is None:
        raise ValueError("case id has invalid syntax")
    if case_id in seen:
        raise ValueError(f"duplicate case id: {case_id}")
    seen.add(case_id)
    subject, operation = case["subject"], case["operation"]
    if not isinstance(subject, str) or subject not in OPERATIONS or not isinstance(operation, str) or operation not in OPERATIONS[subject]:
        raise ValueError(f"unknown or incompatible subject/operation in {case_id}")
    rule = case["rule"]
    if not isinstance(rule, str) or RULE.fullmatch(rule) is None or rule.split("#", 1)[0] != subject:
        raise ValueError(f"invalid or incompatible rule in {case_id}")
    inputs = case["input"]
    if type(inputs) is not dict or set(inputs) != {"args"} or type(inputs["args"]) is not list:
        raise ValueError("input must contain exactly an args array")
    minimum, maximum = ARITY[operation]
    if not minimum <= len(inputs["args"]) <= maximum:
        raise ValueError(f"invalid argument count for {operation}: expected {minimum}..{maximum}")
    expected = case["expected"]
    if type(expected) is not dict or type(expected.get("outcome")) is not str or expected["outcome"] not in _outcomes(operation):
        raise ValueError(f"invalid expected outcome for {operation}")
    outcome = expected["outcome"]
    if outcome == "ok":
        keys = {"outcome", "value"}
    elif outcome in {"invalid", "nonconforming"}:
        keys = {"outcome", "includesErrorPaths"}
        paths = expected.get("includesErrorPaths")
        if type(paths) is not list or not paths or not all(isinstance(p, str) and p for p in paths) or len(set(paths)) != len(paths):
            raise ValueError("expected error paths must be nonempty, unique strings")
    else:
        keys = {"outcome"}
    if set(expected) != keys:
        raise ValueError("unexpected or missing expected-result fields")
    if outcome == "ok" and operation in {"conforms", "conformsBody", "conformsScene"} and type(expected["value"]) is not bool:
        raise ValueError("conforms operations require a boolean expected value")


def load_corpus(path: str | Path) -> dict[str, Any]:
    document = loads_portable_json(Path(path).read_text(encoding="utf-8"))
    if not core._is_finite_json(document):
        raise ValueError("corpus must contain finite JSON values")
    if type(document) is not dict or set(document) != {"corpus", "cases"} or document["corpus"] != "paper-family-conformance/v2":
        raise ValueError("invalid corpus-v2 envelope")
    if type(document["cases"]) is not list or not document["cases"]:
        raise ValueError("corpus cases must be a nonempty array")
    seen: set[str] = set()
    for case in document["cases"]:
        _check_case(case, seen)
    return document


def matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    if expected["outcome"] in {"invalid", "nonconforming"}:
        return (actual.get("outcome") == expected["outcome"] and type(actual.get("errorPaths")) is list
                and set(expected["includesErrorPaths"]).issubset(actual["errorPaths"]))
    return core._json_equal(actual, expected)


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    module_name = MODULES[case["subject"]]
    module = importlib.import_module(f".{module_name}", __package__) if __package__ else importlib.import_module(module_name)
    return module.run_case(case)


def run_files(paths: list[str | Path], dispatch: Callable | None = None) -> list[str]:
    # Validate identity across all selected files before executing any case.
    if not paths:
        raise ValueError("at least one corpus file is required")
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        for case in load_corpus(path)["cases"]:
            if case["id"] in seen:
                raise ValueError(f"duplicate case id across files: {case['id']}")
            seen.add(case["id"])
            cases.append(case)
    execute = dispatch or run_case
    failures = []
    for case in cases:
        actual = execute(case)
        if not matches(actual, case["expected"]):
            failures.append(f"{case['id']}: expected {case['expected']!r}; got {actual!r}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", nargs="+")
    args = parser.parse_args(argv)
    try:
        failures = run_files(args.corpus)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print(f"All corpus cases passed across {len(args.corpus)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
