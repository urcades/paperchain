import {
  PAPER_DOLL_PROTOCOL,
  formatProtocolErrors,
  isId,
  parseAddress,
  resolveAddress,
  validateDocument,
  validateKnownKeys,
  type Body,
  type ProtocolError,
  type ResolvedAddress,
  type Result
} from "paperdoll";

export const PAPERCHAIN_PROTOCOL = "paperchain/v1" as const;

export type BodyName = string;
export type KindId = string;

/**
 * A scene address is "<bodyName>/<paper-doll-v3-address>": the first segment
 * names a body in the scene's "bodies", the remainder is resolved within that
 * body by paperdoll's address grammar. A bare body name is not a scene
 * address — an endpoint must reach at least a vessel.
 */
export type SceneAddress = string;

export type KindDeclaration = {
  symmetric?: boolean;
  irreflexive?: boolean;
  fromMax?: number;
  toMax?: number;
};

export type Relation = {
  kind: KindId;
  from: SceneAddress;
  to: SceneAddress;
};

export type Scene = {
  protocol: typeof PAPERCHAIN_PROTOCOL;
  bodies: Record<BodyName, Body>;
  kinds: Record<KindId, KindDeclaration>;
  relations: Relation[];
};

export type SplitSceneAddress = {
  bodyName: BodyName;
  address: string;
};

const KIND_DECLARATION_KEYS = ["symmetric", "irreflexive", "fromMax", "toMax"] as const;
const RELATION_KEYS = ["kind", "from", "to"] as const;

// Parsing and validation

export function parseScene(input: unknown): Result<Scene, ProtocolError[]> {
  const errors = validateScene(input);
  if (errors.length > 0) return { ok: false, errors };
  const scene = input as Scene;
  return {
    ok: true,
    value: {
      protocol: PAPERCHAIN_PROTOCOL,
      bodies: structuredClone(scene.bodies),
      kinds: structuredClone(scene.kinds),
      relations: structuredClone(scene.relations)
    }
  };
}

export function assertScene(input: unknown): asserts input is Scene {
  const result = parseScene(input);
  if (!result.ok) {
    throw new Error(formatProtocolErrors(result.errors));
  }
}

export function validateScene(input: unknown): ProtocolError[] {
  const errors: ProtocolError[] = [];

  if (!isRecord(input)) {
    return [{ path: "$", message: "Scene must be an object." }];
  }

  if (input.protocol !== PAPERCHAIN_PROTOCOL) {
    errors.push({ path: "$.protocol", message: `Expected "${PAPERCHAIN_PROTOCOL}".` });
  }

  validateKnownKeys(input, ["protocol", "bodies", "kinds", "relations"], "$", errors);

  const bodies = validateBodies(input.bodies, errors);
  const kinds = validateKinds(input.kinds, errors);
  validateRelations(input.relations, bodies, kinds, errors);

  return errors;
}

// Scene addresses

/**
 * Splits a scene address into its body name and the address inside that body.
 * Throws on malformed addresses, including bare body names: an endpoint must
 * reach at least a vessel.
 */
export function parseSceneAddress(address: string): SplitSceneAddress {
  const segments = parseAddress(address);
  if (segments.length < 2) {
    throw new Error(
      `Scene address "${address}" must pair a body name with an address inside that body ("<body>/<vessel...>"); a bare body name does not reach a vessel.`
    );
  }
  return { bodyName: segments[0] as string, address: segments.slice(1).join("/") };
}

/**
 * Resolves a scene address against the scene's bodies. Returns null when the
 * body name is missing or the remainder does not resolve; throws on malformed
 * addresses (mirroring paperdoll's resolveAddress).
 */
export function resolveSceneAddress(scene: Scene, address: SceneAddress): ResolvedAddress | null {
  const split = parseSceneAddress(address);
  if (!Object.hasOwn(scene.bodies, split.bodyName)) return null;
  return resolveAddress(scene.bodies[split.bodyName] as Body, split.address);
}

// Operations
//
// Operations are pure: they never mutate their inputs, and destructive
// operations return what they destroyed. They enforce the local laws
// (declared kinds, existence, irreflexivity, no duplicates, multiplicity,
// no dangling endpoints) and throw with precise messages; they do not
// re-validate whole bodies — global validity stays a validateScene concern.

export function declareKind(scene: Scene, kindId: KindId, declaration: KindDeclaration = {}): Scene {
  if (!isId(kindId)) {
    throw new Error(
      `Kind id "${kindId}" must start with a lowercase letter and contain only lowercase letters, numbers, and hyphens.`
    );
  }
  if (Object.hasOwn(scene.kinds, kindId)) {
    throw new Error(`Kind "${kindId}" is already declared.`);
  }

  const errors: ProtocolError[] = [];
  validateKindDeclaration(declaration, `$.kinds.${kindId}`, errors);
  if (errors.length > 0) {
    throw new Error(formatProtocolErrors(errors));
  }

  const next = cloneScene(scene);
  next.kinds[kindId] = structuredClone(declaration);
  return next;
}

export function deleteKind(scene: Scene, kindId: KindId): { scene: Scene; declaration: KindDeclaration } {
  if (!Object.hasOwn(scene.kinds, kindId)) {
    throw new Error(`Kind "${kindId}" is not declared.`);
  }
  const used = scene.relations.filter((relation) => relation.kind === kindId).length;
  if (used > 0) {
    throw new Error(`Cannot delete kind "${kindId}"; ${used} relation(s) use it. Remove them first.`);
  }

  const next = cloneScene(scene);
  const declaration = next.kinds[kindId] as KindDeclaration;
  delete next.kinds[kindId];
  return { scene: next, declaration };
}

export function insertBody(scene: Scene, name: BodyName, body: Body): Scene {
  if (!isId(name)) {
    throw new Error(
      `Body name "${name}" must start with a lowercase letter and contain only lowercase letters, numbers, and hyphens.`
    );
  }
  if (Object.hasOwn(scene.bodies, name)) {
    throw new Error(`Body name "${name}" is already used.`);
  }

  const errors = validateDocument({ protocol: PAPER_DOLL_PROTOCOL, body }).map((error) => ({
    path: rewriteBodyPath(error.path, name),
    message: error.message
  }));
  if (errors.length > 0) {
    throw new Error(formatProtocolErrors(errors));
  }

  const next = cloneScene(scene);
  next.bodies[name] = structuredClone(body);
  return next;
}

export function deleteBody(scene: Scene, name: BodyName): { scene: Scene; body: Body } {
  if (!Object.hasOwn(scene.bodies, name)) {
    throw new Error(`Body "${name}" does not exist.`);
  }
  const touching = scene.relations.filter((relation) => relationTouchesBody(relation, name)).length;
  if (touching > 0) {
    throw new Error(
      `Cannot delete body "${name}"; ${touching} relation(s) have an endpoint in it. Remove them in the same transaction (dangling relations are invalid).`
    );
  }

  const next = cloneScene(scene);
  const body = next.bodies[name] as Body;
  delete next.bodies[name];
  return { scene: next, body };
}

export function addRelation(scene: Scene, relation: Relation): Scene {
  assertRelationShape(relation);
  if (!Object.hasOwn(scene.kinds, relation.kind)) {
    throw new Error(`Relation kind "${relation.kind}" is not declared in "kinds".`);
  }
  const declaration = scene.kinds[relation.kind] as KindDeclaration;
  const symmetric = declaration.symmetric === true;

  assertEndpointResolves(scene, relation.from, "from");
  assertEndpointResolves(scene, relation.to, "to");

  if (declaration.irreflexive === true && relation.from === relation.to) {
    throw new Error(`Kind "${relation.kind}" is irreflexive; "${relation.from}" cannot relate to itself.`);
  }

  if (scene.relations.some((existing) => sameRelation(existing, relation, symmetric))) {
    throw new Error(
      `Relation ("${relation.kind}", "${relation.from}", "${relation.to}") already exists${
        symmetric ? " (symmetric kinds match either order)" : ""
      }.`
    );
  }

  if (symmetric) {
    if (declaration.fromMax !== undefined) {
      const endpoints = relation.from === relation.to ? [relation.from] : [relation.from, relation.to];
      for (const endpoint of endpoints) {
        const added = relation.from === relation.to ? 2 : 1;
        const count = participationCount(scene.relations, relation.kind, endpoint) + added;
        if (count > declaration.fromMax) {
          throw new Error(
            `Endpoint "${endpoint}" would participate in ${count} "${relation.kind}" relations; fromMax is ${declaration.fromMax} (symmetric kinds count either position).`
          );
        }
      }
    }
  } else {
    if (declaration.fromMax !== undefined) {
      const count = scene.relations.filter(
        (existing) => existing.kind === relation.kind && existing.from === relation.from
      ).length;
      if (count + 1 > declaration.fromMax) {
        throw new Error(
          `Endpoint "${relation.from}" would be "from" in ${count + 1} "${relation.kind}" relations; fromMax is ${declaration.fromMax}.`
        );
      }
    }
    if (declaration.toMax !== undefined) {
      const count = scene.relations.filter(
        (existing) => existing.kind === relation.kind && existing.to === relation.to
      ).length;
      if (count + 1 > declaration.toMax) {
        throw new Error(
          `Endpoint "${relation.to}" would be "to" in ${count + 1} "${relation.kind}" relations; toMax is ${declaration.toMax}.`
        );
      }
    }
  }

  const next = cloneScene(scene);
  next.relations.push(structuredClone(relation));
  return next;
}

export function removeRelation(scene: Scene, relation: Relation): { scene: Scene; relation: Relation } {
  assertRelationShape(relation);
  const declaration = Object.hasOwn(scene.kinds, relation.kind) ? scene.kinds[relation.kind] : undefined;
  const symmetric = isRecord(declaration) && declaration.symmetric === true;

  const index = scene.relations.findIndex((existing) => sameRelation(existing, relation, symmetric));
  if (index === -1) {
    throw new Error(
      `No relation ("${relation.kind}", "${relation.from}", "${relation.to}") exists${
        symmetric ? " in either order" : ""
      }.`
    );
  }

  const next = cloneScene(scene);
  const [removed] = next.relations.splice(index, 1);
  return { scene: next, relation: removed as Relation };
}

/**
 * Every relation touching the given endpoint, in either position (which is
 * what makes it symmetric-aware: a symmetric relation stored as (a, b) is
 * found from b). Returns copies; throws on malformed addresses.
 */
export function relationsAt(scene: Scene, address: SceneAddress): Relation[] {
  parseSceneAddress(address);
  return scene.relations
    .filter((relation) => relation.from === address || relation.to === address)
    .map((relation) => structuredClone(relation));
}

// Validation internals

function validateBodies(input: unknown, errors: ProtocolError[]): {
  record: Record<string, unknown> | null;
  valid: Set<string>;
} {
  const valid = new Set<string>();
  if (!isRecord(input)) {
    errors.push({ path: "$.bodies", message: "Bodies must be an object keyed by body name." });
    return { record: null, valid };
  }

  for (const [name, body] of Object.entries(input)) {
    if (!isId(name)) {
      errors.push({
        path: `$.bodies.${name}`,
        message: "Body name must start with a lowercase letter and contain only lowercase letters, numbers, and hyphens."
      });
    }

    const bodyErrors = validateDocument({ protocol: PAPER_DOLL_PROTOCOL, body });
    for (const error of bodyErrors) {
      errors.push({ path: rewriteBodyPath(error.path, name), message: error.message });
    }

    if (isId(name) && bodyErrors.length === 0) {
      valid.add(name);
    }
  }

  return { record: input, valid };
}

function validateKinds(input: unknown, errors: ProtocolError[]): {
  record: Record<string, unknown> | null;
  clean: Map<string, KindDeclaration>;
} {
  const clean = new Map<string, KindDeclaration>();
  if (!isRecord(input)) {
    errors.push({ path: "$.kinds", message: "Kinds must be an object keyed by kind id." });
    return { record: null, clean };
  }

  for (const [kindId, declaration] of Object.entries(input)) {
    const path = `$.kinds.${kindId}`;
    if (!isId(kindId)) {
      errors.push({
        path,
        message: "Kind id must start with a lowercase letter and contain only lowercase letters, numbers, and hyphens."
      });
    }

    const before = errors.length;
    validateKindDeclaration(declaration, path, errors);
    if (isId(kindId) && errors.length === before) {
      clean.set(kindId, declaration as KindDeclaration);
    }
  }

  return { record: input, clean };
}

function validateKindDeclaration(input: unknown, path: string, errors: ProtocolError[]): void {
  if (!isRecord(input)) {
    errors.push({ path, message: "Kind declaration must be an object." });
    return;
  }

  validateKnownKeys(input, KIND_DECLARATION_KEYS, path, errors);

  for (const flag of ["symmetric", "irreflexive"] as const) {
    if (input[flag] !== undefined && typeof input[flag] !== "boolean") {
      errors.push({ path: `${path}.${flag}`, message: `${flag} must be a boolean.` });
    }
  }
  for (const budget of ["fromMax", "toMax"] as const) {
    const value = input[budget];
    if (value !== undefined && (!Number.isInteger(value) || (value as number) < 0)) {
      errors.push({ path: `${path}.${budget}`, message: `${budget} must be an integer >= 0.` });
    }
  }

  if (input.symmetric === true && input.toMax !== undefined) {
    errors.push({
      path: `${path}.toMax`,
      message: `Symmetric kinds use fromMax as the per-endpoint budget; "toMax" is not allowed on a symmetric kind.`
    });
  }
}

function validateRelations(
  input: unknown,
  bodies: { record: Record<string, unknown> | null; valid: Set<string> },
  kinds: { record: Record<string, unknown> | null; clean: Map<string, KindDeclaration> },
  errors: ProtocolError[]
): void {
  if (!Array.isArray(input)) {
    errors.push({ path: "$.relations", message: "Relations must be an array of relation objects." });
    return;
  }

  type Checkable = { index: number; kind: string; from: string; to: string; declaration: KindDeclaration | undefined };
  const checkable: Checkable[] = [];

  input.forEach((relation, index) => {
    const path = `$.relations.${index}`;
    if (!isRecord(relation)) {
      errors.push({ path, message: "Relation must be an object." });
      return;
    }

    validateKnownKeys(relation, RELATION_KEYS, path, errors);

    let kindDeclared = false;
    if (!isId(relation.kind)) {
      errors.push({ path: `${path}.kind`, message: "Relation kind must be a lowercase id." });
    } else if (kinds.record && !Object.hasOwn(kinds.record, relation.kind)) {
      errors.push({ path: `${path}.kind`, message: `Relation kind "${relation.kind}" is not declared in "kinds".` });
    } else if (kinds.record) {
      kindDeclared = true;
    }

    const endpoints: Partial<Record<"from" | "to", string>> = {};
    for (const field of ["from", "to"] as const) {
      const value = relation[field];
      const endpointPath = `${path}.${field}`;
      if (typeof value !== "string") {
        errors.push({ path: endpointPath, message: "Relation endpoint must be a scene address string." });
        continue;
      }

      let split: SplitSceneAddress;
      try {
        split = parseSceneAddress(value);
      } catch (error) {
        errors.push({ path: endpointPath, message: (error as Error).message });
        continue;
      }
      endpoints[field] = value;

      if (bodies.record && !Object.hasOwn(bodies.record, split.bodyName)) {
        errors.push({ path: endpointPath, message: `Endpoint "${value}" names missing body "${split.bodyName}".` });
        continue;
      }
      if (bodies.valid.has(split.bodyName)) {
        const resolved = resolveAddress(bodies.record?.[split.bodyName] as Body, split.address);
        if (resolved === null) {
          errors.push({
            path: endpointPath,
            message: `Endpoint "${value}" does not resolve within body "${split.bodyName}".`
          });
        }
      }
    }

    if (!kindDeclared || endpoints.from === undefined || endpoints.to === undefined) return;
    const kind = relation.kind as string;
    const declaration = kinds.clean.get(kind);

    if (declaration?.irreflexive === true && endpoints.from === endpoints.to) {
      errors.push({ path, message: `Kind "${kind}" is irreflexive; "${endpoints.from}" cannot relate to itself.` });
    }

    checkable.push({ index, kind, from: endpoints.from, to: endpoints.to, declaration });
  });

  // No duplicates: relation identity is (kind, from, to); symmetric kinds
  // canonicalize the endpoint pair.
  const seen = new Map<string, number>();
  for (const { index, kind, from, to, declaration } of checkable) {
    const key = relationKey(kind, from, to, declaration?.symmetric === true);
    const prior = seen.get(key);
    if (prior !== undefined) {
      errors.push({
        path: `$.relations.${index}`,
        message: `Duplicate relation ("${kind}", "${from}", "${to}"); already declared at $.relations.${prior}.`
      });
    } else {
      seen.set(key, index);
    }
  }

  // Multiplicity: declared budgets per kind.
  const counts = new Map<string, number>();
  const bump = (key: string): number => {
    const count = (counts.get(key) ?? 0) + 1;
    counts.set(key, count);
    return count;
  };
  for (const { index, kind, from, to, declaration } of checkable) {
    if (!declaration) continue;
    if (declaration.symmetric === true) {
      if (declaration.fromMax === undefined) continue;
      for (const [endpoint, field] of [
        [from, "from"],
        [to, "to"]
      ] as const) {
        const count = bump(`${kind} either ${endpoint}`);
        if (count > declaration.fromMax) {
          errors.push({
            path: `$.relations.${index}.${field}`,
            message: `Endpoint "${endpoint}" participates in ${count} "${kind}" relations; fromMax is ${declaration.fromMax} (symmetric kinds count either position).`
          });
        }
      }
    } else {
      if (declaration.fromMax !== undefined) {
        const count = bump(`${kind} from ${from}`);
        if (count > declaration.fromMax) {
          errors.push({
            path: `$.relations.${index}.from`,
            message: `Endpoint "${from}" is "from" in ${count} "${kind}" relations; fromMax is ${declaration.fromMax}.`
          });
        }
      }
      if (declaration.toMax !== undefined) {
        const count = bump(`${kind} to ${to}`);
        if (count > declaration.toMax) {
          errors.push({
            path: `$.relations.${index}.to`,
            message: `Endpoint "${to}" is "to" in ${count} "${kind}" relations; toMax is ${declaration.toMax}.`
          });
        }
      }
    }
  }
}


function rewriteBodyPath(path: string, name: string): string {
  const prefix = `$.bodies.${name}`;
  if (path === "$.body") return prefix;
  if (path.startsWith("$.body.")) return prefix + path.slice("$.body".length);
  return prefix;
}

// Operation internals

function cloneScene(scene: Scene): Scene {
  return structuredClone(scene);
}

function assertRelationShape(relation: unknown): asserts relation is Relation {
  if (!isRecord(relation)) {
    throw new Error("Relation must be an object.");
  }
  for (const key of Object.keys(relation)) {
    if (!(RELATION_KEYS as readonly string[]).includes(key)) {
      throw new Error(`Unknown key "${key}" on relation.`);
    }
  }
  if (!isId(relation.kind)) {
    throw new Error("Relation kind must be a lowercase id.");
  }
  if (typeof relation.from !== "string") {
    throw new Error(`Relation "from" must be a scene address string.`);
  }
  if (typeof relation.to !== "string") {
    throw new Error(`Relation "to" must be a scene address string.`);
  }
}

function assertEndpointResolves(scene: Scene, address: SceneAddress, label: string): void {
  const split = parseSceneAddress(address);
  if (!Object.hasOwn(scene.bodies, split.bodyName)) {
    throw new Error(`${label} endpoint "${address}" names missing body "${split.bodyName}".`);
  }
  const resolved = resolveAddress(scene.bodies[split.bodyName] as Body, split.address);
  if (resolved === null) {
    throw new Error(`${label} endpoint "${address}" does not resolve within body "${split.bodyName}".`);
  }
}

function relationTouchesBody(relation: Relation, name: BodyName): boolean {
  return endpointBodyName(relation.from) === name || endpointBodyName(relation.to) === name;
}

function endpointBodyName(address: SceneAddress): string {
  return address.split("/")[0] as string;
}

function sameRelation(a: Relation, b: Relation, symmetric: boolean): boolean {
  if (a.kind !== b.kind) return false;
  if (a.from === b.from && a.to === b.to) return true;
  return symmetric && a.from === b.to && a.to === b.from;
}

function relationKey(kind: string, from: string, to: string, symmetric: boolean): string {
  const pair = symmetric ? [from, to].sort() : [from, to];
  return [kind, ...pair].join(" ");
}

function participationCount(relations: readonly Relation[], kind: KindId, endpoint: SceneAddress): number {
  let count = 0;
  for (const relation of relations) {
    if (relation.kind !== kind) continue;
    if (relation.from === endpoint) count += 1;
    if (relation.to === endpoint) count += 1;
  }
  return count;
}

// Predicates

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
