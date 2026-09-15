"""Pure Paperdoll and Paperchain edits derived from their written specs."""

from __future__ import annotations

import copy
from typing import Any

try:
    from . import paper_conformance as core
except ImportError:  # Supports a direct-path CLI/bootstrap import.
    import paper_conformance as core  # type: ignore[no-redef]


_OMITTED = object()


def _require_endpoint(body: dict[str, Any], endpoint: dict[str, Any]) -> None:
    vessel_id = endpoint.get("vessel")
    side = endpoint.get("side")
    if vessel_id not in body["vessels"]:
        raise ValueError(f"unknown vessel: {vessel_id!r}")
    if side not in core.SIDES:
        raise ValueError(f"invalid side: {side!r}")


def _disconnect_in_place(
    body: dict[str, Any], endpoint: dict[str, Any]
) -> dict[str, Any] | None:
    vessel = body["vessels"][endpoint["vessel"]]
    ports = vessel.get("ports")
    if not isinstance(ports, dict) or endpoint["side"] not in ports:
        return None

    peer = ports.pop(endpoint["side"])
    peer_vessel = body["vessels"].get(peer["vessel"])
    if isinstance(peer_vessel, dict):
        peer_ports = peer_vessel.get("ports")
        if isinstance(peer_ports, dict):
            peer_ports.pop(peer["side"], None)
    return {
        "from": copy.deepcopy(endpoint),
        "to": copy.deepcopy(peer),
    }


def _connection_key(connection: dict[str, Any]) -> frozenset[tuple[str, str]]:
    return frozenset(
        (
            (connection["from"]["vessel"], connection["from"]["side"]),
            (connection["to"]["vessel"], connection["to"]["side"]),
        )
    )


def connect(
    body: dict[str, Any],
    from_endpoint: dict[str, Any],
    to_endpoint: dict[str, Any],
) -> dict[str, Any]:
    """Replace both endpoint occupants with one reciprocal connection."""

    _require_endpoint(body, from_endpoint)
    _require_endpoint(body, to_endpoint)
    if from_endpoint["vessel"] == to_endpoint["vessel"]:
        raise ValueError("a vessel cannot connect to itself")
    if to_endpoint["side"] != core.OPPOSITE[from_endpoint["side"]]:
        raise ValueError("connection sides must be opposite")

    edited = copy.deepcopy(body)
    displaced: list[dict[str, Any]] = []
    seen: set[frozenset[tuple[str, str]]] = set()
    for endpoint in (from_endpoint, to_endpoint):
        removed = _disconnect_in_place(edited, endpoint)
        if removed is not None and _connection_key(removed) not in seen:
            displaced.append(removed)
            seen.add(_connection_key(removed))
    edited["vessels"][from_endpoint["vessel"]].setdefault("ports", {})[
        from_endpoint["side"]
    ] = copy.deepcopy(to_endpoint)
    edited["vessels"][to_endpoint["vessel"]].setdefault("ports", {})[
        to_endpoint["side"]
    ] = copy.deepcopy(from_endpoint)
    return {"body": edited, "displaced": displaced}


def disconnect(body: dict[str, Any], endpoint: dict[str, Any]) -> dict[str, Any]:
    """Remove an endpoint's reciprocal connection, if present."""

    _require_endpoint(body, endpoint)
    edited = copy.deepcopy(body)
    return {"body": edited, "removed": _disconnect_in_place(edited, endpoint)}


def insert_vessel(
    body: dict[str, Any],
    vessel: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert a free vessel, attach it, or split an occupied connection."""

    vessel = {} if vessel is None else vessel
    options = {} if options is None else options
    requested_id = options.get("id")
    if requested_id is not None:
        if not core._is_id(requested_id):
            raise ValueError(f"invalid vessel id: {requested_id!r}")
        if requested_id in body["vessels"]:
            raise ValueError(f"vessel id is already used: {requested_id!r}")
        vessel_id = requested_id
    else:
        suffix = 1
        while f"vessel-{suffix}" in body["vessels"]:
            suffix += 1
        vessel_id = f"vessel-{suffix}"

    at = options.get("at")
    if at is not None:
        _require_endpoint(body, at)

    edited = copy.deepcopy(body)
    edited["vessels"][vessel_id] = copy.deepcopy(vessel)
    if at is None:
        return {"body": edited, "vesselId": vessel_id, "bridged": None}

    bridged = _disconnect_in_place(edited, at)
    opposite = core.OPPOSITE[at["side"]]
    if bridged is not None:
        neighbor_connection = connect(
            edited,
            bridged["to"],
            {"vessel": vessel_id, "side": at["side"]},
        )
        edited = neighbor_connection["body"]
    attachment = connect(
        edited,
        at,
        {"vessel": vessel_id, "side": opposite},
    )
    return {"body": attachment["body"], "vesselId": vessel_id, "bridged": bridged}


def delete_vessel(
    body: dict[str, Any],
    vessel_id: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Delete a non-root vessel and optionally join opposite neighbors."""

    if vessel_id not in body["vessels"]:
        raise ValueError(f"unknown vessel: {vessel_id!r}")
    if vessel_id == body["root"]:
        raise ValueError("cannot delete the root vessel")

    options = {} if options is None else options
    deleted = copy.deepcopy(body["vessels"][vessel_id])
    incident_sides = list(deleted.get("ports", {}))
    edited = copy.deepcopy(body)
    incident: list[dict[str, Any]] = []
    for side in incident_sides:
        removed = _disconnect_in_place(edited, {"vessel": vessel_id, "side": side})
        if removed is not None:
            incident.append(removed)
    del edited["vessels"][vessel_id]

    collapsed = None
    should_collapse = options.get("collapseOppositeNeighbors") is True
    if should_collapse and len(incident) == 2:
        first, second = incident
        opposite_sides = (
            core.OPPOSITE[first["from"]["side"]] == second["from"]["side"]
        )
        different_neighbors = first["to"]["vessel"] != second["to"]["vessel"]
        if opposite_sides and different_neighbors:
            collapse_result = connect(edited, first["to"], second["to"])
            edited = collapse_result["body"]
            collapsed = {
                "from": copy.deepcopy(first["to"]),
                "to": copy.deepcopy(second["to"]),
            }
    return {"body": edited, "vessel": deleted, "collapsed": collapsed}


def _require_vessel(body: dict[str, Any], vessel_id: str) -> dict[str, Any]:
    if vessel_id not in body["vessels"]:
        raise ValueError(f"unknown vessel: {vessel_id!r}")
    return body["vessels"][vessel_id]


def _require_index(index: Any, length: int, *, allow_end: bool) -> int:
    if not core._is_json_integer(index):
        raise ValueError("element index must be an integer")
    normalized = int(index)
    maximum = length if allow_end else length - 1
    if normalized < 0 or normalized > maximum:
        raise ValueError(f"element index out of range: {index!r}")
    return normalized


def _is_accepted(vessel: dict[str, Any], element: dict[str, Any]) -> bool:
    accepts = vessel.get("accepts")
    return accepts is None or any(core._matches(token, element) for token in accepts)


def _require_insertable_element(
    vessel: dict[str, Any], element: dict[str, Any]
) -> None:
    if not core._is_id(element.get("kind")):
        raise ValueError("element kind must be a valid id")
    for field in ("type", "id"):
        if field in element and not core._is_id(element[field]):
            raise ValueError(f"element {field} must be a valid id")
    if "body" in element:
        errors: list[str] = []
        core._validate_body(element["body"], "$.body", errors)
        if errors:
            raise ValueError("embedded element body is invalid")
    if not _is_accepted(vessel, element):
        raise ValueError("element is not accepted by destination vessel")
    element_id = element.get("id")
    if element_id is not None and any(
        existing.get("id") == element_id for existing in vessel.get("contains", [])
    ):
        raise ValueError(f"element id is already used: {element_id!r}")


def insert_element(
    body: dict[str, Any],
    vessel_id: str,
    element: dict[str, Any],
    at: int | float | None = None,
) -> dict[str, Any]:
    """Insert an accepted element at a checked array position."""

    vessel = _require_vessel(body, vessel_id)
    _require_insertable_element(vessel, element)
    contains = vessel.get("contains", [])
    index = len(contains) if at is None else _require_index(at, len(contains), allow_end=True)
    edited = copy.deepcopy(body)
    edited_contains = edited["vessels"][vessel_id].setdefault("contains", [])
    edited_contains.insert(index, copy.deepcopy(element))
    return edited


def remove_element(
    body: dict[str, Any], vessel_id: str, index: int | float
) -> dict[str, Any]:
    """Remove one contained element by its current array index."""

    vessel = _require_vessel(body, vessel_id)
    contains = vessel.get("contains", [])
    normalized = _require_index(index, len(contains), allow_end=False)
    edited = copy.deepcopy(body)
    element = edited["vessels"][vessel_id]["contains"].pop(normalized)
    return {"body": edited, "element": element}


def move_element(
    body: dict[str, Any],
    from_vessel_id: str,
    index: int | float,
    to_vessel_id: str,
) -> dict[str, Any]:
    """Move one element to the end of a destination vessel atomically."""

    source = _require_vessel(body, from_vessel_id)
    destination = _require_vessel(body, to_vessel_id)
    source_contains = source.get("contains", [])
    normalized = _require_index(index, len(source_contains), allow_end=False)
    element = source_contains[normalized]
    if not _is_accepted(destination, element):
        raise ValueError("element is not accepted by destination vessel")
    element_id = element.get("id")
    if from_vessel_id != to_vessel_id and element_id is not None and any(
        existing.get("id") == element_id
        for existing in destination.get("contains", [])
    ):
        raise ValueError(f"element id is already used at destination: {element_id!r}")

    edited = copy.deepcopy(body)
    moved = edited["vessels"][from_vessel_id]["contains"].pop(normalized)
    edited["vessels"][to_vessel_id].setdefault("contains", []).append(moved)
    return edited


def declare_kind(
    scene: dict[str, Any],
    kind_id: str,
    declaration: Any = _OMITTED,
) -> dict[str, Any]:
    """Declare a checked relation kind in a fresh scene."""

    if declaration is _OMITTED:
        declaration = {}
    if not core._is_id(kind_id):
        raise ValueError(f"invalid kind id: {kind_id!r}")
    if kind_id in scene["kinds"]:
        raise ValueError(f"kind id is already declared: {kind_id!r}")
    errors: list[str] = []
    if not core._valid_kind_declaration(declaration, "$.declaration", errors):
        raise ValueError("malformed kind declaration")
    edited = copy.deepcopy(scene)
    edited["kinds"][kind_id] = copy.deepcopy(declaration)
    return edited


def delete_kind(scene: dict[str, Any], kind_id: str) -> dict[str, Any]:
    """Delete an unused kind and return its exact declaration."""

    if kind_id not in scene["kinds"]:
        raise ValueError(f"kind is not declared: {kind_id!r}")
    if any(relation["kind"] == kind_id for relation in scene["relations"]):
        raise ValueError(f"kind is still used by a relation: {kind_id!r}")
    edited = copy.deepcopy(scene)
    declaration = edited["kinds"].pop(kind_id)
    return {"scene": edited, "declaration": declaration}


def insert_body(
    scene: dict[str, Any], name: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Insert a valid Paperdoll body by value."""

    if not core._is_id(name):
        raise ValueError(f"invalid body name: {name!r}")
    if name in scene["bodies"]:
        raise ValueError(f"body name is already used: {name!r}")
    errors: list[str] = []
    core._validate_body(body, "$.body", errors)
    if errors:
        raise ValueError("body is not paper-doll/v3-valid")
    edited = copy.deepcopy(scene)
    edited["bodies"][name] = copy.deepcopy(body)
    return edited


def delete_body(scene: dict[str, Any], name: str) -> dict[str, Any]:
    """Delete an unreferenced body and return its exact stored value."""

    if name not in scene["bodies"]:
        raise ValueError(f"body does not exist: {name!r}")
    if any(
        relation[field].split("/", 1)[0] == name
        for relation in scene["relations"]
        for field in ("from", "to")
    ):
        raise ValueError(f"body is still referenced by a relation: {name!r}")
    edited = copy.deepcopy(scene)
    body = edited["bodies"].pop(name)
    return {"scene": edited, "body": body}


def _require_scene_address(scene: dict[str, Any], address: str) -> None:
    segments = core._parse_address(address, minimum_segments=2)
    body = scene["bodies"].get(segments[0])
    if body is None or core._resolve_address(body, "/".join(segments[1:])) is None:
        raise ValueError(f"scene address does not resolve: {address!r}")


def _relation_key(
    scene: dict[str, Any], relation: dict[str, Any]
) -> tuple[str, str, str]:
    declaration = scene["kinds"].get(relation["kind"], {})
    if declaration.get("symmetric") is True:
        first, second = sorted((relation["from"], relation["to"]))
        return relation["kind"], first, second
    return relation["kind"], relation["from"], relation["to"]


def add_relation(
    scene: dict[str, Any], relation: dict[str, Any]
) -> dict[str, Any]:
    """Append a relation when doing so preserves Paperchain laws 3 through 7."""

    kind = relation["kind"]
    if kind not in scene["kinds"]:
        raise ValueError(f"kind is not declared: {kind!r}")
    _require_scene_address(scene, relation["from"])
    _require_scene_address(scene, relation["to"])
    declaration = scene["kinds"][kind]
    if declaration.get("irreflexive") is True and relation["from"] == relation["to"]:
        raise ValueError(f"kind is irreflexive: {kind!r}")
    candidate_key = _relation_key(scene, relation)
    if any(_relation_key(scene, existing) == candidate_key for existing in scene["relations"]):
        raise ValueError("duplicate relation")

    same_kind = [existing for existing in scene["relations"] if existing["kind"] == kind]
    if declaration.get("symmetric") is True and "fromMax" in declaration:
        budget = declaration["fromMax"]
        for endpoint in (relation["from"], relation["to"]):
            count = sum(
                int(existing["from"] == endpoint) + int(existing["to"] == endpoint)
                for existing in same_kind
            )
            count += int(relation["from"] == endpoint) + int(relation["to"] == endpoint)
            if count > budget:
                raise ValueError("symmetric relation multiplicity exceeded")
    elif declaration.get("symmetric") is not True:
        if "fromMax" in declaration:
            count = sum(existing["from"] == relation["from"] for existing in same_kind)
            if count + 1 > declaration["fromMax"]:
                raise ValueError("from multiplicity exceeded")
        if "toMax" in declaration:
            count = sum(existing["to"] == relation["to"] for existing in same_kind)
            if count + 1 > declaration["toMax"]:
                raise ValueError("to multiplicity exceeded")

    edited = copy.deepcopy(scene)
    edited["relations"].append(copy.deepcopy(relation))
    return edited


def remove_relation(
    scene: dict[str, Any], relation: dict[str, Any]
) -> dict[str, Any]:
    """Remove the first equivalent relation and return its stored orientation."""

    candidate_key = _relation_key(scene, relation)
    index = next(
        (
            index
            for index, existing in enumerate(scene["relations"])
            if _relation_key(scene, existing) == candidate_key
        ),
        None,
    )
    if index is None:
        raise ValueError("relation does not exist")
    edited = copy.deepcopy(scene)
    stored = edited["relations"].pop(index)
    return {"scene": edited, "relation": stored}


def relations_at(scene: dict[str, Any], scene_address: str) -> list[dict[str, Any]]:
    """Return copies of all relations touching a syntactically valid address."""

    core._parse_address(scene_address, minimum_segments=2)
    return copy.deepcopy(
        [
            relation
            for relation in scene["relations"]
            if relation["from"] == scene_address or relation["to"] == scene_address
        ]
    )


def _endpoint_key(endpoint: dict[str, Any]) -> str:
    return f"{endpoint['vessel']}:{endpoint['side']}"


def _normalize_connection(connection: dict[str, Any]) -> dict[str, Any]:
    first = copy.deepcopy(connection["from"])
    second = copy.deepcopy(connection["to"])
    if _endpoint_key(first) > _endpoint_key(second):
        first, second = second, first
    return {"from": first, "to": second}


def _normalize_doll_projection(operation: str, value: Any) -> Any:
    """Apply the corpus-v2 normalization for orientation-free connections."""

    normalized = copy.deepcopy(value)
    if operation == "connect":
        normalized["displaced"] = sorted(
            (_normalize_connection(item) for item in normalized["displaced"]),
            key=lambda item: (_endpoint_key(item["from"]), _endpoint_key(item["to"])),
        )
    elif operation == "disconnect" and normalized["removed"] is not None:
        normalized["removed"] = _normalize_connection(normalized["removed"])
    elif operation == "insertVessel" and normalized["bridged"] is not None:
        normalized["bridged"] = _normalize_connection(normalized["bridged"])
    elif operation == "deleteVessel" and normalized["collapsed"] is not None:
        normalized["collapsed"] = _normalize_connection(normalized["collapsed"])
    return normalized


_DOLL_OPERATIONS = {
    "connect": connect,
    "disconnect": disconnect,
    "insertVessel": insert_vessel,
    "deleteVessel": delete_vessel,
    "insertElement": insert_element,
    "removeElement": remove_element,
    "moveElement": move_element,
}

_CHAIN_OPERATIONS = {
    "declareKind": declare_kind,
    "deleteKind": delete_kind,
    "insertBody": insert_body,
    "deleteBody": delete_body,
    "addRelation": add_relation,
    "removeRelation": remove_relation,
    "relationsAt": relations_at,
}


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run one corpus-v2 editing case and return its language-neutral projection."""

    if type(case) is not dict:
        raise ValueError("case must be an object")
    subject = case.get("subject")
    operation = case.get("operation")
    input_value = case.get("input")
    if type(input_value) is not dict or set(input_value) != {"args"}:
        raise ValueError("editing case input must be exactly {'args': [...]}")
    args = input_value["args"]
    if type(args) is not list:
        raise ValueError("editing case args must be an array")
    operations = (
        _DOLL_OPERATIONS
        if subject == "paper-doll/v3"
        else _CHAIN_OPERATIONS
        if subject == "paperchain/v1"
        else None
    )
    if operations is None or operation not in operations:
        raise ValueError(f"unsupported subject/operation: {subject!r}/{operation!r}")
    try:
        value = operations[operation](*args)
    except ValueError:
        return {"outcome": "error"}
    if subject == "paper-doll/v3":
        value = _normalize_doll_projection(operation, value)
    return {"outcome": "ok", "value": value}
