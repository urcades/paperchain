/// <reference path="./node-shims.d.ts" />

import { readFileSync } from "node:fs";

export const V2_CORPUS = "paper-family-conformance/v2" as const;

export type V2Subject =
  | "paper-doll/v3"
  | "paperchain/v1"
  | "paperfold/v1"
  | "paperfold/v2"
  | "papermold/v1"
  | "papermold/v2";

export type V2Operation =
  | "connect"
  | "disconnect"
  | "insertVessel"
  | "deleteVessel"
  | "insertElement"
  | "removeElement"
  | "moveElement"
  | "declareKind"
  | "deleteKind"
  | "insertBody"
  | "deleteBody"
  | "addRelation"
  | "removeRelation"
  | "relationsAt"
  | "validatePatch"
  | "applyPatch"
  | "invertPatch"
  | "composePatches"
  | "diffLaws"
  | "validateScenePatch"
  | "applyScenePatch"
  | "invertScenePatch"
  | "composeScenePatches"
  | "diffSceneLaws"
  | "validateProfiles"
  | "judge"
  | "conforms"
  | "validateSceneProfiles"
  | "judgeBody"
  | "conformsBody"
  | "judgeScene"
  | "conformsScene";

export type OkProjection = { outcome: "ok"; value: unknown };
export type ValidProjection = { outcome: "valid" };
export type InvalidProjection = { outcome: "invalid"; errorPaths: string[] };
export type ErrorProjection = { outcome: "error" };
export type ConformsProjection = { outcome: "conforms" };
export type NonconformingProjection = { outcome: "nonconforming"; errorPaths: string[] };
export type Projection =
  | OkProjection
  | ValidProjection
  | InvalidProjection
  | ErrorProjection
  | ConformsProjection
  | NonconformingProjection;

export type ExpectedProjection =
  | OkProjection
  | ValidProjection
  | { outcome: "invalid"; includesErrorPaths: string[] }
  | ErrorProjection
  | ConformsProjection
  | { outcome: "nonconforming"; includesErrorPaths: string[] };

export type V2Case = {
  id: string;
  rule: string;
  subject: V2Subject;
  operation: V2Operation;
  input: { args: unknown[] };
  expected: ExpectedProjection;
};

export type V2Corpus = {
  corpus: typeof V2_CORPUS;
  cases: V2Case[];
};

export type CaseDispatcher = (testCase: V2Case) => Projection;

type ErrorLike = { path: string };
type ResultLike = { ok: true; value: unknown } | { ok: false; errors: ErrorLike[] };

const CASE_KEYS = ["id", "rule", "subject", "operation", "input", "expected"] as const;
const ASCII_CASE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const RULE = /^(paper-doll\/v3|paperchain\/v1|paperfold\/v[12]|papermold\/v[12])#[a-z0-9-]+$/;

const OPERATIONS: Readonly<Record<V2Subject, readonly V2Operation[]>> = {
  "paper-doll/v3": ["connect", "disconnect", "insertVessel", "deleteVessel", "insertElement", "removeElement", "moveElement"],
  "paperchain/v1": ["declareKind", "deleteKind", "insertBody", "deleteBody", "addRelation", "removeRelation", "relationsAt"],
  "paperfold/v1": ["validatePatch", "applyPatch", "invertPatch", "composePatches", "diffLaws"],
  "paperfold/v2": ["validateScenePatch", "applyScenePatch", "invertScenePatch", "composeScenePatches", "diffSceneLaws"],
  "papermold/v1": ["validateProfiles", "judge", "conforms"],
  "papermold/v2": ["validateSceneProfiles", "judgeBody", "conformsBody", "judgeScene", "conformsScene"]
};

const ARITIES: Readonly<Record<V2Operation, readonly [minimum: number, maximum: number]>> = {
  connect: [3, 3],
  disconnect: [2, 2],
  insertVessel: [1, 3],
  deleteVessel: [2, 3],
  insertElement: [3, 4],
  removeElement: [3, 3],
  moveElement: [4, 4],
  declareKind: [2, 3],
  deleteKind: [2, 2],
  insertBody: [3, 3],
  deleteBody: [2, 2],
  addRelation: [2, 2],
  removeRelation: [2, 2],
  relationsAt: [2, 2],
  validatePatch: [1, 1],
  applyPatch: [2, 2],
  invertPatch: [1, 1],
  composePatches: [2, 2],
  diffLaws: [2, 2],
  validateScenePatch: [1, 1],
  applyScenePatch: [2, 2],
  invertScenePatch: [1, 1],
  composeScenePatches: [2, 2],
  diffSceneLaws: [2, 2],
  validateProfiles: [1, 1],
  judge: [3, 3],
  conforms: [3, 3],
  validateSceneProfiles: [1, 1],
  judgeBody: [3, 3],
  conformsBody: [3, 3],
  judgeScene: [3, 3],
  conformsScene: [3, 3]
};

const VALIDATIONS = new Set<V2Operation>([
  "validatePatch",
  "validateScenePatch",
  "validateProfiles",
  "validateSceneProfiles"
]);
const FOLD_RESULTS = new Set<V2Operation>(["applyPatch", "diffLaws", "applyScenePatch", "diffSceneLaws"]);
const JUDGMENTS = new Set<V2Operation>(["judge", "judgeBody", "judgeScene"]);
const BOOLEANS = new Set<V2Operation>(["conforms", "conformsBody", "conformsScene"]);

/** Load one corpus while retaining duplicate-key detection. */
export function loadCorpusFile(path: string | URL): V2Corpus {
  const label = path instanceof URL ? path.pathname : path;
  return parseCorpusJson(readFileSync(path, "utf8"), label);
}

/** Load and merge selected files, rejecting ids repeated across file boundaries. */
export function loadCorpusFiles(paths: readonly (string | URL)[]): V2Corpus {
  if (paths.length === 0) throw new Error("at least one corpus file is required");
  const cases: V2Case[] = [];
  const seen = new Set<string>();
  for (const path of paths) {
    for (const testCase of loadCorpusFile(path).cases) {
      if (seen.has(testCase.id)) throw new Error(`duplicate case id ${JSON.stringify(testCase.id)} across selected files`);
      seen.add(testCase.id);
      cases.push(testCase);
    }
  }
  return { corpus: V2_CORPUS, cases };
}

export function parseCorpusJson(source: string, label = "<corpus>"): V2Corpus {
  return validateCorpusEnvelope(new StrictJsonParser(source, label).parse(), label);
}

/** Verify each rule fragment against the explicit anchors in its subject's spec. */
export function assertRuleAnchorsExist(
  corpus: V2Corpus,
  specSources: Readonly<Partial<Record<V2Subject, string>>>
): void {
  const anchorsBySubject = new Map<V2Subject, ReadonlySet<string>>();
  for (const testCase of corpus.cases) {
    let anchors = anchorsBySubject.get(testCase.subject);
    if (anchors === undefined) {
      const source = specSources[testCase.subject];
      if (source === undefined) throw new Error(`missing specification source for ${testCase.subject}`);
      anchors = explicitAnchors(source, testCase.subject);
      anchorsBySubject.set(testCase.subject, anchors);
    }
    const fragment = testCase.rule.slice(testCase.rule.indexOf("#") + 1);
    if (!anchors.has(fragment)) throw new Error(`${testCase.id}: missing normative anchor #${fragment}`);
  }
}

function explicitAnchors(source: string, subject: V2Subject): ReadonlySet<string> {
  const anchors = new Set<string>();
  for (const match of source.matchAll(/<a\s+id=["']([a-z0-9-]+)["']\s*><\/a>/g)) {
    const anchor = match[1] as string;
    if (anchors.has(anchor)) throw new Error(`${subject}: duplicate explicit anchor #${anchor}`);
    anchors.add(anchor);
  }
  return anchors;
}

/** Catch a public API's checked precondition throw at the portable boundary. */
export function runCase(testCase: V2Case, dispatch: CaseDispatcher): Projection {
  try {
    return dispatch(testCase);
  } catch {
    return { outcome: "error" };
  }
}

export function runCorpus(corpus: V2Corpus, dispatch: CaseDispatcher): void {
  for (const testCase of corpus.cases) assertCaseMatches(testCase, runCase(testCase, dispatch));
}

export function assertCaseMatches(testCase: V2Case, actual: Projection): void {
  const expected = testCase.expected;
  if (expected.outcome === "invalid" || expected.outcome === "nonconforming") {
    if (actual.outcome !== expected.outcome) {
      throw new Error(`${testCase.id}: expected outcome ${expected.outcome}, actual outcome ${actual.outcome}`);
    }
    const missing = expected.includesErrorPaths.filter((path) => !actual.errorPaths.includes(path));
    if (missing.length > 0) throw new Error(`${testCase.id}: missing expected error paths: ${missing.join(", ")}`);
    return;
  }
  if (!deepEqual(actual, expected)) {
    throw new Error(`${testCase.id}: expected ${JSON.stringify(expected)}, actual ${JSON.stringify(actual)}`);
  }
}

export function projectValidation(errors: readonly ErrorLike[]): ValidProjection | InvalidProjection {
  return errors.length === 0
    ? { outcome: "valid" }
    : { outcome: "invalid", errorPaths: errors.map((error) => error.path) };
}

export function projectResult(result: ResultLike): OkProjection | InvalidProjection {
  return result.ok
    ? { outcome: "ok", value: result.value }
    : { outcome: "invalid", errorPaths: result.errors.map((error) => error.path) };
}

export function projectJudgment(errors: readonly ErrorLike[]): ConformsProjection | NonconformingProjection {
  return errors.length === 0
    ? { outcome: "conforms" }
    : { outcome: "nonconforming", errorPaths: errors.map((error) => error.path) };
}

export function projectValue(value: unknown): OkProjection {
  return { outcome: "ok", value };
}

function validateCorpusEnvelope(value: unknown, label: string): V2Corpus {
  const envelope = requireRecord(value, label);
  requireExactKeys(envelope, ["corpus", "cases"], label);
  if (envelope.corpus !== V2_CORPUS) throw new Error(`${label}: unknown corpus ${JSON.stringify(envelope.corpus)}`);
  if (!Array.isArray(envelope.cases) || envelope.cases.length === 0) {
    throw new Error(`${label}: cases must be a nonempty array`);
  }
  const seen = new Set<string>();
  const cases = envelope.cases.map((entry, index) => validateCase(entry, `${label}: cases[${index}]`));
  for (const testCase of cases) {
    if (seen.has(testCase.id)) throw new Error(`${label}: duplicate case id ${JSON.stringify(testCase.id)}`);
    seen.add(testCase.id);
  }
  return { corpus: V2_CORPUS, cases };
}

function validateCase(value: unknown, path: string): V2Case {
  const entry = requireRecord(value, path);
  requireExactKeys(entry, CASE_KEYS, path);
  if (typeof entry.id !== "string" || !ASCII_CASE_ID.test(entry.id)) throw new Error(`${path}.id is invalid`);
  if (typeof entry.subject !== "string" || !Object.hasOwn(OPERATIONS, entry.subject)) {
    throw new Error(`${path}.subject is unknown`);
  }
  const subject = entry.subject as V2Subject;
  if (typeof entry.rule !== "string" || !RULE.test(entry.rule) || !entry.rule.startsWith(`${subject}#`)) {
    throw new Error(`${path}.rule must be a normative anchor belonging to ${subject}`);
  }
  if (typeof entry.operation !== "string") throw new Error(`${path}.operation is unknown`);
  if (!OPERATIONS[subject].includes(entry.operation as V2Operation)) {
    throw new Error(`${path}.operation ${entry.operation} is incompatible with subject ${subject}`);
  }
  const operation = entry.operation as V2Operation;

  const input = requireRecord(entry.input, `${path}.input`);
  requireExactKeys(input, ["args"], `${path}.input`);
  if (!Array.isArray(input.args)) throw new Error(`${path}.input.args must be an array`);
  const [minimum, maximum] = ARITIES[operation];
  if (input.args.length < minimum || input.args.length > maximum) {
    const requirement = minimum === maximum ? `exactly ${minimum}` : `${minimum} to ${maximum}`;
    throw new Error(`${path}.input.args requires ${requirement} arguments for ${operation}`);
  }
  const expected = validateExpected(operation, entry.expected, `${path}.expected`);
  return { id: entry.id, rule: entry.rule, subject, operation, input: { args: input.args }, expected };
}

function validateExpected(operation: V2Operation, value: unknown, path: string): ExpectedProjection {
  const expected = requireRecord(value, path);
  if (typeof expected.outcome !== "string") throw new Error(`${path}.outcome must be a string`);

  if (VALIDATIONS.has(operation)) {
    if (expected.outcome === "valid") {
      requireExactKeys(expected, ["outcome"], path);
      return { outcome: "valid" };
    }
    if (expected.outcome === "invalid") return invalidExpected(expected, path);
    throw new Error(`${path}.outcome is invalid for operation ${operation}`);
  }

  if (JUDGMENTS.has(operation)) {
    if (expected.outcome === "conforms") {
      requireExactKeys(expected, ["outcome"], path);
      return { outcome: "conforms" };
    }
    if (expected.outcome === "nonconforming") return nonconformingExpected(expected, path);
    if (expected.outcome === "error") return errorExpected(expected, path);
    throw new Error(`${path}.outcome is invalid for operation ${operation}`);
  }

  if (expected.outcome === "error") return errorExpected(expected, path);
  if (FOLD_RESULTS.has(operation) && expected.outcome === "invalid") return invalidExpected(expected, path);
  if (expected.outcome !== "ok") throw new Error(`${path}.outcome is invalid for operation ${operation}`);
  requireExactKeys(expected, ["outcome", "value"], path);
  if (BOOLEANS.has(operation) && typeof expected.value !== "boolean") {
    throw new Error(`${path}.value must be boolean for operation ${operation}`);
  }
  return { outcome: "ok", value: expected.value };
}

function invalidExpected(value: Record<string, unknown>, path: string): ExpectedProjection {
  requireExactKeys(value, ["outcome", "includesErrorPaths"], path);
  return { outcome: "invalid", includesErrorPaths: requireNonemptyUniqueStrings(value.includesErrorPaths, `${path}.includesErrorPaths`) };
}

function nonconformingExpected(value: Record<string, unknown>, path: string): ExpectedProjection {
  requireExactKeys(value, ["outcome", "includesErrorPaths"], path);
  return {
    outcome: "nonconforming",
    includesErrorPaths: requireNonemptyUniqueStrings(value.includesErrorPaths, `${path}.includesErrorPaths`)
  };
}

function errorExpected(value: Record<string, unknown>, path: string): ErrorProjection {
  requireExactKeys(value, ["outcome"], path);
  return { outcome: "error" };
}

function requireRecord(value: unknown, path: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error(`${path} must be an object`);
  return value as Record<string, unknown>;
}

function requireExactKeys(object: Record<string, unknown>, keys: readonly string[], path: string): void {
  const allowed = new Set(keys);
  for (const key of Object.keys(object)) if (!allowed.has(key)) throw new Error(`${path} has unknown key ${JSON.stringify(key)}`);
  for (const key of keys) if (!Object.hasOwn(object, key)) throw new Error(`${path} is missing required key ${JSON.stringify(key)}`);
}

function requireNonemptyUniqueStrings(value: unknown, path: string): string[] {
  if (!Array.isArray(value) || value.length === 0 || value.some((entry) => typeof entry !== "string" || entry.length === 0)) {
    throw new Error(`${path} must be a nonempty array of nonempty strings`);
  }
  if (new Set(value).size !== value.length) throw new Error(`${path} must not contain duplicates`);
  return value as string[];
}

function deepEqual(left: unknown, right: unknown): boolean {
  if (typeof left === "number" && typeof right === "number") return left === right;
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((v, i) => deepEqual(v, right[i]));
  }
  if (left === null || right === null || typeof left !== "object" || typeof right !== "object") return false;
  const a = left as Record<string, unknown>;
  const b = right as Record<string, unknown>;
  const keysA = Object.keys(a).sort();
  const keysB = Object.keys(b).sort();
  return deepEqual(keysA, keysB) && keysA.every((key) => deepEqual(a[key], b[key]));
}

/** Complete JSON parser with duplicate object-key and non-finite number rejection. */
class StrictJsonParser {
  private offset = 0;
  constructor(private readonly source: string, private readonly label: string) {}

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
      Object.defineProperty(result, key, {
        value: this.parseValue(`${path}.${key}`), enumerable: true, configurable: true, writable: true
      });
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
    const start = this.offset++;
    while (this.offset < this.source.length) {
      const character = this.source[this.offset];
      if (character === "\\") { this.offset += 2; continue; }
      if (character === '"') {
        this.offset += 1;
        try { return JSON.parse(this.source.slice(start, this.offset)) as string; }
        catch { this.fail("invalid JSON string"); }
      }
      this.offset += 1;
    }
    this.fail("unterminated JSON string");
  }

  private parseNumber(): number {
    const match = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(this.source.slice(this.offset));
    if (!match) this.fail("invalid JSON number");
    this.offset += match[0].length;
    const value = Number(match[0]);
    if (!Number.isFinite(value)) this.fail("JSON number must be finite");
    if (Number.isInteger(value) && Math.abs(value) > Number.MAX_SAFE_INTEGER) {
      this.fail("JSON integer exceeds the paper-json-portable/v1 portable integer range");
    }
    return value;
  }

  private parseLiteral<T>(spelling: string, value: T): T {
    if (this.source.slice(this.offset, this.offset + spelling.length) !== spelling) this.fail(`expected ${spelling}`);
    this.offset += spelling.length;
    return value;
  }

  private skipWhitespace(): void {
    while ([" ", "\t", "\n", "\r"].includes(this.source[this.offset] ?? "")) this.offset += 1;
  }

  private consume(character: string): boolean {
    if (this.source[this.offset] !== character) return false;
    this.offset += 1;
    return true;
  }

  private fail(message: string): never { throw new Error(`${this.label}:${this.offset}: ${message}`); }
}
