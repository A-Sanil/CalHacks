import { GRAPH_EDGES, GRAPH_NODES } from '../simulation/graph'
import type { HazardScenario, SimulationResult } from '../types'

const BASELINE_PATH = 'M 82 430 L 178 286 L 300 176 L 386 91 L 495 65 L 620 83'
const edgeKey = (a: number, b: number) => a < b ? `${a}-${b}` : `${b}-${a}`

type Props = {
  scenario: HazardScenario | null
  result: SimulationResult | null
  optimizing: boolean
}

export function TacticalMap({ scenario, result, optimizing }: Props) {
  const blocked = new Set(scenario?.blockedEdges.map(([a, b]) => edgeKey(a, b)) ?? [])
  const activePath = result?.svgPath || BASELINE_PATH

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

      <path d={BASELINE_PATH} className={`route-path old ${result ? 'blocked' : ''}`} />
      {result && <path d={activePath} className="route-path safe deployed" />}

      <g className="graph-nodes">
        {GRAPH_NODES.map((node) => {
          const special = node.id === 18 ? 'base-node' : node.id === 5 || node.id === 16 ? 'target-node' : ''
          const onRoute = result?.path.includes(node.id)
          return <g key={node.id} transform={`translate(${node.x} ${node.y})`} className={`${special} ${onRoute ? 'route-node' : ''}`}>
            <circle r={special ? 8 : 4.5} />
            <text x="8" y="-7">{node.id}</text>
            {special && <text className="node-name" x="11" y="14">{node.label}</text>}
          </g>
        })}
      </g>

      <g className="vehicle" key={`${result?.scenarioId ?? 0}-${optimizing}`}>
        <circle r="11"/><path d="M-4 -6 L7 0 L-4 6 Z"/>
        <animateMotion dur="9s" repeatCount="indefinite" path={activePath} />
      </g>

      {optimizing && <g className="scan-ring" transform={`translate(${scenario?.hazard.x ?? 350} ${scenario?.hazard.y ?? 250})`}><circle r="25"/><circle r="42"/></g>}
      <text x="28" y="510" className="coordinates">24 NODES | 53 EDGES | DIJKSTRA HEURISTIC</text>
      <text x="640" y="510" className="north">N ^</text>
    </svg>
  </div>
}
