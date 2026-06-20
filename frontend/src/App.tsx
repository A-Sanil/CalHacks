import { useEffect, useState } from 'react'
import { IncidentFeed } from './components/IncidentFeed'
import { OperationsSidebar } from './components/OperationsSidebar'
import { Status } from './components/Shared'
import { TacticalMap } from './components/TacticalMap'
import { initialFeed } from './data/scenario'
import { buildRequestFromScenario, optimizeRoute } from './services/solver'
import { HAZARD_SCENARIOS, runSimulation } from './simulation/graph'
import type { FeedItem, HazardScenario, OptimizedRoute, SimulationResult, SolverStatus } from './types'

const wait = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds))

function App() {
  const [status, setStatus] = useState<SolverStatus>('idle')
  const [seconds, setSeconds] = useState(0)
  const [feed, setFeed] = useState<FeedItem[]>(initialFeed)
  const [results, setResults] = useState<SimulationResult[]>([])
  const [activeScenario, setActiveScenario] = useState<HazardScenario | null>(null)
  const [activeResult, setActiveResult] = useState<SimulationResult | null>(null)
  const [backendRoutes, setBackendRoutes] = useState<OptimizedRoute[] | null>(null)
  const [liveSolver, setLiveSolver] = useState(false)
  const optimizing = status === 'optimizing'

  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const executeScenario = async (scenario: HazardScenario) => {
    setStatus('optimizing')
    setActiveScenario(scenario)
    setFeed((items) => [{ time: `14:32:${String(15 + scenario.id).padStart(2, '0')}`, source: `SIM-${scenario.id}`, message: scenario.description, tone: 'critical' }, ...items])
    await wait(450)

    // 1) Instant local Dijkstra preview (keeps the map responsive while we call the API).
    const simulation = runSimulation(scenario)
    setActiveResult(simulation)
    setResults((items) => [...items.filter((item) => item.scenarioId !== simulation.scenarioId), simulation].sort((a, b) => a.scenarioId - b.scenarioId))

    // 2) Real OR-Tools CVRP solve via the FastAPI backend (falls back gracefully if offline).
    const outcome = await optimizeRoute(buildRequestFromScenario(scenario))
    if (outcome.source === 'live') {
      setBackendRoutes(outcome.result.routes)
      setLiveSolver(true)
      const m = outcome.result.metrics
      setFeed((items) => [{
        time: `14:32:${String(16 + scenario.id).padStart(2, '0')}`,
        source: 'OR-TOOLS SOLVER',
        message: `LIVE | ${outcome.result.routes.length} routes | ${m.people_routed} people | priority ${m.total_priority_served} | ${outcome.result.solve_time_ms}ms`,
        tone: 'success',
      }, ...items])
    } else {
      setBackendRoutes(null)
      setLiveSolver(false)
      setFeed((items) => [{
        time: `14:32:${String(16 + scenario.id).padStart(2, '0')}`,
        source: 'LOCAL ENGINE',
        message: `Backend offline (${outcome.error ?? 'no response'}) | local path cost ${simulation.routeCost}`,
        tone: 'warning',
      }, ...items])
    }

    setStatus('success')
    return simulation
  }

  const runNext = async () => {
    if (optimizing) return
    const nextIndex = results.length >= HAZARD_SCENARIOS.length ? 0 : results.length
    if (nextIndex === 0 && results.length) setResults([])
    await executeScenario(HAZARD_SCENARIOS[nextIndex])
  }

  const runBatch = async () => {
    if (optimizing) return
    setResults([])
    setFeed(initialFeed)
    for (const scenario of HAZARD_SCENARIOS) await executeScenario(scenario)
    setFeed((items) => [{ time: '14:32:30', source: 'AEGIS', message: 'Batch complete | 7 of 7 safe routes found', tone: 'success' }, ...items])
  }

  const reset = () => {
    setStatus('idle')
    setResults([])
    setActiveScenario(null)
    setActiveResult(null)
    setBackendRoutes(null)
    setLiveSolver(false)
    setFeed(initialFeed)
    setSeconds(0)
  }

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark">A</div><div><strong>AEGIS ROUTE</strong><span>Wildfire Command</span></div></div>
      <div className="status-strip">
        <Status label="Graph scale" value="24 nodes / 51 edges" />
        <Status label="Operational time" value={`00:${String(18 + Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`} />
        <Status label="Solver" value={liveSolver ? 'OR-Tools LIVE' : optimizing ? 'Searching' : 'Offline'} active={liveSolver} />
      </div>
      <div className="weather"><span>SW</span><strong>18</strong><small>MPH WIND</small></div>
    </header>

    <section className="dashboard">
      <IncidentFeed items={feed} />
      <section className="map-panel">
        <div className="map-heading">
          <div><span>ROUTING TESTBED</span><strong>{activeScenario ? `Simulation ${activeScenario.id}/7 | ${activeScenario.name}` : 'Coyote Ridge | Baseline network'}</strong></div>
          <div className="map-legend"><span><i className="dot priority" /> 24 graph nodes</span><span><i className="line route" /> {liveSolver ? 'Live CVRP routes' : 'Selected path'}</span></div>
        </div>
        <TacticalMap scenario={activeScenario} result={activeResult} optimizing={optimizing} backendRoutes={backendRoutes} live={liveSolver} />
        <div className={`event-banner ${optimizing ? 'visible' : ''}`}><span>SIMULATION {activeScenario?.id}/7</span><strong>Solving weighted graph...</strong></div>
        <div className="map-controls">
          <button className="crisis-button" onClick={runBatch} disabled={optimizing}><span>!</span>{optimizing ? 'Running simulation...' : 'Run all 7 simulations'}</button>
          <button className="reset-button" onClick={runNext} disabled={optimizing}>Run next</button>
          <button className="reset-button" onClick={reset} disabled={optimizing}>Reset</button>
        </div>
      </section>
      <OperationsSidebar status={status} activeScenario={activeScenario} activeResult={activeResult} results={results} />
    </section>
  </main>
}

export default App
