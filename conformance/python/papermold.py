"""Independent, standard-library Papermold v1/v2 reference implementation."""

from __future__ import annotations

import math
import re
from typing import Any

try:  # Package import when installed; direct import for the fixture bootstrap.
    from .paper_conformance import validate_document, validate_scene
except ImportError:  # pragma: no cover - exercised by direct-file test execution.
    from paper_conformance import validate_document, validate_scene


ID_RE = re.compile(r"[a-z][a-z0-9-]*\Z", re.ASCII)
SIDES = {"top", "right", "bottom", "left"}
_MISSING = object()

Error = dict[str, str]


def _is_id(value: Any) -> bool:
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def _is_integer(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value) and value.is_integer())


def _is_finite_json(value: Any, active: set[int] | None = None) -> bool:
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) not in (dict, list):
        return False
    if active is None:
        active = set()
    identity = id(value)
    if identity in active:
        return False
    active.add(identity)
    try:
        if type(value) is list:
            return all(_is_finite_json(item, active) for item in value)
        return all(type(key) is str and _is_finite_json(item, active) for key, item in value.items())
    finally:
        active.remove(identity)


def _error(errors: list[Error], path: str, message: str = "Invalid value.") -> None:
    errors.append({"path": path, "message": message})


def _unknown_keys(value: dict[str, Any], allowed: set[str], path: str, errors: list[Error]) -> None:
    for key in value:
        if key not in allowed:
            _error(errors, f"{path}.{key}", f"Unknown key {key!r}.")


def _validate_id_map(value: Any, path: str, errors: list[Error]) -> dict[str, Any]:
    if type(value) is not dict:
        _error(errors, path, "Expected an object keyed by ids.")
        return {}
    for key in value:
        if not _is_id(key):
            _error(errors, f"{path}.{key}", "Invalid id.")
    return value


def _validate_token(value: Any, path: str, errors: list[Error]) -> None:
    if type(value) is not dict:
        _error(errors, path, "Expected an accept token.")
        return
    _unknown_keys(value, {"kind", "type"}, path, errors)
    if not _is_id(value.get("kind")):
        _error(errors, f"{path}.kind", "Token kind must be an id.")
    if "type" in value and not _is_id(value["type"]):
        _error(errors, f"{path}.type", "Token type must be an id.")


def _validate_token_list(value: Any, path: str, errors: list[Error]) -> None:
    if type(value) is not list or not value:
        _error(errors, path, "Expected a non-empty token array.")
        return
    for index, token in enumerate(value):
        _validate_token(token, f"{path}.{index}", errors)


def _validate_port(value: Any, path: str, errors: list[Error]) -> None:
    if type(value) is not dict:
        _error(errors, path, "Expected a port address.")
        return
    _unknown_keys(value, {"vessel", "side"}, path, errors)
    if not _is_id(value.get("vessel")):
        _error(errors, f"{path}.vessel", "Port vessel must be an id.")
    side = value.get("side")
    if not isinstance(side, str) or side not in SIDES:
        _error(errors, f"{path}.side", "Port side is invalid.")


def _validate_vessel_demand(
    value: Any, path: str, errors: list[Error], profile_ids: set[str]
) -> None:
    if type(value) is not dict:
        _error(errors, path, "Expected a vessel demand object.")
        return
    allowed = {"exists", "ports", "acceptsAtLeast", "containsAtLeast", "conformsTo", "forbids"}
    _unknown_keys(value, allowed, path, errors)
    if not value:
        _error(errors, path, "A vessel demand must contain a clause.")
    if "exists" in value and value["exists"] is not True:
        _error(errors, f"{path}.exists", "exists must be literal true.")
    if "ports" in value:
        ports = value["ports"]
        if type(ports) is not dict or not ports:
            _error(errors, f"{path}.ports", "ports must be a non-empty object.")
        else:
            for side, address in ports.items():
                if side not in SIDES:
                    _error(errors, f"{path}.ports.{side}", "Unknown side.")
                else:
                    _validate_port(address, f"{path}.ports.{side}", errors)
    for clause in ("acceptsAtLeast", "containsAtLeast", "forbids"):
        if clause in value:
            _validate_token_list(value[clause], f"{path}.{clause}", errors)
    if "conformsTo" in value:
        conforms_to = value["conformsTo"]
        clause_path = f"{path}.conformsTo"
        if type(conforms_to) is not dict:
            _error(errors, clause_path, "Expected {token, profile}.")
        else:
            _unknown_keys(conforms_to, {"token", "profile"}, clause_path, errors)
            if "token" not in conforms_to:
                _error(errors, f"{clause_path}.token", "Missing token.")
            else:
                _validate_token(conforms_to["token"], f"{clause_path}.token", errors)
            target = conforms_to.get("profile")
            if not _is_id(target) or target not in profile_ids:
                _error(errors, f"{clause_path}.profile", "Profile reference does not resolve.")


def _validate_profile(value: Any, path: str, errors: list[Error], profile_ids: set[str]) -> None:
    if type(value) is not dict:
        _error(errors, path, "Expected a profile object.")
        return
    _unknown_keys(value, {"vessels", "atLeast"}, path, errors)
    if "vessels" in value:
        vessels = _validate_id_map(value["vessels"], f"{path}.vessels", errors)
        for vessel_id, demand in vessels.items():
            _validate_vessel_demand(demand, f"{path}.vessels.{vessel_id}", errors, profile_ids)
    if "atLeast" not in value:
        return
    threshold = value["atLeast"]
    threshold_path = f"{path}.atLeast"
    if type(threshold) is not dict:
        _error(errors, threshold_path, "Expected a threshold object.")
        return
    _unknown_keys(threshold, {"n", "of"}, threshold_path, errors)
    n = threshold.get("n")
    if not _is_integer(n) or n < 1:
        _error(errors, f"{threshold_path}.n", "n must be an integer of at least one.")
    checks = threshold.get("of")
    if type(checks) is not list or not checks:
        _error(errors, f"{threshold_path}.of", "of must be a non-empty array.")
        return
    if _is_integer(n) and n > len(checks):
        _error(errors, f"{threshold_path}.n", "n cannot exceed the number of checks.")
    for index, check in enumerate(checks):
        check_path = f"{threshold_path}.of.{index}"
        if type(check) is not dict:
            _error(errors, check_path, "Expected {vessel, check}.")
            continue
        _unknown_keys(check, {"vessel", "check"}, check_path, errors)
        if not _is_id(check.get("vessel")):
            _error(errors, f"{check_path}.vessel", "vessel must be an id.")
        if "check" not in check:
            _error(errors, f"{check_path}.check", "Missing demand.")
        else:
            _validate_vessel_demand(check["check"], f"{check_path}.check", errors, profile_ids)


def _validate_profiles_envelope(
    document: Any, protocol: str, allowed: set[str], errors: list[Error]
) -> dict[str, Any]:
    if not _is_finite_json(document):
        _error(errors, "$", "Expected finite JSON.")
        if type(document) is not dict:
            return {}
    if type(document) is not dict:
        _error(errors, "$", "Expected a document object.")
        return {}
    _unknown_keys(document, allowed, "$", errors)
    if document.get("protocol") != protocol:
        _error(errors, "$.protocol", f"Expected {protocol!r}.")
    profiles = _validate_id_map(document.get("profiles", _MISSING), "$.profiles", errors)
    profile_ids = {key for key in profiles if _is_id(key)}
    for profile_id, profile in profiles.items():
        _validate_profile(profile, f"$.profiles.{profile_id}", errors, profile_ids)
    return document


def validate_profiles(document: Any) -> list[Error]:
    """Return all structural errors for a papermold/v1 profile document."""

    errors: list[Error] = []
    _validate_profiles_envelope(document, "papermold/v1", {"protocol", "profiles"}, errors)
    return errors


def _validate_body_demand(value: Any, path: str, errors: list[Error], profile_ids: set[str]) -> None:
    if type(value) is not dict:
        _error(errors, path, "Expected a body demand object.")
        return
    _unknown_keys(value, {"exists", "conformsTo"}, path, errors)
    if not value:
        _error(errors, path, "A body demand must contain a clause.")
    if "exists" in value and value["exists"] is not True:
        _error(errors, f"{path}.exists", "exists must be literal true.")
    if "conformsTo" in value:
        target = value["conformsTo"]
        if not _is_id(target) or target not in profile_ids:
            _error(errors, f"{path}.conformsTo", "Profile reference does not resolve.")


def _validate_kind_declaration(value: Any, path: str, errors: list[Error]) -> None:
    if type(value) is not dict:
        _error(errors, path, "Expected a kind declaration.")
        return
    _unknown_keys(value, {"symmetric", "irreflexive", "fromMax", "toMax"}, path, errors)
    for field in ("symmetric", "irreflexive"):
        if field in value and type(value[field]) is not bool:
            _error(errors, f"{path}.{field}", f"{field} must be boolean.")
    for field in ("fromMax", "toMax"):
        if field in value and (not _is_integer(value[field]) or value[field] < 0):
            _error(errors, f"{path}.{field}", f"{field} must be a non-negative integer.")
    if value.get("symmetric") is True and "toMax" in value:
        _error(errors, f"{path}.toMax", "Symmetric kinds cannot declare toMax.")


def _validate_kind_demand(value: Any, path: str, errors: list[Error]) -> None:
    if type(value) is not dict:
        _error(errors, path, "Expected a kind demand object.")
        return
    _unknown_keys(value, {"declared", "declaration"}, path, errors)
    if not value:
        _error(errors, path, "A kind demand must contain a clause.")
    if "declared" in value and value["declared"] is not True:
        _error(errors, f"{path}.declared", "declared must be literal true.")
    if "declaration" in value:
        _validate_kind_declaration(value["declaration"], f"{path}.declaration", errors)


def _validate_anchor(value: Any, path: str, errors: list[Error]) -> None:
    if not isinstance(value, str) or any(not _is_id(segment) for segment in value.split("/")):
        _error(errors, path, "Malformed anchor.")


def _validate_relation_demand(
    value: Any, path: str, errors: list[Error], profile_ids: set[str]
) -> None:
    if type(value) is not dict:
        _error(errors, path, "Expected a relation demand.")
        return
    _unknown_keys(value, {"at", "kind", "role", "atLeast", "atMost", "otherEndpoint"}, path, errors)
    _validate_anchor(value.get("at"), f"{path}.at", errors)
    if not _is_id(value.get("kind")):
        _error(errors, f"{path}.kind", "kind must be an id.")
    if "role" in value and value["role"] not in ("from", "to"):
        _error(errors, f"{path}.role", "role must be from or to.")
    if "atLeast" not in value and "atMost" not in value:
        _error(errors, path, "A relation demand needs atLeast or atMost.")
    lower, upper = value.get("atLeast"), value.get("atMost")
    if "atLeast" in value and (not _is_integer(lower) or lower < 1):
        _error(errors, f"{path}.atLeast", "atLeast must be an integer of at least one.")
    if "atMost" in value and (not _is_integer(upper) or upper < 0):
        _error(errors, f"{path}.atMost", "atMost must be a non-negative integer.")
    if _is_integer(lower) and _is_integer(upper) and lower > upper:
        _error(errors, f"{path}.atLeast", "atLeast cannot exceed atMost.")
    if "otherEndpoint" in value:
        endpoint = value["otherEndpoint"]
        endpoint_path = f"{path}.otherEndpoint"
        if type(endpoint) is not dict:
            _error(errors, endpoint_path, "Expected an endpoint filter.")
        else:
            _unknown_keys(endpoint, {"prefix", "conformsTo"}, endpoint_path, errors)
            if not endpoint:
                _error(errors, endpoint_path, "An endpoint filter must contain a clause.")
            if "prefix" in endpoint:
                _validate_anchor(endpoint["prefix"], f"{endpoint_path}.prefix", errors)
            if "conformsTo" in endpoint:
                target = endpoint["conformsTo"]
                if not _is_id(target) or target not in profile_ids:
                    _error(errors, f"{endpoint_path}.conformsTo", "Profile reference does not resolve.")


def _validate_scene_profile(
    value: Any, path: str, errors: list[Error], profile_ids: set[str]
) -> None:
    if type(value) is not dict:
        _error(errors, path, "Expected a scene profile object.")
        return
    _unknown_keys(value, {"bodies", "kinds", "relations", "forAllBodies", "forbidsRelations"}, path, errors)
    if "bodies" in value:
        bodies = _validate_id_map(value["bodies"], f"{path}.bodies", errors)
        for name, demand in bodies.items():
            _validate_body_demand(demand, f"{path}.bodies.{name}", errors, profile_ids)
    if "kinds" in value:
        kinds = _validate_id_map(value["kinds"], f"{path}.kinds", errors)
        for kind, demand in kinds.items():
            _validate_kind_demand(demand, f"{path}.kinds.{kind}", errors)
    if "relations" in value:
        relations = value["relations"]
        if type(relations) is not list or not relations:
            _error(errors, f"{path}.relations", "relations must be a non-empty array.")
        else:
            for index, demand in enumerate(relations):
                _validate_relation_demand(demand, f"{path}.relations.{index}", errors, profile_ids)
    if "forAllBodies" in value:
        checks = value["forAllBodies"]
        if type(checks) is not list or not checks:
            _error(errors, f"{path}.forAllBodies", "forAllBodies must be a non-empty array.")
        else:
            for index, entry in enumerate(checks):
                entry_path = f"{path}.forAllBodies.{index}"
                if type(entry) is not dict:
                    _error(errors, entry_path, "Expected a universal body check.")
                    continue
                _unknown_keys(entry, {"excluding", "check"}, entry_path, errors)
                if "excluding" in entry:
                    excluding = entry["excluding"]
                    if type(excluding) is not list or not excluding:
                        _error(errors, f"{entry_path}.excluding", "excluding must be a non-empty id array.")
                    else:
                        for item_index, name in enumerate(excluding):
                            if not _is_id(name):
                                _error(errors, f"{entry_path}.excluding.{item_index}", "Invalid body name.")
                if "check" not in entry:
                    _error(errors, f"{entry_path}.check", "Missing body check.")
                else:
                    _validate_body_demand(entry["check"], f"{entry_path}.check", errors, profile_ids)
    if "forbidsRelations" in value:
        bans = value["forbidsRelations"]
        if type(bans) is not list or not bans:
            _error(errors, f"{path}.forbidsRelations", "forbidsRelations must be a non-empty array.")
        else:
            for index, ban in enumerate(bans):
                ban_path = f"{path}.forbidsRelations.{index}"
                if type(ban) is not dict:
                    _error(errors, ban_path, "Expected a relation ban.")
                    continue
                _unknown_keys(ban, {"kind", "at"}, ban_path, errors)
                if not _is_id(ban.get("kind")):
                    _error(errors, f"{ban_path}.kind", "kind must be an id.")
                if "at" in ban:
                    _validate_anchor(ban["at"], f"{ban_path}.at", errors)


def validate_scene_profiles(document: Any) -> list[Error]:
    """Return all structural errors for a papermold/v2 scene-profile document."""

    errors: list[Error] = []
    checked = _validate_profiles_envelope(
        document,
        "papermold/v2",
        {"protocol", "profiles", "sceneProfiles"},
        errors,
    )
    profiles = checked.get("profiles") if type(checked) is dict else None
    profile_ids = {key for key in profiles if _is_id(key)} if type(profiles) is dict else set()
    scene_profiles = _validate_id_map(
        checked.get("sceneProfiles", _MISSING) if type(checked) is dict else _MISSING,
        "$.sceneProfiles",
        errors,
    )
    for profile_id, profile in scene_profiles.items():
        _validate_scene_profile(profile, f"$.sceneProfiles.{profile_id}", errors, profile_ids)
    return errors


def _matches(token: dict[str, Any], element: dict[str, Any]) -> bool:
    return token["kind"] == element["kind"] and (
        "type" not in token or token["type"] == element.get("type", _MISSING)
    )


def _admits_at_least(accepts: list[dict[str, Any]], demand: dict[str, Any]) -> bool:
    return any(
        accepted["kind"] == demand["kind"]
        and ("type" not in accepted or accepted["type"] == demand.get("type", _MISSING))
        for accepted in accepts
    )


def _judge_vessel_demand(
    body_value: dict[str, Any],
    vessel_id: str,
    demand: dict[str, Any],
    path: str,
    document: dict[str, Any],
    memo: dict[tuple[int, str], list[Error]],
) -> list[Error]:
    vessel = body_value["vessels"].get(vessel_id)
    if vessel is None:
        return [{"path": path, "message": f'Body has no vessel "{vessel_id}".'}]
    errors: list[Error] = []
    if "ports" in demand:
        actual_ports = vessel.get("ports", {})
        for side, wanted in demand["ports"].items():
            if actual_ports.get(side) != wanted:
                _error(
                    errors,
                    f"{path}.ports.{side}",
                    f'Body vessel "{vessel_id}" does not have the demanded port on {side}.',
                )
    if "acceptsAtLeast" in demand and "accepts" in vessel:
        for index, token in enumerate(demand["acceptsAtLeast"]):
            if not _admits_at_least(vessel["accepts"], token):
                _error(
                    errors,
                    f"{path}.acceptsAtLeast.{index}",
                    f'Body vessel "{vessel_id}" does not admit the demanded token.',
                )
    contains = vessel.get("contains", [])
    if "containsAtLeast" in demand:
        for index, token in enumerate(demand["containsAtLeast"]):
            if not any(_matches(token, element) for element in contains):
                _error(
                    errors,
                    f"{path}.containsAtLeast.{index}",
                    f'Body vessel "{vessel_id}" contains no matching element.',
                )
    if "forbids" in demand:
        for index, token in enumerate(demand["forbids"]):
            if any(_matches(token, element) for element in contains):
                _error(
                    errors,
                    f"{path}.forbids.{index}",
                    f'Body vessel "{vessel_id}" contains a forbidden element.',
                )
    if "conformsTo" in demand:
        recursive = demand["conformsTo"]
        satisfied = any(
            _matches(recursive["token"], element)
            and "body" in element
            and not _judge_profile(element["body"], document, recursive["profile"], memo)
            for element in contains
        )
        if not satisfied:
            _error(
                errors,
                f"{path}.conformsTo",
                f'Body vessel "{vessel_id}" contains no matching conforming body.',
            )
    return errors


def _judge_profile(
    body_value: dict[str, Any],
    document: dict[str, Any],
    profile_id: str,
    memo: dict[tuple[int, str], list[Error]],
) -> list[Error]:
    key = (id(body_value), profile_id)
    cached = memo.get(key)
    if cached is not None:
        return cached
    profile = document["profiles"][profile_id]
    errors: list[Error] = []
    # Store before descent. Valid finite JSON cannot return to this same body,
    # but the early entry also prevents accidental blowups for aliased inputs.
    memo[key] = errors
    for vessel_id, demand in profile.get("vessels", {}).items():
        errors.extend(
            _judge_vessel_demand(
                body_value,
                vessel_id,
                demand,
                f"$.profiles.{profile_id}.vessels.{vessel_id}",
                document,
                memo,
            )
        )
    if "atLeast" in profile:
        threshold = profile["atLeast"]
        passed = 0
        for index, check in enumerate(threshold["of"]):
            candidate_errors = _judge_vessel_demand(
                body_value,
                check["vessel"],
                check["check"],
                f"$.profiles.{profile_id}.atLeast.of.{index}.check",
                document,
                memo,
            )
            if not candidate_errors:
                passed += 1
        if passed < threshold["n"]:
            _error(
                errors,
                f"$.profiles.{profile_id}.atLeast",
                f"Only {passed} of {len(threshold['of'])} checks passed; "
                f"the profile requires at least {threshold['n']}.",
            )
    return errors


def _raise_invalid(label: str, errors: list[Any]) -> None:
    if errors:
        rendered = ", ".join(
            error["path"] if type(error) is dict else str(error) for error in errors
        )
        raise ValueError(f"invalid {label}: {rendered}")


def _validate_body_domain(body_value: Any) -> None:
    _raise_invalid(
        "paper-doll body",
        validate_document({"protocol": "paper-doll/v3", "body": body_value}),
    )


def judge(body_value: Any, document: Any, profile_id: Any) -> list[Error]:
    """Judge a valid body against a named papermold/v1 profile."""

    _validate_body_domain(body_value)
    _raise_invalid("papermold/v1 document", validate_profiles(document))
    if not isinstance(profile_id, str) or profile_id not in document["profiles"]:
        raise ValueError(f"unknown profile id: {profile_id!r}")
    return _judge_profile(body_value, document, profile_id, {})


def conforms(body_value: Any, document: Any, profile_id: Any) -> bool:
    """Return whether a valid body conforms to a named v1 profile."""

    return not judge(body_value, document, profile_id)


def judge_body(body_value: Any, document: Any, profile_id: Any) -> list[Error]:
    """Judge a valid body against the body-profile namespace of a v2 document."""

    _validate_body_domain(body_value)
    _raise_invalid("papermold/v2 document", validate_scene_profiles(document))
    if not isinstance(profile_id, str) or profile_id not in document["profiles"]:
        raise ValueError(f"unknown profile id: {profile_id!r}")
    return _judge_profile(body_value, document, profile_id, {})


def conforms_body(body_value: Any, document: Any, profile_id: Any) -> bool:
    """Return whether a valid body conforms to a v2 document's body profile."""

    return not judge_body(body_value, document, profile_id)


def _resolve_anchor(scene_value: dict[str, Any], anchor: str) -> bool:
    segments = anchor.split("/")
    current_body = scene_value["bodies"].get(segments[0])
    if current_body is None:
        return False
    if len(segments) == 1:
        return True
    cursor = 1
    while True:
        vessel = current_body["vessels"].get(segments[cursor])
        if vessel is None:
            return False
        if cursor == len(segments) - 1:
            return True
        element_id = segments[cursor + 1]
        element = next(
            (item for item in vessel.get("contains", []) if item.get("id") == element_id),
            None,
        )
        if element is None:
            return False
        if cursor + 1 == len(segments) - 1:
            return True
        current_body = element.get("body")
        if current_body is None:
            return False
        cursor += 2


def _under(endpoint: str, anchor: str) -> bool:
    return endpoint == anchor or endpoint.startswith(anchor + "/")


def _body_conforms(
    body_value: dict[str, Any],
    document: dict[str, Any],
    profile_id: str,
    memo: dict[tuple[int, str], list[Error]],
) -> bool:
    return not _judge_profile(body_value, document, profile_id, memo)


def _scene_body_demand_passes(
    body_value: dict[str, Any],
    demand: dict[str, Any],
    document: dict[str, Any],
    memo: dict[tuple[int, str], list[Error]],
) -> bool:
    return "conformsTo" not in demand or _body_conforms(
        body_value, document, demand["conformsTo"], memo
    )


def _endpoint_filter_passes(
    endpoint: str,
    endpoint_filter: dict[str, Any] | None,
    scene_value: dict[str, Any],
    document: dict[str, Any],
    memo: dict[tuple[int, str], list[Error]],
) -> bool:
    if endpoint_filter is None:
        return True
    if "prefix" in endpoint_filter and not _under(endpoint, endpoint_filter["prefix"]):
        return False
    if "conformsTo" in endpoint_filter:
        body_name = endpoint.split("/", 1)[0]
        body_value = scene_value["bodies"].get(body_name)
        if body_value is None or not _body_conforms(
            body_value, document, endpoint_filter["conformsTo"], memo
        ):
            return False
    return True


def _relation_matches_demand(
    relation: dict[str, Any],
    demand: dict[str, Any],
    scene_value: dict[str, Any],
    document: dict[str, Any],
    memo: dict[tuple[int, str], list[Error]],
) -> bool:
    if relation["kind"] != demand["kind"]:
        return False
    declaration = scene_value["kinds"].get(relation["kind"], {})
    symmetric = declaration.get("symmetric") is True
    if symmetric or "role" not in demand:
        assignments = (
            (relation["from"], relation["to"]),
            (relation["to"], relation["from"]),
        )
    elif demand["role"] == "from":
        assignments = ((relation["from"], relation["to"]),)
    else:
        assignments = ((relation["to"], relation["from"]),)
    endpoint_filter = demand.get("otherEndpoint")
    return any(
        _under(anchored, demand["at"])
        and _endpoint_filter_passes(other, endpoint_filter, scene_value, document, memo)
        for anchored, other in assignments
    )


def _judge_scene_profile(
    scene_value: dict[str, Any],
    document: dict[str, Any],
    scene_profile_id: str,
    memo: dict[tuple[int, str], list[Error]],
) -> list[Error]:
    profile = document["sceneProfiles"][scene_profile_id]
    prefix = f"$.sceneProfiles.{scene_profile_id}"
    errors: list[Error] = []

    for body_name, demand in profile.get("bodies", {}).items():
        path = f"{prefix}.bodies.{body_name}"
        body_value = scene_value["bodies"].get(body_name)
        if body_value is None:
            _error(errors, path, f'Scene has no body "{body_name}".')
        elif "conformsTo" in demand and not _scene_body_demand_passes(
            body_value, demand, document, memo
        ):
            _error(
                errors,
                f"{path}.conformsTo",
                f'Body "{body_name}" does not conform to profile "{demand["conformsTo"]}".',
            )

    for kind, demand in profile.get("kinds", {}).items():
        path = f"{prefix}.kinds.{kind}"
        actual = scene_value["kinds"].get(kind)
        if actual is None:
            _error(errors, path, f'Scene declares no kind "{kind}".')
            continue
        for field, wanted in demand.get("declaration", {}).items():
            if field in ("symmetric", "irreflexive"):
                matches = actual.get(field, False) == wanted
            else:
                matches = field in actual and actual[field] == wanted
            if not matches:
                _error(
                    errors,
                    f"{path}.declaration.{field}",
                    f'Kind "{kind}" does not have the demanded {field} declaration.',
                )

    for index, demand in enumerate(profile.get("relations", [])):
        path = f"{prefix}.relations.{index}"
        if not _resolve_anchor(scene_value, demand["at"]):
            _error(errors, path, f'Anchor "{demand["at"]}" does not resolve in the scene.')
            continue
        count = sum(
            _relation_matches_demand(relation, demand, scene_value, document, memo)
            for relation in scene_value["relations"]
        )
        if "atLeast" in demand and count < demand["atLeast"]:
            _error(
                errors,
                f"{path}.atLeast",
                f"Only {count} relations matched; at least {demand['atLeast']} are required.",
            )
        if "atMost" in demand and count > demand["atMost"]:
            _error(
                errors,
                f"{path}.atMost",
                f"{count} relations matched; at most {demand['atMost']} are allowed.",
            )

    for index, universal in enumerate(profile.get("forAllBodies", [])):
        path = f"{prefix}.forAllBodies.{index}.check"
        excluded = set(universal.get("excluding", []))
        demand = universal["check"]
        if "conformsTo" not in demand:
            continue  # exists:true is vacuous over bodies already in the quantifier.
        for body_name in sorted(scene_value["bodies"]):
            if body_name in excluded:
                continue
            if not _scene_body_demand_passes(
                scene_value["bodies"][body_name], demand, document, memo
            ):
                _error(
                    errors,
                    f"{path}.conformsTo",
                    f'Body "{body_name}" does not conform to profile "{demand["conformsTo"]}".',
                )

    for index, ban in enumerate(profile.get("forbidsRelations", [])):
        witnesses = [
            relation
            for relation in scene_value["relations"]
            if relation["kind"] == ban["kind"]
            and (
                "at" not in ban
                or _under(relation["from"], ban["at"])
                or _under(relation["to"], ban["at"])
            )
        ]
        if witnesses:
            _error(
                errors,
                f"{prefix}.forbidsRelations.{index}",
                f'{len(witnesses)} forbidden "{ban["kind"]}" relations exist.',
            )
    return errors


def judge_scene(scene_value: Any, document: Any, scene_profile_id: Any) -> list[Error]:
    """Judge a valid paperchain scene against a named v2 scene profile."""

    _raise_invalid("paperchain scene", validate_scene(scene_value))
    _raise_invalid("papermold/v2 document", validate_scene_profiles(document))
    if (
        not isinstance(scene_profile_id, str)
        or scene_profile_id not in document["sceneProfiles"]
    ):
        raise ValueError(f"unknown scene profile id: {scene_profile_id!r}")
    return _judge_scene_profile(scene_value, document, scene_profile_id, {})


def conforms_scene(scene_value: Any, document: Any, scene_profile_id: Any) -> bool:
    """Return whether a valid scene conforms to a named v2 scene profile."""

    return not judge_scene(scene_value, document, scene_profile_id)


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Execute one corpus-v2 Mold case and return its language-neutral projection."""

    if type(case) is not dict or type(case.get("input")) is not dict:
        raise ValueError("case and case input must be objects")
    args = case["input"].get("args")
    if type(args) is not list:
        raise ValueError("case input must contain an args array")
    subject = case.get("subject")
    operation = case.get("operation")
    domains: dict[str, dict[str, tuple[Any, str]]] = {
        "papermold/v1": {
            "validateProfiles": (validate_profiles, "validate"),
            "judge": (judge, "judge"),
            "conforms": (conforms, "value"),
        },
        "papermold/v2": {
            "validateSceneProfiles": (validate_scene_profiles, "validate"),
            "judgeBody": (judge_body, "judge"),
            "conformsBody": (conforms_body, "value"),
            "judgeScene": (judge_scene, "judge"),
            "conformsScene": (conforms_scene, "value"),
        },
    }
    if subject not in domains or operation not in domains[subject]:
        raise ValueError(f"unsupported subject/operation: {subject!r}/{operation!r}")
    function, projection = domains[subject][operation]
    try:
        result = function(*args)
    except (TypeError, ValueError):
        return {"outcome": "error"}
    if projection == "validate":
        return (
            {"outcome": "invalid", "errorPaths": [error["path"] for error in result]}
            if result
            else {"outcome": "valid"}
        )
    if projection == "judge":
        return (
            {"outcome": "nonconforming", "errorPaths": [error["path"] for error in result]}
            if result
            else {"outcome": "conforms"}
        )
    return {"outcome": "ok", "value": result}
