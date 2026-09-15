# paperchain

`paperchain` is a small TypeScript protocol library for scenes: flat, typed, geometry-free relations between addresses across [paperdoll](https://github.com/urcades/paperdoll) bodies.

paperdoll has two edge types, both hierarchical and both geometric: connection (ports) and containment (`contains` / `element.body`). paperchain adds the third and final edge type — **relations**. The motivating specimen is two humans holding hands: neither hand contains the other, and a port connection would be *wrong*, not just awkward, because connections drag geometry with them. Holding hands needs an edge with no geometric consequences.

It has one runtime dependency (`paperdoll`, the kernel it relates) and does not interpret semantics. `holds` means nothing to paperchain; kinds are declared in the document with their laws, and the protocol validates declared structure only.

## Install

```sh
npm install paperchain
```

## Minimal Document

```ts
import { PAPERCHAIN_PROTOCOL, parseScene, relationsAt } from "paperchain";

const scene = {
  protocol: PAPERCHAIN_PROTOCOL,
  bodies: {
    alice: {
      root: "torso",
      vessels: {
        torso: { ports: { left: { vessel: "left-hand", side: "right" } } },
        "left-hand": { ports: { right: { vessel: "torso", side: "left" } } }
      }
    },
    bob: {
      root: "torso",
      vessels: {
        torso: { ports: { right: { vessel: "right-hand", side: "left" } } },
        "right-hand": { ports: { left: { vessel: "torso", side: "right" } } }
      }
    }
  },
  kinds: {
    "holding-hands": { symmetric: true, fromMax: 1 }
  },
  relations: [
    { kind: "holding-hands", from: "alice/left-hand", to: "bob/right-hand" }
  ]
};

const parsed = parseScene(scene);
if (!parsed.ok) throw new Error(parsed.errors[0].message);

console.log(relationsAt(parsed.value, "bob/right-hand"));
// [{ kind: "holding-hands", from: "alice/left-hand", to: "bob/right-hand" }]
```

## The Model

A **scene** is paperchain's document: named paperdoll bodies embedded by value, a set of declared relation **kinds**, and a flat table of **relations**. A scene is self-contained — "every endpoint resolves" is checkable with nothing else in hand, offline, in any language.

A relation endpoint is a **scene address**: `<bodyName>/<paper-doll-v3-address>`. The first segment names a body in `bodies`; the remainder is resolved *within* that body by paperdoll's address grammar, so endpoints may be vessels or id-bearing elements at any nesting depth (`bob/back/field-pack/main-pocket/rope`). A bare body name is not an endpoint — an address must reach at least a vessel.

Kinds carry their laws as declarations, exactly as `accepts` declares compatibility in paperdoll:

- `symmetric` — `holding-hands(a, b)` ≡ `holding-hands(b, a)`: one unordered relation.
- `irreflexive` — `from` and `to` must differ. Per-kind, never global: you *can* hold your own hand.
- `fromMax` / `toMax` — multiplicity budgets: "a hand holds at most one thing." Symmetric kinds use `fromMax` as the per-endpoint budget (participation in either position counts); declaring `toMax` on a symmetric kind is itself invalid.

## Laws

Scene validity is the conjunction of seven laws, with all violations collected and path-annotated (`$.relations.3.from`):

1. **Structure** — strict shapes, known keys only, valid lowercase ids, exact protocol string.
2. **Body validity** — every body in `bodies` is paper-doll/v3-valid, judged by the kernel itself; error paths are prefixed `$.bodies.<name>`.
3. **Declared kinds** — every `relation.kind` exists in `kinds`.
4. **Existence** — every endpoint resolves: the body exists and the remainder resolves via paperdoll's `resolveAddress`.
5. **Irreflexivity** — when declared on the kind, `from !== to`.
6. **No duplicates** — relation identity is `(kind, from, to)`; symmetric kinds canonicalize the endpoint pair, so reversed duplicates are equally invalid.
7. **Multiplicity** — when declared, no endpoint exceeds its `fromMax` / `toMax` budget for that kind.

Dangling relations are invalid, strictly: deleting a body out from under a relation does not auto-drop the relation, it invalidates the scene. Cleanup travels in the same transaction as the structural change — the rope drops when the arm is severed, as part of the severing.

## What paperchain deliberately does not do

Containment-shaped relations dissolve into paperdoll recursion. Trading needs a desk — a third *body* with escrow vessels — and zero relations; likewise chests, mounts-as-saddle-containment, docking-as-hangar. And there are no state-vetoes: no relation law inspects body contents ("may only grapple with a free hand" is consumer judgment, including a [papermold](https://github.com/urcades/papermold) profile). paperchain validates structure: existence, multiplicity, symmetry, irreflexivity. Nothing else.

## Editing Scenes

All operations return new scenes and never mutate their inputs. Destructive operations return what they destroyed, so every edit can be undone without diffing:

```ts
import { addRelation, declareKind, deleteBody, insertBody, removeRelation } from "paperchain";

const guarded = declareKind(scene, "guards", { irreflexive: true });
const linked = addRelation(guarded, { kind: "guards", from: "alice/torso", to: "bob/torso" });

const { scene: unlinked, relation } = removeRelation(linked, {
  kind: "guards", from: "alice/torso", to: "bob/torso"
});
// relation: the removed relation exactly as stored (symmetric kinds match either order)

const { scene: smaller, body } = deleteBody(unlinked, "bob");
// body: the deleted paperdoll body, ready to re-insert

const { scene: fewer, declaration } = deleteKind(unlinked, "guards");
// declaration: the destroyed kind declaration; throws while relations still use it
```

Operations enforce the local laws (declared kinds, existence, irreflexivity, duplicates, multiplicity, no dangling endpoints) and throw with precise messages. They do not re-validate whole bodies — global validity stays a `validateScene` concern, mirroring the kernel's local/global law split. `deleteBody` throws while any relation endpoint enters the body: remove relations first, in the same transaction.

## The paper* family

- [`paperdoll`](https://github.com/urcades/paperdoll) — the kernel: bodies, vessels, containment, connection, the address grammar (law 8 is what makes scene addresses possible).
- [`paperchain`](https://github.com/urcades/paperchain) — this library: relations between addresses across bodies.
- [`paperfold`](https://github.com/urcades/paperfold) — dynamics: transactional patches over bodies (`paperfold/v1`) and complete scenes (`paperfold/v2`).
- [`papermold`](https://github.com/urcades/papermold) — judgment: profiles and structural conformance ("is this really mech-shaped?").

## Portability

The protocol is the document format plus the laws in the current normative [`paperchain/v1 specification`](docs/spec.md). [`schema/paperchain-v1.schema.json`](schema/paperchain-v1.schema.json) is its structural JSON Schema (2020-12) companion, not a complete specification. Package versions and dependency floors are listed in the [`paper* family compatibility matrix`](https://github.com/urcades/paperdoll/blob/main/docs/family-compatibility.md). Any language can validate paperchain scenes.

The optional [`paper-json-portable/v1` profile](docs/spec.md#portable-json) limits integral binary64 values, including multiplicity budgets and opaque nested data, to `±9007199254740991`. `validatePortableJson` checks that independent second verdict; larger exact integers should use canonical decimal strings under an application field contract.

## API

- constants: `PAPERCHAIN_PROTOCOL`, `MAX_PORTABLE_INTEGER` (re-exported from paperdoll)
- validation: `parseScene`, `assertScene`, `validateScene`, `validatePortableJson`, `formatProtocolErrors` (portable helpers re-exported from paperdoll)
- addressing: `parseSceneAddress`, `resolveSceneAddress`
- kind operations: `declareKind`, `deleteKind`
- body operations: `insertBody`, `deleteBody`
- relation operations: `addRelation`, `removeRelation`
- queries: `relationsAt`
- types: `Scene`, `Relation`, `KindDeclaration`, `SceneAddress`, `SplitSceneAddress`, `BodyName`, `KindId`, plus `Body`, `ProtocolError`, `ResolvedAddress`, and `Result` re-exported from paperdoll

Validation is strict: unknown keys anywhere in a scene are rejected, all errors are collected with paths, and `parseScene` returns a deep copy of its input. `ContainedElement.data` remains opaque — paperchain never reads it.

## Design Notes

See [`docs/spec.md`](docs/spec.md) for normative behavior. [`docs/rfc-paperchain.md`](docs/rfc-paperchain.md) is the historical pre-RFC that recorded the original design decisions.
