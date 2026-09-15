import { describe, expect, it } from "vitest";

import {
  PAPERCHAIN_PROTOCOL,
  validatePortableJson,
  validateScene,
  type Scene
} from "../src/index";

describe("paper-json-portable/v1 through paperchain", () => {
  it("keeps dialect validity separate from portable numeric validity", () => {
    const scene: Scene = {
      protocol: PAPERCHAIN_PROTOCOL,
      bodies: {},
      kinds: { limited: { fromMax: 9_007_199_254_740_992, toMax: 9_007_199_254_740_991 } },
      relations: []
    };

    expect(validateScene(scene)).toEqual([]);
    expect(validatePortableJson(scene)).toEqual([
      {
        path: "$.kinds.limited.fromMax",
        message: "Integer must be between -9007199254740991 and 9007199254740991 for paper-json-portable/v1."
      }
    ]);
  });

  it("checks opaque data recursively inside scene bodies", () => {
    const scene: Scene = {
      protocol: PAPERCHAIN_PROTOCOL,
      bodies: {
        alice: {
          root: "root",
          vessels: {
            root: { contains: [{ kind: "item", data: { exactCounter: 9_007_199_254_740_992 } }] }
          }
        }
      },
      kinds: {},
      relations: []
    };

    expect(validateScene(scene)).toEqual([]);
    expect(validatePortableJson(scene).map((error) => error.path)).toEqual([
      "$.bodies.alice.vessels.root.contains.0.data.exactCounter"
    ]);
  });
});
