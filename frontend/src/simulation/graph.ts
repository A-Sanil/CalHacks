import type { GraphEdge, GraphNode, HazardScenario, SimulationResult } from '../types'

export const GRAPH_NODES: GraphNode[] = [
  { id: 0, x: 72, y: 72, label: 'N00' }, { id: 1, x: 178, y: 86, label: 'N01' },
  { id: 2, x: 282, y: 68, label: 'N02' }, { id: 3, x: 386, y: 91, label: 'N03' },
  { id: 4, x: 495, y: 65, label: 'N04' }, { id: 5, x: 620, y: 83, label: 'ECHO' },
  { id: 6, x: 90, y: 184, label: 'N06' }, { id: 7, x: 190, y: 195, label: 'N07' },
  { id: 8, x: 300, y: 176, label: 'N08' }, { id: 9, x: 402, y: 204, label: 'N09' },
  { id: 10, x: 510, y: 178, label: 'N10' }, { id: 11, x: 628, y: 196, label: 'N11' },
  { id: 12, x: 68, y: 300, label: 'N12' }, { id: 13, x: 178, y: 286, label: 'N13' },
  { id: 14, x: 288, y: 313, label: 'N14' }, { id: 15, x: 395, y: 287, label: 'N15' },
  { id: 16, x: 505, y: 315, label: 'FOXTROT' }, { id: 17, x: 630, y: 292, label: 'N17' },
  { id: 18, x: 82, y: 430, label: 'BASE' }, { id: 19, x: 190, y: 412, label: 'N19' },
  { id: 20, x: 300, y: 438, label: 'N20' }, { id: 21, x: 410, y: 408, label: 'N21' },
  { id: 22, x: 518, y: 433, label: 'N22' }, { id: 23, x: 625, y: 408, label: 'N23' },
]

const links: Array<[number, number]> = [
  [0,1],[1,2],[2,3],[3,4],[4,5], [6,7],[7,8],[8,9],[9,10],[10,11],
  [12,13],[13,14],[14,15],[15,16],[16,17], [18,19],[19,20],[20,21],[21,22],[22,23],
  [0,6],[6,12],[12,18], [1,7],[7,13],[13,19], [2,8],[8,14],[14,20],
  [3,9],[9,15],[15,21], [4,10],[10,16],[16,22], [5,11],[11,17],[17,23],
  [18,13],[13,8],[8,3], [19,14],[14,9],[9,4], [20,15],[15,10],[10,5],
  [12,7],[7,2], [21,16],[16,11],
]

const point = (id: number) => GRAPH_NODES[id]
const distance = (a: number, b: number) => Math.round(Math.hypot(point(a).x - point(b).x, point(a).y - point(b).y) / 10)

export const GRAPH_EDGES: GraphEdge[] = links.map(([from, to]) => ({ from, to, weight: distance(from, to) }))

const segmentTouchesHazard = (edge: GraphEdge, scenario: HazardScenario) => {
  const start = point(edge.from)
  const end = point(edge.to)
  const dx = end.x - start.x
  const dy = end.y - start.y
  const lengthSquared = dx * dx + dy * dy
  const projection = lengthSquared === 0 ? 0 : Math.max(0, Math.min(1,
    ((scenario.hazard.x - start.x) * dx + (scenario.hazard.y - start.y) * dy) / lengthSquared,
  ))
  const closestX = start.x + projection * dx
  const closestY = start.y + projection * dy
  // Small buffer treats the drawn road width as part of the hazard boundary.
  return Math.hypot(closestX - scenario.hazard.x, closestY - scenario.hazard.y) <= scenario.hazard.radius + 5
}

export function hazardBlockedEdges(scenario: HazardScenario): Array<[number, number]> {
  const blocked = new Map<string, [number, number]>()
  for (const [from, to] of scenario.blockedEdges) blocked.set(edgeKey(from, to), [from, to])
  for (const edge of GRAPH_EDGES) {
    if (segmentTouchesHazard(edge, scenario)) blocked.set(edgeKey(edge.from, edge.to), [edge.from, edge.to])
  }
  return [...blocked.values()]
}

export const HAZARD_SCENARIOS: HazardScenario[] = [
  { id: 1, name: 'Fireline expansion', description: 'Primary diagonal corridor closed', blockedEdges: [[13,8],[8,3]], penalties: [], hazard: { x: 285, y: 205, radius: 76 } },
  { id: 2, name: 'Bridge collapse', description: 'Central crossing is impassable', blockedEdges: [[14,9],[9,4]], penalties: [], hazard: { x: 390, y: 230, radius: 60 } },
  { id: 3, name: 'Heavy smoke', description: 'Visibility reduces east corridor speed', blockedEdges: [], penalties: [{ edge: [15,10], multiplier: 4 }, { edge: [10,5], multiplier: 3 }], hazard: { x: 515, y: 205, radius: 90 } },
  { id: 4, name: 'Road debris', description: 'Southern launch route partially blocked', blockedEdges: [[18,19],[19,14]], penalties: [{ edge: [12,13], multiplier: 2 }], hazard: { x: 175, y: 382, radius: 64 } },
  { id: 5, name: 'Wind shift', description: 'Fire pushes northeast across two roads', blockedEdges: [[8,9],[3,4],[4,5]], penalties: [{ edge: [9,10], multiplier: 2.5 }], hazard: { x: 430, y: 120, radius: 92 } },
  { id: 6, name: 'Multi-edge failure', description: 'Three simultaneous closures reported', blockedEdges: [[13,8],[14,9],[15,10]], penalties: [{ edge: [9,10], multiplier: 3 }], hazard: { x: 345, y: 240, radius: 105 } },
  { id: 7, name: 'Worst-case surge', description: 'Fire and congestion isolate direct routes', blockedEdges: [[13,8],[8,3],[14,9],[10,5]], penalties: [{ edge: [15,10], multiplier: 5 }, { edge: [4,5], multiplier: 4 }], hazard: { x: 410, y: 185, radius: 120 } },
]

const edgeKey = (a: number, b: number) => a < b ? `${a}-${b}` : `${b}-${a}`

export function runSimulation(scenario: HazardScenario): SimulationResult {
  const startTime = performance.now()
  const effectiveBlockedEdges = hazardBlockedEdges(scenario)
  const blocked = new Set(effectiveBlockedEdges.map(([a, b]) => edgeKey(a, b)))
  const penalties = new Map(scenario.penalties.map(({ edge: [a, b], multiplier }) => [edgeKey(a, b), multiplier]))
  const distances = new Map<number, number>(GRAPH_NODES.map((node) => [node.id, Infinity]))
  const previous = new Map<number, number>()
  const unvisited = new Set(GRAPH_NODES.map((node) => node.id))
  let evaluated = 0
  distances.set(18, 0)

  while (unvisited.size) {
    let current = -1
    let currentDistance = Infinity
    for (const id of unvisited) {
      const candidate = distances.get(id) ?? Infinity
      if (candidate < currentDistance) { current = id; currentDistance = candidate }
    }
    if (current === -1 || current === 5) break
    unvisited.delete(current)
    evaluated += 1

    for (const edge of GRAPH_EDGES) {
      const neighbor = edge.from === current ? edge.to : edge.to === current ? edge.from : -1
      if (neighbor === -1 || !unvisited.has(neighbor) || blocked.has(edgeKey(current, neighbor))) continue
      const candidate = currentDistance + edge.weight * (penalties.get(edgeKey(current, neighbor)) ?? 1)
      if (candidate < (distances.get(neighbor) ?? Infinity)) {
        distances.set(neighbor, candidate)
        previous.set(neighbor, current)
      }
    }
  }

  const path = [5]
  while (path[0] !== 18 && previous.has(path[0])) path.unshift(previous.get(path[0])!)
  const svgPath = path[0] === 18 ? path.map((id, index) => `${index ? 'L' : 'M'} ${point(id).x} ${point(id).y}`).join(' ') : ''

  return {
    scenarioId: scenario.id,
    name: scenario.name,
    path,
    svgPath,
    routeCost: Math.round(distances.get(5) ?? 0),
    nodesEvaluated: evaluated,
    blockedEdges: effectiveBlockedEdges.length,
    solveTimeMs: Math.max(1, Math.round(performance.now() - startTime)),
  }
}
