import { GRAPH_EDGES, GRAPH_NODES, hazardBlockedEdges } from '../simulation/graph'
import type { HazardScenario, OptimizedRoute, SimulationResult } from '../types'

const BASELINE_PATH = 'M 82 430 L 178 286 L 300 176 L 386 91 L 495 65 L 620 83'
const ROUTE_COLORS = ['#37f0cf', '#ffd166', '#a78bfa', '#f87171', '#60a5fa']
const edgeKey = (a: number, b: number) => a < b ? `${a}-${b}` : `${b}-${a}`
const pathFromNodes = (nodes: number[]) => nodes
  .map((nodeId, index) => {
    const node = GRAPH_NODES[nodeId]
    return node ? `${index ? 'L' : 'M'} ${node.x} ${node.y}` : ''
  })
  .filter(Boolean)
  .join(' ')

type Props = {
  scenario: HazardScenario | null
  result: SimulationResult | null
  optimizing: boolean
  backendRoutes?: OptimizedRoute[] | null
  live?: boolean
  showFleetRoutes?: boolean
  focusTargetId?: number
  requiredNodeIds?: number[]
  onToggleNode?: (nodeId: number) => void
}

export function TacticalMap({ scenario, result, optimizing, backendRoutes, live, showFleetRoutes = false, focusTargetId, requiredNodeIds = [], onToggleNode }: Props) {
  const blocked = new Set(scenario ? hazardBlockedEdges(scenario).map(([a, b]) => edgeKey(a, b)) : [])
  const activePath = result?.svgPath || BASELINE_PATH
  // Normal scenario stepping focuses on the lead asset. Guided Demo keeps the
  // complete CVRP fleet view so the audience can see multi-vehicle coordination.
  const allRoutes = backendRoutes ?? []
  const routes = showFleetRoutes ? allRoutes : allRoutes.slice(0, 1)
  const hasBackend = routes.length > 0

  return <div className={`tactical-map ${result ? 'crisis' : ''} ${optimizing ? 'optimizing' : ''}`}>
    <svg viewBox="0 0 700 540" role="img" aria-label="24-node wildfire routing simulation">
      <defs>
        <pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M 36 0 L 0 0 0 36" fill="none" stroke="#22302d" strokeWidth="0.7" /></pattern>
        <filter id="glow"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <radialGradient id="hazard"><stop offset="0" stopColor="#ff4d22" stopOpacity=".62"/><stop offset="1" stopColor="#ff7b32" stopOpacity=".06"/></radialGradient>
      </defs>
      <rect width="700" height="540" fill="#0b1412" />
      <rect width="700" height="540" fill="url(#grid)" />
      <g className="terrain" fill="none" stroke="#233833" strokeWidth="1.2" opacity=".55">
        <path d="M-40 125 Q95 55 205 124 T440 108 T750 76"/><path d="M-55 182 Q80 112 195 174 T425 156 T745 125"/><path d="M-30 488 Q95 420 230 456 T470 432 T735 395"/>
      </g>

      <g className="graph-edges">
        {GRAPH_EDGES.map((edge) => {
          const from = GRAPH_NODES[edge.from]
          const to = GRAPH_NODES[edge.to]
          const isBlocked = blocked.has(edgeKey(edge.from, edge.to))
          return <line key={`${edge.from}-${edge.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={isBlocked ? 'blocked-edge' : ''} />
        })}
      </g>

      {scenario && <g className="hazard-area">
        <circle cx={scenario.hazard.x} cy={scenario.hazard.y} r={scenario.hazard.radius} fill="url(#hazard)" stroke="#ff6835" strokeWidth="1.5" strokeDasharray="5 6" />
        <text x={scenario.hazard.x} y={scenario.hazard.y - scenario.hazard.radius - 9}>HAZARD ZONE</text>
      </g>}

      {/* The local preview disappears in normal live mode to avoid implying a
          second recommendation. Guided Demo keeps it faint for comparison. */}
      {!hasBackend && <path d={BASELINE_PATH} className={`route-path old ${result ? 'blocked' : ''}`} />}
      {result && (!hasBackend || showFleetRoutes) && <path d={activePath} className="route-path safe deployed" opacity={hasBackend ? 0.12 : 1} />}

      {/* Real OR-Tools CVRP routes from the backend, one colour per vehicle */}
      {hasBackend && <g className="backend-routes">
        {routes.map((route, i) => {
          const color = ROUTE_COLORS[i % ROUTE_COLORS.length]
          const isClosedTour = route.ordered_nodes.length > 1 && route.ordered_nodes[0] === route.ordered_nodes.at(-1)
          const required = requiredNodeIds.length ? requiredNodeIds : focusTargetId === undefined ? [] : [focusTargetId]
          const remaining = new Set(required)
          let missionEnd = -1
          route.ordered_nodes.forEach((nodeId, index) => {
            remaining.delete(nodeId)
            if (missionEnd < 0 && required.length && remaining.size === 0) missionEnd = index
          })
          const displayNodes = !showFleetRoutes && missionEnd >= 0
            ? route.ordered_nodes.slice(0, missionEnd + 1)
            : !showFleetRoutes && isClosedTour ? route.ordered_nodes.slice(0, -1) : route.ordered_nodes
          const displayPath = !showFleetRoutes ? pathFromNodes(displayNodes) : route.svg_path
          return <g key={route.vehicle_id}>
            <path d={displayPath} fill="none" stroke={color} strokeWidth={3.2} strokeLinejoin="round" strokeLinecap="round" opacity={0.95} style={{ filter: 'url(#glow)' }} />
            {displayNodes.map((nid, j) => {
              const n = GRAPH_NODES[nid]
              if (!n) return null
              return <circle key={`${route.vehicle_id}-${nid}-${j}`} cx={n.x} cy={n.y} r={3.6} fill={color} />
            })}
          </g>
        })}
      </g>}

      <g className="graph-nodes">
        {GRAPH_NODES.map((node) => {
          const special = node.id === 18 ? 'base-node' : node.id === 5 || node.id === 16 ? 'target-node' : ''
          const onRoute = result?.path.includes(node.id)
          const required = requiredNodeIds.includes(node.id)
          return <g key={node.id} transform={`translate(${node.x} ${node.y})`} className={`${special} ${onRoute ? 'route-node' : ''} ${required ? 'required-node' : ''} ${onToggleNode && node.id !== 18 ? 'selectable-node' : ''}`} onClick={() => node.id !== 18 && onToggleNode?.(node.id)} role={onToggleNode && node.id !== 18 ? 'button' : undefined}>
            <circle r={special ? 8 : 4.5} />
            <text x="8" y="-7">{node.id}</text>
            {special && <text className="node-name" x="11" y="14">{node.label}</text>}
            {required && <circle className="required-ring" r="11" />}
          </g>
        })}
      </g>

      {/* Live route legend */}
      {hasBackend && <g className="route-legend" transform="translate(28 34)">
        {routes.map((route, i) => (
          <g key={route.vehicle_id} transform={`translate(0 ${i * 17})`}>
            <rect width="16" height="4" y="-4" rx="2" fill={ROUTE_COLORS[i % ROUTE_COLORS.length]} />
            <text x="23" y="0" className="legend-text" fill="#cfeee6" style={{ fontSize: '11px' }}>{route.vehicle_id} · {route.eta_minutes}m · P{route.priority_served}</text>
          </g>
        ))}
      </g>}

      {hasBackend && routes.map((route, index) => {
        const color = ROUTE_COLORS[index % ROUTE_COLORS.length]
        const required = requiredNodeIds.length ? requiredNodeIds : focusTargetId === undefined ? [] : [focusTargetId]
        const remaining = new Set(required)
        let missionEnd = -1
        route.ordered_nodes.forEach((nodeId, routeIndex) => {
          remaining.delete(nodeId)
          if (missionEnd < 0 && required.length && remaining.size === 0) missionEnd = routeIndex
        })
        const motionNodes = !showFleetRoutes && missionEnd >= 0 ? route.ordered_nodes.slice(0, missionEnd + 1) : route.ordered_nodes
        const path = showFleetRoutes ? route.svg_path : pathFromNodes(motionNodes)
        return <g className="backend-vehicle" key={`vehicle-${route.vehicle_id}-${route.svg_path}`}>
          <circle r="8" fill="#07100e" stroke={color} strokeWidth="2.5" />
          <path d="M-3 -4 L5 0 L-3 4 Z" fill={color} />
          <animateMotion dur="9s" repeatCount="indefinite" path={path} />
        </g>
      })}

      {!hasBackend && <g className="vehicle" key={`${result?.scenarioId ?? 0}-${optimizing}`}>
        <circle r="11"/><path d="M-4 -6 L7 0 L-4 6 Z"/>
        <animateMotion dur="9s" repeatCount="indefinite" path={activePath} />
      </g>}

      {optimizing && <g className="scan-ring" transform={`translate(${scenario?.hazard.x ?? 350} ${scenario?.hazard.y ?? 250})`}><circle r="25"/><circle r="42"/></g>}
      <text x="28" y="510" className="coordinates">{hasBackend ? showFleetRoutes ? `24 NODES | LIVE OR-TOOLS CVRP | ${routes.length} VEHICLES` : `24 NODES | PRIMARY ROUTE | ${routes[0].vehicle_id}` : '24 NODES | 51 EDGES | DIJKSTRA HEURISTIC'}</text>
      <text x="500" y="510" className="coordinates" fill={live ? '#37f0cf' : '#ff9b5a'}>{live ? 'SOLVER: LIVE' : 'SOLVER: OFFLINE'}</text>
      <text x="640" y="510" className="north">N ^</text>
    </svg>
  </div>
}
