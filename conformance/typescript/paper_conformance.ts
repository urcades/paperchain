/// <reference path="./node-shims.d.ts" />

import { readFileSync } from "node:fs";
import { deriveLayout, resolveAddress, validateDocument, type Body, type ResolvedAddress } from "paperdoll";
import { resolveSceneAddress, validateScene, type Scene } from "../../src/paperchain";

export type Subject = "paper-doll/v3" | "paperchain/v1";
export type Operation =
  | "validateDocument"
  | "resolveAddress"
  | "deriveLayout"
  | "validateScene"
  | "resolveSceneAddress";

export type ValidationExpected =
  | { outcome: "valid" }
  | { outcome: "invalid"; includesErrorPaths: string[] };
export type ResolutionExpected =
  | { outcome: "error" }
  | { outcome: "unresolved" }
  | { outcome: "resolved"; value: ResolvedProjection };
export type LayoutExpected = { outcome: "layout"; value: LayoutProjection };
export type ExpectedResult = ValidationExpected | ResolutionExpected | LayoutExpected;

export type ConformanceCase = {
  id: string;
  rule: string;
  subject: Subject;
  operation: Operation;
  input: Record<string, unknown>;
  expected: ExpectedResult;
};

export type Corpus = {
  corpus: "paper-family-conformance/v1";
  cases: ConformanceCase[];
};

export type ResolvedProjection =
  | { kind: "vessel"; vesselId: string }
  | { kind: "element"; vesselId: string; index: number; element: Record<string, unknown> };

export type EndpointProjection = { vessel: string; side: "top" | "right" | "bottom" | "left" };
export type ConnectionProjection = { from: EndpointProjection; to: EndpointProjection };
export type LayoutProjection = {
  figure: Record<string, { x: number; y: number }>;
  free: string[];
  connections: ConnectionProjection[];
};

export type ActualResult =
  | { outcome: "valid" }
  | { outcome: "invalid"; errorPaths: string[] }
  | { outcome: "error" }
  | { outcome: "unresolved" }
  | { outcome: "resolved"; value: ResolvedProjection }
  | { outcome: "layout"; value: LayoutProjection };

const CASE_KEYS = ["id", "rule", "subject", "operation", "input", "expected"] as const;
const SUBJECTS = new Set<Subject>(["paper-doll/v3", "paperchain/v1"]);
const OPERATIONS = new Set<Operation>([
  "validateDocument",
  "resolveAddress",
  "deriveLayout",
  "validateScene",
  "resolveSceneAddress"
]);
const SIDES = new Set(["top", "right", "bottom", "left"]);
const ASCII_CASE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const RULE = /^(paper-doll\/v3|paperchain\/v1)#[a-z0-9-]+$/;

/** Load a corpus without allowing JSON.parse to erase duplicate object keys. */
export function loadCorpusFile(path: string | URL): Corpus {
  const label = path instanceof URL ? path.pathname : path;
  return parseCorpusJson(readFileSync(path, "utf8"), label);
}

export function parseCorpusJson(source: string, label = "<corpus>"): Corpus {
  const value = new StrictJsonParser(source, label).parse();
  return validateCorpusEnvelope(value, label);
}

export function runCase(testCase: ConformanceCase): ActualResult {
  switch (testCase.operation) {
    case "validateDocument": {
      const errors = validateDocument(testCase.input.document);
      return errors.length === 0
        ? { outcome: "valid" }
        : { outcome: "invalid", errorPaths: errors.map((error) => error.path) };
    }
    case "validateScene": {
      const errors = validateScene(testCase.input.scene);
      return errors.length === 0
        ? { outcome: "valid" }
        : { outcome: "invalid", errorPaths: errors.map((error) => error.path) };
    }
    case "resolveAddress":
      return resolve(() => resolveAddress(testCase.input.body as Body, testCase.input.address as string));
    case "resolveSceneAddress":
      return resolve(() =>
        resolveSceneAddress(testCase.input.scene as Scene, testCase.input.address as string)
      );
    case "deriveLayout":
      return {
        outcome: "layout",
        value: normalizeLayout(deriveLayout(testCase.input.body as Body))
      };
  }
}

/**
 * Compare a runner result to the portable expectation. Invalid cases assert a
 * path subset so implementations may report additional useful violations.
 */
export function assertCaseMatches(testCase: ConformanceCase, actual: ActualResult): void {
  const expected = testCase.expected;
  if (expected.outcome === "invalid") {
    if (actual.outcome !== "invalid") {
      throw new Error(
        `${testCase.id}: expected outcome invalid, actual outcome ${actual.outcome}`
      );
    }
    const missing = expected.includesErrorPaths.filter((path) => !actual.errorPaths.includes(path));
    if (missing.length > 0) {
      throw new Error(`${testCase.id}: missing expected error paths: ${missing.join(", ")}`);
    }
    return;
  }

  if (!deepEqual(actual, expected)) {
    throw new Error(
      `${testCase.id}: expected ${JSON.stringify(expected)}, actual ${JSON.stringify(actual)}`
    );
  }
}

export function runCorpus(corpus: Corpus): void {
  for (const testCase of corpus.cases) {
    assertCaseMatches(testCase, runCase(testCase));
  }
}

function resolve(operation: () => ResolvedAddress | null): ActualResult {
  try {
    const resolved = operation();
    if (resolved === null) return { outcome: "unresolved" };
    if (resolved.kind === "vessel") {
      return { outcome: "resolved", value: { kind: "vessel", vesselId: resolved.vesselId } };
    }
    return {
      outcome: "resolved",
      value: {
        kind: "element",
        vesselId: resolved.vesselId,
        index: resolved.index,
        element: resolved.element as Record<string, unknown>
      }
    };
  } catch {
    return { outcome: "error" };
  }
}

function normalizeLayout(layout: ReturnType<typeof deriveLayout>): LayoutProjection {
  const figure: LayoutProjection["figure"] = {};
  for (const vesselId of Object.keys(layout.figure).sort(compareAscii)) {
    const position = layout.figure[vesselId];
    if (position) figure[vesselId] = { x: position.x, y: position.y };
  }

  const connections = layout.connections
    .map((connection): ConnectionProjection => {
      const from = { ...connection.from } as EndpointProjection;
      const to = { ...connection.to } as EndpointProjection;
      return endpointKey(from) <= endpointKey(to) ? { from, to } : { from: to, to: from };
    })
    .sort((left, right) => {
      const fromOrder = compareAscii(endpointKey(left.from), endpointKey(right.from));
      return fromOrder || compareAscii(endpointKey(left.to), endpointKey(right.to));
    });

  return {
    figure,
    free: [...layout.free].sort(compareAscii),
    connections
  };
}

function validateCorpusEnvelope(value: unknown, label: string): Corpus {
  const corpus = requireRecord(value, label);
  requireExactKeys(corpus, ["corpus", "cases"], label);
  if (corpus.corpus !== "paper-family-conformance/v1") {
    throw new Error(`${label}: unknown corpus ${JSON.stringify(corpus.corpus)}`);
  }
  if (!Array.isArray(corpus.cases)) throw new Error(`${label}: cases must be an array`);
  if (corpus.cases.length === 0) throw new Error(`${label}: cases must not be empty`);

  const seen = new Set<string>();
  const cases = corpus.cases.map((value, index) => validateCase(value, `${label}: cases[${index}]`));
  for (const testCase of cases) {
    if (seen.has(testCase.id)) throw new Error(`${label}: duplicate case id ${JSON.stringify(testCase.id)}`);
    seen.add(testCase.id);
  }
  return { corpus: "paper-family-conformance/v1", cases };
}

function validateCase(value: unknown, path: string): ConformanceCase {
  const testCase = requireRecord(value, path);
  requireExactKeys(testCase, CASE_KEYS, path);
  if (typeof testCase.id !== "string" || !ASCII_CASE_ID.test(testCase.id)) {
    throw new Error(`${path}.id must be a nonempty ASCII case id`);
  }
  if (typeof testCase.subject !== "string" || !SUBJECTS.has(testCase.subject as Subject)) {
    throw new Error(`${path}.subject is unknown`);
  }
  if (typeof testCase.rule !== "string" || !RULE.test(testCase.rule)) {
    throw new Error(`${path}.rule must be a normative paper-family anchor`);
  }
  if (!testCase.rule.startsWith(`${testCase.subject}#`)) {
    throw new Error(`${path}.rule must belong to subject ${testCase.subject}`);
  }
  if (typeof testCase.operation !== "string" || !OPERATIONS.has(testCase.operation as Operation)) {
    throw new Error(`${path}.operation is unknown`);
  }

  const subject = testCase.subject as Subject;
  const operation = testCase.operation as Operation;
  validateSubjectOperation(subject, operation, path);
  const input = requireRecord(testCase.input, `${path}.input`);
  validateInput(operation, input, `${path}.input`);
  const expected = validateExpected(operation, testCase.expected, `${path}.expected`);

  return {
    id: testCase.id,
    rule: testCase.rule,
    subject,
    operation,
    input,
    expected
  };
}

function validateSubjectOperation(subject: Subject, operation: Operation, path: string): void {
  const doll = new Set<Operation>(["validateDocument", "resolveAddress", "deriveLayout"]);
  const allowed = subject === "paper-doll/v3" ? doll.has(operation) : operation === "validateScene" || operation === "resolveSceneAddress";
  if (!allowed) throw new Error(`${path}: operation ${operation} is incompatible with subject ${subject}`);
}

function validateInput(operation: Operation, input: Record<string, unknown>, path: string): void {
  switch (operation) {
    case "validateDocument":
      requireExactKeys(input, ["document"], path);
      return;
    case "validateScene":
      requireExactKeys(input, ["scene"], path);
      return;
    case "resolveAddress":
      requireExactKeys(input, ["body", "address"], path);
      requireRecord(input.body, `${path}.body`);
      requireString(input.address, `${path}.address`);
      return;
    case "resolveSceneAddress":
      requireExactKeys(input, ["scene", "address"], path);
      requireRecord(input.scene, `${path}.scene`);
      requireString(input.address, `${path}.address`);
      return;
    case "deriveLayout":
      requireExactKeys(input, ["body"], path);
      requireRecord(input.body, `${path}.body`);
  }
}

function validateExpected(operation: Operation, value: unknown, path: string): ExpectedResult {
  const expected = requireRecord(value, path);
  if (typeof expected.outcome !== "string") throw new Error(`${path}.outcome must be a string`);

  if (operation === "validateDocument" || operation === "validateScene") {
    if (expected.outcome === "valid") {
      requireExactKeys(expected, ["outcome"], path);
      return { outcome: "valid" };
    }
    if (expected.outcome === "invalid") {
      requireExactKeys(expected, ["outcome", "includesErrorPaths"], path);
      const paths = requireNonemptyUniqueStrings(expected.includesErrorPaths, `${path}.includesErrorPaths`);
      return { outcome: "invalid", includesErrorPaths: paths };
    }
    throw new Error(`${path}.outcome is invalid for validation operation ${operation}`);
  }

  if (operation === "resolveAddress" || operation === "resolveSceneAddress") {
    if (expected.outcome === "error" || expected.outcome === "unresolved") {
      requireExactKeys(expected, ["outcome"], path);
      return { outcome: expected.outcome };
    }
    if (expected.outcome === "resolved") {
      requireExactKeys(expected, ["outcome", "value"], path);
      return { outcome: "resolved", value: validateResolved(expected.value, `${path}.value`) };
    }
    throw new Error(`${path}.outcome is invalid for resolution operation ${operation}`);
  }

  if (expected.outcome !== "layout") {
    throw new Error(`${path}.outcome is invalid for deriveLayout`);
  }
  requireExactKeys(expected, ["outcome", "value"], path);
  return { outcome: "layout", value: validateLayout(expected.value, `${path}.value`) };
}

function validateResolved(value: unknown, path: string): ResolvedProjection {
  const resolved = requireRecord(value, path);
  if (resolved.kind === "vessel") {
    requireExactKeys(resolved, ["kind", "vesselId"], path);
    return { kind: "vessel", vesselId: requireString(resolved.vesselId, `${path}.vesselId`) };
  }
  if (resolved.kind === "element") {
    requireExactKeys(resolved, ["kind", "vesselId", "index", "element"], path);
    const index = resolved.index;
    if (!Number.isInteger(index) || (index as number) < 0) throw new Error(`${path}.index must be an integer >= 0`);
    return {
      kind: "element",
      vesselId: requireString(resolved.vesselId, `${path}.vesselId`),
      index: index as number,
      element: requireRecord(resolved.element, `${path}.element`)
    };
  }
  throw new Error(`${path}.kind must be vessel or element`);
}

function validateLayout(value: unknown, path: string): LayoutProjection {
  const layout = requireRecord(value, path);
  requireExactKeys(layout, ["figure", "free", "connections"], path);

  const rawFigure = requireRecord(layout.figure, `${path}.figure`);
  const figure: LayoutProjection["figure"] = {};
  for (const [vesselId, rawPosition] of Object.entries(rawFigure)) {
    const position = requireRecord(rawPosition, `${path}.figure.${vesselId}`);
    requireExactKeys(position, ["x", "y"], `${path}.figure.${vesselId}`);
    if (!isFiniteNumber(position.x) || !isFiniteNumber(position.y)) {
      throw new Error(`${path}.figure.${vesselId} coordinates must be finite numbers`);
    }
    figure[vesselId] = { x: position.x, y: position.y };
  }

  const free = requireUniqueStrings(layout.free, `${path}.free`);
  if (!deepEqual(free, [...free].sort(compareAscii))) throw new Error(`${path}.free must be ASCII-sorted`);

  if (!Array.isArray(layout.connections)) throw new Error(`${path}.connections must be an array`);
  const connections = layout.connections.map((entry, index) =>
    validateConnection(entry, `${path}.connections[${index}]`)
  );
  for (const connection of connections) {
    if (endpointKey(connection.from) > endpointKey(connection.to)) {
      throw new Error(`${path}.connections must normalize each undirected endpoint pair`);
    }
  }
  const sorted = [...connections].sort((left, right) => {
    const first = compareAscii(endpointKey(left.from), endpointKey(right.from));
    return first || compareAscii(endpointKey(left.to), endpointKey(right.to));
  });
  if (!deepEqual(connections, sorted)) throw new Error(`${path}.connections must be ASCII-sorted`);

  return { figure, free, connections };
}

function validateConnection(value: unknown, path: string): ConnectionProjection {
  const connection = requireRecord(value, path);
  requireExactKeys(connection, ["from", "to"], path);
  return {
    from: validateEndpoint(connection.from, `${path}.from`),
    to: validateEndpoint(connection.to, `${path}.to`)
  };
}

function validateEndpoint(value: unknown, path: string): EndpointProjection {
  const endpoint = requireRecord(value, path);
  requireExactKeys(endpoint, ["vessel", "side"], path);
  const vessel = requireString(endpoint.vessel, `${path}.vessel`);
  if (typeof endpoint.side !== "string" || !SIDES.has(endpoint.side)) {
    throw new Error(`${path}.side is invalid`);
  }
  return { vessel, side: endpoint.side as EndpointProjection["side"] };
}

function requireRecord(value: unknown, path: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${path} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requireString(value: unknown, path: string): string {
  if (typeof value !== "string") throw new Error(`${path} must be a string`);
  return value;
}

function requireExactKeys(object: Record<string, unknown>, allowed: readonly string[], path: string): void {
  const allowedSet = new Set(allowed);
  for (const key of Object.keys(object)) {
    if (!allowedSet.has(key)) throw new Error(`${path} has unknown key ${JSON.stringify(key)}`);
  }
  for (const key of allowed) {
    if (!Object.hasOwn(object, key)) throw new Error(`${path} is missing required key ${JSON.stringify(key)}`);
  }
}

function requireNonemptyUniqueStrings(value: unknown, path: string): string[] {
  const strings = requireUniqueStrings(value, path);
  if (strings.length === 0 || strings.some((item) => item.length === 0)) {
    throw new Error(`${path} must contain nonempty strings`);
  }
  return strings;
}

function requireUniqueStrings(value: unknown, path: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${path} must be an array of strings`);
  }
  if (new Set(value).size !== value.length) throw new Error(`${path} must not contain duplicates`);
  return value as string[];
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function endpointKey(endpoint: EndpointProjection): string {
  return `${endpoint.vessel}:${endpoint.side}`;
}

function compareAscii(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function deepEqual(left: unknown, right: unknown): boolean {
  // Paper-family JSON equality compares finite numbers by numeric value, so
  // the two JSON spellings -0 and 0 are equal. Requiring both operands to be
  // numbers keeps booleans distinct from 0/1.
  if (typeof left === "number" && typeof right === "number") return left === right;
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((value, index) => deepEqual(value, right[index]))
    );
  }
  if (left === null || right === null || typeof left !== "object" || typeof right !== "object") return false;
  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const leftKeys = Object.keys(leftRecord).sort(compareAscii);
  const rightKeys = Object.keys(rightRecord).sort(compareAscii);
  return (
    deepEqual(leftKeys, rightKeys) &&
    leftKeys.every((key) => deepEqual(leftRecord[key], rightRecord[key]))
  );
}

/** A deliberately small complete JSON parser whose object production rejects duplicate keys. */
class StrictJsonParser {
  private offset = 0;

  constructor(
    private readonly source: string,
    private readonly label: string
  ) {}

  parse(): unknown {
    const value = this.parseValue("$");
    this.skipWhitespace();
    if (this.offset !== this.source.length) this.fail("unexpected trailing input");
    return value;
  }

  private parseValue(path: string): unknown {
    this.skipWhitespace();
    const token = this.source[this.offset];
    if (token === "{") return this.parseObject(path);
    if (token === "[") return this.parseArray(path);
    if (token === '"') return this.parseString();
    if (token === "t") return this.parseLiteral("true", true);
    if (token === "f") return this.parseLiteral("false", false);
    if (token === "n") return this.parseLiteral("null", null);
    if (token === "-" || (token !== undefined && token >= "0" && token <= "9")) return this.parseNumber();
    this.fail("expected a JSON value");
  }

  private parseObject(path: string): Record<string, unknown> {
    this.offset += 1;
    const result: Record<string, unknown> = {};
    const keys = new Set<string>();
    this.skipWhitespace();
    if (this.consume("}")) return result;

    for (;;) {
      this.skipWhitespace();
      if (this.source[this.offset] !== '"') this.fail("expected an object key");
      const key = this.parseString();
      if (keys.has(key)) this.fail(`duplicate object key ${JSON.stringify(key)} at ${path}`);
      keys.add(key);
      this.skipWhitespace();
      if (!this.consume(":")) this.fail("expected ':' after an object key");
      const value = this.parseValue(`${path}.${key}`);
      Object.defineProperty(result, key, { value, enumerable: true, configurable: true, writable: true });
      this.skipWhitespace();
      if (this.consume("}")) return result;
      if (!this.consume(",")) this.fail("expected ',' or '}' in object");
    }
  }

  private parseArray(path: string): unknown[] {
    this.offset += 1;
    const result: unknown[] = [];
    this.skipWhitespace();
    if (this.consume("]")) return result;
    for (;;) {
      result.push(this.parseValue(`${path}[${result.length}]`));
      this.skipWhitespace();
      if (this.consume("]")) return result;
      if (!this.consume(",")) this.fail("expected ',' or ']' in array");
    }
  }

  private parseString(): string {
    const start = this.offset;
    this.offset += 1;
    while (this.offset < this.source.length) {
      const character = this.source[this.offset];
      if (character === "\\") {
        this.offset += 2;
        continue;
      }
      if (character === '"') {
        this.offset += 1;
        try {
          return JSON.parse(this.source.slice(start, this.offset)) as string;
        } catch {
          this.fail("invalid JSON string");
        }
      }
      this.offset += 1;
    }
    this.fail("unterminated JSON string");
  }

  private parseNumber(): number {
    const match = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(
      this.source.slice(this.offset)
    );
    if (!match) this.fail("invalid JSON number");
    this.offset += match[0].length;
    const value = Number(match[0]);
    if (!Number.isFinite(value)) this.fail("JSON number must be finite");
    return value;
  }

  private parseLiteral<T>(spelling: string, value: T): T {
    if (this.source.slice(this.offset, this.offset + spelling.length) !== spelling) {
      this.fail(`expected ${spelling}`);
    }
    this.offset += spelling.length;
    return value;
  }

  private skipWhitespace(): void {
    while (
      this.source[this.offset] === " " ||
      this.source[this.offset] === "\t" ||
      this.source[this.offset] === "\n" ||
      this.source[this.offset] === "\r"
    ) {
      this.offset += 1;
    }
  }

  private consume(character: string): boolean {
    if (this.source[this.offset] !== character) return false;
    this.offset += 1;
    return true;
  }

  private fail(message: string): never {
    throw new Error(`${this.label}:${this.offset}: ${message}`);
  }
}
