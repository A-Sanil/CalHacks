import type { FeedItem, OptimizationRequest, OptimizationResult } from '../types'

export const PRIMARY_ROUTE = 'M 118 390 C 205 340, 260 302, 348 273 S 475 214, 568 170'
export const SAFE_ROUTE = 'M 118 390 C 188 334, 235 266, 315 232 S 410 125, 568 170'
export const SECONDARY_ROUTE = 'M 150 460 C 245 432, 350 400, 505 315'

export const initialFeed: FeedItem[] = [
  { time: '14:32:08', source: 'CAL FIRE', message: 'Perimeter update received | 1,840 acres', tone: 'warning' },
  { time: '14:31:42', source: 'SAR-02', message: 'Team en route to evacuation zone Echo', tone: 'normal' },
  { time: '14:30:19', source: 'DISPATCH', message: 'Two priority targets assigned', tone: 'success' },
  { time: '14:29:55', source: 'WEATHER', message: 'Wind holding SW at 18 mph', tone: 'normal' },
]

export const crisisFeed: FeedItem = {
  time: '14:32:16',
  source: 'ROADS',
  message: 'CRITICAL: Route 9 blocked by advancing fire',
  tone: 'critical',
}

export function buildCrisisRequest(): OptimizationRequest {
  return {
    timestamp: new Date().toISOString(),
    disaster_state: 'escalating_wildfire',
    vehicles: [
      { id: 'SAR-01', type: 'ground_rescue', capacity: 8, start_node: 0 },
      { id: 'SAR-02', type: 'medical_response', capacity: 4, start_node: 1 },
    ],
    target_nodes: [
      { id: 5, priority: 9.5, demand: 8, time_window: [0, 45] },
      { id: 8, priority: 7.0, demand: 6, time_window: [0, 90] },
    ],
    dynamic_edge_modifiers: [
      { edge: [3, 5], multiplier: 1000, reason: 'active_fire_front' },
    ],
  }
}

export const fallbackResult: OptimizationResult = {
  generated_at: 'mock',
  solve_time_ms: 842,
  routes: [
    {
      vehicle_id: 'SAR-01',
      ordered_nodes: [0, 4, 7, 5],
      svg_path: SAFE_ROUTE,
      eta_minutes: 14,
      priority_served: 9.5,
    },
  ],
  metrics: { people_routed: 17, total_priority_served: 16.5 },
}
