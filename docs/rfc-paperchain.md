# RFC: paperchain — The Third Edge Type

Status: pre-RFC (decisions recorded 2026-07-10; drafting precedes any implementation)
Depends on: paper-doll/v3 (the identity/addressing law — see `rfc-vessel-calculus.md`)
Relates to: `design-gamecraft-consumer.md`

## Definition

paperdoll has two edge types, both hierarchical and both geometric: **connection** (ports; carries laws 3–4 — opposite faces, one shared planar embedding) and **containment** (`contains` / `element.body`; carries laws 6–7). paperchain adds the third and final edge type: **relations** — flat, typed, geometry-free, cross-cutting edges between vessel and element addresses.

The specimen that motivates it: two humans holding hands. Neither hand contains the other, and a port connection would be *wrong*, not just awkward — connections drag geometry with them, so connected bodies would be fused into one collision-checked planar figure. Holding hands needs an edge with no geometric consequences. That edge is a relation.

Relations also solve the aliasing problem that got embedding-by-reference exiled from paper-doll/v2: if Alice mounts a horse by becoming an element in its saddle vessel, she now exists in two documents — duplicated state. `mounted(alice, horse/saddle)` keeps her in exactly one place and points.

## What paperchain deliberately does not do

**Containment-shaped relations dissolve into paperdoll recursion and are out of scope.** The canonical example (Edouard's): trading. Alice and Bob exchange items via a trading desk — a third *body* with escrow vessels (`accepts` for what's tradeable, sealed vessels for locked-in offers). The desk can be an imaginary object or a literal in-game object; either way it is plain paperdoll. Likewise chests, mounts-as-saddle-containment, docking-as-hangar. Anything expressible as "X is in/on Y" needs zero paperchain.

Two consequences worth recording:

- Cross-document movement (Alice's hand → the desk) is either two operations on two documents with the consumer owning transactionality, or — if the *world itself is a body* containing characters as elements — a single-document operation that requires **deep operations** (ops that reach through `element.body` boundaries via v3 deep addresses). Deep operations are a paperdoll v3.x question, not a paperchain one.
- **State-conditions on relations are out of scope** (see decision 3).

## The scene document

A scene is paperchain's document format — the thing its validator judges, parallel to paperdoll's `{protocol, body}`:

```jsonc
{
  "protocol": "paperchain/v1",
  "bodies": {
    "alice": { "root": "...", "vessels": { } },
    "bob":   { "root": "...", "vessels": { } }
  },
  "kinds": {
    "holds":         { "symmetric": false, "from-max": 1 },
    "holding-hands": { "symmetric": true, "from-max": 1, "to-max": 1 }
  },
  "relations": [
    { "kind": "holding-hands", "from": "alice/left-hand", "to": "bob/right-hand" }
  ]
}
```

Relation kinds are *declared in the document* with their laws, exactly as `accepts` declares compatibility in paperdoll: the protocol validates declared structure and never interprets semantics. `holds` means nothing to paperchain.

## Decisions

Five hard decisions, all resolved 2026-07-10:

### 1. Bodies are embedded by value, not referenced

The scene *contains* its bodies. A scene is therefore self-contained: "every endpoint address resolves" is checkable with nothing else in hand, offline, in any language. This is the by-value discipline the whole family runs on. The rejected alternative — scenes as thin overlays referencing bodies the validator cannot see — makes validity conditional ("valid relative to bindings") and reopens the aliasing swamp v2 exiled. Consequences accepted knowingly: the scene becomes the source of truth for the bodies it holds, and a future paperfold must be able to target scenes, not only bare bodies. Consumers wanting overlay-style ephemeral scenes can assemble and discard them.

### 2. The law vocabulary is closed at four

- **Existence** (mandatory, the base law): every endpoint address resolves within `bodies`, recursing through `element.body`. This is what makes paper-doll/v3 a hard prerequisite — the address grammar must be defined once, in paperdoll, not per-sibling.
- **Multiplicity** (declarable): `from-max` / `to-max` per kind — "a hand holds at most one thing." Note this is the *easy* fragment of counting: relations at an endpoint are a linear scan, with none of the token-budget assignment problem recorded in paperdoll's capacity deferral. It does not reopen that trapdoor.
- **Symmetry** (declarable): `holding-hands(a,b)` ≡ `holding-hands(b,a)` — one unordered relation; vs. `holds`, where holder/held is meaningful.
- **Irreflexivity** (declarable): per-kind, never global — you *can* hold your own hand (right holds left), which is the taste test proving these must be declarations, not protocol axioms.

Transitivity, endpoint type-guards, and anything else waits for a consumer to demand it.

### 3. No state-vetoes

A veto is a relation law that inspects body *state*: "`grapples(x, y)` only if vessel `x` contains no two-handed weapon." Rejected, decisively:

- Scene validity would stop being a fact about the relation table and become a join across every body's contents — expensive, and every patch to any body could silently invalidate the scene.
- "What counts as an occupied hand" is unmistakably game semantics — the item-database slope the core ontology forbids.

Conditions on relations belong to consumers, or eventually to profiles ("may only grapple if conforming to `free-handed`"), where body-inspecting judgment machinery properly lives. paperchain validates structure: existence, multiplicity, symmetry, irreflexivity. Nothing else.

### 4. Dangling relations are invalid (strict)

When a vessel is deleted out from under a relation (a patch severs Alice's arm), the scene is **invalid** — relations do not auto-drop. Auto-dropping would give patch application side effects outside its target. Instead, the relation-cleanup travels *in the same transaction* as the structural change — which is also the mechanically honest model: the rope drops when the arm is severed, as part of the severing. This matches paperdoll's temperament (strict validation, no silent repair) and gives paperfold's transactional patches a real job.

### 5. paper-doll/v3 comes first

The address grammar (`alice/left-hand/steel-dagger`, recursing through `element.body`) is a shared dependency of paperchain and paperfold. It is designed once, in paperdoll, as law 8 plus the grammar — never per-sibling. paperchain drafting can proceed; paperchain implementation cannot start before v3 ships. (v3 shipped: paperdoll 0.8.0, 2026-07-10.)

## What this unlocks

All as *data with laws* — validatable in any language, diffable by a future paperfold-for-scenes, none of it expressible today without abusing geometry or going protocol-blind:

- **Physical entanglement**: holding hands, grappling, tethered-by-rope, leashes, chains, puppet strings, two ships docked (touching without merging).
- **Spatial-but-not-contained arrangement**: formations, squads, riding alongside.
- **Directed attention**: targeting, aggro, guarding, following.
- **Social and ownership overlays**: party membership, "this chest belongs to Bob," claims and bonds.

## Sequencing

1. paperdoll v2.x — destructive-operation symmetry-completion (API-only).
2. paperdoll v3 — law 8 + address grammar.
3. paperchain v1 — this document hardened into a full RFC: scene schema, the four laws, JSON Schema, reference validator.
4. paperfold — patches over bodies *and scenes* (decision 1 requires scene-targeting; decision 4 gives its transactions a job).
