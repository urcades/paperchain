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
python3 -m conformance.python.paper_conformance conformance/cases/paperdoll-v3.json conformance/cases/paperchain-v1.json
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
Values above that range are intentionally uncovered by corpus v1. This fixture
range is not a new protocol bound. Corpus v2 enforces the additive
`paper-json-portable/v1` profile described below.


## Extended editing, patch, and judgment corpus (v2)

`paper-family-conformance/v2` adds the seven Doll edits, six Chain edits plus
`relationsAt`, Fold body/scene patch validation, application, inversion,
composition and diff laws, and Mold body/scene validation and judgments.
The exact operation catalog and envelopes are in `corpus-v2.schema.json`.
Each input is `{"args": [...]}` in the corresponding public API argument order.
The existing v1 corpus and runner retain their original behavior.

```sh
npm run test:conformance:extended
python3 -m unittest discover -s conformance/python -t . -p 'test_*.py'
```

The independent standard-library Python modules are `paper_edits.py`,
`paperfold.py`, and `papermold.py`; they implement protocol behavior from the
specifications without invoking Node. Fold and Mold ship their own fixture
files and TypeScript adapters. From an installed Fold or Mold package:

```sh
npm run test:conformance:python
```

Unlike the v1 source adapter, the generic v2 transport is compiled and available
as `paperchain/conformance/v2`. It exports strict loading, expected-result
comparison, and projection helpers. Protocol dispatch stays in each repository's
adapter; the transport introduces no upward production dependency from Chain.

### Results and equality

- Value-returning operations project `{"outcome":"ok","value":...}`.
- Validators project `valid` or `invalid`; failed Fold results project `invalid`.
- Checked precondition exceptions project `error`, distinct from a failed result.
- Mold judgments project `conforms` or `nonconforming`; boolean `conforms*`
  operations retain their boolean value.
- Expected `invalid` and `nonconforming` records use nonempty, unique
  `includesErrorPaths`. Error wording and extra diagnostic paths are not compared.

Objects compare without member order; arrays remain ordered, and booleans are
not numbers. Doll editing connection return records normalize undirected endpoint
orientation and sort displaced connections. Chain relations retain their stored
orientation. `diffLaws` and `diffSceneLaws` check application, inversion, and
composition against canonical source/target values without requiring identical
diff algorithms. Fold also runs seeded cross-language checks: Python applies
TypeScript-generated patches and inverses, and TypeScript applies Python's.

### Portable numeric evidence

Every v2 corpus number follows `paper-json-portable/v1`: JSON number tokens are
interpreted as finite IEEE 754 binary64 values, and integral results must be in
`[-9007199254740991, 9007199254740991]`. This applies recursively, including opaque
`data`. Negative zero equals zero. Python normalizes safe integral values to
`int` for indexing, while retaining booleans as booleans. Fractions have binary64
rounding semantics; the profile does not promise exact decimal arithmetic.

Unsafe integers and overflow are rejected by the corpus loader, rather than
being used as misleading evidence of agreement. Current dialect validators
remain broader; use the separately exported `validatePortableJson` to request
this additional verdict. Exact larger integers in opaque data can be encoded as
decimal strings. These strings do not replace existing numeric control fields.
