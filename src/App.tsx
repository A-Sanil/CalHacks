import { useEffect, useState } from 'react'
import { IncidentFeed } from './components/IncidentFeed'
import { OperationsSidebar } from './components/OperationsSidebar'
import { Status } from './components/Shared'
import { TacticalMap } from './components/TacticalMap'
import { initialFeed } from './data/scenario'
import { HAZARD_SCENARIOS, runSimulation } from './simulation/graph'
import type { FeedItem, HazardScenario, SimulationResult, SolverStatus } from './types'

const wait = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds))

function App() {
  const [status, setStatus] = useState<SolverStatus>('idle')
  const [seconds, setSeconds] = useState(0)
  const [feed, setFeed] = useState<FeedItem[]>(initialFeed)
  const [results, setResults] = useState<SimulationResult[]>([])
  const [activeScenario, setActiveScenario] = useState<HazardScenario | null>(null)
  const [activeResult, setActiveResult] = useState<SimulationResult | null>(null)
  const optimizing = status === 'optimizing'

  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const executeScenario = async (scenario: HazardScenario) => {
    setStatus('optimizing')
    setActiveScenario(scenario)
    setFeed((items) => [{ time: `14:32:${String(15 + scenario.id).padStart(2, '0')}`, source: `SIM-${scenario.id}`, message: scenario.description, tone: 'critical' }, ...items])
    await wait(650)
    const simulation = runSimulation(scenario)
    setActiveResult(simulation)
    setResults((items) => [...items.filter((item) => item.scenarioId !== simulation.scenarioId), simulation].sort((a, b) => a.scenarioId - b.scenarioId))
    setStatus('success')
    setFeed((items) => [{ time: `14:32:${String(16 + scenario.id).padStart(2, '0')}`, source: 'LOCAL ENGINE', message: `Path found | cost ${simulation.routeCost} | ${simulation.nodesEvaluated} nodes searched`, tone: 'success' }, ...items])
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
    setFeed(initialFeed)
    setSeconds(0)
  }

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark">A</div><div><strong>AEGIS ROUTE</strong><span>Wildfire Command</span></div></div>
      <div className="status-strip">
        <Status label="Graph scale" value="24 nodes / 53 edges" />
        <Status label="Operational time" value={`00:${String(18 + Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`} />
        <Status label="Engine" value={optimizing ? 'Searching' : results.length === 7 ? '7/7 Complete' : 'Ready'} active />
      </div>
      <div className="weather"><span>SW</span><strong>18</strong><small>MPH WIND</small></div>
    </header>

    <section className="dashboard">
      <IncidentFeed items={feed} />
      <section className="map-panel">
        <div className="map-heading">
          <div><span>ROUTING TESTBED</span><strong>{activeScenario ? `Simulation ${activeScenario.id}/7 | ${activeScenario.name}` : 'Coyote Ridge | Baseline network'}</strong></div>
          <div className="map-legend"><span><i className="dot priority" /> 24 graph nodes</span><span><i className="line route" /> Selected path</span></div>
        </div>
        <TacticalMap scenario={activeScenario} result={activeResult} optimizing={optimizing} />
        <div className={`event-banner ${optimizing ? 'visible' : ''}`}><span>SIMULATION {activeScenario?.id}/7</span><strong>Evaluating weighted graph...</strong></div>
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
