export type FeedTone = 'normal' | 'warning' | 'critical' | 'success'

export type FeedItem = {
  time: string
  source: string
  message: string
  tone: FeedTone
}

export type SolverVehicle = {
  id: string
  type: string
  capacity: number
  start_node: number
}

export type TargetNode = {
  id: number
  priority: number
  demand: number
  time_window: [number, number]
  required?: boolean
}

export type EdgeModifier = {
  edge: [number, number]
  multiplier: number
  reason: string
}

export type OptimizationRequest = {
  timestamp: string
  disaster_state: string
  vehicles: SolverVehicle[]
  target_nodes: TargetNode[]
  dynamic_edge_modifiers: EdgeModifier[]
}

export type OptimizedRoute = {
  vehicle_id: string
  ordered_nodes: number[]
  svg_path: string
  eta_minutes: number
  priority_served: number
}

export type OptimizationResult = {
  generated_at: string
  solve_time_ms: number
  routes: OptimizedRoute[]
  metrics: {
    people_routed: number
    total_priority_served: number
  }
}

export type SolverStatus = 'idle' | 'optimizing' | 'success' | 'fallback'

export type GraphNode = {
  id: number
  x: number
  y: number
  label: string
}

export type GraphEdge = {
  from: number
  to: number
  weight: number
}

export type HazardScenario = {
  id: number
  name: string
  description: string
  blockedEdges: Array<[number, number]>
  penalties: Array<{ edge: [number, number]; multiplier: number }>
  hazard: { x: number; y: number; radius: number }
}

export type SimulationResult = {
  scenarioId: number
  name: string
  path: number[]
  svgPath: string
  routeCost: number
  nodesEvaluated: number
  blockedEdges: number
  solveTimeMs: number
}
