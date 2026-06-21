import { GRAPH_EDGES, GRAPH_NODES } from './graph'

export type EdgeCondition = {
  risk: number
  timeFactor: number
  reason: string
}

export type EdgeConditions = Record<string, EdgeCondition>

export type MissionEvent = {
  tick: number
  title: string
  detail: string
  edges: Array<[number, number]>
  risk: number
  timeFactor: number
}

export type MissionPlan = {
  path: number[]
  visitOrder: number[]
  weightedCost: number
  travelTime: number
  riskCost: number
}

export const START_NODE = 18
export const REQUIRED_SITES = [0, 2, 5, 11, 16, 22]
export const REROUTE_INTERVAL = 4

export const MISSION_EVENTS: MissionEvent[] = [
  {
    tick: 4,
    title: 'Smoke reduces visibility',
    detail: 'Travel time and risk increased on the southeast corridor.',
    edges: [[21, 22], [22, 16], [16, 17]],
    risk: 0.62,
    timeFactor: 2.1,
  },
  {
    tick: 8,
    title: 'Road damage reported',
    detail: 'The eastern connector is now slow and high-risk.',
    edges: [[16, 11], [10, 11], [11, 17]],
    risk: 0.82,
    timeFactor: 2.8,
  },
  {
    tick: 12,
    title: 'Wind shifts fire north',
    detail: 'Approaches to the final site receive severe risk penalties.',
    edges: [[10, 5], [4, 5], [5, 11]],
    risk: 0.94,
    timeFactor: 3.4,
  },
]

export const edgeKey = (a: number, b: number) => a < b ? `${a}-${b}` : `${b}-${a}`

export function applyEvent(conditions: EdgeConditions, event: MissionEvent): EdgeConditions {
  const next = { ...conditions }
  for (const [a, b] of event.edges) {
    const key = edgeKey(a, b)
    const previous = next[key]
    next[key] = {
      risk: Math.max(previous?.risk ?? 0, event.risk),
      timeFactor: Math.max(previous?.timeFactor ?? 1, event.timeFactor),
      reason: event.title,
    }
  }
  return next
}

export function edgeCondition(conditions: EdgeConditions, a: number, b: number): EdgeCondition {
  return conditions[edgeKey(a, b)] ?? { risk: 0, timeFactor: 1, reason: 'Normal' }
}

function weightedEdgeCost(base: number, condition: EdgeCondition) {
  return base * condition.timeFactor * (1 + condition.risk * 3)
}

function shortestPath(start: number, destination: number, conditions: EdgeConditions) {
  const distance = new Map(GRAPH_NODES.map((node) => [node.id, Infinity]))
  const previous = new Map<number, number>()
  const unvisited = new Set(GRAPH_NODES.map((node) => node.id))
  distance.set(start, 0)

  while (unvisited.size) {
    let current = -1
    let best = Infinity
    for (const node of unvisited) {
      const candidate = distance.get(node) ?? Infinity
      if (candidate < best) { current = node; best = candidate }
    }
    if (current < 0 || current === destination) break
    unvisited.delete(current)

    for (const edge of GRAPH_EDGES) {
      const neighbor = edge.from === current ? edge.to : edge.to === current ? edge.from : -1
      if (neighbor < 0 || !unvisited.has(neighbor)) continue
      const cost = weightedEdgeCost(edge.weight, edgeCondition(conditions, current, neighbor))
      if (best + cost < (distance.get(neighbor) ?? Infinity)) {
        distance.set(neighbor, best + cost)
        previous.set(neighbor, current)
      }
    }
  }

  const path = [destination]
  while (path[0] !== start && previous.has(path[0])) path.unshift(previous.get(path[0])!)
  return { path, cost: distance.get(destination) ?? Infinity }
}

function permutations(values: number[]): number[][] {
  if (values.length <= 1) return [values]
  return values.flatMap((value, index) => permutations([...values.slice(0, index), ...values.slice(index + 1)]).map((rest) => [value, ...rest]))
}

export function optimizeMission(currentNode: number, remainingSites: number[], conditions: EdgeConditions): MissionPlan {
  if (!remainingSites.length) return { path: [currentNode], visitOrder: [], weightedCost: 0, travelTime: 0, riskCost: 0 }

  let best: MissionPlan | null = null
  for (const order of permutations(remainingSites)) {
    let cursor = currentNode
    let path = [currentNode]
    let weightedCost = 0
    let travelTime = 0
    let riskCost = 0

    for (const site of order) {
      const leg = shortestPath(cursor, site, conditions)
      weightedCost += leg.cost
      path = [...path, ...leg.path.slice(1)]
      for (let index = 0; index < leg.path.length - 1; index++) {
        const from = leg.path[index]
        const to = leg.path[index + 1]
        const edge = GRAPH_EDGES.find((candidate) => edgeKey(candidate.from, candidate.to) === edgeKey(from, to))!
        const condition = edgeCondition(conditions, from, to)
        travelTime += edge.weight * condition.timeFactor
        riskCost += edge.weight * condition.risk
      }
      cursor = site
    }

    const candidate = { path, visitOrder: order, weightedCost, travelTime, riskCost }
    if (!best || candidate.weightedCost < best.weightedCost) best = candidate
  }
  return best!
}

export function routePath(nodes: number[]) {
  return nodes.map((nodeId, index) => {
    const node = GRAPH_NODES[nodeId]
    return `${index ? 'L' : 'M'} ${node.x} ${node.y}`
  }).join(' ')
}
