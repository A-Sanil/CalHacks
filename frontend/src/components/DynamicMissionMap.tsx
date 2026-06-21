import { GRAPH_EDGES, GRAPH_NODES } from '../simulation/graph'
import { edgeCondition, edgeKey, routePath, type EdgeConditions, type MissionEvent, type MissionPlan } from '../simulation/dynamicMission'

type Props = {
  currentNode: number
  requiredSites: number[]
  remainingSites: number[]
  plan: MissionPlan
  conditions: EdgeConditions
  latestEvent: MissionEvent | null
}

export function DynamicMissionMap({ currentNode, requiredSites, remainingSites, plan, conditions, latestEvent }: Props) {
  const current = GRAPH_NODES[currentNode]
  const eventEdges = new Set(latestEvent?.edges.map(([a, b]) => edgeKey(a, b)) ?? [])

  return <svg className="mission-map" viewBox="0 0 700 540" role="img" aria-label="Dynamic route optimization map">
    <defs>
      <pattern id="mission-grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M36 0H0V36" fill="none" stroke="#172521" strokeWidth=".8" /></pattern>
      <filter id="mission-glow"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <rect width="700" height="540" fill="#09110f" />
    <rect width="700" height="540" fill="url(#mission-grid)" />

    <g className="mission-edges">
      {GRAPH_EDGES.map((edge) => {
        const from = GRAPH_NODES[edge.from]
        const to = GRAPH_NODES[edge.to]
        const condition = edgeCondition(conditions, edge.from, edge.to)
        const severity = condition.risk >= .8 ? 'severe' : condition.risk >= .4 ? 'elevated' : ''
        const active = eventEdges.has(edgeKey(edge.from, edge.to)) ? 'new-event' : ''
        return <line key={`${edge.from}-${edge.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={`${severity} ${active}`} />
      })}
    </g>

    <path className="mission-route" d={routePath(plan.path)} />

    <g className="mission-nodes">
      {GRAPH_NODES.map((node) => {
        const isRequired = requiredSites.includes(node.id)
        const visited = isRequired && !remainingSites.includes(node.id)
        return <g key={node.id} transform={`translate(${node.x} ${node.y})`} className={`${isRequired ? 'required' : ''} ${visited ? 'visited' : ''}`}>
          <circle r={isRequired ? 8 : 4} />
          <text x="8" y="-7">{node.id}</text>
          {isRequired && <text className="site-label" x="11" y="14">SITE {String.fromCharCode(65 + requiredSites.indexOf(node.id))}</text>}
        </g>
      })}
    </g>

    <g className="responder" style={{ transform: `translate(${current.x}px, ${current.y}px)` }}>
      <circle r="11" />
      <path d="M-4 -6 L7 0 L-4 6 Z" />
    </g>

    <g className="map-key" transform="translate(24 30)">
      <circle r="5" fill="#ff9d45"/><text x="11" y="3">REQUIRED</text>
      <circle cx="91" r="5" fill="#48e1bd"/><text x="102" y="3">VISITED</text>
      <line x1="171" x2="191" stroke="#ff5f3a" strokeWidth="3"/><text x="198" y="3">HIGH RISK</text>
    </g>
  </svg>
}
