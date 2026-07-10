export {
  PAPERCHAIN_PROTOCOL,
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
  validateScene
} from "./paperchain.js";

export type {
  BodyName,
  KindDeclaration,
  KindId,
  Relation,
  Scene,
  SceneAddress,
  SplitSceneAddress
} from "./paperchain.js";

export { formatProtocolErrors } from "paperdoll";

export type { Body, ProtocolError, ResolvedAddress, Result } from "paperdoll";
