import {
  connect,
  deleteVessel,
  disconnect,
  insertElement,
  insertVessel,
  moveElement,
  removeElement,
  type Body,
  type Connection,
  type ContainedElement,
  type DeleteVesselOptions,
  type Endpoint,
  type InsertVesselOptions,
  type Vessel
} from "paperdoll";
import {
  addRelation,
  declareKind,
  deleteBody,
  deleteKind,
  insertBody,
  relationsAt,
  removeRelation,
  type KindDeclaration,
  type Relation,
  type Scene
} from "../../src/index";
import { projectValue, type CaseDispatcher } from "./extended_conformance";

/** Public-API dispatcher for the editing subset of corpus v2. */
export const dispatchEditingCase: CaseDispatcher = (testCase) => {
  const args = testCase.input.args;
  switch (testCase.operation) {
    case "connect": {
      const result = connect(args[0] as Body, args[1] as Endpoint, args[2] as Endpoint);
      return projectValue({ body: result.body, displaced: normalizeConnectionSet(result.displaced) });
    }
    case "disconnect": {
      const result = disconnect(args[0] as Body, args[1] as Endpoint);
      return projectValue({ body: result.body, removed: normalizeNullableConnection(result.removed) });
    }
    case "insertVessel": {
      const result = insertVessel(args[0] as Body, args[1] as Omit<Vessel, "ports">, args[2] as InsertVesselOptions | undefined);
      return projectValue({ ...result, bridged: normalizeNullableConnection(result.bridged) });
    }
    case "deleteVessel": {
      const result = deleteVessel(args[0] as Body, args[1] as string, args[2] as DeleteVesselOptions | undefined);
      return projectValue({ ...result, collapsed: normalizeNullableConnection(result.collapsed) });
    }
    case "insertElement":
      return projectValue(insertElement(args[0] as Body, args[1] as string, args[2] as ContainedElement, args[3] as number | undefined));
    case "removeElement":
      return projectValue(removeElement(args[0] as Body, args[1] as string, args[2] as number));
    case "moveElement":
      return projectValue(moveElement(args[0] as Body, args[1] as string, args[2] as number, args[3] as string));
    case "declareKind":
      return projectValue(declareKind(args[0] as Scene, args[1] as string, args[2] as KindDeclaration | undefined));
    case "deleteKind":
      return projectValue(deleteKind(args[0] as Scene, args[1] as string));
    case "insertBody":
      return projectValue(insertBody(args[0] as Scene, args[1] as string, args[2] as Body));
    case "deleteBody":
      return projectValue(deleteBody(args[0] as Scene, args[1] as string));
    case "addRelation":
      return projectValue(addRelation(args[0] as Scene, args[1] as Relation));
    case "removeRelation":
      return projectValue(removeRelation(args[0] as Scene, args[1] as Relation));
    case "relationsAt":
      return projectValue(relationsAt(args[0] as Scene, args[1] as string));
    default:
      throw new Error(`Unsupported editing operation ${testCase.operation}`);
  }
};

export function normalizeConnection(connection: Connection): Connection {
  return endpointKey(connection.from) <= endpointKey(connection.to)
    ? structuredClone(connection)
    : { from: structuredClone(connection.to), to: structuredClone(connection.from) };
}

function normalizeNullableConnection(connection: Connection | null): Connection | null {
  return connection === null ? null : normalizeConnection(connection);
}

function normalizeConnectionSet(connections: readonly Connection[]): Connection[] {
  return connections.map(normalizeConnection).sort((left, right) => {
    const from = compareAscii(endpointKey(left.from), endpointKey(right.from));
    return from || compareAscii(endpointKey(left.to), endpointKey(right.to));
  });
}

function endpointKey(endpoint: Endpoint): string {
  return `${endpoint.vessel}:${endpoint.side}`;
}

function compareAscii(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}
