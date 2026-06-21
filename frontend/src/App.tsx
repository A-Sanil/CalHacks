import { useEffect, useMemo, useRef, useState } from 'react'
import simplify from '@turf/simplify'
import { PalisadesMap } from './components/PalisadesMap'
import './enhancements.css'
import { averageSmoke, evaluateEdges, optimizeRouteAlternatives, priorityFromFireDistance, type HazardSnapshot, type MissionPlan, type ReplayEvent, type RoadGraph, type WeightedEdge } from './simulation/palisadesMission'

const API = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const FIRE_STATION = 6
const RESCUE_SITES = [9, 15, 21]
const HOSPITAL = 14
const AMBULANCE_CAPACITY = 3
const MEDICAL_CALLS = [10, 24, 18, 0, 22]
const DEMO_START_FIRE_INDEX = 3
const EMPTY_PLAN: MissionPlan = { order: [], edges: [], coordinates: [], eta: 0, risk: 0, blockedEdges: 0 }
type MissionPhase = 'outbound' | 'returning' | 'complete'
type VirtualSplit = { id: number; position: [number, number]; originalSource: number; originalTarget: number; edges: WeightedEdge[] }

function initialFireState(events: ReplayEvent[]) {
  const fireEvents = events.filter((event) => event.type === 'fire_perimeter')
  const selected = fireEvents[Math.min(DEMO_START_FIRE_INDEX, fireEvents.length - 1)]
  if (!selected) return { collection: null, timestamp: '', eventIndex: 0, latest: null }
  const selectedIndex = events.indexOf(selected)
  const features = events.slice(0, selectedIndex + 1).filter((event) => event.type === 'fire_perimeter').map((event) => simplify(event.payload, { tolerance: 0.00035, highQuality: false }))
  return { collection: { type: 'FeatureCollection', features }, timestamp: selected.timestamp, eventIndex: selectedIndex + 1, latest: selected }
}

function localFirePatch([longitude, latitude]: [number, number]) {
  const radiusKm = 0.55
  const coordinates: [number, number][] = []
  for (let step = 0; step <= 32; step++) {
    const angle = step / 32 * Math.PI * 2
    coordinates.push([longitude + Math.cos(angle) * radiusKm / (111 * Math.cos(latitude * Math.PI / 180)), latitude + Math.sin(angle) * radiusKm / 111])
  }
  return { type: 'Feature', properties: { source: 'demo_local_flare_up' }, geometry: { type: 'Polygon', coordinates: [coordinates] } }
}

function App() {
  const [graph, setGraph] = useState<RoadGraph | null>(null)
  const [events, setEvents] = useState<ReplayEvent[]>([])
  const [hazardMatrix, setHazardMatrix] = useState<Record<string, HazardSnapshot>>({})
  const [eventIndex, setEventIndex] = useState(0)
  const [running, setRunning] = useState(false)
  const [started, setStarted] = useState(false)
  const [currentNode, setCurrentNode] = useState(FIRE_STATION)
  const [remainingSites, setRemainingSites] = useState([...RESCUE_SITES])
  const [rescuedSites, setRescuedSites] = useState<number[]>([])
  const [activeSite, setActiveSite] = useState<number | null>(null)
  const [phase, setPhase] = useState<MissionPhase>('outbound')
  const [fire, setFire] = useState<any | null>(null)
  const [fireTimestamp, setFireTimestamp] = useState('')
  const [pm25, setPm25] = useState(0)
  const [latest, setLatest] = useState<ReplayEvent | null>(null)
  const [loadError, setLoadError] = useState('')
  const [movement, setMovement] = useState<WeightedEdge | null>(null)
  const [movementDelay, setMovementDelay] = useState(650)
  const [interrupted, setInterrupted] = useState(false)
  const [virtualSplit, setVirtualSplit] = useState<VirtualSplit | null>(null)
  const [ambulanceNode, setAmbulanceNode] = useState(HOSPITAL)
  const [medicalCalls, setMedicalCalls] = useState([...MEDICAL_CALLS])
  const [collectedCalls, setCollectedCalls] = useState<number[]>([])
  const [ambulanceOnboard, setAmbulanceOnboard] = useState(0)
  const [ambulanceDelivered, setAmbulanceDelivered] = useState(0)
  const [ambulancePhase, setAmbulancePhase] = useState<'collecting' | 'returning' | 'complete'>('collecting')
  const [ambulanceMovement, setAmbulanceMovement] = useState<WeightedEdge | null>(null)
  const [ambulanceDelay, setAmbulanceDelay] = useState(850)
  const [playbackSpeed, setPlaybackSpeed] = useState(0.65)
  const ambulanceProgress = useRef<{ position: [number, number]; segmentIndex: number; remainingRatio: number } | null>(null)
  const movementProgress = useRef<{ position: [number, number]; segmentIndex: number; remainingRatio: number } | null>(null)
  const virtualNodeSequence = useRef(1000)
  const midpathDemoTriggered = useRef(false)
  // --- Voice 911 intake (Deepgram) ---------------------------------------
  const [voiceSites, setVoiceSites] = useState<{ node: number; demand: number; priority: number; label: string }[]>([])
  const [voicePriority, setVoicePriority] = useState<Record<number, number>>({})
  const [recording, setRecording] = useState(false)
  const [voiceMsg, setVoiceMsg] = useState('')
  const [voiceTranscript, setVoiceTranscript] = useState('')
  const [typedCall, setTypedCall] = useState('')
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])

  useEffect(() => {
    Promise.all([
      fetch(`${API}/data/palisades/road_graph_25.json`).then((response) => response.json()),
      fetch(`${API}/data/palisades/replay_timeline.json`).then((response) => response.json()),
      fetch(`${API}/data/palisades/hazard_route_matrix.json`).then((response) => response.json()),
    ]).then(([nextGraph, nextEvents, nextMatrix]) => {
      const seed = initialFireState(nextEvents)
      setGraph(nextGraph); setEvents(nextEvents); setHazardMatrix(nextMatrix)
      setFire(seed.collection); setFireTimestamp(seed.timestamp); setEventIndex(seed.eventIndex); setLatest(seed.latest)
    }).catch(() => setLoadError('Start the API on port 8000, then refresh.'))
  }, [])

  const snapshot = hazardMatrix[fireTimestamp]
  const exposureByRoute = snapshot?.route_exposure_steps ?? {}
  const distances = snapshot?.node_distances_km ?? {}
  const priorities = useMemo(() => Object.fromEntries(graph?.nodes.map((node) => [node.id, priorityFromFireDistance(distances[String(node.id)])]) ?? []), [graph, distances])
  const weighted = useMemo(() => {
    if (!graph) return []
    const base = evaluateEdges(graph, exposureByRoute, pm25)
    if (!virtualSplit) return base
    return [...base.filter((edge) => !((edge.source === virtualSplit.originalSource && edge.target === virtualSplit.originalTarget) || (edge.source === virtualSplit.originalTarget && edge.target === virtualSplit.originalSource))), ...virtualSplit.edges]
  }, [graph, exposureByRoute, pm25, virtualSplit])

  const rankedSites = useMemo(() => remainingSites.map((site) => {
    const outbound = optimizeRouteAlternatives(FIRE_STATION, site, weighted, 1)[0]
    const inbound = optimizeRouteAlternatives(site, FIRE_STATION, weighted, 1)[0]
    const travelCost = [...(outbound?.edges ?? []), ...(inbound?.edges ?? [])].reduce((sum, edge) => sum + edge.cost, 0)
    return { site, score: travelCost / (1 + (voicePriority[site] ?? priorities[site] ?? 1) * 0.12) }
  }).sort((a, b) => a.score - b.score), [remainingSites, weighted, priorities, voicePriority])
  const selectedSite = activeSite ?? rankedSites[0]?.site ?? null
  const targetNode = phase === 'returning' ? FIRE_STATION : selectedSite
  const plans = useMemo(() => targetNode === null ? [EMPTY_PLAN] : optimizeRouteAlternatives(currentNode, targetNode, weighted, 3), [currentNode, targetNode, weighted])
  const plan = plans[0] ?? EMPTY_PLAN
  const rankedMedicalCalls = useMemo(() => medicalCalls.map((site) => {
    const candidate = optimizeRouteAlternatives(ambulanceNode, site, weighted, 1)[0]
    return { site, score: (candidate?.edges ?? []).reduce((sum, edge) => sum + edge.cost, 0) / (1 + (priorities[site] ?? 1) * 0.1) }
  }).sort((a, b) => a.score - b.score), [medicalCalls, ambulanceNode, weighted, priorities])
  const ambulanceTarget = ambulancePhase === 'returning' ? HOSPITAL : rankedMedicalCalls[0]?.site ?? null
  const ambulancePlans = useMemo(() => ambulanceTarget === null ? [EMPTY_PLAN] : optimizeRouteAlternatives(ambulanceNode, ambulanceTarget, weighted, 3), [ambulanceNode, ambulanceTarget, weighted])
  const ambulancePlan = ambulancePlans[0] ?? EMPTY_PLAN

  useEffect(() => {
    if (!running || !events.length || eventIndex >= events.length) return
    const timer = window.setTimeout(() => {
      const event = events[eventIndex]
      setLatest(event)
      if (event.type === 'fire_perimeter') {
        setFire((history: any) => ({ type: 'FeatureCollection', features: [...(history?.features ?? []), simplify(event.payload, { tolerance: 0.00035, highQuality: false })] }))
        setFireTimestamp(event.timestamp)
        const nextSnapshot = hazardMatrix[event.timestamp]
        if (nextSnapshot) setMovement((active) => {
          if (!active) return active
          const progress = movementProgress.current
          if (!progress || progress.remainingRatio <= 0.01) return active
          const historicalExposure = nextSnapshot.route_exposure_steps[`${active.source}:${active.target}`] ?? active.exposureSteps
          const forceDemoFlareUp = !midpathDemoTriggered.current
          const exposureSteps = forceDemoFlareUp ? Math.max(historicalExposure, active.exposureSteps + 3) : historicalExposure
          if (exposureSteps <= active.exposureSteps) return active
          if (forceDemoFlareUp) {
            midpathDemoTriggered.current = true
            setFire((history: any) => ({ type: 'FeatureCollection', features: [...(history?.features ?? []), localFirePatch(progress.position)] }))
          }
          const risk = Math.min(0.32 + exposureSteps * 0.1, 0.95)
          const timeFactor = 1 + exposureSteps * 0.42
          const remainingRatio = Math.max(0.01, progress.remainingRatio)
          const completedRatio = Math.max(0.01, 1 - remainingRatio)
          const virtualId = virtualNodeSequence.current++
          const forwardPath = [progress.position, ...active.path.slice(progress.segmentIndex)] as [number, number][]
          const backwardPath = [progress.position, ...active.path.slice(0, progress.segmentIndex).reverse()] as [number, number][]
          const makeEdge = (source: number, target: number, path: [number, number][], ratio: number): WeightedEdge => {
            const baseTime = active.base_time_min * ratio
            return { ...active, source, target, path, base_time_min: baseTime, distance_m: active.distance_m * ratio, exposureSteps, blocked: true, risk, timeFactor, cost: baseTime * timeFactor * (1 + 3 * risk) }
          }
          const forward = makeEdge(virtualId, active.target, forwardPath, remainingRatio)
          const backward = makeEdge(virtualId, active.source, backwardPath, completedRatio)
          setVirtualSplit({ id: virtualId, position: progress.position, originalSource: active.source, originalTarget: active.target, edges: [forward, backward, makeEdge(active.target, virtualId, [...forwardPath].reverse(), remainingRatio), makeEdge(active.source, virtualId, [...backwardPath].reverse(), completedRatio)] })
          setCurrentNode(virtualId); setInterrupted(true)
          return null
        })
        if (nextSnapshot) setAmbulanceMovement((active) => {
          if (!active) return active
          const progress = ambulanceProgress.current
          if (!progress || progress.remainingRatio <= 0.01) return active
          const exposureSteps = nextSnapshot.route_exposure_steps[`${active.source}:${active.target}`] ?? active.exposureSteps
          if (exposureSteps <= active.exposureSteps) return active
          const remainingRatio = Math.max(0.01, progress.remainingRatio)
          const risk = Math.min(0.32 + exposureSteps * 0.1, 0.95)
          const timeFactor = 1 + exposureSteps * 0.42
          const baseTime = active.base_time_min * remainingRatio
          return { ...active, path: [progress.position, ...active.path.slice(progress.segmentIndex)], base_time_min: baseTime, distance_m: active.distance_m * remainingRatio, exposureSteps, blocked: true, risk, timeFactor, cost: baseTime * timeFactor * (1 + 3 * risk) }
        })
      }
      if (event.type === 'smoke_observation') setPm25(averageSmoke(event.payload))
      setEventIndex((index) => index + 1)
    }, (events[eventIndex]?.type === 'fire_perimeter' ? 1400 : 3400) / playbackSpeed)
    return () => window.clearTimeout(timer)
  }, [running, eventIndex, events, hazardMatrix, playbackSpeed])

  useEffect(() => {
    if (!running || movement || phase === 'complete' || !plan.edges.length) return
    const timer = window.setTimeout(() => {
      if (phase === 'outbound' && activeSite === null && selectedSite !== null) setActiveSite(selectedSite)
      setInterrupted(false); movementProgress.current = null; setMovement(plan.edges[0])
    }, movementDelay / playbackSpeed)
    return () => window.clearTimeout(timer)
  }, [running, movement, phase, plan.edges, movementDelay, activeSite, selectedSite, playbackSpeed])

  useEffect(() => {
    if (!running || ambulanceMovement || ambulancePhase === 'complete' || !ambulancePlan.edges.length) return
    const timer = window.setTimeout(() => {
      ambulanceProgress.current = null
      setAmbulanceMovement(ambulancePlan.edges[0])
    }, ambulanceDelay / playbackSpeed)
    return () => window.clearTimeout(timer)
  }, [running, ambulanceMovement, ambulancePhase, ambulancePlan.edges, ambulanceDelay, playbackSpeed])

  const finishMovement = (destination: number) => {
    const exitedVirtualNode = virtualSplit && movement?.source === virtualSplit.id
    setMovement(null); setCurrentNode(destination)
    if (exitedVirtualNode) setVirtualSplit(null)
    if (destination === targetNode) {
      if (phase === 'outbound') {
        setPhase('returning'); setMovementDelay(1100)
      } else {
        const rescued = activeSite
        if (rescued !== null) {
          setRemainingSites((sites) => sites.filter((site) => site !== rescued))
          setRescuedSites((sites) => [...sites, rescued])
        }
        setActiveSite(null)
        if (remainingSites.length <= 1) setPhase('complete')
        else { setPhase('outbound'); setMovementDelay(1100) }
      }
    } else setMovementDelay(0)
  }

  const finishAmbulanceMovement = (destination: number) => {
    setAmbulanceMovement(null)
    setAmbulanceNode(destination)
    if (destination !== ambulanceTarget) { setAmbulanceDelay(0); return }
    if (ambulancePhase === 'returning') {
      setAmbulanceDelivered((count) => count + ambulanceOnboard)
      setAmbulanceOnboard(0)
      if (!medicalCalls.length) setAmbulancePhase('complete')
      else { setAmbulancePhase('collecting'); setAmbulanceDelay(1200) }
      return
    }
    setMedicalCalls((calls) => calls.filter((site) => site !== destination))
    setCollectedCalls((calls) => [...calls, destination])
    const nextLoad = ambulanceOnboard + 1
    setAmbulanceOnboard(nextLoad)
    if (nextLoad >= AMBULANCE_CAPACITY || medicalCalls.length <= 1) setAmbulancePhase('returning')
    setAmbulanceDelay(850)
  }

  useEffect(() => {
    if (phase === 'complete' && ambulancePhase === 'complete') setRunning(false)
  }, [phase, ambulancePhase])

  const reset = () => {
    const seed = initialFireState(events)
    setRunning(false); setStarted(false); setEventIndex(seed.eventIndex); setCurrentNode(FIRE_STATION); setRemainingSites([...RESCUE_SITES]); setRescuedSites([]); setActiveSite(null); setPhase('outbound'); setFire(seed.collection); setFireTimestamp(seed.timestamp); setPm25(0); setLatest(seed.latest); setMovement(null); setMovementDelay(650); setInterrupted(false); setVirtualSplit(null); movementProgress.current = null; virtualNodeSequence.current = 1000; midpathDemoTriggered.current = false
    setAmbulanceNode(HOSPITAL); setMedicalCalls([...MEDICAL_CALLS]); setCollectedCalls([]); setAmbulanceOnboard(0); setAmbulanceDelivered(0); setAmbulancePhase('collecting'); setAmbulanceMovement(null); setAmbulanceDelay(850); ambulanceProgress.current = null
    setVoiceSites([]); setVoicePriority({}); setVoiceMsg(''); setVoiceTranscript(''); setRecording(false)
  }

  // --- Voice 911 intake: speak (or type) an emergency -> drop a NEW SAR site
  //     into the running rescue loop so the optimizer reroutes to it ----------
  const VOICE_NUM: Record<string, number> = { one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,eleven:11,twelve:12,thirteen:13,fourteen:14,fifteen:15,sixteen:16,seventeen:17,eighteen:18,nineteen:19,twenty:20,'twenty-one':21,'twenty-two':22,'twenty-three':23,'twenty-four':24,a:1,an:1,couple:2,few:3,several:4 }
  const voiceNum = (w: string) => (/^\d+$/.test(w) ? parseInt(w, 10) : VOICE_NUM[w])
  const numAlt = () => Object.keys(VOICE_NUM).sort((a, b) => b.length - a.length).join('|')
  function vParseNode(text: string): number | null {
    const t = text.toLowerCase()
    let m = t.match(new RegExp('\\b(?:node|site|sector|grid|sar)\\s+n?\\.?\\s*(\\d+|' + numAlt() + ')\\b'))
    if (!m) m = t.match(/\bn[\s.\-]?(\d{1,2})\b/)
    if (m) { const n = voiceNum(m[1]); if (n != null && n >= 0 && n <= 24) return n }
    return null
  }
  function vParseDemand(text: string): number {
    const t = text.toLowerCase()
    const victims = '(?:victim|people|persons?|trapped|evacuees?|civilians?|souls?|injured|patients?)'
    let m = t.match(new RegExp('(\\d+|' + numAlt() + ')\\s+(?:\\w+\\s+)?' + victims))
    if (!m) m = t.match(new RegExp('family of (\\d+|' + numAlt() + ')'))
    if (m) { const n = voiceNum(m[1]); if (n) return Math.max(1, Math.min(n, 99)) }
    return 1
  }
  function vParsePriority(text: string): { label: string; weight: number } {
    const t = text.toLowerCase()
    if (/critical|life.?threat|mayday|code red|trapped/.test(t)) return { label: 'critical', weight: 99 }
    if (/urgent|high|serious/.test(t)) return { label: 'high', weight: 40 }
    if (/medium|moderate/.test(t)) return { label: 'medium', weight: 20 }
    if (/low|minor/.test(t)) return { label: 'low', weight: 8 }
    return { label: 'high', weight: 40 }
  }
  function vPickFallback(): number {
    const taken = new Set<number>([...remainingSites, ...rescuedSites, currentNode, FIRE_STATION, HOSPITAL])
    for (const c of [12, 3, 20, 8, 17, 2, 24, 5, 0, 11]) if (!taken.has(c)) return c
    for (let i = 0; i <= 24; i++) if (!taken.has(i)) return i
    return 12
  }
  function applyDispatch(transcript: string, source: string) {
    const node = vParseNode(transcript) ?? vPickFallback()
    const demand = vParseDemand(transcript)
    const { label, weight } = vParsePriority(transcript)
    setVoiceTranscript(transcript)
    setVoiceSites((prev) => (prev.some((v) => v.node === node) ? prev : [...prev, { node, demand, priority: weight, label }]))
    setVoicePriority((prev) => ({ ...prev, [node]: weight }))
    setRemainingSites((prev) => (prev.includes(node) ? prev : [...prev, node]))
    if (phase !== 'returning') setActiveSite(node)
    if (!started) setStarted(true)
    setRunning(true)
    setVoiceMsg('New SAR site at N' + node + ' · ' + demand + ' victim' + (demand > 1 ? 's' : '') + ' · ' + label.toUpperCase() + ' — ' + (source === 'typed' ? 'dispatching' : 'transcribed, dispatching') + ', rerouting fire unit')
  }
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      audioChunksRef.current = []
      mr.ondataavailable = (e) => { if (e.data.size) audioChunksRef.current.push(e.data) }
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setRecording(false)
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        setVoiceMsg('Transcribing 911 call with Deepgram…')
        try {
          const fd = new FormData()
          fd.append('audio', blob, 'call.webm')
          const res = await fetch(API + '/voice/transcribe', { method: 'POST', body: fd })
          if (!res.ok) throw new Error('HTTP ' + res.status)
          const data = await res.json()
          if (!data.transcript) throw new Error('empty transcript')
          applyDispatch(data.transcript, 'deepgram')
        } catch (err) {
          setVoiceMsg('Mic transcription unavailable (' + (err instanceof Error ? err.message : String(err)) + '). Type the call instead.')
        }
      }
      mediaRecorderRef.current = mr
      mr.start()
      setRecording(true)
      setVoiceMsg('Listening… click STOP when the caller finishes')
    } catch (err) {
      setVoiceMsg('Mic blocked (' + (err instanceof Error ? err.message : String(err)) + '). Use the text box to simulate the call.')
    }
  }
  function stopRecording() { mediaRecorderRef.current?.stop() }
  function toggleMic() { if (recording) stopRecording(); else startRecording() }


  const timestamp = latest ? new Date(latest.timestamp).toLocaleString('en-US', { timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—'
  const totalDistance = plan.edges.reduce((sum, edge) => sum + edge.distance_m, 0)
  const fireDistance = plan.edges.filter((edge) => edge.exposureSteps).reduce((sum, edge) => sum + edge.distance_m, 0)
  const firePercent = totalDistance ? Math.round(fireDistance / totalDistance * 100) : 0
  const missionLabel = phase === 'complete' ? 'ALL RESCUES COMPLETE' : phase === 'returning' ? `RETURNING WITH SITE N${activeSite}` : `RESPONDING TO SITE N${selectedSite}`

  return <main className="geo-app">
    <header className="geo-header"><div><strong>AEGIS RESCUE</strong><span>Fire Station 6 · Palisades response loop</span></div><div className={`run-status ${running ? 'running' : ''}`}><i />{loadError ? 'DATA OFFLINE' : running ? missionLabel : phase === 'complete' ? 'MISSION COMPLETE' : graph ? 'READY' : 'LOADING DATA'}</div></header>
    <section className="geo-layout">
      <div className="map-shell">
        {graph ? <PalisadesMap graph={graph} currentNode={currentNode} requiredSites={remainingSites} visitedSites={rescuedSites} compromisedSites={RESCUE_SITES} priorities={priorities} fire={fire} plan={plan} alternatives={plans} overview={!started && !movement && !ambulanceMovement} movement={movement} virtualNode={virtualSplit ? { id: virtualSplit.id, position: virtualSplit.position } : null} baseStation={FIRE_STATION} hospital={HOSPITAL} ambulanceNode={ambulanceNode} medicalSites={medicalCalls} collectedMedicalSites={collectedCalls} ambulancePlan={ambulancePlan} ambulanceMovement={ambulanceMovement} playbackSpeed={playbackSpeed} onMovementComplete={finishMovement} onMovementProgress={(progress) => { movementProgress.current = progress }} onAmbulanceComplete={finishAmbulanceMovement} onAmbulanceProgress={(progress) => { ambulanceProgress.current = progress }} /> : <div className="map-loading">{loadError || 'Loading rescue network…'}</div>}
        <div className="time-card"><span>{phase === 'returning' ? 'PEOPLE ONBOARD' : 'CURRENT TASK'}</span><strong>{missionLabel}</strong><small>{timestamp}</small></div>
        {latest?.type === 'fire_perimeter' && <div className="event-card"><span>FIRE UPDATE</span><strong>Perimeter expanded · edge weights recalculated</strong></div>}
        {interrupted && <div className="interrupt-card"><span>LIVE NODE INSERTED · N{currentNode}</span><strong>Road split here; choosing continue or retreat.</strong></div>}
        <label className="speed-control"><span>SIMULATION SPEED <b>{playbackSpeed.toFixed(2)}×</b></span><input type="range" min="0.4" max="1.5" step="0.05" value={playbackSpeed} onChange={(event) => setPlaybackSpeed(Number(event.target.value))} /></label>
        <div className="map-legend"><span><i className="route-dot" />Fire truck</span><span><i className="ambulance-dot" />Ambulance</span><span><i className="exposed-dot" />In fire</span><span><i className="fire-dot" />Fire</span></div>
        <div className="geo-controls"><button className="primary" disabled={!graph || (phase === 'complete' && ambulancePhase === 'complete')} onClick={() => { setStarted(true); setRunning((value) => !value) }}>{running ? 'Pause rescue' : started ? 'Resume rescue' : 'Start rescue demo'}</button><button onClick={reset}>Reset</button></div>
      </div>
      <aside className="geo-sidebar">
        <section><span className="eyebrow">SIMPLE RESCUE LOOP</span><h1>Station → site → station</h1><p>Each trip starts at Fire Station 6, reaches one site inside the fire, loads survivors, and returns them to the station before the next rescue begins.</p></section>
        <section><div className="section-label">MISSION STATUS</div><div className={`phase-banner ${phase}`}><strong>{missionLabel}</strong><span>{phase === 'returning' ? 'Survivors secured—return to station' : phase === 'outbound' ? 'Traveling to people in danger' : 'Everyone returned safely'}</span></div></section>
        <section className="voice-panel">
          <div className="section-label">911 VOICE INTAKE <b>{voiceSites.length} live</b></div>
          <div className="voice-controls">
            <button className={'mic-btn ' + (recording ? 'rec' : '')} onClick={toggleMic} disabled={!graph} type="button">{recording ? '\u23F9 STOP' : '\uD83C\uDFA4 SIMULATE 911 CALL'}</button>
            <form className="voice-typed" onSubmit={(e) => { e.preventDefault(); const t = typedCall.trim(); if (t) { applyDispatch(t, 'typed'); setTypedCall('') } }}>
              <input value={typedCall} onChange={(e) => setTypedCall(e.target.value)} placeholder='e.g. "two trapped at node twelve, critical"' />
              <button type="submit">DISPATCH</button>
            </form>
          </div>
          {voiceMsg && <div className="voice-msg">{voiceMsg}</div>}
          {voiceTranscript && <div className="voice-transcript">&ldquo;{voiceTranscript}&rdquo;</div>}
          {voiceSites.map((v) => (
            <div className={'rescue-row ' + (rescuedSites.includes(v.node) ? 'rescued' : activeSite === v.node ? 'active' : '')} key={'voice-' + v.node}>
              <i>{rescuedSites.includes(v.node) ? '\u2713' : activeSite === v.node ? '\u2192' : '!'}</i>
              <span>SAR N{v.node}<small>{v.demand} victims · {v.label.toUpperCase()}</small></span>
              <strong>{rescuedSites.includes(v.node) ? 'SAFE' : activeSite === v.node ? phase.toUpperCase() : 'QUEUED'}</strong>
            </div>
          ))}
        </section>
        <section><div className="section-label">RESCUE SITES <b>{rescuedSites.length}/{RESCUE_SITES.length}</b></div>{RESCUE_SITES.map((site) => <div className={`rescue-row ${rescuedSites.includes(site) ? 'rescued' : activeSite === site ? 'active' : ''}`} key={site}><i>{rescuedSites.includes(site) ? '✓' : activeSite === site ? '→' : '!'}</i><span>Site N{site}<small>Inside active fire · P{priorities[site] ?? 10}</small></span><strong>{rescuedSites.includes(site) ? 'SAFE' : activeSite === site ? phase.toUpperCase() : 'WAITING'}</strong></div>)}</section>
        <section className="ambulance-panel"><div className="section-label">AMBULANCE · HOSPITAL 14 <b>{ambulanceOnboard}/{AMBULANCE_CAPACITY} onboard</b></div><div className={`ambulance-status ${ambulancePhase}`}><strong>{ambulancePhase === 'returning' ? 'RETURNING TO HOSPITAL' : ambulancePhase === 'complete' ? 'MEDICAL MISSION COMPLETE' : `COLLECTING AT N${ambulanceTarget ?? '—'}`}</strong><span>{ambulanceDelivered} delivered · {medicalCalls.length} calls waiting</span></div><div className="capacity-track"><i style={{width:`${ambulanceOnboard / AMBULANCE_CAPACITY * 100}%`}} /></div><small>At 3/3 onboard, the ambulance automatically returns, unloads, then resumes the remaining calls.</small></section>
        <section className="metric-grid"><div><span>LEG ETA</span><strong>{Math.round(plan.eta)} min</strong></div><div><span>TRAVEL IN FIRE</span><strong>{firePercent}%</strong></div><div><span>CURRENT TARGET</span><strong>N{targetNode ?? '—'}</strong></div><div><span>AT STATION</span><strong>{currentNode === FIRE_STATION ? 'YES' : 'NO'}</strong></div></section>
        <section><div className="section-label">ACTIVE EDGE WEIGHTS</div>{plan.edges.slice(0,4).map((edge,index)=><div className={`weight-row ${edge.exposureSteps ? 'exposed' : ''}`} key={`${edge.source}-${edge.target}-${index}`}><span>N{edge.source} → N{edge.target}</span><b>{edge.exposureSteps ? `${edge.exposureSteps} fire intervals` : 'clear'}</b><strong>{edge.cost.toFixed(1)}</strong></div>)}</section>
        <section><div className="section-label">PATH OPTIONS TO N{targetNode ?? '—'}</div>{plans.slice(0,3).map((candidate,index)=><p className={`visit-order option-${index+1}`} key={index}><b>#{index+1}</b><span>{candidate.edges.map((edge) => `N${edge.source}`).concat(targetNode === null ? [] : [`N${targetNode}`]).join(' → ')}</span><em>{Math.round(candidate.eta)}m</em></p>)}<small>Fastest route wins, with strong penalties for distance and time spent inside fire.</small></section>
      </aside>
    </section>
  </main>
}

export default App