import type { Scene } from "../src/paperchain";
import { PAPERCHAIN_PROTOCOL } from "../src/paperchain";

// The pre-RFC's motivating specimen: two humans holding hands. Neither hand
// contains the other, and a port connection would fuse the bodies into one
// collision-checked figure. The edge with no geometric consequences is a
// relation.
export const HOLDING_HANDS_SCENE: Scene = {
  protocol: PAPERCHAIN_PROTOCOL,
  bodies: {
    alice: {
      root: "torso",
      vessels: {
        torso: {
          ports: {
            left: { vessel: "left-hand", side: "right" },
            right: { vessel: "right-hand", side: "left" }
          }
        },
        "left-hand": {
          accepts: [{ kind: "item" }],
          contains: [{ kind: "item", type: "weapon", id: "steel-dagger" }],
          ports: { right: { vessel: "torso", side: "left" } }
        },
        "right-hand": {
          accepts: [{ kind: "item" }],
          ports: { left: { vessel: "torso", side: "right" } }
        }
      }
    },
    bob: {
      root: "torso",
      vessels: {
        torso: {
          ports: {
            left: { vessel: "left-hand", side: "right" },
            right: { vessel: "right-hand", side: "left" },
            bottom: { vessel: "back", side: "top" }
          }
        },
        "left-hand": {
          accepts: [{ kind: "item" }],
          ports: { right: { vessel: "torso", side: "left" } }
        },
        "right-hand": {
          accepts: [{ kind: "item" }],
          ports: { left: { vessel: "torso", side: "right" } }
        },
        back: {
          accepts: [{ kind: "item", type: "back" }],
          contains: [
            {
              kind: "item",
              type: "back",
              id: "field-pack",
              body: {
                root: "main-pocket",
                vessels: {
                  "main-pocket": {
                    accepts: [{ kind: "item" }],
                    contains: [{ kind: "item", type: "tool", id: "rope" }]
                  }
                }
              }
            }
          ],
          ports: { top: { vessel: "torso", side: "bottom" } }
        }
      }
    }
  },
  kinds: {
    holds: { symmetric: false, fromMax: 1 },
    "holding-hands": { symmetric: true, fromMax: 1 }
  },
  relations: [{ kind: "holding-hands", from: "alice/left-hand", to: "bob/right-hand" }]
};

// The pre-RFC's non-example: trading. Alice and Bob exchange items via a
// trading desk — a third body with escrow vessels. Anything expressible as
// "X is in/on Y" is plain paperdoll; trading needs zero relations.
export const TRADING_DESK_SCENE: Scene = {
  protocol: PAPERCHAIN_PROTOCOL,
  bodies: {
    alice: {
      root: "torso",
      vessels: {
        torso: { ports: { left: { vessel: "left-hand", side: "right" } } },
        "left-hand": {
          accepts: [{ kind: "item" }],
          contains: [{ kind: "item", type: "trade-good", id: "amber" }],
          ports: { right: { vessel: "torso", side: "left" } }
        }
      }
    },
    bob: {
      root: "torso",
      vessels: {
        torso: { ports: { right: { vessel: "right-hand", side: "left" } } },
        "right-hand": {
          accepts: [{ kind: "item" }],
          contains: [{ kind: "item", type: "trade-good", id: "flint" }],
          ports: { left: { vessel: "torso", side: "right" } }
        }
      }
    },
    desk: {
      root: "counter",
      vessels: {
        counter: {
          ports: {
            left: { vessel: "offer-tray", side: "right" },
            right: { vessel: "escrow", side: "left" }
          }
        },
        "offer-tray": {
          accepts: [{ kind: "item", type: "trade-good" }],
          ports: { right: { vessel: "counter", side: "left" } }
        },
        escrow: {
          accepts: [],
          ports: { left: { vessel: "counter", side: "right" } }
        }
      }
    }
  },
  kinds: {},
  relations: []
};
