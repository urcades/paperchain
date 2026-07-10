import { describe, expect, it } from "vitest";
import {
  addRelation,
  assertScene,
  declareKind,
  deleteBody,
  deleteKind,
  insertBody,
  parseScene,
  parseSceneAddress,
  relationsAt,
  removeRelation,
  resolveSceneAddress,
  validateScene,
  type Scene
} from "../src/paperchain";
import { HOLDING_HANDS_SCENE, TRADING_DESK_SCENE } from "./sample-scene";

function cloneScene(overrides: Partial<Scene> = {}): Scene {
  return {
    ...structuredClone(HOLDING_HANDS_SCENE),
    ...overrides
  };
}

function errorMessages(result: ReturnType<typeof parseScene>): string {
  return result.ok ? "" : result.errors.map((error) => error.message).join("\n");
}

function errorPaths(result: ReturnType<typeof parseScene>): string[] {
  return result.ok ? [] : result.errors.map((error) => error.path);
}

describe("paperchain protocol v1", () => {
  it("accepts the holding-hands sample scene", () => {
    const parsed = parseScene(HOLDING_HANDS_SCENE);
    expect(errorMessages(parsed)).toBe("");
    expect(parsed.ok).toBe(true);
  });

  it("accepts the trading-desk non-example: three bodies, zero relations", () => {
    // Trading dissolves into paperdoll recursion: the desk is a plain body
    // with escrow vessels. A scene may carry bodies and no relations at all.
    const parsed = parseScene(TRADING_DESK_SCENE);
    expect(errorMessages(parsed)).toBe("");
    expect(parsed.ok).toBe(true);
    expect(TRADING_DESK_SCENE.relations).toEqual([]);
  });

  it("rejects wrong protocol strings with a clear error", () => {
    const scene = cloneScene() as unknown as Record<string, unknown>;
    scene.protocol = "paperchain/v0";

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain('Expected "paperchain/v1"');
    expect(errorPaths(parsed)).toContain("$.protocol");
  });

  it("requires bodies, kinds, and relations", () => {
    const parsed = parseScene({ protocol: "paperchain/v1" });
    expect(parsed.ok).toBe(false);
    const messages = errorMessages(parsed);
    expect(messages).toContain("Bodies must be an object keyed by body name");
    expect(messages).toContain("Kinds must be an object keyed by kind id");
    expect(messages).toContain("Relations must be an array of relation objects");
  });

  it("rejects unknown keys at every level", () => {
    const scene = cloneScene() as unknown as Record<string, any>;
    scene.stage = "tavern";
    scene.kinds.holds.label = "Holding";
    scene.relations[0].weight = 3;

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    const messages = errorMessages(parsed);
    expect(messages).toContain('Unknown key "stage"');
    expect(messages).toContain('Unknown key "label"');
    expect(messages).toContain('Unknown key "weight"');
  });

  it("validates every body as paper-doll/v3 and prefixes error paths with $.bodies.<name>", () => {
    const scene = cloneScene();
    delete scene.bodies.alice!.vessels.torso!.ports?.left;

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain("Must be reciprocated");
    expect(errorPaths(parsed).some((path) => path.startsWith("$.bodies.alice.vessels"))).toBe(true);
  });

  it("rejects invalid body names", () => {
    const scene = cloneScene() as unknown as { bodies: Record<string, unknown> };
    scene.bodies["Alice Prime"] = structuredClone(HOLDING_HANDS_SCENE.bodies.alice);

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain("Body name must start with a lowercase letter");
  });

  it("law 3: rejects undeclared relation kinds", () => {
    const scene = cloneScene();
    scene.relations.push({ kind: "grapples", from: "alice/right-hand", to: "bob/left-hand" });

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain('Relation kind "grapples" is not declared in "kinds"');
    expect(errorPaths(parsed)).toContain("$.relations.1.kind");
  });

  it("law 4: rejects endpoints naming a missing body", () => {
    const scene = cloneScene();
    scene.relations[0]!.to = "carol/right-hand";

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain('Endpoint "carol/right-hand" names missing body "carol"');
    expect(errorPaths(parsed)).toContain("$.relations.0.to");
  });

  it("law 4: rejects endpoints that do not resolve within their body", () => {
    const scene = cloneScene();
    scene.relations[0]!.from = "alice/tail";
    scene.relations.push({ kind: "holds", from: "alice/left-hand/ghost-dagger", to: "bob/torso" });

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    const messages = errorMessages(parsed);
    expect(messages).toContain('Endpoint "alice/tail" does not resolve within body "alice"');
    expect(messages).toContain('Endpoint "alice/left-hand/ghost-dagger" does not resolve within body "alice"');
  });

  it("law 4: a bare body name is not an endpoint", () => {
    const scene = cloneScene();
    scene.relations[0]!.from = "alice";

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain("a bare body name does not reach a vessel");

    expect(() => parseSceneAddress("alice")).toThrow("does not reach a vessel");
  });

  it("law 4: malformed addresses get precise errors", () => {
    const scene = cloneScene();
    scene.relations[0]!.from = "Alice/Left Hand";
    (scene.relations[0] as unknown as Record<string, unknown>).to = 7;

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    const messages = errorMessages(parsed);
    expect(messages).toContain('"/"-separated lowercase ids');
    expect(messages).toContain("Relation endpoint must be a scene address string");
  });

  it("endpoints reach elements and nested embedded bodies", () => {
    const scene = cloneScene();
    scene.relations.push({
      kind: "holds",
      from: "alice/left-hand/steel-dagger",
      to: "bob/back/field-pack/main-pocket/rope"
    });

    const parsed = parseScene(scene);
    expect(errorMessages(parsed)).toBe("");
    expect(parsed.ok).toBe(true);

    const nested = resolveSceneAddress(scene, "bob/back/field-pack/main-pocket/rope");
    expect(nested).toMatchObject({ kind: "element", element: { id: "rope" } });
    expect(resolveSceneAddress(scene, "carol/left-hand")).toBeNull();
  });

  it("law 5: irreflexivity is per-kind and declared, never a protocol axiom", () => {
    // You *can* hold your own hand: "holds" is not irreflexive.
    const reflexive = cloneScene();
    reflexive.relations.push({ kind: "holds", from: "alice/right-hand", to: "alice/right-hand" });
    expect(parseScene(reflexive).ok).toBe(true);

    const guarded = cloneScene();
    guarded.kinds.guards = { irreflexive: true };
    guarded.relations.push({ kind: "guards", from: "bob/torso", to: "bob/torso" });

    const parsed = parseScene(guarded);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain('Kind "guards" is irreflexive; "bob/torso" cannot relate to itself');
  });

  it("law 6: exact duplicate relations are invalid", () => {
    const scene = cloneScene();
    scene.relations.push({ kind: "holding-hands", from: "alice/left-hand", to: "bob/right-hand" });

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain("Duplicate relation");
    expect(errorMessages(parsed)).toContain("already declared at $.relations.0");
  });

  it("law 6: symmetric kinds canonicalize the endpoint pair, so reversed duplicates are invalid", () => {
    const scene = cloneScene();
    scene.relations.push({ kind: "holding-hands", from: "bob/right-hand", to: "alice/left-hand" });

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain("Duplicate relation");

    // Asymmetric kinds do not canonicalize: both directions may coexist.
    const directed = cloneScene({ relations: [] });
    directed.kinds.follows = {};
    directed.relations = [
      { kind: "follows", from: "alice/torso", to: "bob/torso" },
      { kind: "follows", from: "bob/torso", to: "alice/torso" }
    ];
    expect(parseScene(directed).ok).toBe(true);
  });

  it("law 7: fromMax and toMax budget asymmetric kinds per endpoint and position", () => {
    const scene = cloneScene();
    scene.relations.push(
      { kind: "holds", from: "alice/left-hand", to: "bob/torso" },
      { kind: "holds", from: "alice/left-hand", to: "bob/back" }
    );

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain('Endpoint "alice/left-hand" is "from" in 2 "holds" relations; fromMax is 1');
    expect(errorPaths(parsed)).toContain("$.relations.2.from");

    const targeted = cloneScene({ relations: [] });
    targeted.kinds.targets = { toMax: 1 };
    targeted.relations = [
      { kind: "targets", from: "alice/torso", to: "bob/torso" },
      { kind: "targets", from: "alice/left-hand", to: "bob/torso" }
    ];
    const targetedParsed = parseScene(targeted);
    expect(targetedParsed.ok).toBe(false);
    expect(errorMessages(targetedParsed)).toContain('Endpoint "bob/torso" is "to" in 2 "targets" relations; toMax is 1');
  });

  it("law 7: symmetric kinds count participation in either position against fromMax", () => {
    const scene = cloneScene();
    // bob/right-hand already holds hands with alice/left-hand; appearing as
    // "from" in a second holding-hands relation exceeds its budget of 1.
    scene.relations.push({ kind: "holding-hands", from: "bob/right-hand", to: "bob/left-hand" });

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain(
      'Endpoint "bob/right-hand" participates in 2 "holding-hands" relations; fromMax is 1'
    );
  });

  it("declaring toMax on a symmetric kind is itself a validation error", () => {
    const scene = cloneScene();
    scene.kinds["holding-hands"] = { symmetric: true, fromMax: 1, toMax: 1 };

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    expect(errorMessages(parsed)).toContain("Symmetric kinds use fromMax as the per-endpoint budget");
    expect(errorPaths(parsed)).toContain("$.kinds.holding-hands.toMax");
  });

  it("kind declarations are strictly typed", () => {
    const scene = cloneScene() as unknown as { kinds: Record<string, unknown> };
    scene.kinds.holds = { symmetric: "yes", fromMax: -1 };
    scene.kinds.leads = { toMax: 1.5 };

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    const messages = errorMessages(parsed);
    expect(messages).toContain("symmetric must be a boolean");
    expect(messages).toContain("fromMax must be an integer >= 0");
    expect(messages).toContain("toMax must be an integer >= 0");
  });

  it("collects all errors instead of stopping at the first", () => {
    const scene = cloneScene();
    scene.kinds["holding-hands"] = { symmetric: true, toMax: 1 };
    scene.relations.push(
      { kind: "grapples", from: "alice/right-hand", to: "bob/left-hand" },
      { kind: "holds", from: "carol/hand", to: "alice" }
    );

    const parsed = parseScene(scene);
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.errors.length).toBeGreaterThanOrEqual(4);
    const paths = errorPaths(parsed);
    expect(paths).toContain("$.kinds.holding-hands.toMax");
    expect(paths).toContain("$.relations.1.kind");
    expect(paths).toContain("$.relations.2.from");
    expect(paths).toContain("$.relations.2.to");
  });

  it("parseScene returns a defensive copy of the input", () => {
    const input = structuredClone(HOLDING_HANDS_SCENE);
    const parsed = parseScene(input);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    input.relations[0]!.from = "bob/left-hand";
    input.bodies.alice!.vessels["left-hand"]!.contains = [];
    input.kinds.holds!.fromMax = 99;

    expect(parsed.value.relations[0]!.from).toBe("alice/left-hand");
    expect(parsed.value.bodies.alice!.vessels["left-hand"]!.contains).toEqual([
      { kind: "item", type: "weapon", id: "steel-dagger" }
    ]);
    expect(parsed.value.kinds.holds!.fromMax).toBe(1);
  });

  it("assertScene throws formatted, path-annotated errors", () => {
    const scene = cloneScene();
    scene.relations.push({ kind: "grapples", from: "alice/right-hand", to: "bob/left-hand" });

    expect(() => assertScene(scene)).toThrow('$.relations.1.kind: Relation kind "grapples" is not declared');
    expect(() => assertScene(HOLDING_HANDS_SCENE)).not.toThrow();
  });

  it("declareKind declares a kind and refuses collisions and invalid declarations", () => {
    const before = structuredClone(HOLDING_HANDS_SCENE);
    const next = declareKind(HOLDING_HANDS_SCENE, "guards", { irreflexive: true });

    expect(HOLDING_HANDS_SCENE).toEqual(before);
    expect(next.kinds.guards).toEqual({ irreflexive: true });
    expect(parseScene(next).ok).toBe(true);

    expect(() => declareKind(HOLDING_HANDS_SCENE, "holds")).toThrow('Kind "holds" is already declared');
    expect(() => declareKind(HOLDING_HANDS_SCENE, "Bad Kind")).toThrow("lowercase");
    expect(() => declareKind(HOLDING_HANDS_SCENE, "linked", { symmetric: true, toMax: 1 })).toThrow(
      "Symmetric kinds use fromMax as the per-endpoint budget"
    );
    expect(() =>
      declareKind(HOLDING_HANDS_SCENE, "linked", { fromMax: -2 } as never)
    ).toThrow("fromMax must be an integer >= 0");
  });

  it("deleteKind returns the destroyed declaration and protects kinds in use", () => {
    const before = structuredClone(HOLDING_HANDS_SCENE);
    const { scene: next, declaration } = deleteKind(HOLDING_HANDS_SCENE, "holds");

    expect(HOLDING_HANDS_SCENE).toEqual(before);
    expect(declaration).toEqual({ symmetric: false, fromMax: 1 });
    expect(next.kinds.holds).toBeUndefined();
    expect(parseScene(next).ok).toBe(true);

    // round-trip: re-declaring the returned declaration restores the scene
    expect(declareKind(next, "holds", declaration)).toEqual(HOLDING_HANDS_SCENE);

    expect(() => deleteKind(HOLDING_HANDS_SCENE, "holding-hands")).toThrow(
      'Cannot delete kind "holding-hands"; 1 relation(s) use it'
    );
    expect(() => deleteKind(HOLDING_HANDS_SCENE, "grapples")).toThrow('Kind "grapples" is not declared');
  });

  it("insertBody validates the body as paper-doll/v3 and refuses taken names", () => {
    const before = structuredClone(HOLDING_HANDS_SCENE);
    const horse = { root: "saddle", vessels: { saddle: { accepts: [{ kind: "rider" }] } } };
    const next = insertBody(HOLDING_HANDS_SCENE, "horse", horse);

    expect(HOLDING_HANDS_SCENE).toEqual(before);
    expect(next.bodies.horse).toEqual(horse);
    expect(parseScene(next).ok).toBe(true);

    expect(() => insertBody(HOLDING_HANDS_SCENE, "alice", horse)).toThrow('Body name "alice" is already used');
    expect(() => insertBody(HOLDING_HANDS_SCENE, "Horse", horse)).toThrow("lowercase");
    expect(() =>
      insertBody(HOLDING_HANDS_SCENE, "ghost", { root: "missing", vessels: {} })
    ).toThrow('$.bodies.ghost.root: Root vessel "missing" does not exist');
  });

  it("deleteBody refuses to strand relations: cleanup travels in the same transaction", () => {
    const before = structuredClone(HOLDING_HANDS_SCENE);

    // dangling protection: bob anchors the holding-hands relation
    expect(() => deleteBody(HOLDING_HANDS_SCENE, "bob")).toThrow(
      'Cannot delete body "bob"; 1 relation(s) have an endpoint in it'
    );
    expect(HOLDING_HANDS_SCENE).toEqual(before);

    // the remove-then-delete transaction succeeds
    const { scene: unlinked, relation } = removeRelation(HOLDING_HANDS_SCENE, HOLDING_HANDS_SCENE.relations[0]!);
    const { scene: without, body } = deleteBody(unlinked, "bob");
    expect(without.bodies.bob).toBeUndefined();
    expect(body).toEqual(HOLDING_HANDS_SCENE.bodies.bob);
    expect(parseScene(without).ok).toBe(true);

    // round-trip: what was destroyed is enough to rebuild the scene
    expect(addRelation(insertBody(without, "bob", body), relation)).toEqual(HOLDING_HANDS_SCENE);

    expect(() => deleteBody(HOLDING_HANDS_SCENE, "carol")).toThrow('Body "carol" does not exist');
  });

  it("addRelation appends immutably and checks every local law", () => {
    const before = structuredClone(HOLDING_HANDS_SCENE);
    const next = addRelation(HOLDING_HANDS_SCENE, { kind: "holds", from: "alice/right-hand", to: "bob/torso" });

    expect(HOLDING_HANDS_SCENE).toEqual(before);
    expect(next.relations).toHaveLength(2);
    expect(parseScene(next).ok).toBe(true);

    expect(() =>
      addRelation(HOLDING_HANDS_SCENE, { kind: "grapples", from: "alice/torso", to: "bob/torso" })
    ).toThrow('Relation kind "grapples" is not declared in "kinds"');
    expect(() =>
      addRelation(HOLDING_HANDS_SCENE, { kind: "holds", from: "carol/hand", to: "bob/torso" })
    ).toThrow('from endpoint "carol/hand" names missing body "carol"');
    expect(() =>
      addRelation(HOLDING_HANDS_SCENE, { kind: "holds", from: "alice/torso", to: "bob/tail" })
    ).toThrow('to endpoint "bob/tail" does not resolve within body "bob"');
    expect(() =>
      addRelation(HOLDING_HANDS_SCENE, { kind: "holds", from: "alice", to: "bob/torso" })
    ).toThrow("a bare body name does not reach a vessel");
  });

  it("addRelation enforces irreflexivity when declared", () => {
    const scene = declareKind(HOLDING_HANDS_SCENE, "guards", { irreflexive: true });
    expect(() => addRelation(scene, { kind: "guards", from: "bob/torso", to: "bob/torso" })).toThrow(
      'Kind "guards" is irreflexive; "bob/torso" cannot relate to itself'
    );
    // holding your own hand is fine when the kind does not declare it
    expect(parseScene(addRelation(scene, { kind: "holds", from: "alice/right-hand", to: "alice/right-hand" })).ok).toBe(
      true
    );
  });

  it("addRelation rejects duplicates, matching symmetric kinds in either order", () => {
    expect(() =>
      addRelation(HOLDING_HANDS_SCENE, { kind: "holding-hands", from: "alice/left-hand", to: "bob/right-hand" })
    ).toThrow("already exists");
    expect(() =>
      addRelation(HOLDING_HANDS_SCENE, { kind: "holding-hands", from: "bob/right-hand", to: "alice/left-hand" })
    ).toThrow("symmetric kinds match either order");
  });

  it("addRelation enforces multiplicity budgets", () => {
    const held = addRelation(HOLDING_HANDS_SCENE, { kind: "holds", from: "alice/right-hand", to: "bob/torso" });
    expect(() => addRelation(held, { kind: "holds", from: "alice/right-hand", to: "bob/back" })).toThrow(
      'Endpoint "alice/right-hand" would be "from" in 2 "holds" relations; fromMax is 1'
    );

    // symmetric: bob/right-hand already participates via the sample relation
    expect(() =>
      addRelation(HOLDING_HANDS_SCENE, { kind: "holding-hands", from: "bob/right-hand", to: "bob/left-hand" })
    ).toThrow('Endpoint "bob/right-hand" would participate in 2 "holding-hands" relations; fromMax is 1');
  });

  it("removeRelation returns what it removed and matches symmetric relations in either order", () => {
    const before = structuredClone(HOLDING_HANDS_SCENE);
    const reversed = { kind: "holding-hands", from: "bob/right-hand", to: "alice/left-hand" };
    const { scene: next, relation } = removeRelation(HOLDING_HANDS_SCENE, reversed);

    expect(HOLDING_HANDS_SCENE).toEqual(before);
    // the relation is returned as stored, not as queried
    expect(relation).toEqual({ kind: "holding-hands", from: "alice/left-hand", to: "bob/right-hand" });
    expect(next.relations).toEqual([]);
    expect(parseScene(next).ok).toBe(true);

    // round-trip: re-adding the returned relation restores the scene
    expect(addRelation(next, relation)).toEqual(HOLDING_HANDS_SCENE);

    expect(() => removeRelation(next, relation)).toThrow(
      'No relation ("holding-hands", "alice/left-hand", "bob/right-hand") exists in either order'
    );
    expect(() =>
      removeRelation(HOLDING_HANDS_SCENE, { kind: "holds", from: "bob/right-hand", to: "alice/left-hand" })
    ).toThrow('No relation ("holds", "bob/right-hand", "alice/left-hand") exists.');
  });

  it("relationsAt returns every relation touching an endpoint, in either position", () => {
    const scene = addRelation(HOLDING_HANDS_SCENE, { kind: "holds", from: "alice/right-hand", to: "bob/right-hand" });

    // bob/right-hand is "to" in both relations; alice/left-hand is "from" in one
    expect(relationsAt(scene, "bob/right-hand")).toHaveLength(2);
    expect(relationsAt(scene, "alice/left-hand")).toEqual([
      { kind: "holding-hands", from: "alice/left-hand", to: "bob/right-hand" }
    ]);
    expect(relationsAt(scene, "alice/torso")).toEqual([]);
    expect(() => relationsAt(scene, "alice")).toThrow("a bare body name does not reach a vessel");

    // returned relations are copies: mutating them does not touch the scene
    const [first] = relationsAt(scene, "alice/left-hand");
    first!.from = "bob/left-hand";
    expect(scene.relations[0]!.from).toBe("alice/left-hand");
  });

  it("every operation leaves its input scene untouched", () => {
    const before = structuredClone(HOLDING_HANDS_SCENE);

    declareKind(HOLDING_HANDS_SCENE, "guards");
    deleteKind(HOLDING_HANDS_SCENE, "holds");
    insertBody(HOLDING_HANDS_SCENE, "horse", { root: "saddle", vessels: { saddle: {} } });
    addRelation(HOLDING_HANDS_SCENE, { kind: "holds", from: "alice/right-hand", to: "bob/torso" });
    removeRelation(HOLDING_HANDS_SCENE, HOLDING_HANDS_SCENE.relations[0]!);
    relationsAt(HOLDING_HANDS_SCENE, "alice/left-hand");
    const unlinked = removeRelation(HOLDING_HANDS_SCENE, HOLDING_HANDS_SCENE.relations[0]!).scene;
    deleteBody(unlinked, "bob");

    expect(HOLDING_HANDS_SCENE).toEqual(before);
  });

  it("validateScene returns no errors for valid scenes and never throws on garbage", () => {
    expect(validateScene(HOLDING_HANDS_SCENE)).toEqual([]);
    expect(validateScene(null)).toEqual([{ path: "$", message: "Scene must be an object." }]);
    expect(validateScene([])).toEqual([{ path: "$", message: "Scene must be an object." }]);
    expect(validateScene({ protocol: "paperchain/v1", bodies: [], kinds: 3, relations: {} }).length).toBe(3);
  });
});
