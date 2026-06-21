export type RoadNode = { id: number; osm_id: number; latitude: number; longitude: number }
export type RoadEdge = { source: number; target: number; base_time_min: number; distance_m: number; path: [number, number][] }
export type RoadGraph = { bbox: [number, number, number, number]; nodes: RoadNode[]; edges: RoadEdge[] }
export type SmokeReading = { pm25_ug_m3: number; aqi: number; station_name: string }
export type ReplayEvent = {
  timestamp: string
  type: 'fire_perimeter' | 'smoke_observation' | 'sar_request'
  source: string
  payload: any
}
export type WeightedEdge = RoadEdge & { blocked: boolean; exposureSteps: number; risk: number; timeFactor: number; cost: number }
export type MissionPlan = { order: number[]; edges: WeightedEdge[]; coordinates: [number, number][]; eta: number; risk: number; blockedEdges: number }
export type HazardSnapshot = { blocked_routes: string[]; route_exposure_steps: Record<string, number>; consumed_sites: number[]; node_distances_km: Record<string, number> }

export const START_NODE = 18
export const INITIAL_SITES = [10, 24, 15, 0, 6]

export function priorityFromFireDistance(distanceKm: number | undefined) {
  if (distanceKm === undefined) return 2
  if (distanceKm <= 0.1) return 10
  if (distanceKm <= 0.75) return 9
  if (distanceKm <= 1.5) return 8
  if (distanceKm <= 3) return 7
  if (distanceKm <= 5) return 5
  if (distanceKm <= 10) return 3
  return 1
}

function edgeKey(source: number, target: number) { return `${source}:${target}` }

export function evaluateEdges(graph: RoadGraph, exposureByRoute: Record<string, number>, pm25: number) {
  const smokeRisk = Math.min(pm25 / 120, 0.75)
  return graph.edges.map((edge): WeightedEdge => {
    const exposureSteps = exposureByRoute[edgeKey(edge.source, edge.target)] ?? 0
    const blocked = exposureSteps > 0
    const risk = Math.max(smokeRisk, exposureSteps ? Math.min(0.32 + exposureSteps * 0.1, 0.95) : 0)
    const timeFactor = 1 + exposureSteps * 0.42
    return { ...edge, blocked, exposureSteps, risk, timeFactor, cost: edge.base_time_min * timeFactor * (1 + 3 * risk) }
  })
}

export function optimizeMission(current: number, sites: number[], weighted: WeightedEdge[]): MissionPlan {
  if (!sites.length) return { order: [], edges: [], coordinates: [], eta: 0, risk: 0, blockedEdges: weighted.filter((edge) => edge.blocked).length }
  const lookup = new Map(weighted.map((edge) => [edgeKey(edge.source, edge.target), edge]))
  const size = 1 << sites.length
  const cost = Array.from({ length: size }, () => Array(sites.length).fill(Number.POSITIVE_INFINITY))
  const previous = Array.from({ length: size }, () => Array(sites.length).fill(-1))

  for (let i = 0; i < sites.length; i++) cost[1 << i][i] = lookup.get(edgeKey(current, sites[i]))?.cost ?? Number.POSITIVE_INFINITY
  for (let mask = 1; mask < size; mask++) {
    for (let end = 0; end < sites.length; end++) {
      if (!(mask & (1 << end))) continue
      const priorMask = mask ^ (1 << end)
      if (!priorMask) continue
      for (let prior = 0; prior < sites.length; prior++) {
        if (!(priorMask & (1 << prior))) continue
        const edge = lookup.get(edgeKey(sites[prior], sites[end]))
        const candidate = cost[priorMask][prior] + (edge?.cost ?? Number.POSITIVE_INFINITY)
        if (candidate < cost[mask][end]) { cost[mask][end] = candidate; previous[mask][end] = prior }
      }
    }
  }

  const full = size - 1
  let end = cost[full].reduce((best, value, index, values) => value < values[best] ? index : best, 0)
  let mask = full
  const order: number[] = []
  while (end >= 0) {
    order.unshift(sites[end])
    const next = previous[mask][end]
    mask ^= 1 << end
    end = next
  }

  const routeEdges: WeightedEdge[] = []
  let cursor = current
  for (const destination of order) {
    const edge = lookup.get(edgeKey(cursor, destination))
    if (edge) routeEdges.push(edge)
    cursor = destination
  }
  const coordinates = routeEdges.flatMap((edge, index) => index ? edge.path.slice(1) : edge.path)
  return {
    order,
    edges: routeEdges,
    coordinates,
    eta: routeEdges.reduce((sum, edge) => sum + edge.base_time_min * edge.timeFactor, 0),
    risk: routeEdges.reduce((sum, edge) => sum + edge.risk * edge.base_time_min, 0),
    blockedEdges: weighted.filter((edge) => edge.blocked).length,
  }
}

function permutations(values: number[]): number[][] {
  if (values.length <= 1) return [values]
  return values.flatMap((value, index) => permutations([...values.slice(0, index), ...values.slice(index + 1)]).map((rest) => [value, ...rest]))
}

export function optimizeMissionAlternatives(current: number, sites: number[], weighted: WeightedEdge[], priorities: Record<number, number>, limit = 3) {
  if (!sites.length) return [optimizeMission(current, sites, weighted)]
  const nodes = [...new Set(weighted.flatMap((edge) => [edge.source, edge.target]))]
  const adjacency = new Map(nodes.map((node) => [node, weighted.filter((edge) => edge.source === node)]))
  const routeLookup = new Map<string, WeightedEdge[]>()
  for (const source of nodes) {
    const distance = new Map(nodes.map((node) => [node, Number.POSITIVE_INFINITY]))
    const previous = new Map<number, WeightedEdge>()
    const unvisited = new Set(nodes)
    distance.set(source, 0)
    while (unvisited.size) {
      let active = -1
      let best = Number.POSITIVE_INFINITY
      for (const node of unvisited) {
        const candidate = distance.get(node)!
        if (candidate < best) { best = candidate; active = node }
      }
      if (active < 0) break
      unvisited.delete(active)
      for (const edge of adjacency.get(active) ?? []) {
        const candidate = best + edge.cost
        if (candidate < distance.get(edge.target)!) { distance.set(edge.target, candidate); previous.set(edge.target, edge) }
      }
    }
    for (const destination of nodes) {
      if (destination === source || !previous.has(destination)) continue
      const route: WeightedEdge[] = []
      let cursor = destination
      while (cursor !== source && previous.has(cursor)) {
        const edge = previous.get(cursor)!
        route.unshift(edge)
        cursor = edge.source
      }
      if (cursor === source) routeLookup.set(edgeKey(source, destination), route)
    }
  }
  const candidates: Array<{ plan: MissionPlan; score: number }> = []
  for (const order of permutations(sites)) {
    let cursor = current
    const edges: WeightedEdge[] = []
    let arrivalCost = 0
    let urgencyCost = 0
    let valid = true
    for (const destination of order) {
      const route = routeLookup.get(edgeKey(cursor, destination))
      if (!route) { valid = false; break }
      edges.push(...route)
      arrivalCost += route.reduce((sum, edge) => sum + edge.cost, 0)
      urgencyCost += arrivalCost * (priorities[destination] ?? 1)
      cursor = destination
    }
    if (!valid) continue
    const plan = {
      order,
      edges,
      coordinates: edges.flatMap((edge, index) => index ? edge.path.slice(1) : edge.path),
      eta: edges.reduce((sum, edge) => sum + edge.base_time_min * edge.timeFactor, 0),
      risk: edges.reduce((sum, edge) => sum + edge.risk * edge.base_time_min, 0),
      blockedEdges: weighted.filter((edge) => edge.blocked).length,
    }
    candidates.push({ plan, score: plan.edges.reduce((sum, edge) => sum + edge.cost, 0) + urgencyCost * 0.45 })
  }
  return candidates.sort((a, b) => a.score - b.score).slice(0, limit).map((candidate) => candidate.plan)
}

function shortestRoute(current: number, destination: number, weighted: WeightedEdge[], excluded: Set<string>) {
  const nodes = [...new Set(weighted.flatMap((edge) => [edge.source, edge.target]))]
  const adjacency = new Map(nodes.map((node) => [node, weighted.filter((edge) => edge.source === node && !excluded.has(edgeKey(edge.source, edge.target)))]))
  const distance = new Map(nodes.map((node) => [node, Number.POSITIVE_INFINITY]))
  const previous = new Map<number, WeightedEdge>()
  const unvisited = new Set(nodes)
  distance.set(current, 0)
  while (unvisited.size) {
    let active = -1
    let best = Number.POSITIVE_INFINITY
    for (const node of unvisited) {
      const candidate = distance.get(node)!
      if (candidate < best) { best = candidate; active = node }
    }
    if (active < 0 || active === destination) break
    unvisited.delete(active)
    for (const edge of adjacency.get(active) ?? []) {
      const candidate = best + edge.cost
      if (candidate < distance.get(edge.target)!) { distance.set(edge.target, candidate); previous.set(edge.target, edge) }
    }
  }
  const edges: WeightedEdge[] = []
  let cursor = destination
  while (cursor !== current && previous.has(cursor)) {
    const edge = previous.get(cursor)!
    edges.unshift(edge)
    cursor = edge.source
  }
  return cursor === current ? edges : []
}

function routePlan(destination: number, edges: WeightedEdge[], weighted: WeightedEdge[]): MissionPlan {
  return {
    order: [destination],
    edges,
    coordinates: edges.flatMap((edge, index) => index ? edge.path.slice(1) : edge.path),
    eta: edges.reduce((sum, edge) => sum + edge.base_time_min * edge.timeFactor, 0),
    risk: edges.reduce((sum, edge) => sum + edge.risk * edge.base_time_min, 0),
    blockedEdges: weighted.filter((edge) => edge.blocked).length,
  }
}

export function optimizeRouteAlternatives(current: number, destination: number, weighted: WeightedEdge[], limit = 3) {
  if (current === destination) return [routePlan(destination, [], weighted)]
  const best = shortestRoute(current, destination, weighted, new Set())
  if (!best.length) return []
  const candidates = [best]
  for (const edge of best) {
    const candidate = shortestRoute(current, destination, weighted, new Set([edgeKey(edge.source, edge.target)]))
    if (candidate.length) candidates.push(candidate)
  }
  const unique = new Map<string, WeightedEdge[]>()
  for (const route of candidates) unique.set(route.map((edge) => edgeKey(edge.source, edge.target)).join('|'), route)
  return [...unique.values()]
    .sort((a, b) => a.reduce((sum, edge) => sum + edge.cost, 0) - b.reduce((sum, edge) => sum + edge.cost, 0))
    .slice(0, limit)
    .map((edges) => routePlan(destination, edges, weighted))
}

export function averageSmoke(payload: SmokeReading[] | null) {
  if (!payload?.length) return 0
  return payload.reduce((sum, reading) => sum + reading.pm25_ug_m3, 0) / payload.length
}
