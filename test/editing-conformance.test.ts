/// <reference path="../conformance/typescript/node-shims.d.ts" />

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  assertCaseMatches,
  assertRuleAnchorsExist,
  loadCorpusFiles,
  parseCorpusJson,
  runCase,
  type V2Case
} from "../conformance/typescript/extended_conformance";
import { dispatchEditingCase } from "../conformance/typescript/editing_adapter";

const OK_CASE: V2Case = {
  id: "kernel-connect",
  rule: "paper-doll/v3#connect",
  subject: "paper-doll/v3",
  operation: "connect",
  input: { args: [{}, { vessel: "a", side: "right" }, { vessel: "b", side: "left" }] },
  expected: { outcome: "ok", value: { body: {}, displaced: [] } }
};

describe("v2 conformance envelope", () => {
  it("accepts the exact positional-argument case shape", () => {
    const corpus = parseCorpusJson(JSON.stringify({ corpus: "paper-family-conformance/v2", cases: [OK_CASE] }));
    expect(corpus.cases).toEqual([OK_CASE]);
  });

  it("rejects duplicate object keys before JSON parsing can erase them", () => {
    expect(() =>
      parseCorpusJson(
        '{"corpus":"paper-family-conformance/v2","corpus":"paper-family-conformance/v2","cases":[]}'
      )
    ).toThrow("duplicate object key");
  });

  it("rejects an operation paired with the wrong subject", () => {
    const wrong = { ...OK_CASE, subject: "paperfold/v1", rule: "paperfold/v1#connect" };
    expect(() =>
      parseCorpusJson(JSON.stringify({ corpus: "paper-family-conformance/v2", cases: [wrong] }))
    ).toThrow("incompatible");
  });

  it("rejects malformed operation-specific projections", () => {
    const wrong = { ...OK_CASE, expected: { outcome: "valid" } };
    expect(() =>
      parseCorpusJson(JSON.stringify({ corpus: "paper-family-conformance/v2", cases: [wrong] }))
    ).toThrow("invalid for operation connect");
  });

  it("rejects missing and extra operation arguments while loading", () => {
    for (const args of [OK_CASE.input.args.slice(0, 2), [...OK_CASE.input.args, {}]]) {
      const wrong = { ...OK_CASE, input: { args } };
      expect(() =>
        parseCorpusJson(JSON.stringify({ corpus: "paper-family-conformance/v2", cases: [wrong] }))
      ).toThrow("requires exactly 3 arguments");
    }
  });

  it("accepts both declared arities for operations with an optional terminal argument", () => {
    const declareKind = {
      ...OK_CASE,
      subject: "paperchain/v1",
      rule: "paperchain/v1#operations",
      operation: "declareKind",
      input: { args: [{}, "person"] }
    };
    for (const args of [declareKind.input.args, [...declareKind.input.args, {}]]) {
      expect(() =>
        parseCorpusJson(JSON.stringify({
          corpus: "paper-family-conformance/v2",
          cases: [{ ...declareKind, input: { args } }]
        }))
      ).not.toThrow();
    }
  });

  it("projects a thrown checked precondition as error", () => {
    expect(
      runCase(OK_CASE, () => {
        throw new Error("checked precondition");
      })
    ).toEqual({ outcome: "error" });
  });

  it("compares invalid and nonconforming expected paths as subsets", () => {
    const invalid = {
      ...OK_CASE,
      operation: "validatePatch" as const,
      subject: "paperfold/v1" as const,
      rule: "paperfold/v1#patch-document",
      input: { args: [{}] },
      expected: { outcome: "invalid" as const, includesErrorPaths: ["$.protocol"] }
    };
    expect(() =>
      assertCaseMatches(invalid, { outcome: "invalid", errorPaths: ["$.protocol", "$.entries"] })
    ).not.toThrow();

    const nonconforming = {
      ...OK_CASE,
      operation: "judge" as const,
      subject: "papermold/v1" as const,
      rule: "papermold/v1#judgment",
      input: { args: [{}, {}, "p"] },
      expected: { outcome: "nonconforming" as const, includesErrorPaths: ["$.profiles.p.vessels.head"] }
    };
    expect(() =>
      assertCaseMatches(nonconforming, {
        outcome: "nonconforming",
        errorPaths: ["$.profiles.p.vessels.head", "$.profiles.p.atLeast"]
      })
    ).not.toThrow();
  });

  it("rejects duplicate ids across selected files", () => {
    expect(() =>
      loadCorpusFiles([
        new URL("../conformance/cases/editing-v2.json", import.meta.url),
        new URL("../conformance/cases/editing-v2.json", import.meta.url)
      ])
    ).toThrow("duplicate case id");
  });

  it.each([
    ["9007199254740991", 9007199254740991],
    ["-9007199254740991", -9007199254740991],
    ["1e3", 1000],
    ["0.125", 0.125]
  ])("accepts portable binary64 number %s", (spelling, value) => {
    expect(numericProbe(parseCorpusJson(corpusWithNumber(spelling)).cases[0])).toBe(value);
  });

  it("preserves negative zero while JSON equality treats it by numeric value", () => {
    const value = numericProbe(parseCorpusJson(corpusWithNumber("-0")).cases[0]);
    expect(Object.is(value, -0)).toBe(true);
    assertCaseMatches({ ...OK_CASE, expected: { outcome: "ok", value: 0 } }, { outcome: "ok", value });
  });

  it.each(["9007199254740992", "-9007199254740992", "9007199254740993", "9.007199254740992e15"])(
    "rejects nonportable integral number %s",
    (spelling) => expect(() => parseCorpusJson(corpusWithNumber(spelling))).toThrow("portable integer range")
  );

  it("rejects a binary64 overflow token", () => {
    expect(() => parseCorpusJson(corpusWithNumber("1e309"))).toThrow("finite");
  });
});

function corpusWithNumber(spelling: string): string {
  return JSON.stringify({ ...OK_CASE, input: { args: [{ probe: "NUMBER" }, ...OK_CASE.input.args.slice(1)] } })
    .replace('"NUMBER"', spelling)
    .replace(/^/, '{"corpus":"paper-family-conformance/v2","cases":[')
    .replace(/$/, "]}");
}

function numericProbe(testCase: V2Case | undefined): unknown {
  return (testCase?.input.args[0] as { probe?: unknown } | undefined)?.probe;
}

describe("editing corpus", () => {
  const corpus = loadCorpusFiles([new URL("../conformance/cases/editing-v2.json", import.meta.url)]);

  it("links every rule to an explicit normative anchor", () => {
    assertRuleAnchorsExist(corpus, {
      "paper-doll/v3": readFileSync(new URL("../node_modules/paperdoll/docs/spec.md", import.meta.url), "utf8"),
      "paperchain/v1": readFileSync(new URL("../docs/spec.md", import.meta.url), "utf8")
    });
  });

  for (const testCase of corpus.cases) {
    it(`${testCase.id}: ${testCase.rule}`, () => {
      const before = structuredClone(testCase.input.args);
      const actual = runCase(testCase, dispatchEditingCase);
      assertCaseMatches(testCase, actual);
      expect(testCase.input.args).toEqual(before);
    });
  }
});
