import type { HazardScenario, SimulationResult, SolverStatus } from '../types'
import { FleetCard, PanelTitle } from './Shared'

type Props = {
  status: SolverStatus
  activeScenario: HazardScenario | null
  activeResult: SimulationResult | null
  results: SimulationResult[]
}

export function OperationsSidebar({ status, activeScenario, activeResult, results }: Props) {
  const optimizing = status === 'optimizing'
  const averageCost = results.length ? Math.round(results.reduce((sum, item) => sum + item.routeCost, 0) / results.length) : 0
  const totalEvaluated = results.reduce((sum, item) => sum + item.nodesEvaluated, 0)

  return <aside className="right-column">
    <section className="panel agent-panel">
      <PanelTitle eyebrow="LOCAL ROUTING ENGINE" title="Simulation results" count={results.length} />
      <div className={`agent-state ${optimizing ? 'working' : ''}`}>
        <i />
        <div>
          <span>{optimizing ? 'SEARCHING GRAPH' : results.length === 7 ? 'BATCH COMPLETE' : 'READY'}</span>
          <p>{optimizing ? activeScenario?.description : activeResult ? `${activeResult.name}: safe path found through ${activeResult.path.length} nodes` : 'Run seven deterministic hazard tests before solver integration'}</p>
        </div>
      </div>
      <div className="simulation-results">
        {Array.from({ length: 7 }, (_, index) => {
          const result = results[index]
          return <div className={`result-row ${result ? 'complete' : ''}`} key={index}>
            <span>S{index + 1}</span><i style={{ width: result ? `${Math.min(100, result.routeCost)}%` : '0%' }} />
            <strong>{result ? `${result.routeCost} cost` : 'pending'}</strong>
          </div>
        })}
      </div>
    </section>

    <section className="panel fleet-panel">
      <PanelTitle eyebrow="CURRENT RUN" title={activeScenario?.name ?? 'Baseline route'} />
      <FleetCard id="SAR-01" type="Ground rescue" eta={activeResult ? `${Math.round(activeResult.routeCost / 5)} min` : '12 min'} capacity="6 / 8" progress={activeResult ? 58 : 68} accent="orange" />
      <div className="run-metrics">
        <div><span>ROUTE COST</span><strong>{activeResult?.routeCost ?? '--'}</strong></div>
        <div><span>NODES SEARCHED</span><strong>{activeResult?.nodesEvaluated ?? '--'}</strong></div>
        <div><span>BLOCKED EDGES</span><strong>{activeResult?.blockedEdges ?? '--'}</strong></div>
      </div>
    </section>

    <section className="impact-card">
      <span>BATCH PERFORMANCE</span>
      <div><strong>{results.length}/7</strong><p>runs complete<br />avg cost {averageCost || '--'} | {totalEvaluated} nodes</p></div>
    </section>
  </aside>
}
