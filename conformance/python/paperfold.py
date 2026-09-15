"""Independent, standard-library Paperfold v1/v2 reference implementation.

The code follows the protocol documents directly.  It intentionally does not
load, invoke, or translate the TypeScript implementation.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

try:  # Package import.
    from . import paper_conformance as core
except ImportError:  # Direct file-path/bootstrap import.
    import paper_conformance as core  # type: ignore[no-redef]


_SIDES = ("top", "right", "bottom", "left")
_OPPOSITE = {"top": "bottom", "right": "left", "bottom": "top", "left": "right"}
_KERNEL_OPS = {
    "connect", "disconnect", "insertVessel", "deleteVessel",
    "insertElement", "removeElement", "moveElement",
}
_SCENE_OPS = {
    "declareKind", "deleteKind", "insertBody", "deleteBody",
    "addRelation", "removeRelation",
}


def _editing_module() -> Any:
    """Load the sibling edit reference without imposing import order."""

    try:
        from . import paper_edits
    except ImportError:
        import paper_edits  # type: ignore[no-redef]
    return paper_edits


def _record_error(errors: list[dict[str, str]], path: str, message: str) -> None:
    error = {"path": path, "message": message}
    if error not in errors:
        errors.append(error)


def _paths_to_errors(paths: list[str], message: str = "invalid value") -> list[dict[str, str]]:
    return [{"path": path, "message": message} for path in dict.fromkeys(paths)]


def _is_index(value: Any) -> bool:
    return core._is_json_integer(value) and value >= 0


def _known_and_required(
    value: dict[str, Any], path: str, errors: list[dict[str, str]],
    allowed: set[str], required: set[str],
) -> None:
    for key in value:
        if key not in allowed:
            _record_error(errors, f"{path}.{key}", "unknown member")
    for key in required:
        if key not in value:
            _record_error(errors, f"{path}.{key}", "required member is missing")


def _fragment_errors(
    validator: Callable[[Any, str, list[str]], bool], value: Any, path: str,
) -> list[dict[str, str]]:
    paths: list[str] = []
    validator(value, path, paths)
    return _paths_to_errors(paths)


def _validate_id(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not core._is_id(value):
        _record_error(errors, path, "expected lowercase id")


def _validate_index(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not _is_index(value):
        _record_error(errors, path, "expected nonnegative integer")


def _validate_endpoint(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    errors.extend(_fragment_errors(core._validate_endpoint, value, path))


def _validate_connection(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if type(value) is not dict:
        _record_error(errors, path, "expected connection")
        return
    _known_and_required(value, path, errors, {"from", "to"}, {"from", "to"})
    if "from" in value:
        _validate_endpoint(value["from"], f"{path}.from", errors)
    if "to" in value:
        _validate_endpoint(value["to"], f"{path}.to", errors)


def _validate_nullable_connection(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if value is not None:
        _validate_connection(value, path, errors)


def _validate_connection_list(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if type(value) is not list:
        _record_error(errors, path, "expected connection array")
        return
    for index, connection in enumerate(value):
        _validate_connection(connection, f"{path}.{index}", errors)


def _validate_vessel(value: Any, path: str, errors: list[dict[str, str]], portless: bool) -> None:
    errors.extend(_fragment_errors(core._validate_vessel, value, path))
    if portless and type(value) is dict and "ports" in value:
        _record_error(errors, f"{path}.ports", "inserted vessel must be portless")


def _validate_element(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    errors.extend(_fragment_errors(core._validate_element, value, path))


def _validate_body(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    paths: list[str] = []
    core._validate_body(value, path, paths)
    errors.extend(_paths_to_errors(paths))


def _validate_declaration(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    paths: list[str] = []
    core._valid_kind_declaration(value, path, paths)
    errors.extend(_paths_to_errors(paths))


def _validate_relation(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    paths: list[str] = []
    core._valid_relation(value, path, paths)
    errors.extend(_paths_to_errors(paths))


def _validate_body_path(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, str):
        _record_error(errors, path, "expected body path")
        return
    try:
        segments = core._parse_address(value, minimum_segments=2)
    except ValueError:
        _record_error(errors, path, "malformed body path")
        return
    if len(segments) % 2 != 0:
        _record_error(errors, path, "body path must contain vessel/element pairs")


def _validate_kernel_entry(
    entry: Any, path: str, errors: list[dict[str, str]], *, targeted: bool,
) -> None:
    if type(entry) is not dict:
        _record_error(errors, path, "expected patch entry")
        return
    op = entry.get("op")
    if type(op) is not str or op not in _KERNEL_OPS:
        _record_error(errors, f"{path}.op", "unknown kernel operation")
        return

    fields: dict[str, tuple[set[str], set[str]]] = {
        "connect": ({"op", "from", "to", "displaced"}, {"op", "from", "to", "displaced"}),
        "disconnect": ({"op", "endpoint", "removed"}, {"op", "endpoint", "removed"}),
        "insertVessel": ({"op", "vesselId", "vessel", "at", "bridged"}, {"op", "vesselId", "vessel", "bridged"}),
        "deleteVessel": ({"op", "vesselId", "collapseOppositeNeighbors", "vessel", "collapsed"}, {"op", "vesselId", "vessel", "collapsed"}),
        "insertElement": ({"op", "vesselId", "element", "index"}, {"op", "vesselId", "element", "index"}),
        "removeElement": ({"op", "vesselId", "index", "element"}, {"op", "vesselId", "index", "element"}),
        "moveElement": ({"op", "from", "index", "to", "element", "toIndex"}, {"op", "from", "index", "to", "element", "toIndex"}),
    }
    allowed, required = (set(part) for part in fields[op])
    if targeted:
        allowed.update({"body", "path"})
        required.add("body")
    _known_and_required(entry, path, errors, allowed, required)

    if targeted and "body" in entry:
        _validate_id(entry["body"], f"{path}.body", errors)
    if targeted and "path" in entry:
        _validate_body_path(entry["path"], f"{path}.path", errors)
    if op == "connect":
        if "from" in entry: _validate_endpoint(entry["from"], f"{path}.from", errors)
        if "to" in entry: _validate_endpoint(entry["to"], f"{path}.to", errors)
        if "displaced" in entry: _validate_connection_list(entry["displaced"], f"{path}.displaced", errors)
    elif op == "disconnect":
        if "endpoint" in entry: _validate_endpoint(entry["endpoint"], f"{path}.endpoint", errors)
        if "removed" in entry: _validate_connection(entry["removed"], f"{path}.removed", errors)
    elif op == "insertVessel":
        if "vesselId" in entry: _validate_id(entry["vesselId"], f"{path}.vesselId", errors)
        if "vessel" in entry: _validate_vessel(entry["vessel"], f"{path}.vessel", errors, True)
        if "at" in entry: _validate_endpoint(entry["at"], f"{path}.at", errors)
        if "bridged" in entry: _validate_nullable_connection(entry["bridged"], f"{path}.bridged", errors)
    elif op == "deleteVessel":
        if "vesselId" in entry: _validate_id(entry["vesselId"], f"{path}.vesselId", errors)
        if "collapseOppositeNeighbors" in entry and type(entry["collapseOppositeNeighbors"]) is not bool:
            _record_error(errors, f"{path}.collapseOppositeNeighbors", "expected boolean")
        if "vessel" in entry: _validate_vessel(entry["vessel"], f"{path}.vessel", errors, False)
        if "collapsed" in entry: _validate_nullable_connection(entry["collapsed"], f"{path}.collapsed", errors)
    elif op in {"insertElement", "removeElement"}:
        if "vesselId" in entry: _validate_id(entry["vesselId"], f"{path}.vesselId", errors)
        if "element" in entry: _validate_element(entry["element"], f"{path}.element", errors)
        if "index" in entry: _validate_index(entry["index"], f"{path}.index", errors)
    else:
        for field in ("from", "to"):
            if field in entry: _validate_id(entry[field], f"{path}.{field}", errors)
        if "element" in entry: _validate_element(entry["element"], f"{path}.element", errors)
        for field in ("index", "toIndex"):
            if field in entry: _validate_index(entry[field], f"{path}.{field}", errors)


def _validate_scene_entry(entry: Any, path: str, errors: list[dict[str, str]]) -> None:
    if type(entry) is not dict:
        _record_error(errors, path, "expected patch entry")
        return
    op = entry.get("op")
    if type(op) is str and op in _KERNEL_OPS:
        _validate_kernel_entry(entry, path, errors, targeted=True)
        return
    if type(op) is not str or op not in _SCENE_OPS:
        _record_error(errors, f"{path}.op", "unknown scene operation")
        return
    fields = {
        "declareKind": ({"op", "kindId", "declaration"}, {"op", "kindId", "declaration"}),
        "deleteKind": ({"op", "kindId", "declaration"}, {"op", "kindId", "declaration"}),
        "insertBody": ({"op", "name", "body"}, {"op", "name", "body"}),
        "deleteBody": ({"op", "name", "body"}, {"op", "name", "body"}),
        "addRelation": ({"op", "relation"}, {"op", "relation"}),
        "removeRelation": ({"op", "relation"}, {"op", "relation"}),
    }
    allowed, required = fields[op]
    _known_and_required(entry, path, errors, allowed, required)
    if op in {"declareKind", "deleteKind"}:
        if "kindId" in entry: _validate_id(entry["kindId"], f"{path}.kindId", errors)
        if "declaration" in entry: _validate_declaration(entry["declaration"], f"{path}.declaration", errors)
    elif op in {"insertBody", "deleteBody"}:
        if "name" in entry: _validate_id(entry["name"], f"{path}.name", errors)
        if "body" in entry: _validate_body(entry["body"], f"{path}.body", errors)
    elif "relation" in entry:
        _validate_relation(entry["relation"], f"{path}.relation", errors)


def _validate_patch_document(value: Any, protocol: str, scene: bool) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not core._is_finite_json(value):
        _record_error(errors, "$", "expected finite JSON value")
    if type(value) is not dict:
        _record_error(errors, "$", "expected patch document")
        return errors
    _known_and_required(value, "$", errors, {"protocol", "patch"}, {"protocol", "patch"})
    if value.get("protocol") != protocol:
        _record_error(errors, "$.protocol", f"expected {protocol}")
    entries = value.get("patch")
    if type(entries) is not list:
        _record_error(errors, "$.patch", "expected entry array")
        return errors
    for index, entry in enumerate(entries):
        if scene:
            _validate_scene_entry(entry, f"$.patch.{index}", errors)
        else:
            _validate_kernel_entry(entry, f"$.patch.{index}", errors, targeted=False)
    return errors


def validate_patch(value: Any) -> list[dict[str, str]]:
    return _validate_patch_document(value, "paperfold/v1", False)


def validate_scene_patch(value: Any) -> list[dict[str, str]]:
    return _validate_patch_document(value, "paperfold/v2", True)


def _json_equal(left: Any, right: Any) -> bool:
    return core._json_equal(left, right)


def canonicalize_body(body: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(body)
    for vessel in result.get("vessels", {}).values():
        contains = vessel.get("contains")
        if type(contains) is list:
            for element in contains:
                if type(element) is dict and type(element.get("body")) is dict:
                    element["body"] = canonicalize_body(element["body"])
            if not contains:
                vessel.pop("contains", None)
        if vessel.get("ports") == {}:
            vessel.pop("ports", None)
    return result


def _canonicalize_vessel(vessel: dict[str, Any]) -> dict[str, Any]:
    wrapper = {"root": "holder", "vessels": {"holder": vessel}}
    return canonicalize_body(wrapper)["vessels"]["holder"]


def canonicalize_scene(scene: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(scene)
    if type(result.get("bodies")) is dict:
        result["bodies"] = {
            name: canonicalize_body(body) for name, body in result["bodies"].items()
        }
    if type(result.get("relations")) is list:
        result["relations"].sort(key=lambda relation: (
            relation["kind"], relation["from"], relation["to"]
        ))
    return result


def _endpoint_key(endpoint: dict[str, Any]) -> tuple[str, str]:
    return endpoint["vessel"], endpoint["side"]


def _connection_key(connection: dict[str, Any]) -> tuple[tuple[str, str], tuple[str, str]]:
    return tuple(sorted((_endpoint_key(connection["from"]), _endpoint_key(connection["to"]))))  # type: ignore[return-value]


def _connection_equal(left: Any, right: Any) -> bool:
    return type(left) is dict and type(right) is dict and _connection_key(left) == _connection_key(right)


def _connections_equal(left: Any, right: Any) -> bool:
    return (
        type(left) is list and type(right) is list
        and sorted(_connection_key(item) for item in left)
        == sorted(_connection_key(item) for item in right)
    )


def _stale(path: str, field: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"path": f"{path}.{field}", "message": f"stale patch: {field} differs"}]}


def _operation_failure(path: str, error: Exception) -> dict[str, Any]:
    return {"ok": False, "errors": [{"path": path, "message": str(error)}]}


def _apply_body_entry(body: dict[str, Any], entry: dict[str, Any], path: str) -> dict[str, Any]:
    edits = _editing_module()
    try:
        op = entry["op"]
        if op == "connect":
            outcome = edits.connect(body, entry["from"], entry["to"])
            if not _connections_equal(outcome["displaced"], entry["displaced"]):
                return _stale(path, "displaced")
            return {"ok": True, "value": outcome["body"]}
        if op == "disconnect":
            outcome = edits.disconnect(body, entry["endpoint"])
            if outcome["removed"] is None or not _connection_equal(outcome["removed"], entry["removed"]):
                return _stale(path, "removed")
            return {"ok": True, "value": outcome["body"]}
        if op == "insertVessel":
            options: dict[str, Any] = {"id": entry["vesselId"]}
            if "at" in entry:
                options["at"] = entry["at"]
            outcome = edits.insert_vessel(body, entry["vessel"], options)
            actual = outcome["bridged"]
            recorded = entry["bridged"]
            if not (actual is None and recorded is None) and not _connection_equal(actual, recorded):
                return _stale(path, "bridged")
            return {"ok": True, "value": outcome["body"]}
        if op == "deleteVessel":
            options = {"collapseOppositeNeighbors": entry.get("collapseOppositeNeighbors", False)}
            outcome = edits.delete_vessel(body, entry["vesselId"], options)
            if not _json_equal(_canonicalize_vessel(outcome["vessel"]), _canonicalize_vessel(entry["vessel"])):
                return _stale(path, "vessel")
            actual, recorded = outcome["collapsed"], entry["collapsed"]
            if not (actual is None and recorded is None) and not _connection_equal(actual, recorded):
                return _stale(path, "collapsed")
            return {"ok": True, "value": outcome["body"]}
        if op == "insertElement":
            value = edits.insert_element(body, entry["vesselId"], entry["element"], entry["index"])
            return {"ok": True, "value": value}
        if op == "removeElement":
            outcome = edits.remove_element(body, entry["vesselId"], entry["index"])
            if not _json_equal(_canonicalize_element(outcome["element"]), _canonicalize_element(entry["element"])):
                return _stale(path, "element")
            return {"ok": True, "value": outcome["body"]}
        source = body["vessels"][entry["from"]].get("contains", [])
        if entry["index"] >= len(source) or not _json_equal(
            _canonicalize_element(source[entry["index"]]), _canonicalize_element(entry["element"])
        ):
            return _stale(path, "element")
        value = edits.move_element(body, entry["from"], entry["index"], entry["to"])
        destination = value["vessels"][entry["to"]].get("contains", [])
        landing = len(destination) - 1
        if landing != entry["toIndex"]:
            return _stale(path, "toIndex")
        return {"ok": True, "value": value}
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return _operation_failure(path, error)


def _canonicalize_element(element: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(element)
    if type(result.get("body")) is dict:
        result["body"] = canonicalize_body(result["body"])
    return result


def apply_patch(body: dict[str, Any], document: Any) -> dict[str, Any]:
    errors = validate_patch(document)
    if errors:
        return {"ok": False, "errors": errors}
    current = copy.deepcopy(body)
    for index, entry in enumerate(document["patch"]):
        outcome = _apply_body_entry(current, entry, f"$.patch.{index}")
        if not outcome["ok"]:
            return outcome
        current = outcome["value"]
    final_paths = core.validate_document({"protocol": "paper-doll/v3", "body": current})
    if final_paths:
        return {"ok": False, "errors": _paths_to_errors(final_paths, "resulting body is invalid")}
    return {"ok": True, "value": canonicalize_body(current)}


def _without_ports(vessel: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(vessel)
    result.pop("ports", None)
    return result


def _inverse_kernel_entry(entry: dict[str, Any]) -> list[dict[str, Any]]:
    op = entry["op"]
    if op == "connect":
        inverse = [{
            "op": "disconnect", "endpoint": copy.deepcopy(entry["from"]),
            "removed": {"from": copy.deepcopy(entry["from"]), "to": copy.deepcopy(entry["to"])},
        }]
        inverse.extend({
            "op": "connect", "from": copy.deepcopy(connection["from"]),
            "to": copy.deepcopy(connection["to"]), "displaced": [],
        } for connection in entry["displaced"])
        return inverse
    if op == "disconnect":
        return [{"op": "connect", "from": copy.deepcopy(entry["removed"]["from"]),
                 "to": copy.deepcopy(entry["removed"]["to"]), "displaced": []}]
    if op == "insertVessel":
        vessel = copy.deepcopy(entry["vessel"])
        collapsed = None
        inverse: dict[str, Any] = {
            "op": "deleteVessel", "vesselId": entry["vesselId"],
            "vessel": vessel, "collapsed": None,
        }
        if "at" in entry:
            at = copy.deepcopy(entry["at"])
            ports = {_OPPOSITE[at["side"]]: at}
            if entry["bridged"] is not None:
                bridged = entry["bridged"]
                prior = bridged["to"] if bridged["from"] == entry["at"] else bridged["from"]
                ports[at["side"]] = copy.deepcopy(prior)
                collapsed = {"from": copy.deepcopy(at), "to": copy.deepcopy(prior)}
                inverse["collapseOppositeNeighbors"] = True
            vessel["ports"] = ports
            inverse["collapsed"] = collapsed
        return [inverse]
    if op == "deleteVessel":
        inverse = []
        if entry["collapsed"] is not None:
            inverse.append({"op": "disconnect", "endpoint": copy.deepcopy(entry["collapsed"]["from"]),
                            "removed": copy.deepcopy(entry["collapsed"])})
        inverse.append({"op": "insertVessel", "vesselId": entry["vesselId"],
                        "vessel": _without_ports(entry["vessel"]), "bridged": None})
        ports = entry["vessel"].get("ports", {})
        for side in _SIDES:
            if side in ports:
                inverse.append({
                    "op": "connect", "from": {"vessel": entry["vesselId"], "side": side},
                    "to": copy.deepcopy(ports[side]), "displaced": [],
                })
        return inverse
    if op == "insertElement":
        return [{"op": "removeElement", "vesselId": entry["vesselId"],
                 "index": entry["index"], "element": copy.deepcopy(entry["element"])}]
    if op == "removeElement":
        return [{"op": "insertElement", "vesselId": entry["vesselId"],
                 "element": copy.deepcopy(entry["element"]), "index": entry["index"]}]
    return [
        {"op": "removeElement", "vesselId": entry["to"], "index": entry["toIndex"],
         "element": copy.deepcopy(entry["element"])},
        {"op": "insertElement", "vesselId": entry["from"],
         "element": copy.deepcopy(entry["element"]), "index": entry["index"]},
    ]


def invert_patch(document: Any) -> dict[str, Any]:
    errors = validate_patch(document)
    if errors:
        raise ValueError(f"invalid paperfold/v1 patch: {errors!r}")
    entries: list[dict[str, Any]] = []
    for entry in reversed(document["patch"]):
        entries.extend(_inverse_kernel_entry(entry))
    return {"protocol": "paperfold/v1", "patch": entries}


def compose_patches(first: Any, second: Any) -> dict[str, Any]:
    first_errors, second_errors = validate_patch(first), validate_patch(second)
    if first_errors or second_errors:
        raise ValueError(f"cannot compose invalid patches: {first_errors + second_errors!r}")
    return {"protocol": "paperfold/v1", "patch": copy.deepcopy(first["patch"] + second["patch"])}


def _strip_target(entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    target = {"body": entry["body"]}
    if "path" in entry:
        target["path"] = entry["path"]
    local = {key: copy.deepcopy(value) for key, value in entry.items() if key not in {"body", "path"}}
    return target, local


def _resolve_inner_body(root: dict[str, Any], path: str | None) -> dict[str, Any] | None:
    if path is None:
        return root
    segments = path.split("/")
    if len(segments) % 2:
        return None
    current = root
    for offset in range(0, len(segments), 2):
        vessel = current.get("vessels", {}).get(segments[offset])
        if type(vessel) is not dict:
            return None
        element = next((item for item in vessel.get("contains", [])
                        if type(item) is dict and item.get("id") == segments[offset + 1]), None)
        if type(element) is not dict or type(element.get("body")) is not dict:
            return None
        current = element["body"]
    return current


def _apply_targeted_entry(scene: dict[str, Any], entry: dict[str, Any], path: str) -> dict[str, Any]:
    body_name = entry["body"]
    if body_name not in scene.get("bodies", {}):
        return _stale(path, "body")
    top = copy.deepcopy(scene["bodies"][body_name])
    inner = _resolve_inner_body(top, entry.get("path"))
    if inner is None:
        return _stale(path, "path")
    _, local = _strip_target(entry)
    outcome = _apply_body_entry(inner, local, path)
    if not outcome["ok"]:
        return outcome
    if entry.get("path") is None:
        top = outcome["value"]
    else:
        resolved = _resolve_inner_body(top, entry["path"])
        assert resolved is not None
        resolved.clear()
        resolved.update(copy.deepcopy(outcome["value"]))
    updated = copy.deepcopy(scene)
    updated["bodies"][body_name] = top
    return {"ok": True, "value": updated}


def _apply_scene_entry(scene: dict[str, Any], entry: dict[str, Any], path: str) -> dict[str, Any]:
    if entry["op"] in _KERNEL_OPS:
        return _apply_targeted_entry(scene, entry, path)
    edits = _editing_module()
    try:
        op = entry["op"]
        if op == "declareKind":
            value = edits.declare_kind(scene, entry["kindId"], entry["declaration"])
        elif op == "deleteKind":
            outcome = edits.delete_kind(scene, entry["kindId"])
            if not _json_equal(outcome["declaration"], entry["declaration"]):
                return _stale(path, "declaration")
            value = outcome["scene"]
        elif op == "insertBody":
            value = edits.insert_body(scene, entry["name"], entry["body"])
        elif op == "deleteBody":
            outcome = edits.delete_body(scene, entry["name"])
            if not _json_equal(canonicalize_body(outcome["body"]), canonicalize_body(entry["body"])):
                return _stale(path, "body")
            value = outcome["scene"]
        elif op == "addRelation":
            value = edits.add_relation(scene, entry["relation"])
        else:
            outcome = edits.remove_relation(scene, entry["relation"])
            if not _json_equal(outcome["relation"], entry["relation"]):
                return _stale(path, "relation")
            value = outcome["scene"]
        return {"ok": True, "value": value}
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return _operation_failure(path, error)


def apply_scene_patch(scene: dict[str, Any], document: Any) -> dict[str, Any]:
    errors = validate_scene_patch(document)
    if errors:
        return {"ok": False, "errors": errors}
    current = copy.deepcopy(scene)
    for index, entry in enumerate(document["patch"]):
        outcome = _apply_scene_entry(current, entry, f"$.patch.{index}")
        if not outcome["ok"]:
            return outcome
        current = outcome["value"]
    final_paths = core.validate_scene(current)
    if final_paths:
        return {"ok": False, "errors": _paths_to_errors(final_paths, "resulting scene is invalid")}
    return {"ok": True, "value": canonicalize_scene(current)}


def invert_scene_patch(document: Any) -> dict[str, Any]:
    errors = validate_scene_patch(document)
    if errors:
        raise ValueError(f"invalid paperfold/v2 patch: {errors!r}")
    inverse: list[dict[str, Any]] = []
    for entry in reversed(document["patch"]):
        op = entry["op"]
        if op in _KERNEL_OPS:
            target, local = _strip_target(entry)
            for local_inverse in _inverse_kernel_entry(local):
                inverse.append({"op": local_inverse.pop("op"), **target, **local_inverse})
        elif op == "declareKind":
            inverse.append({"op": "deleteKind", "kindId": entry["kindId"],
                            "declaration": copy.deepcopy(entry["declaration"])})
        elif op == "deleteKind":
            inverse.append({"op": "declareKind", "kindId": entry["kindId"],
                            "declaration": copy.deepcopy(entry["declaration"])})
        elif op == "insertBody":
            inverse.append({"op": "deleteBody", "name": entry["name"], "body": copy.deepcopy(entry["body"])})
        elif op == "deleteBody":
            inverse.append({"op": "insertBody", "name": entry["name"], "body": copy.deepcopy(entry["body"])})
        elif op == "addRelation":
            inverse.append({"op": "removeRelation", "relation": copy.deepcopy(entry["relation"])})
        else:
            inverse.append({"op": "addRelation", "relation": copy.deepcopy(entry["relation"])})
    return {"protocol": "paperfold/v2", "patch": inverse}


def compose_scene_patches(first: Any, second: Any) -> dict[str, Any]:
    first_errors, second_errors = validate_scene_patch(first), validate_scene_patch(second)
    if first_errors or second_errors:
        raise ValueError(f"cannot compose invalid scene patches: {first_errors + second_errors!r}")
    return {"protocol": "paperfold/v2", "patch": copy.deepcopy(first["patch"] + second["patch"])}


def _diff_error(path: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"path": path, "message": message}]}


def _assert_valid_body(body: Any) -> None:
    errors = core.validate_document({"protocol": "paper-doll/v3", "body": body})
    if errors:
        raise ValueError(f"diff body is outside the valid caller domain: {errors!r}")


def diff_bodies(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    _assert_valid_body(source)
    _assert_valid_body(target)
    a, b = canonicalize_body(source), canonicalize_body(target)
    if a["root"] != b["root"]:
        return _diff_error("$.root", "roots differ")
    root = a["root"]
    a_has_accepts = "accepts" in a["vessels"][root]
    b_has_accepts = "accepts" in b["vessels"][root]
    if a_has_accepts != b_has_accepts or (
        a_has_accepts
        and not _json_equal(a["vessels"][root]["accepts"], b["vessels"][root]["accepts"])
    ):
        return _diff_error(f"$.vessels.{root}.accepts", "root accepts differs")

    edits = _editing_module()
    live = copy.deepcopy(a)
    entries: list[dict[str, Any]] = []
    for vessel_id in sorted(name for name in live["vessels"] if name != root):
        outcome = edits.delete_vessel(live, vessel_id)
        entries.append({"op": "deleteVessel", "vesselId": vessel_id,
                        "vessel": outcome["vessel"], "collapsed": outcome["collapsed"]})
        live = outcome["body"]
    contains = live["vessels"][root].get("contains", [])
    for index in range(len(contains) - 1, -1, -1):
        outcome = edits.remove_element(live, root, index)
        entries.append({"op": "removeElement", "vesselId": root, "index": index,
                        "element": outcome["element"]})
        live = outcome["body"]
    for index, element in enumerate(b["vessels"][root].get("contains", [])):
        live = edits.insert_element(live, root, element, index)
        entries.append({"op": "insertElement", "vesselId": root,
                        "element": copy.deepcopy(element), "index": index})
    for vessel_id in sorted(name for name in b["vessels"] if name != root):
        vessel = _without_ports(b["vessels"][vessel_id])
        outcome = edits.insert_vessel(live, vessel, {"id": vessel_id})
        entries.append({"op": "insertVessel", "vesselId": vessel_id,
                        "vessel": copy.deepcopy(vessel), "bridged": outcome["bridged"]})
        live = outcome["body"]
    for connection in core._derive_connections(b):
        outcome = edits.connect(live, connection["from"], connection["to"])
        entries.append({"op": "connect", "from": copy.deepcopy(connection["from"]),
                        "to": copy.deepcopy(connection["to"]),
                        "displaced": outcome["displaced"]})
        live = outcome["body"]
    return {"ok": True, "value": {"protocol": "paperfold/v1", "patch": entries}}


def _relation_sort(relation: dict[str, Any]) -> tuple[str, str, str]:
    return relation["kind"], relation["from"], relation["to"]


def diff_scenes(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    source_errors, target_errors = core.validate_scene(source), core.validate_scene(target)
    if source_errors or target_errors:
        raise ValueError(f"diff scene is outside the valid caller domain: {source_errors + target_errors!r}")
    edits = _editing_module()
    a, b = canonicalize_scene(source), canonicalize_scene(target)
    live = copy.deepcopy(a)
    entries: list[dict[str, Any]] = []
    for relation in sorted(copy.deepcopy(live["relations"]), key=_relation_sort):
        outcome = edits.remove_relation(live, relation)
        entries.append({"op": "removeRelation", "relation": outcome["relation"]})
        live = outcome["scene"]
    for name in sorted(set(a["bodies"]) - set(b["bodies"])):
        outcome = edits.delete_body(live, name)
        entries.append({"op": "deleteBody", "name": name, "body": outcome["body"]})
        live = outcome["scene"]
    changed_kinds = {name for name in set(a["kinds"]) & set(b["kinds"])
                     if not _json_equal(a["kinds"][name], b["kinds"][name])}
    for kind_id in sorted((set(a["kinds"]) - set(b["kinds"])) | changed_kinds):
        outcome = edits.delete_kind(live, kind_id)
        entries.append({"op": "deleteKind", "kindId": kind_id,
                        "declaration": outcome["declaration"]})
        live = outcome["scene"]
    for kind_id in sorted((set(b["kinds"]) - set(a["kinds"])) | changed_kinds):
        declaration = copy.deepcopy(b["kinds"][kind_id])
        live = edits.declare_kind(live, kind_id, declaration)
        entries.append({"op": "declareKind", "kindId": kind_id, "declaration": declaration})
    for name in sorted(set(b["bodies"]) - set(a["bodies"])):
        body = copy.deepcopy(b["bodies"][name])
        live = edits.insert_body(live, name, body)
        entries.append({"op": "insertBody", "name": name, "body": body})
    for name in sorted(set(a["bodies"]) & set(b["bodies"])):
        if _json_equal(canonicalize_body(a["bodies"][name]), canonicalize_body(b["bodies"][name])):
            continue
        body_diff = diff_bodies(live["bodies"][name], b["bodies"][name])
        if not body_diff["ok"]:
            errors = []
            for error in body_diff["errors"]:
                suffix = error["path"][1:] if error["path"].startswith("$") else f".{error['path']}"
                errors.append({"path": f"$.bodies.{name}{suffix}", "message": error["message"]})
            return {"ok": False, "errors": errors}
        applied = apply_patch(live["bodies"][name], body_diff["value"])
        if not applied["ok"]:
            return applied
        for entry in body_diff["value"]["patch"]:
            entries.append({"op": entry["op"], "body": name,
                            **{key: copy.deepcopy(value) for key, value in entry.items() if key != "op"}})
        live["bodies"][name] = applied["value"]
    for relation in sorted(copy.deepcopy(b["relations"]), key=_relation_sort):
        live = edits.add_relation(live, relation)
        entries.append({"op": "addRelation", "relation": relation})
    return {"ok": True, "value": {"protocol": "paperfold/v2", "patch": entries}}


def _project_result(result: dict[str, Any]) -> dict[str, Any]:
    if result["ok"]:
        return {"outcome": "ok", "value": result["value"]}
    return {"outcome": "invalid", "errorPaths": [error["path"] for error in result["errors"]]}


def _diff_laws(source: dict[str, Any], target: dict[str, Any], *, scene: bool) -> dict[str, Any]:
    differ = diff_scenes if scene else diff_bodies
    apply = apply_scene_patch if scene else apply_patch
    invert = invert_scene_patch if scene else invert_patch
    compose = compose_scene_patches if scene else compose_patches
    canonicalize = canonicalize_scene if scene else canonicalize_body
    difference = differ(source, target)
    if not difference["ok"]:
        return _project_result(difference)
    applied = apply(source, difference["value"])
    if not applied["ok"]:
        return _project_result(applied)
    inverse = invert(difference["value"])
    restored = apply(applied["value"], inverse)
    if not restored["ok"]:
        return _project_result(restored)
    composed_restore = apply(source, compose(difference["value"], inverse))
    if not composed_restore["ok"]:
        return _project_result(composed_restore)
    if not _json_equal(composed_restore["value"], canonicalize(source)):
        return {"outcome": "invalid", "errorPaths": ["$"]}
    return {"outcome": "ok", "value": {
        "applied": canonicalize(applied["value"]),
        "restored": canonicalize(restored["value"]),
    }}


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    if type(case) is not dict or type(case.get("input")) is not dict:
        raise ValueError("case must contain an input object")
    if set(case["input"]) != {"args"} or type(case["input"]["args"]) is not list:
        raise ValueError("case input must be exactly {'args': [...]}")
    subject, operation, args = case.get("subject"), case.get("operation"), case["input"]["args"]
    domains = {
        "paperfold/v1": {
            "validatePatch": validate_patch, "applyPatch": apply_patch,
            "invertPatch": invert_patch, "composePatches": compose_patches,
            "canonicalizeBody": canonicalize_body, "diffBodies": diff_bodies,
        },
        "paperfold/v2": {
            "validateScenePatch": validate_scene_patch, "applyScenePatch": apply_scene_patch,
            "invertScenePatch": invert_scene_patch, "composeScenePatches": compose_scene_patches,
            "canonicalizeScene": canonicalize_scene, "diffScenes": diff_scenes,
        },
    }
    if operation == "diffLaws" and subject == "paperfold/v1":
        try: return _diff_laws(*args, scene=False)
        except (TypeError, ValueError, KeyError): return {"outcome": "error"}
    if operation == "diffSceneLaws" and subject == "paperfold/v2":
        try: return _diff_laws(*args, scene=True)
        except (TypeError, ValueError, KeyError): return {"outcome": "error"}
    if subject not in domains or operation not in domains[subject]:
        raise ValueError(f"unsupported subject/operation: {subject!r}/{operation!r}")
    function = domains[subject][operation]
    try:
        value = function(*args)
    except (TypeError, ValueError, KeyError, IndexError):
        return {"outcome": "error"}
    if operation.startswith("validate"):
        return ({"outcome": "invalid", "errorPaths": [error["path"] for error in value]}
                if value else {"outcome": "valid"})
    if operation.startswith("apply") or operation.startswith("diff"):
        return _project_result(value)
    return {"outcome": "ok", "value": value}
