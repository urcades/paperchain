# paperchain/v1 — Specification

Status: current v1 protocol dialect
Depends on: paper-doll/v3 (the identity/addressing law)
Historical lineage: [`rfc-paperchain.md`](rfc-paperchain.md)

This document states the paperchain/v1 scene format and its laws precisely enough to reimplement in another language. The protocol is the document format plus the laws — not the TypeScript library.

## Normative status and operation domains
<a id="normative-status-and-operation-domains"></a>

This document is normative for `paperchain/v1`. The JSON Schema is a
structural companion; the RFC is a historical design record. Package and
dependency versions are listed in the
[`paper* family compatibility matrix`](https://github.com/urcades/paperdoll/blob/main/docs/family-compatibility.md).
The family-wide equality definitions are normative in the
[`paper-doll/v3` specification](https://github.com/urcades/paperdoll/blob/main/docs/spec.md#equality).

`validateScene` accepts any finite JSON value and returns `ProtocolError[]`;
`parseScene` accepts the same domain and returns a `Result` containing a deep
copy or validation errors. Invalid JSON values do not make either function
throw. `assertScene` throws on validation failure.

`parseSceneAddress` and `resolveSceneAddress` throw on malformed address
syntax. For well-formed syntax, `resolveSceneAddress` returns `null` when the
named body or inner address is missing. Scene and argument records supplied to
queries and edits are assumed to satisfy their public structural types; these
operations are not substitutes for `validateScene`/`parseScene` on external
JSON. Within that typed caller domain, scene edits and `relationsAt` throw on
the checked violations documented below. Out-of-domain structural argument
behavior is unspecified. These statements concern finite JSON values within
ordinary host memory, stack, execution, and cancellation limits; host resource
failure is not a protocol verdict.

## 1. The scene document

```jsonc
{
  "protocol": "paperchain/v1",
  "bodies": {
    "<bodyName>": { /* a paper-doll/v3 body, by value */ }
  },
  "kinds": {
    "<kindId>": {
      "symmetric": false,     // optional boolean
      "irreflexive": false,   // optional boolean
      "fromMax": 1,           // optional integer >= 0
      "toMax": 1              // optional integer >= 0; forbidden when symmetric
    }
  },
  "relations": [
    { "kind": "<kindId>", "from": "<sceneAddress>", "to": "<sceneAddress>" }
  ]
}
```

- All four top-level keys are required. An empty scene declares `"bodies": {}`, `"kinds": {}`, `"relations": []` explicitly.
- `bodyName` and `kindId` are lowercase ids matching paperdoll's id pattern: `^[a-z][a-z0-9-]*$`.
- Unknown keys are invalid at every level: the document, each kind declaration, each relation. Bodies inherit the kernel's own strictness.
- Bodies are embedded **by value** (pre-RFC decision 1). A scene is self-contained: every law below is checkable with nothing else in hand, offline, in any language.

## 2. Scene addresses

A scene address is:

```
<bodyName> "/" <paper-doll-v3-address>
```

- The first segment names a body in `bodies`. The remainder is a paper-doll/v3 address resolved *within* that body: a `/`-separated path of lowercase ids, alternating vessel and element segments, descending through `element.body`. The address grammar is defined once, in paperdoll (its law 8 plus grammar), never per-sibling — a scene address is exactly `bodyName` prefixed to the kernel grammar.
- Endpoints may therefore be vessels (`alice/left-hand`) or id-bearing elements at any nesting depth (`bob/back/field-pack/main-pocket/rope`).
- A bare `<bodyName>` is **not** a valid scene address: an endpoint must reach at least a vessel. Relations relate places within bodies, not bodies as wholes; "the whole body" has no single vessel-or-element referent, and admitting it would create a second, weaker endpoint sort.
- Scene addresses are canonical as strings: the grammar admits exactly one spelling of each path, so address equality is string equality.

## 3. Laws

Scene validity is the conjunction of the laws below. Validation collects **all** violations (no early exit except structural dead-ends, e.g. `relations` not being an array) and annotates each with a JSONPath-style path (`$.relations.3.from`).

<a id="law-1-structure"></a>
### Law 1 — Structure

The document is an object with exactly the four required keys; `protocol` is exactly `"paperchain/v1"`; `bodies` and `kinds` are objects keyed by lowercase ids; `relations` is an array of `{kind, from, to}` objects; kind declarations have only the four optional keys with the types given above; endpoints are strings in the scene-address grammar.

<a id="law-2-body-validity"></a>
### Law 2 — Body validity

Every body in `bodies` is a valid paper-doll/v3 body, judged by the kernel's own validator (wrap as `{protocol: "paper-doll/v3", body}` and delegate). Kernel error paths are re-rooted from `$.body...` to `$.bodies.<name>...`.

<a id="law-3-declared-kinds"></a>
### Law 3 — Declared kinds

Every `relation.kind` exists as a key in `kinds`. paperchain never interprets what a kind means.

<a id="law-4-existence"></a>
### Law 4 — Existence

Every endpoint resolves: its first segment names a body in `bodies`, and the remainder resolves within that body via the kernel's `resolveAddress` (returning a vessel or an element; `null` or a grammar error is a violation, reported with the endpoint string and body name). Existence is only checked against bodies that individually satisfy law 2 — a broken body already carries its own errors.

Corollary (pre-RFC decision 4): **dangling relations are invalid, strictly.** Deleting a vessel or body out from under a relation does not auto-drop the relation; it invalidates the scene. Cleanup travels in the same transaction as the structural change.

<a id="law-5-irreflexivity"></a>
### Law 5 — Irreflexivity (declarable)

When a relation's kind declares `"irreflexive": true`, `from !== to` (string equality of canonical addresses). Irreflexivity is per-kind, never a protocol axiom: you can hold your own hand.

<a id="law-6-no-duplicates"></a>
### Law 6 — No duplicates

Relation identity is the triple `(kind, from, to)`. For **symmetric** kinds, identity canonicalizes the endpoint pair: sort the two address strings lexicographically, so `(k, a, b)` and `(k, b, a)` are the same relation. Two relations with the same identity are invalid; the second and every later occurrence is reported, naming the index of the first.

This is the family definition of
[Paperchain relation equivalence](https://github.com/urcades/paperdoll/blob/main/docs/spec.md#equality):
symmetric endpoint orientation is ignored for duplicate detection and
`removeRelation` matching. The stored relation itself retains the orientation
in which it was added.

Asymmetric kinds do not canonicalize: `follows(a, b)` and `follows(b, a)` are distinct relations and may coexist.

<a id="law-7-multiplicity"></a>
### Law 7 — Multiplicity (declarable)

For an **asymmetric** kind `k` declaring `fromMax` (resp. `toMax`): the number of relations of kind `k` whose `from` (resp. `to`) equals a given endpoint is at most `fromMax` (resp. `toMax`).

For a **symmetric** kind: declaring `toMax` is itself a validation error — symmetric kinds use `fromMax` as the per-endpoint budget. An endpoint's participation in **either** position counts against `fromMax`. A reflexive symmetric relation (`from === to`, legal unless the kind is also irreflexive) counts twice against its endpoint's budget: both participations are real.

Laws 5 and 7, and law 6's symmetric pair-canonicalization, are evaluated only for relations whose kind declaration is itself structurally valid; a malformed declaration already carries its own error and cannot supply reliable symmetry. Law 6's exact-order duplicate detection still runs, treating the kind as asymmetric — two relations identical in `(kind, from, to)` are duplicates under any reading of the declaration.

## 4. Operations

The reference library exposes pure operations. All return new scenes and never mutate inputs; every destructive or overwriting operation returns what it destroyed, so callers can construct the inverse without diffing.

| Operation | Returns | Throws when |
|---|---|---|
| `declareKind(scene, kindId, declaration)` | `Scene` | kind id taken or invalid; declaration malformed (incl. `toMax` on symmetric) |
| `deleteKind(scene, kindId)` | `{ scene, declaration }` | kind undeclared; any relation uses it |
| `insertBody(scene, name, body)` | `Scene` | name taken or invalid; body not paper-doll/v3-valid (kernel errors, formatted) |
| `deleteBody(scene, name)` | `{ scene, body }` | body missing; **any** relation endpoint enters the body (remove relations first — same transaction) |
| `addRelation(scene, relation)` | `Scene` | laws 3–7 would be violated |
| `removeRelation(scene, relation)` | `{ scene, relation }` | no such relation (symmetric kinds match either order; the stored relation is returned) |
| `relationsAt(scene, sceneAddress)` | `Relation[]` (copies) | address malformed |

Operations enforce the **local** laws and throw with messages naming the offending thing; they do not re-validate whole bodies. Global validity stays a `validateScene` concern, mirroring the kernel's local/global law split — legitimate multi-step edits pass through globally incomplete states.

`relationsAt` matches the endpoint in either position of every relation, which is what makes it symmetric-aware: a symmetric relation stored as `(a, b)` is found from `b`.

## 5. Resolved micro-decisions

All resolved 2026-07-10, alongside the pre-RFC's five decisions:

1. **`fromMax` / `toMax`, not `from-max` / `to-max`.** The pre-RFC sketch used hyphenated keys; the shipped format uses camelCase. Family documents use single-token or camelCase keys — hyphens are for *values* in id position (kind ids, vessel ids, addresses), where they are part of the id grammar, not for structural key names.
2. **`toMax` on a symmetric kind is a validation error, not an ignored key.** A symmetric relation has no distinguished `to` position, so the declaration would be meaningless; the family's temperament is strict validation, never silent repair. Consequence: the pre-RFC sketch's `"holding-hands": { "symmetric": true, "from-max": 1, "to-max": 1 }` is, hardened, `{ "symmetric": true, "fromMax": 1 }`.
3. **A bare body name is not an endpoint.** An endpoint must reach at least a vessel. Bodies as wholes are not addressable referents in the kernel grammar, and admitting them would fork the endpoint sort in two.
4. **Relation identity is `(kind, from, to)` with symmetric pair-canonicalization by lexicographic sort of the address strings.** String sort is total, stable, and language-independent — any implementation canonicalizes identically.
5. **A reflexive symmetric relation counts twice against its endpoint's `fromMax`.** The endpoint genuinely occupies both positions; counting once would let `fromMax: 1` admit a self-relation plus nothing else ambiguously.
6. **All four top-level keys are required.** An empty relation table is a statement (see the trading non-example), not an omission.
7. **Laws 5 and 7, and law 6's symmetric canonicalization, are suspended for relations whose kind declaration is malformed.** The declaration's own error is reported; guessing at symmetry to force extra errors would report phantoms. Exact-order duplicate detection is not suspended: two relations identical in `(kind, from, to)` are duplicates under any reading of the declaration, so no guess is involved.
8. **Existence is checked only against individually-valid bodies.** Resolving addresses inside a structurally broken body is undefined; the body's law-2 errors stand in.

## 6. What paperchain/v1 does not do

- **No containment-shaped relations.** Anything expressible as "X is in/on Y" is plain paperdoll (trading desks, chests, mounts, hangars) and dissolves into recursion. Cross-document movement is a consumer transaction or a future paperdoll deep-operation question — not paperchain's.
- **No state-vetoes** (pre-RFC decision 3). No relation law inspects body contents. Conditions like "may only grapple with a free hand" belong to consumers or to papermold profiles.
- **No semantics.** `holds` means nothing to paperchain. Kinds are validated structure, exactly as `accepts` tokens are in the kernel.
- **No law vocabulary beyond the four** (existence, multiplicity, symmetry, irreflexivity). Transitivity, endpoint type-guards, and the rest wait for a consumer to demand them (pre-RFC decision 2).
- **No auto-repair.** No relation is ever dropped, rewritten, or canonically reordered on the document's behalf.
- **No geometry.** Relations never participate in layout, planarity, or collision. That is the entire point.

## 7. paperfold scene patches

`paperfold/v2` now targets complete paperchain scenes. A patch that severs
Alice's arm can carry removal of a relation touching that arm in the same
transaction, and final scene validation enforces strict dangling. See the
current [`paperfold` specification](https://github.com/urcades/paperfold/blob/main/docs/spec.md#paperfold-v2-scene-patches).
