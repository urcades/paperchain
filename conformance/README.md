# Paper family conformance corpus

This directory is the shared, language-neutral executable corpus for
`paper-doll/v3` and `paperchain/v1`. Both runners read the checked-in JSON
files directly; neither runner generates expectations from the other.

## Run it from a source checkout

```sh
npm run test:conformance:ts
npm run test:conformance:python
```

The TypeScript command and `typescript/paper_conformance.ts` are verification
tools for a Paperchain source checkout: the adapter imports the checkout's
`src/paperchain.ts`, and its Vitest entry lives in `test/`. The packaged
TypeScript source is therefore instructional, not a standalone published CLI.

The packaged corpus and standard-library-only Python adapter are usable from an
unpacked release with:

```sh
python3 -m conformance.python.paper_conformance conformance/cases/*.json
```

The fixture contract is described by `corpus-v1.schema.json`, with cases in
`cases/`.

## Case contract

Each file has this envelope:

```json
{
  "corpus": "paper-family-conformance/v1",
  "cases": [
    {
      "id": "paperdoll-v3.validate.minimal-valid",
      "rule": "paper-doll/v3#document-grammar",
      "subject": "paper-doll/v3",
      "operation": "validateDocument",
      "input": {
        "document": {
          "protocol": "paper-doll/v3",
          "body": { "root": "root", "vessels": { "root": {} } }
        }
      },
      "expected": { "outcome": "valid" }
    }
  ]
}
```

Case IDs are unique ASCII identifiers. `rule` points to a stable normative
heading. The five initial operations are `validateDocument`, `resolveAddress`,
`deriveLayout`, `validateScene`, and `resolveSceneAddress`. Runners reject
unknown operations, subjects, outcomes, extra envelope members, and duplicate
JSON object keys.

Validation failures use `includesErrorPaths`: each listed path must occur, but
an implementation may report additional violations. Malformed address syntax
produces `error`; a well-formed path that does not resolve produces
`unresolved`.

Resolved values deliberately omit TypeScript object back-references. A vessel
is `{kind, vesselId}`. An element is
`{kind, vesselId, index, element}`. JSON objects compare without member-order
significance; arrays retain order.

## Layout projection

Layout results have `{figure, free, connections}`. `figure` maps vessel IDs to
`{x, y}`. Free-vessel IDs are sorted by ASCII code-point order. Every undirected
connection is oriented by the endpoint key `vessel + ":" + side`, smaller key
first, and connections are sorted by their `(from-key, to-key)` pair. This is
the only set-like array normalization in corpus v1.

## Integer portability boundary

Paperchain specifies non-negative integer multiplicity budgets without a
portable maximum. Corpus v1 keeps accepted integer fixtures within
`0..9007199254740991`, the exactly representable JavaScript integer range.
Values above that range are intentionally uncovered. This fixture range is not
a new protocol bound; a future protocol revision must decide their behavior
before conformance cases are added.
