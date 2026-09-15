import { describe, expect, it } from "vitest";
import {
  assertCaseMatches,
  loadCorpusFile,
  parseCorpusJson,
  runCase,
  type ConformanceCase,
  type Corpus
} from "../conformance/typescript/paper_conformance";

const CASE_FILES = [
  new URL("../conformance/cases/paperdoll-v3.json", import.meta.url),
  new URL("../conformance/cases/paperchain-v1.json", import.meta.url)
];

function minimalCase(overrides: Partial<ConformanceCase> = {}): ConformanceCase {
  return {
    id: "paperdoll-v3.validate.minimal",
    rule: "paper-doll/v3#document-grammar",
    subject: "paper-doll/v3",
    operation: "validateDocument",
    input: {
      document: {
        protocol: "paper-doll/v3",
        body: { root: "root", vessels: { root: {} } }
      }
    },
    expected: { outcome: "valid" },
    ...overrides
  } as ConformanceCase;
}

function corpusJson(cases: unknown[]): string {
  return JSON.stringify({ corpus: "paper-family-conformance/v1", cases });
}

describe("shared paper-family conformance corpus", () => {
  it("dispatches every checked-in case and matches its language-neutral expectation", () => {
    const corpora = CASE_FILES.map(loadCorpusFile);
    const ids = new Set<string>();

    for (const corpus of corpora) {
      for (const testCase of corpus.cases) {
        expect(ids.has(testCase.id), `duplicate case id ${testCase.id}`).toBe(false);
        ids.add(testCase.id);
        const actual = runCase(testCase);
        expect(() => assertCaseMatches(testCase, actual), testCase.id).not.toThrow();
      }
    }

    expect(ids.size).toBe(49);
  });

  it("rejects duplicate JSON object keys before JSON.parse can discard one", () => {
    const duplicateRootKey =
      '{"corpus":"paper-family-conformance/v1","corpus":"paper-family-conformance/v1","cases":[]}';
    const duplicateNestedKey =
      '{"corpus":"paper-family-conformance/v1","cases":[{"id":"a","id":"b"}]}';

    expect(() => parseCorpusJson(duplicateRootKey, "duplicate-root.json")).toThrow(/duplicate.*corpus/i);
    expect(() => parseCorpusJson(duplicateNestedKey, "duplicate-nested.json")).toThrow(/duplicate.*id/i);
  });

  it("rejects malformed corpus and case envelopes instead of skipping them", () => {
    expect(() =>
      parseCorpusJson('{"corpus":"paper-family-conformance/v1","cases":[]}', "empty-cases.json")
    ).toThrow(/cases/);
    expect(() => parseCorpusJson('{"corpus":"paper-family-conformance/v1"}', "missing-cases.json")).toThrow(
      /cases/
    );
    expect(() =>
      parseCorpusJson(
        '{"corpus":"paper-family-conformance/v1","cases":[],"ignored":true}',
        "extra-root-key.json"
      )
    ).toThrow(/ignored/);
    expect(() =>
      parseCorpusJson(corpusJson([{ ...minimalCase(), ignored: true }]), "extra-case-key.json")
    ).toThrow(/ignored/);
    expect(() => parseCorpusJson(corpusJson([minimalCase(), minimalCase()]), "duplicate-id.json")).toThrow(
      /duplicate case id/i
    );
  });

  it("rejects unknown subjects, operations, outcome shapes, and incompatible envelopes", () => {
    const invalidCases: Array<[string, unknown]> = [
      ["subject", minimalCase({ subject: "paperfold/v1" as ConformanceCase["subject"] })],
      ["operation", minimalCase({ operation: "skip" as ConformanceCase["operation"] })],
      [
        "outcome",
        minimalCase({ expected: { outcome: "maybe" } as unknown as ConformanceCase["expected"] })
      ],
      [
        "operation input",
        minimalCase({ operation: "resolveAddress", input: { document: {} } } as Partial<ConformanceCase>)
      ],
      [
        "subject operation",
        minimalCase({ subject: "paperchain/v1", operation: "validateDocument" } as Partial<ConformanceCase>)
      ],
      [
        "validation outcome",
        minimalCase({ expected: { outcome: "unresolved" } as ConformanceCase["expected"] })
      ]
    ];

    for (const [label, testCase] of invalidCases) {
      expect(() => parseCorpusJson(corpusJson([testCase]), `${label}.json`), label).toThrow();
    }
  });

  it("fails when a valid case verdict is deliberately flipped", () => {
    const testCase = minimalCase({
      expected: { outcome: "invalid", includesErrorPaths: ["$.body.root"] }
    });
    const actual = runCase(testCase);

    expect(actual).toEqual({ outcome: "valid" });
    expect(() => assertCaseMatches(testCase, actual)).toThrow(/expected.*invalid.*actual.*valid/i);
  });

  it("compares objects without member-order significance while preserving array order", () => {
    const testCase = minimalCase({
      operation: "resolveAddress",
      input: {
        body: {
          root: "root",
          vessels: { root: { contains: [{ kind: "item", id: "key", data: { first: 1, second: 2 } }] } }
        },
        address: "root/key"
      },
      expected: {
        value: {
          element: { data: { second: 2, first: 1 }, id: "key", kind: "item" },
          index: 0,
          vesselId: "root",
          kind: "element"
        },
        outcome: "resolved"
      }
    } as Partial<ConformanceCase>);

    const actual = runCase(testCase);
    expect(() => assertCaseMatches(testCase, actual)).not.toThrow();

    const arrayCase = minimalCase({
      operation: "resolveAddress",
      input: {
        body: {
          root: "root",
          vessels: { root: { contains: [{ kind: "item", id: "key", data: [1, 2] }] } }
        },
        address: "root/key"
      },
      expected: {
        outcome: "resolved",
        value: {
          kind: "element",
          vesselId: "root",
          index: 0,
          element: { kind: "item", id: "key", data: [2, 1] }
        }
      }
    } as Partial<ConformanceCase>);
    expect(() => assertCaseMatches(arrayCase, runCase(arrayCase))).toThrow();
  });

  it("uses JSON numeric-value equality while keeping booleans distinct from numbers", () => {
    const expectedZero = minimalCase({
      operation: "resolveAddress",
      input: { body: { root: "root", vessels: { root: {} } }, address: "root" },
      expected: {
        outcome: "resolved",
        value: {
          kind: "element",
          vesselId: "root",
          index: 0,
          element: { kind: "item", data: 0 }
        }
      }
    } as Partial<ConformanceCase>);

    expect(() =>
      assertCaseMatches(expectedZero, {
        outcome: "resolved",
        value: {
          kind: "element",
          vesselId: "root",
          index: 0,
          element: { kind: "item", data: -0 }
        }
      })
    ).not.toThrow();

    const expectedOne = {
      ...expectedZero,
      expected: {
        outcome: "resolved",
        value: {
          kind: "element",
          vesselId: "root",
          index: 0,
          element: { kind: "item", data: 1 }
        }
      }
    } as ConformanceCase;
    expect(() =>
      assertCaseMatches(expectedOne, {
        outcome: "resolved",
        value: {
          kind: "element",
          vesselId: "root",
          index: 0,
          element: { kind: "item", data: true }
        }
      })
    ).toThrow();
  });

  it("rejects the shared malformed-envelope parity vectors", () => {
    const malformed = [
      minimalCase({ id: "bad@id" }),
      minimalCase({ rule: "anything" }),
      minimalCase({ expected: { outcome: "invalid", includesErrorPaths: [] } }),
      minimalCase({ expected: { outcome: "invalid", includesErrorPaths: ["$.root", "$.root"] } }),
      minimalCase({ operation: "resolveAddress", input: { body: [], address: "root" } } as Partial<ConformanceCase>),
      minimalCase({ operation: "resolveAddress", input: { body: {}, address: 7 } } as Partial<ConformanceCase>),
      minimalCase({
        subject: "paperchain/v1",
        operation: "resolveSceneAddress",
        rule: "paperchain/v1#law-4-existence",
        input: { scene: [], address: "alice/root" }
      } as Partial<ConformanceCase>)
    ];

    for (const [index, testCase] of malformed.entries()) {
      expect(() => parseCorpusJson(corpusJson([testCase]), `parity-${index}.json`)).toThrow();
    }
  });

  it("accepts the schema's general strings and numeric layout coordinates", () => {
    const layout = minimalCase({
      operation: "deriveLayout",
      input: { body: { root: "root", vessels: { root: {} } } },
      expected: {
        outcome: "layout",
        value: {
          figure: { "": { x: 0.5, y: -0 } },
          free: [""],
          connections: [
            {
              from: { vessel: "bad/id", side: "left" },
              to: { vessel: "root", side: "right" }
            }
          ]
        }
      }
    } as Partial<ConformanceCase>);

    expect(() => parseCorpusJson(corpusJson([layout]), "schema-projection-shapes.json")).not.toThrow();
  });
});
