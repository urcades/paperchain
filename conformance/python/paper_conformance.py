"""Independent stdlib-only implementation of Paperdoll and Paperchain.

This module deliberately implements the written protocol specifications rather
than importing, invoking, or translating the TypeScript reference library.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"[a-z][a-z0-9-]*\Z", re.ASCII)
ASCII_CASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z", re.ASCII)
RULE_RE = re.compile(r"(paper-doll/v3|paperchain/v1)#[a-z0-9-]+\Z", re.ASCII)
SIDES = ("top", "right", "bottom", "left")
OPPOSITE = {"top": "bottom", "right": "left", "bottom": "top", "left": "right"}
VECTORS = {"top": (0, -1), "right": (1, 0), "bottom": (0, 1), "left": (-1, 0)}
_MISSING = object()


def _is_id(value: Any) -> bool:
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def _is_json_number(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _is_json_integer(value: Any) -> bool:
    return _is_json_number(value) and (
        type(value) is int or value.is_integer()
    )


def _is_finite_json(value: Any, active: set[int] | None = None) -> bool:
    """Recognize JSON values while rejecting Python-only values and cycles."""

    if value is None or isinstance(value, (str, bool)):
        return True
    if type(value) is int:  # bool is an int subclass, so exact type matters.
        return True
    if type(value) is float:
        return math.isfinite(value)
    if active is None:
        active = set()
    if type(value) not in (list, dict):
        return False
    identity = id(value)
    if identity in active:
        return False
    active.add(identity)
    try:
        if type(value) is list:
            return all(_is_finite_json(item, active) for item in value)
        return all(
            isinstance(key, str) and _is_finite_json(item, active)
            for key, item in value.items()
        )
    finally:
        active.remove(identity)


def _error(errors: list[str], path: str, *also: str) -> None:
    for candidate in (path, *also):
        if candidate not in errors:
            errors.append(candidate)


def _known_keys(value: dict[str, Any], allowed: set[str], path: str, errors: list[str]) -> bool:
    unknown = [key for key in value if key not in allowed]
    for key in unknown:
        _error(errors, f"{path}.{key}", path)
    return not unknown


def _validate_token(value: Any, path: str, errors: list[str]) -> bool:
    if type(value) is not dict:
        _error(errors, path)
        return False
    valid = _known_keys(value, {"kind", "type"}, path, errors)
    if "kind" not in value or not _is_id(value.get("kind")):
        _error(errors, f"{path}.kind")
        valid = False
    if "type" in value and not _is_id(value["type"]):
        _error(errors, f"{path}.type")
        valid = False
    return valid


def _validate_endpoint(value: Any, path: str, errors: list[str]) -> bool:
    if type(value) is not dict:
        _error(errors, path)
        return False
    valid = _known_keys(value, {"vessel", "side"}, path, errors)
    if "vessel" not in value or not _is_id(value.get("vessel")):
        _error(errors, f"{path}.vessel")
        valid = False
    if value.get("side") not in SIDES:
        _error(errors, f"{path}.side")
        valid = False
    return valid


def _validate_element(value: Any, path: str, errors: list[str]) -> bool:
    if type(value) is not dict:
        _error(errors, path)
        return False
    valid = _known_keys(value, {"kind", "type", "id", "data", "body"}, path, errors)
    if "kind" not in value or not _is_id(value.get("kind")):
        _error(errors, f"{path}.kind")
        valid = False
    for field in ("type", "id"):
        if field in value and not _is_id(value[field]):
            _error(errors, f"{path}.{field}")
            valid = False
    if "data" in value and not _is_finite_json(value["data"]):
        _error(errors, f"{path}.data")
        valid = False
    if "body" in value:
        before = len(errors)
        _validate_body(value["body"], f"{path}.body", errors)
        valid = valid and len(errors) == before
    return valid


def _validate_vessel(value: Any, path: str, errors: list[str]) -> bool:
    if type(value) is not dict:
        _error(errors, path)
        return False
    valid = _known_keys(value, {"accepts", "contains", "ports"}, path, errors)
    if "accepts" in value:
        accepts = value["accepts"]
        if type(accepts) is not list:
            _error(errors, f"{path}.accepts")
            valid = False
        else:
            for index, token in enumerate(accepts):
                valid = _validate_token(token, f"{path}.accepts.{index}", errors) and valid
    if "contains" in value:
        contains = value["contains"]
        if type(contains) is not list:
            _error(errors, f"{path}.contains")
            valid = False
        else:
            for index, element in enumerate(contains):
                valid = _validate_element(element, f"{path}.contains.{index}", errors) and valid
    if "ports" in value:
        ports = value["ports"]
        if type(ports) is not dict:
            _error(errors, f"{path}.ports")
            valid = False
        else:
            valid = _known_keys(ports, set(SIDES), f"{path}.ports", errors) and valid
            for side, endpoint in ports.items():
                if side in SIDES:
                    valid = _validate_endpoint(endpoint, f"{path}.ports.{side}", errors) and valid
    return valid


def _validate_endpoint_quiet(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"vessel", "side"}
        and _is_id(value["vessel"])
        and value["side"] in SIDES
    )


def _position_figure(body: dict[str, Any], path: str, errors: list[str] | None) -> dict[str, dict[str, int]]:
    vessels = body["vessels"]
    root = body["root"]
    if root not in vessels:
        return {}
    figure: dict[str, dict[str, int]] = {root: {"x": 0, "y": 0}}
    occupied: dict[tuple[int, int], str] = {(0, 0): root}
    pending: deque[str] = deque([root])
    while pending:
        vessel_id = pending.popleft()
        vessel = vessels[vessel_id]
        ports = vessel.get("ports", {}) if type(vessel) is dict else {}
        if type(ports) is not dict:
            continue
        for side in SIDES:
            endpoint = ports.get(side)
            if not _validate_endpoint_quiet(endpoint) or endpoint["vessel"] not in vessels:
                continue
            target = endpoint["vessel"]
            dx, dy = VECTORS[side]
            candidate = {
                "x": figure[vessel_id]["x"] + dx,
                "y": figure[vessel_id]["y"] + dy,
            }
            edge_path = f"{path}.vessels.{vessel_id}.ports.{side}"
            if target in figure:
                if figure[target] != candidate and errors is not None:
                    _error(errors, edge_path)
                continue
            coordinate = (candidate["x"], candidate["y"])
            occupant = occupied.get(coordinate)
            if occupant is not None and occupant != target and errors is not None:
                _error(errors, edge_path)
            figure[target] = candidate
            occupied.setdefault(coordinate, target)
            pending.append(target)
    return figure


def _matches(token: dict[str, Any], element: dict[str, Any]) -> bool:
    return token["kind"] == element["kind"] and (
        "type" not in token or token["type"] == element.get("type", _MISSING)
    )


def _validate_body(value: Any, path: str, errors: list[str]) -> bool:
    if type(value) is not dict:
        _error(errors, path)
        return False
    valid = _known_keys(value, {"root", "vessels"}, path, errors)
    if "root" not in value or not _is_id(value.get("root")):
        _error(errors, f"{path}.root")
        valid = False
    vessels = value.get("vessels")
    if type(vessels) is not dict:
        _error(errors, f"{path}.vessels")
        return False

    vessel_shapes: dict[str, bool] = {}
    for vessel_id, vessel in vessels.items():
        if not _is_id(vessel_id):
            _error(errors, f"{path}.vessels.{vessel_id}")
            valid = False
        vessel_shapes[vessel_id] = _validate_vessel(vessel, f"{path}.vessels.{vessel_id}", errors)
        valid = vessel_shapes[vessel_id] and valid

    root = value.get("root")
    if _is_id(root) and root not in vessels:
        _error(errors, f"{path}.root")
        valid = False

    for vessel_id, vessel in vessels.items():
        if not vessel_shapes.get(vessel_id) or type(vessel) is not dict:
            continue
        ports = vessel.get("ports", {})
        if type(ports) is dict:
            for side in SIDES:
                endpoint = ports.get(side)
                if not _validate_endpoint_quiet(endpoint):
                    continue
                port_path = f"{path}.vessels.{vessel_id}.ports.{side}"
                target_id = endpoint["vessel"]
                if target_id not in vessels:
                    _error(errors, port_path, f"{port_path}.vessel")
                    valid = False
                else:
                    target = vessels[target_id]
                    target_ports = target.get("ports", {}) if type(target) is dict else {}
                    reciprocal = (
                        type(target_ports) is dict
                        and target_ports.get(endpoint["side"]) == {"vessel": vessel_id, "side": side}
                    )
                    if not reciprocal:
                        _error(errors, port_path)
                        valid = False
                if endpoint["side"] != OPPOSITE[side]:
                    _error(errors, f"{port_path}.side", port_path)
                    valid = False

        contains = vessel.get("contains", [])
        if type(contains) is list:
            accepts = vessel.get("accepts", _MISSING)
            if type(accepts) is list and all(type(token) is dict and "kind" in token for token in accepts):
                for index, element in enumerate(contains):
                    if type(element) is dict and _is_id(element.get("kind")):
                        if not any(_matches(token, element) for token in accepts):
                            _error(errors, f"{path}.vessels.{vessel_id}.contains.{index}")
                            valid = False
            seen_ids: set[str] = set()
            for index, element in enumerate(contains):
                if type(element) is dict and "id" in element and _is_id(element["id"]):
                    if element["id"] in seen_ids:
                        _error(errors, f"{path}.vessels.{vessel_id}.contains.{index}.id")
                        valid = False
                    seen_ids.add(element["id"])

    if _is_id(root) and root in vessels and all(vessel_shapes.values()):
        before = len(errors)
        figure = _position_figure(value, path, errors)
        if len(errors) != before:
            valid = False
        for vessel_id, vessel in vessels.items():
            if (
                vessel_id not in figure
                and type(vessel) is dict
                and type(vessel.get("ports", {})) is dict
                and len(vessel.get("ports", {})) > 0
            ):
                _error(
                    errors,
                    f"{path}.vessels.{vessel_id}.ports",
                    f"{path}.vessels.{vessel_id}",
                )
                valid = False
    return valid


def validate_document(document: Any) -> list[str]:
    errors: list[str] = []
    if not _is_finite_json(document):
        _error(errors, "$")
        if type(document) is not dict:
            return errors
    if type(document) is not dict:
        _error(errors, "$")
        return errors
    _known_keys(document, {"protocol", "body"}, "$", errors)
    if document.get("protocol") != "paper-doll/v3":
        _error(errors, "$.protocol")
    if "body" not in document:
        _error(errors, "$.body")
    else:
        _validate_body(document["body"], "$.body", errors)
    return errors


def _parse_address(address: Any, minimum_segments: int = 1) -> list[str]:
    if not isinstance(address, str):
        raise ValueError("address must be a string")
    segments = address.split("/")
    if len(segments) < minimum_segments or any(not _is_id(segment) for segment in segments):
        raise ValueError("malformed address")
    return segments


def _resolve_address(body: dict[str, Any], address: Any) -> dict[str, Any] | None:
    segments = _parse_address(address)
    current_body = body
    cursor = 0
    while True:
        vessel_id = segments[cursor]
        vessels = current_body["vessels"]
        if vessel_id not in vessels:
            return None
        vessel = vessels[vessel_id]
        if cursor == len(segments) - 1:
            return {"kind": "vessel", "vesselId": vessel_id}
        element_id = segments[cursor + 1]
        found: tuple[int, dict[str, Any]] | None = None
        for index, element in enumerate(vessel.get("contains", [])):
            if element.get("id") == element_id:
                found = (index, element)
                break
        if found is None:
            return None
        index, element = found
        if cursor + 1 == len(segments) - 1:
            return {"kind": "element", "vesselId": vessel_id, "index": index, "element": element}
        if "body" not in element:
            return None
        current_body = element["body"]
        cursor += 2


def _derive_connections(body: dict[str, Any]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for vessel_id, vessel in body["vessels"].items():
        for side, endpoint in vessel.get("ports", {}).items():
            first = {"vessel": vessel_id, "side": side}
            second = {"vessel": endpoint["vessel"], "side": endpoint["side"]}
            first_key = f"{first['vessel']}:{first['side']}"
            second_key = f"{second['vessel']}:{second['side']}"
            if first_key <= second_key:
                key, connection = (first_key, second_key), {"from": first, "to": second}
            else:
                key, connection = (second_key, first_key), {"from": second, "to": first}
            unique[key] = connection
    return [unique[key] for key in sorted(unique)]


def _derive_layout(body: dict[str, Any]) -> dict[str, Any]:
    figure = _position_figure(body, "$.body", None)
    free = sorted(vessel_id for vessel_id in body["vessels"] if vessel_id not in figure)
    return {"figure": figure, "free": free, "connections": _derive_connections(body)}


def _valid_kind_declaration(value: Any, path: str, errors: list[str]) -> bool:
    if type(value) is not dict:
        _error(errors, path)
        return False
    valid = _known_keys(value, {"symmetric", "irreflexive", "fromMax", "toMax"}, path, errors)
    for field in ("symmetric", "irreflexive"):
        if field in value and type(value[field]) is not bool:
            _error(errors, f"{path}.{field}")
            valid = False
    for field in ("fromMax", "toMax"):
        if field in value and (not _is_json_integer(value[field]) or value[field] < 0):
            _error(errors, f"{path}.{field}")
            valid = False
    if value.get("symmetric") is True and "toMax" in value:
        _error(errors, f"{path}.toMax")
        valid = False
    return valid


def _valid_relation(value: Any, path: str, errors: list[str]) -> bool:
    if type(value) is not dict:
        _error(errors, path)
        return False
    valid = _known_keys(value, {"kind", "from", "to"}, path, errors)
    if "kind" not in value or not _is_id(value.get("kind")):
        _error(errors, f"{path}.kind")
        valid = False
    for field in ("from", "to"):
        try:
            _parse_address(value.get(field), minimum_segments=2)
        except ValueError:
            _error(errors, f"{path}.{field}")
            valid = False
    return valid


def validate_scene(scene: Any) -> list[str]:
    errors: list[str] = []
    if not _is_finite_json(scene):
        _error(errors, "$")
        if type(scene) is not dict:
            return errors
    if type(scene) is not dict:
        _error(errors, "$")
        return errors
    _known_keys(scene, {"protocol", "bodies", "kinds", "relations"}, "$", errors)
    if scene.get("protocol") != "paperchain/v1":
        _error(errors, "$.protocol")

    bodies = scene.get("bodies")
    valid_bodies: set[str] = set()
    if type(bodies) is not dict:
        _error(errors, "$.bodies")
        bodies = {}
    else:
        for name, body in bodies.items():
            if not _is_id(name):
                _error(errors, f"$.bodies.{name}")
                continue
            before = len(errors)
            _validate_body(body, f"$.bodies.{name}", errors)
            if len(errors) == before:
                valid_bodies.add(name)

    kinds = scene.get("kinds")
    valid_kinds: dict[str, dict[str, Any]] = {}
    if type(kinds) is not dict:
        _error(errors, "$.kinds")
        kinds = {}
    else:
        for kind, declaration in kinds.items():
            if not _is_id(kind):
                _error(errors, f"$.kinds.{kind}")
                continue
            if _valid_kind_declaration(declaration, f"$.kinds.{kind}", errors):
                valid_kinds[kind] = declaration

    relations = scene.get("relations")
    valid_relations: list[tuple[int, dict[str, Any]]] = []
    if type(relations) is not list:
        _error(errors, "$.relations")
        relations = []
    else:
        for index, relation in enumerate(relations):
            if _valid_relation(relation, f"$.relations.{index}", errors):
                valid_relations.append((index, relation))

    seen: dict[tuple[str, str, str], int] = {}
    from_counts: dict[tuple[str, str], int] = {}
    to_counts: dict[tuple[str, str], int] = {}
    symmetric_counts: dict[tuple[str, str], int] = {}
    for index, relation in valid_relations:
        relation_path = f"$.relations.{index}"
        kind = relation["kind"]
        declaration = valid_kinds.get(kind)
        if kind not in kinds:
            _error(errors, f"{relation_path}.kind")

        for endpoint_field in ("from", "to"):
            address = relation[endpoint_field]
            body_name, local_address = address.split("/", 1)
            if body_name in valid_bodies:
                if _resolve_address(bodies[body_name], local_address) is None:
                    _error(errors, f"{relation_path}.{endpoint_field}")
            elif body_name not in bodies:
                _error(errors, f"{relation_path}.{endpoint_field}")

        symmetric = declaration is not None and declaration.get("symmetric") is True
        if symmetric:
            endpoint_a, endpoint_b = sorted((relation["from"], relation["to"]))
        else:
            endpoint_a, endpoint_b = relation["from"], relation["to"]
        identity = (kind, endpoint_a, endpoint_b)
        if identity in seen:
            _error(errors, relation_path)
        else:
            seen[identity] = index

        if declaration is None:
            continue
        if declaration.get("irreflexive") is True and relation["from"] == relation["to"]:
            _error(errors, f"{relation_path}.to", relation_path)

        if symmetric and "fromMax" in declaration:
            budget = declaration["fromMax"]
            for endpoint_field in ("from", "to"):
                endpoint = relation[endpoint_field]
                key = (kind, endpoint)
                symmetric_counts[key] = symmetric_counts.get(key, 0) + 1
                if symmetric_counts[key] > budget:
                    _error(errors, f"{relation_path}.{endpoint_field}", relation_path)
        elif not symmetric:
            if "fromMax" in declaration:
                key = (kind, relation["from"])
                from_counts[key] = from_counts.get(key, 0) + 1
                if from_counts[key] > declaration["fromMax"]:
                    _error(errors, f"{relation_path}.from", relation_path)
            if "toMax" in declaration:
                key = (kind, relation["to"])
                to_counts[key] = to_counts.get(key, 0) + 1
                if to_counts[key] > declaration["toMax"]:
                    _error(errors, f"{relation_path}.to", relation_path)
    return errors


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run one case and return its actual language-neutral projection."""

    if type(case) is not dict:
        raise ValueError("case must be an object")
    subject, operation, input_value = case.get("subject"), case.get("operation"), case.get("input")
    if type(input_value) is not dict:
        raise ValueError("case input must be an object")
    if subject == "paper-doll/v3" and operation == "validateDocument":
        errors = validate_document(input_value.get("document", _MISSING))
        return {"outcome": "invalid", "errorPaths": errors} if errors else {"outcome": "valid"}
    if subject == "paper-doll/v3" and operation == "resolveAddress":
        try:
            resolved = _resolve_address(input_value["body"], input_value.get("address"))
        except (KeyError, TypeError, ValueError):
            return {"outcome": "error"}
        return {"outcome": "unresolved"} if resolved is None else {"outcome": "resolved", "value": resolved}
    if subject == "paper-doll/v3" and operation == "deriveLayout":
        try:
            layout = _derive_layout(input_value["body"])
        except (KeyError, TypeError, ValueError):
            return {"outcome": "error"}
        return {"outcome": "layout", "value": layout}
    if subject == "paperchain/v1" and operation == "validateScene":
        errors = validate_scene(input_value.get("scene", _MISSING))
        return {"outcome": "invalid", "errorPaths": errors} if errors else {"outcome": "valid"}
    if subject == "paperchain/v1" and operation == "resolveSceneAddress":
        try:
            segments = _parse_address(input_value.get("address"), minimum_segments=2)
            body = input_value["scene"]["bodies"].get(segments[0])
            if body is None:
                return {"outcome": "unresolved"}
            resolved = _resolve_address(body, "/".join(segments[1:]))
        except (KeyError, TypeError, ValueError):
            return {"outcome": "error"}
        return {"outcome": "unresolved"} if resolved is None else {"outcome": "resolved", "value": resolved}
    raise ValueError(f"unsupported subject/operation: {subject!r}/{operation!r}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _validate_expected(expected: Any, operation: str) -> None:
    if type(expected) is not dict or type(expected.get("outcome")) is not str:
        raise ValueError("case expected must be an outcome object")
    outcome = expected["outcome"]
    allowed = {
        "validateDocument": {"valid", "invalid"},
        "validateScene": {"valid", "invalid"},
        "resolveAddress": {"resolved", "unresolved", "error"},
        "resolveSceneAddress": {"resolved", "unresolved", "error"},
        "deriveLayout": {"layout"},
    }[operation]
    if outcome not in allowed:
        raise ValueError(f"unexpected outcome {outcome!r} for {operation}")
    required_keys = {"outcome"}
    if outcome == "invalid":
        required_keys.add("includesErrorPaths")
        paths = expected.get("includesErrorPaths")
        if (
            type(paths) is not list
            or not paths
            or not all(isinstance(path, str) and path for path in paths)
            or len(set(paths)) != len(paths)
        ):
            raise ValueError("invalid expectation requires unique nonempty error paths")
    elif outcome in {"resolved", "layout"}:
        required_keys.add("value")
    if set(expected) != required_keys:
        raise ValueError("unexpected or missing expected-result keys")
    if outcome == "resolved":
        _validate_resolved_projection(expected["value"])
    elif outcome == "layout":
        _validate_layout_projection(expected["value"])


def _validate_resolved_projection(value: Any) -> None:
    if type(value) is not dict:
        raise ValueError("resolved value must be an object")
    if value.get("kind") == "vessel":
        if set(value) != {"kind", "vesselId"} or not isinstance(value.get("vesselId"), str):
            raise ValueError("malformed resolved vessel projection")
        return
    if value.get("kind") == "element":
        if set(value) != {"kind", "vesselId", "index", "element"}:
            raise ValueError("malformed resolved element projection")
        if (
            not isinstance(value["vesselId"], str)
            or not _is_json_integer(value["index"])
            or value["index"] < 0
        ):
            raise ValueError("malformed resolved element location")
        if type(value["element"]) is not dict or not _is_finite_json(value["element"]):
            raise ValueError("malformed resolved element value")
        return
    raise ValueError("unknown resolved projection kind")


def _validate_layout_projection(value: Any) -> None:
    if type(value) is not dict or set(value) != {"figure", "free", "connections"}:
        raise ValueError("malformed layout projection")
    figure = value["figure"]
    if type(figure) is not dict:
        raise ValueError("layout figure must be an object")
    for vessel_id, coordinate in figure.items():
        if (
            not isinstance(vessel_id, str)
            or type(coordinate) is not dict
            or set(coordinate) != {"x", "y"}
            or not _is_json_number(coordinate["x"])
            or not _is_json_number(coordinate["y"])
        ):
            raise ValueError("malformed layout coordinate")
    free = value["free"]
    if type(free) is not list or not all(isinstance(item, str) for item in free):
        raise ValueError("layout free must be an id array")
    if free != sorted(set(free)):
        raise ValueError("layout free must be unique and normalized")
    connections = value["connections"]
    if type(connections) is not list:
        raise ValueError("layout connections must be an array")
    previous: tuple[str, str] | None = None
    for connection in connections:
        if type(connection) is not dict or set(connection) != {"from", "to"}:
            raise ValueError("malformed layout connection")
        if not _validate_projection_endpoint(connection["from"]) or not _validate_projection_endpoint(connection["to"]):
            raise ValueError("malformed layout connection endpoint")
        first = f"{connection['from']['vessel']}:{connection['from']['side']}"
        second = f"{connection['to']['vessel']}:{connection['to']['side']}"
        key = (first, second)
        if first > second or (previous is not None and previous >= key):
            raise ValueError("layout connections must be unique and normalized")
        previous = key


def _validate_projection_endpoint(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"vessel", "side"}
        and isinstance(value["vessel"], str)
        and value["side"] in SIDES
    )


def _validate_fixture_case(case: Any, seen_ids: set[str]) -> None:
    required = {"id", "rule", "subject", "operation", "input", "expected"}
    if type(case) is not dict or set(case) != required:
        raise ValueError("each case must have exactly the six contract fields")
    case_id = case["id"]
    if not isinstance(case_id, str) or ASCII_CASE_ID_RE.fullmatch(case_id) is None:
        raise ValueError("case id must match [A-Za-z0-9][A-Za-z0-9._-]*")
    if case_id in seen_ids:
        raise ValueError(f"duplicate case id: {case_id}")
    seen_ids.add(case_id)
    subject, operation = case["subject"], case["operation"]
    domains = {
        "paper-doll/v3": {"validateDocument", "resolveAddress", "deriveLayout"},
        "paperchain/v1": {"validateScene", "resolveSceneAddress"},
    }
    if subject not in domains or operation not in domains[subject]:
        raise ValueError("unknown or incompatible subject/operation")
    rule = case["rule"]
    if (
        not isinstance(rule, str)
        or RULE_RE.fullmatch(rule) is None
        or not rule.startswith(f"{subject}#")
    ):
        raise ValueError("case rule must be a subject-matching protocol anchor")
    if type(case["input"]) is not dict:
        raise ValueError("case input must be an object")
    expected_input_keys = {
        "validateDocument": {"document"},
        "resolveAddress": {"body", "address"},
        "deriveLayout": {"body"},
        "validateScene": {"scene"},
        "resolveSceneAddress": {"scene", "address"},
    }[operation]
    if set(case["input"]) != expected_input_keys:
        raise ValueError("case input has unexpected or missing keys")
    if operation in {"resolveAddress", "deriveLayout"} and type(case["input"]["body"]) is not dict:
        raise ValueError("body input must be an object")
    if operation in {"resolveSceneAddress"} and type(case["input"]["scene"]) is not dict:
        raise ValueError("scene input must be an object")
    if operation in {"resolveAddress", "resolveSceneAddress"} and not isinstance(case["input"]["address"], str):
        raise ValueError("address input must be a string")
    _validate_expected(case["expected"], operation)


def load_corpus(path: str | Path) -> dict[str, Any]:
    """Load a corpus while rejecting duplicate keys and malformed envelopes."""

    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            corpus = json.load(handle, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load corpus {path}: {error}") from error
    if not _is_finite_json(corpus):
        raise ValueError("corpus must contain only finite JSON values")
    if type(corpus) is not dict or set(corpus) != {"corpus", "cases"}:
        raise ValueError("corpus envelope must contain exactly corpus and cases")
    if corpus["corpus"] != "paper-family-conformance/v1":
        raise ValueError("unknown corpus protocol")
    if type(corpus["cases"]) is not list or not corpus["cases"]:
        raise ValueError("corpus cases must be a nonempty array")
    seen_ids: set[str] = set()
    for case in corpus["cases"]:
        _validate_fixture_case(case, seen_ids)
    return corpus


def _matches_expected(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    if expected["outcome"] == "invalid":
        if actual.get("outcome") != "invalid" or type(actual.get("errorPaths")) is not list:
            return False
        return set(expected["includesErrorPaths"]).issubset(actual["errorPaths"])
    return _json_equal(actual, expected)


def _json_equal(left: Any, right: Any) -> bool:
    """Compare JSON structurally, keeping booleans distinct from numbers."""

    if left is None or right is None:
        return left is None and right is None
    if type(left) is bool or type(right) is bool:
        return type(left) is bool and type(right) is bool and left == right
    if _is_json_number(left) or _is_json_number(right):
        return _is_json_number(left) and _is_json_number(right) and left == right
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if type(left) is list or type(right) is list:
        return (
            type(left) is list
            and type(right) is list
            and len(left) == len(right)
            and all(_json_equal(a, b) for a, b in zip(left, right))
        )
    if type(left) is dict or type(right) is dict:
        return (
            type(left) is dict
            and type(right) is dict
            and set(left) == set(right)
            and all(_json_equal(left[key], right[key]) for key in left)
        )
    return False


def run_corpus_file(path: str | Path) -> list[str]:
    """Run every case, returning one concise mismatch per failed case."""

    return _run_loaded_corpus(load_corpus(path))


def _run_loaded_corpus(corpus: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for case in corpus["cases"]:
        actual = run_case(case)
        if not _matches_expected(actual, case["expected"]):
            mismatches.append(f"{case['id']}: expected {case['expected']!r}, got {actual!r}")
    return mismatches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", nargs="+", help="shared JSON corpus file(s)")
    arguments = parser.parse_args(argv)
    failed = False
    selected: list[tuple[str, dict[str, Any]]] = []
    selected_ids: dict[str, str] = {}
    for path in arguments.corpus:
        try:
            corpus = load_corpus(path)
            duplicate = next(
                (
                    (case["id"], selected_ids[case["id"]])
                    for case in corpus["cases"]
                    if case["id"] in selected_ids
                ),
                None,
            )
            if duplicate is not None:
                case_id, previous = duplicate
                raise ValueError(
                    f"duplicate case id {case_id!r} across {previous} and {path}"
                )
            for case in corpus["cases"]:
                selected_ids[case["id"]] = path
            selected.append((path, corpus))
        except ValueError as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
    for path, corpus in selected:
        mismatches = _run_loaded_corpus(corpus)
        for mismatch in mismatches:
            print(f"{path}: {mismatch}", file=sys.stderr)
        if mismatches:
            failed = True
        else:
            print(f"{path}: all cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
