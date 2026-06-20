import { fallbackResult } from '../data/scenario'
import type { HazardScenario, OptimizationRequest, OptimizationResult } from '../types'

// Backend base URL. Override with VITE_SOLVER_API_URL at build/dev time.
const API_BASE = ((import.meta.env.VITE_SOLVER_API_URL as string | undefined) || 'http://localhost:8000').replace(/\/$/, '')
const API_TIMEOUT_MS = 6000

// Fixed SAR fleet stationed across the corners of the 24-node grid.
const FLEET: OptimizationRequest['vehicles'] = [
  { id: 'AIR-01', type: 'air_rescue', capacity: 8, start_node: 0 },
  { id: 'GND-01', type: 'ground_rescue', capacity: 10, start_node: 23 },
  { id: 'GND-02', type: 'medical', capacity: 6, start_node: 18 },
]

// Standing priority targets (people awaiting evacuation) spread across the map.
const TARGETS: OptimizationRequest['target_nodes'] = [
  { id: 4, priority: 6.0, demand: 3, time_window: [0, 60] },
  { id: 7, priority: 9.0, demand: 4, time_window: [0, 45] },
  { id: 11, priority: 7.5, demand: 3, time_window: [0, 60] },
  { id: 16, priority: 8.0, demand: 5, time_window: [0, 60] },
  { id: 19, priority: 9.5, demand: 6, time_window: [0, 40] },
  { id: 22, priority: 5.5, demand: 2, time_window: [0, 90] },
]

export type OptimizeOutcome = {
  result: OptimizationResult
  source: 'live' | 'offline'
  error?: string
}

// Translate a hazard scenario into a solver contract: blocked edges become
// near-infinite multipliers (closed roads); penalties become slowdown multipliers.
export function buildRequestFromScenario(scenario: HazardScenario): OptimizationRequest {
  const modifiers: OptimizationRequest['dynamic_edge_modifiers'] = [
    ...scenario.blockedEdges.map(([a, b]) => ({
      edge: [a, b] as [number, number],
      multiplier: 9999,
      reason: `${scenario.name}: road closed`,
    })),
    ...scenario.penalties.map((p) => ({
      edge: p.edge,
      multiplier: p.multiplier,
      reason: `${scenario.name}: hazard slowdown`,
    })),
  ]
  return {
    timestamp: new Date().toISOString(),
    disaster_state: scenario.name,
    vehicles: FLEET,
    target_nodes: TARGETS,
    dynamic_edge_modifiers: modifiers,
  }
}

// POST the contract to the real OR-Tools backend. Never throws: on any network
// or solver error it returns the offline fallback so the UI keeps working.
export async function optimizeRoute(request: OptimizationRequest): Promise<OptimizeOutcome> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS)
  try {
    const response = await fetch(`${API_BASE}/optimize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`Solver HTTP ${response.status}`)
    const result = (await response.json()) as OptimizationResult
    if (!result.routes?.length) throw new Error('Solver returned no routes')
    return { result, source: 'live' }
  } catch (err) {
    return {
      result: fallbackResult,
      source: 'offline',
      error: err instanceof Error ? err.message : String(err),
    }
  } finally {
    window.clearTimeout(timeout)
  }
}
