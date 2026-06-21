import { useEffect, useRef, useState } from 'react'
import maplibregl, { type GeoJSONSource, type Map } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { MissionPlan, RoadGraph, WeightedEdge } from '../simulation/palisadesMission'

type Props = {
  graph: RoadGraph
  currentNode: number
  requiredSites: number[]
  visitedSites: number[]
  fire: any | null
  plan: MissionPlan
  alternatives: MissionPlan[]
  compromisedSites: number[]
  priorities: Record<number, number>
  overview: boolean
  movement: WeightedEdge | null
  virtualNode: { id: number; position: [number, number] } | null
  baseStation: number
  hospital: number
  ambulanceNode: number
  medicalSites: number[]
  collectedMedicalSites: number[]
  ambulancePlan: MissionPlan
  ambulanceMovement: WeightedEdge | null
  playbackSpeed: number
  onMovementComplete: (destination: number) => void
  onMovementProgress: (progress: { position: [number, number]; segmentIndex: number; remainingRatio: number }) => void
  onAmbulanceComplete: (destination: number) => void
  onAmbulanceProgress: (progress: { position: [number, number]; segmentIndex: number; remainingRatio: number }) => void
}

const empty = { type: 'FeatureCollection', features: [] } as any
const featureCollection = (features: any[]) => ({ type: 'FeatureCollection', features }) as any

export function PalisadesMap({ graph, currentNode, requiredSites, visitedSites, fire, plan, alternatives, compromisedSites, priorities, overview, movement, virtualNode, baseStation, hospital, ambulanceNode, medicalSites, collectedMedicalSites, ambulancePlan, ambulanceMovement, playbackSpeed, onMovementComplete, onMovementProgress, onAmbulanceComplete, onAmbulanceProgress }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  const completionRef = useRef(onMovementComplete)
  const progressRef = useRef(onMovementProgress)
  const ambulanceCompletionRef = useRef(onAmbulanceComplete)
  const ambulanceProgressRef = useRef(onAmbulanceProgress)
  const playbackSpeedRef = useRef(playbackSpeed)
  const autoFocusUsed = useRef(false)
  const overviewVisible = useRef(false)
  const [mapReady, setMapReady] = useState(false)

  completionRef.current = onMovementComplete
  progressRef.current = onMovementProgress
  ambulanceCompletionRef.current = onAmbulanceComplete
  ambulanceProgressRef.current = onAmbulanceProgress
  playbackSpeedRef.current = playbackSpeed

  useEffect(() => {
    if (!container.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: container.current,
      center: [-118.615, 34.075],
      zoom: 12.3,
      attributionControl: false,
      style: {
        version: 8,
        sources: {
          topo: { type: 'raster', tiles: ['https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, attribution: 'USGS The National Map' },
        },
        layers: [
          { id: 'topo', type: 'raster', source: 'topo', paint: { 'raster-saturation': -0.55, 'raster-brightness-max': 0.7, 'raster-contrast': 0.15 } },
        ],
      },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: 'LAFD · EPA AirNow · OpenStreetMap' }))
    map.on('load', () => {
      map.addSource('fire', { type: 'geojson', data: empty })
      map.addLayer({ id: 'fire-fill', type: 'fill', source: 'fire', paint: { 'fill-color': '#ff542f', 'fill-opacity': 0.34 } })
      map.addLayer({ id: 'fire-edge', type: 'line', source: 'fire', paint: { 'line-color': '#ff6a3d', 'line-width': 2.5, 'line-opacity': 0.95 } })
      map.addSource('route', { type: 'geojson', data: empty })
      map.addSource('active-movement', { type: 'geojson', data: empty })
      map.addSource('ambulance-route', { type: 'geojson', data: empty })
      map.addSource('alternatives', { type: 'geojson', data: empty })
      map.addLayer({ id: 'alternative-routes', type: 'line', source: 'alternatives', paint: { 'line-color': ['match', ['get', 'rank'], 2, '#f4c66a', '#9caab6'], 'line-width': 2.5, 'line-opacity': 0.72, 'line-dasharray': [2, 2] } })
      map.addLayer({ id: 'route-shadow', type: 'line', source: 'route', paint: { 'line-color': '#031412', 'line-width': 8, 'line-opacity': 0.75 } })
      map.addLayer({ id: 'route-live', type: 'line', source: 'route', paint: { 'line-color': ['interpolate', ['linear'], ['get', 'exposure'], 0, '#42e8c0', 1, '#ffb347', 4, '#ff683d', 8, '#d93232'], 'line-width': ['interpolate', ['linear'], ['get', 'exposure'], 0, 4.5, 8, 6], 'line-opacity': 1 } })
      map.addLayer({ id: 'active-movement', type: 'line', source: 'active-movement', paint: { 'line-color': ['interpolate', ['linear'], ['get', 'exposure'], 0, '#7affdc', 1, '#ffc05c', 8, '#ff3f35'], 'line-width': 7, 'line-opacity': 1 } })
      map.addLayer({ id: 'ambulance-route', type: 'line', source: 'ambulance-route', paint: { 'line-color': ['interpolate', ['linear'], ['get', 'exposure'], 0, '#70a7ff', 1, '#b77cff', 8, '#ff4f93'], 'line-width': 4.5, 'line-opacity': .95, 'line-dasharray': [1.2, .6] } })
      map.addSource('sites', { type: 'geojson', data: empty })
      map.addLayer({ id: 'sites', type: 'circle', source: 'sites', paint: { 'circle-radius': ['interpolate', ['linear'], ['get', 'priority'], 1, 6, 10, 11], 'circle-color': ['match', ['get', 'status'], 'visited', '#42e8c0', 'compromised', '#ff493d', '#ff9b45'], 'circle-stroke-color': '#f4fffc', 'circle-stroke-width': 1.5 } })
      map.addLayer({ id: 'site-labels', type: 'symbol', source: 'sites', layout: { 'text-field': ['get', 'label'], 'text-size': 11, 'text-offset': [0, 1.35], 'text-anchor': 'top' }, paint: { 'text-color': '#ffffff', 'text-halo-color': '#07100e', 'text-halo-width': 2 } })
      map.addSource('base-station', { type: 'geojson', data: empty })
      map.addLayer({ id: 'base-station', type: 'circle', source: 'base-station', paint: { 'circle-radius': 12, 'circle-color': '#176c58', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3 } })
      map.addLayer({ id: 'base-station-label', type: 'symbol', source: 'base-station', layout: { 'text-field': 'FIRE STATION 6', 'text-size': 12, 'text-offset': [0, 1.55], 'text-anchor': 'top' }, paint: { 'text-color': '#ffffff', 'text-halo-color': '#07100e', 'text-halo-width': 2 } })
      map.addSource('medical-sites', { type: 'geojson', data: empty })
      map.addLayer({ id: 'medical-sites', type: 'circle', source: 'medical-sites', paint: { 'circle-radius': 7, 'circle-color': ['match', ['get', 'status'], 'collected', '#56707f', '#8e6cff'], 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.5 } })
      map.addLayer({ id: 'medical-labels', type: 'symbol', source: 'medical-sites', layout: { 'text-field': ['get', 'label'], 'text-size': 10, 'text-offset': [0, 1.3], 'text-anchor': 'top' }, paint: { 'text-color': '#d9d1ff', 'text-halo-color': '#07100e', 'text-halo-width': 2 } })
      map.addSource('hospital', { type: 'geojson', data: empty })
      map.addLayer({ id: 'hospital', type: 'circle', source: 'hospital', paint: { 'circle-radius': 12, 'circle-color': '#426fd4', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3 } })
      map.addLayer({ id: 'hospital-label', type: 'symbol', source: 'hospital', layout: { 'text-field': 'HOSPITAL 14', 'text-size': 12, 'text-offset': [0, 1.55], 'text-anchor': 'top' }, paint: { 'text-color': '#ffffff', 'text-halo-color': '#07100e', 'text-halo-width': 2 } })
      map.addSource('responder', { type: 'geojson', data: empty })
      map.addLayer({ id: 'responder', type: 'circle', source: 'responder', paint: { 'circle-radius': 10, 'circle-color': '#ffffff', 'circle-stroke-color': '#42e8c0', 'circle-stroke-width': 4 } })
      map.addSource('ambulance', { type: 'geojson', data: empty })
      map.addLayer({ id: 'ambulance', type: 'circle', source: 'ambulance', paint: { 'circle-radius': 9, 'circle-color': '#ffffff', 'circle-stroke-color': '#7c8cff', 'circle-stroke-width': 4 } })
      map.addSource('virtual-node', { type: 'geojson', data: empty })
      map.addLayer({ id: 'virtual-node-ring', type: 'circle', source: 'virtual-node', paint: { 'circle-radius': 15, 'circle-color': '#08110f', 'circle-opacity': 0, 'circle-stroke-color': '#ffe06a', 'circle-stroke-width': 2, 'circle-stroke-opacity': 1 } })
      map.addLayer({ id: 'virtual-node-label', type: 'symbol', source: 'virtual-node', layout: { 'text-field': ['get', 'label'], 'text-size': 10, 'text-offset': [0, -2], 'text-anchor': 'bottom' }, paint: { 'text-color': '#ffe06a', 'text-halo-color': '#07100e', 'text-halo-width': 2 } })
      setMapReady(true)
    })
    mapRef.current = map
    return () => { map.remove(); mapRef.current = null }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map?.isStyleLoaded()) return
    const route = plan.edges.length ? featureCollection(plan.edges.map((edge) => ({ type: 'Feature', properties: { exposure: edge.exposureSteps, weight: edge.cost }, geometry: { type: 'LineString', coordinates: edge.path } }))) : empty
    ;(map.getSource('route') as GeoJSONSource)?.setData(route)
    const activeMovement = movement ? featureCollection([{ type: 'Feature', properties: { exposure: movement.exposureSteps }, geometry: { type: 'LineString', coordinates: movement.path } }]) : empty
    ;(map.getSource('active-movement') as GeoJSONSource)?.setData(activeMovement)
    const ambulanceRoute = ambulancePlan.edges.length ? featureCollection(ambulancePlan.edges.map((edge) => ({ type: 'Feature', properties: { exposure: edge.exposureSteps }, geometry: { type: 'LineString', coordinates: edge.path } }))) : empty
    ;(map.getSource('ambulance-route') as GeoJSONSource)?.setData(ambulanceRoute)
    const alternateFeatures = alternatives.slice(1, 3).flatMap((candidate, index) => candidate.edges.map((edge) => ({ type: 'Feature', properties: { rank: index + 2, exposure: edge.exposureSteps }, geometry: { type: 'LineString', coordinates: edge.path } })))
    ;(map.getSource('alternatives') as GeoJSONSource)?.setData(featureCollection(alternateFeatures))
    ;(map.getSource('fire') as GeoJSONSource)?.setData(fire ?? empty)
    const allSites = [...new Set([...requiredSites, ...visitedSites, ...compromisedSites])]
    const siteFeatures = allSites.map((id, index) => {
      const node = graph.nodes.find((candidate) => candidate.id === id)!
      return { type: 'Feature', properties: { status: visitedSites.includes(id) ? 'visited' : compromisedSites.includes(id) ? 'compromised' : 'required', priority: priorities[id] ?? 1, label: `RESCUE N${id} · P${priorities[id] ?? 1}` }, geometry: { type: 'Point', coordinates: [node.longitude, node.latitude] } }
    })
    ;(map.getSource('sites') as GeoJSONSource)?.setData(featureCollection(siteFeatures))
    const station = graph.nodes.find((node) => node.id === baseStation)
    ;(map.getSource('base-station') as GeoJSONSource)?.setData(station ? featureCollection([{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [station.longitude, station.latitude] } }]) : empty)
    const hospitalNode = graph.nodes.find((node) => node.id === hospital)
    ;(map.getSource('hospital') as GeoJSONSource)?.setData(hospitalNode ? featureCollection([{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [hospitalNode.longitude, hospitalNode.latitude] } }]) : empty)
    const medicalFeatures = [...new Set([...medicalSites, ...collectedMedicalSites])].map((id) => {
      const node = graph.nodes.find((candidate) => candidate.id === id)!
      return { type: 'Feature', properties: { status: collectedMedicalSites.includes(id) ? 'collected' : 'waiting', label: `MEDICAL N${id}` }, geometry: { type: 'Point', coordinates: [node.longitude, node.latitude] } }
    })
    ;(map.getSource('medical-sites') as GeoJSONSource)?.setData(featureCollection(medicalFeatures))
    const responder = graph.nodes.find((node) => node.id === currentNode)
    if (responder && !movement) (map.getSource('responder') as GeoJSONSource)?.setData(featureCollection([{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [responder.longitude, responder.latitude] } }]))
    const ambulanceNodeData = graph.nodes.find((node) => node.id === ambulanceNode)
    if (ambulanceNodeData && !ambulanceMovement) (map.getSource('ambulance') as GeoJSONSource)?.setData(featureCollection([{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [ambulanceNodeData.longitude, ambulanceNodeData.latitude] } }]))
    ;(map.getSource('virtual-node') as GeoJSONSource)?.setData(virtualNode ? featureCollection([{ type: 'Feature', properties: { label: `LIVE N${virtualNode.id}` }, geometry: { type: 'Point', coordinates: virtualNode.position } }]) : empty)
  }, [mapReady, graph, currentNode, requiredSites, visitedSites, compromisedSites, priorities, fire, plan, alternatives, movement, virtualNode, baseStation, hospital, ambulanceNode, medicalSites, collectedMedicalSites, ambulancePlan, ambulanceMovement])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !movement || !map) return
    const source = map.getSource('responder') as GeoJSONSource
    const coordinates = movement.path
    const distances = [0]
    for (let index = 1; index < coordinates.length; index++) {
      const [ax, ay] = coordinates[index - 1]
      const [bx, by] = coordinates[index]
      distances.push(distances[index - 1] + Math.hypot((bx - ax) * Math.cos(ay * Math.PI / 180), by - ay))
    }
    const total = distances.at(-1) || 1
    const start = performance.now()
    const duration = Math.max(900, Math.min(5200, movement.base_time_min * 220))
    let simulatedElapsed = 0
    let previousFrame = start
    let lastProgressUpdate = 0
    let frame = 0
    const animate = (now: number) => {
      simulatedElapsed += (now - previousFrame) * playbackSpeedRef.current
      previousFrame = now
      const progress = Math.min(simulatedElapsed / duration, 1)
      const target = total * (progress < .5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2)
      let index = 1
      while (index < distances.length - 1 && distances[index] < target) index++
      const segmentStart = distances[index - 1]
      const segmentLength = Math.max(distances[index] - segmentStart, .0000001)
      const local = (target - segmentStart) / segmentLength
      const from = coordinates[index - 1]
      const to = coordinates[index]
      const position = [from[0] + (to[0] - from[0]) * local, from[1] + (to[1] - from[1]) * local]
      source.setData(featureCollection([{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: position } }]))
      if (now - lastProgressUpdate > 120 || progress === 1) {
        progressRef.current({ position: position as [number, number], segmentIndex: index, remainingRatio: Math.max(0, (total - target) / total) })
        lastProgressUpdate = now
      }
      if (progress < 1) frame = requestAnimationFrame(animate)
      else completionRef.current(movement.target)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [mapReady, movement])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !ambulanceMovement || !map) return
    const source = map.getSource('ambulance') as GeoJSONSource
    const coordinates = ambulanceMovement.path
    const distances = [0]
    for (let index = 1; index < coordinates.length; index++) {
      const [ax, ay] = coordinates[index - 1]
      const [bx, by] = coordinates[index]
      distances.push(distances[index - 1] + Math.hypot((bx - ax) * Math.cos(ay * Math.PI / 180), by - ay))
    }
    const total = distances.at(-1) || 1
    const start = performance.now()
    const duration = Math.max(900, Math.min(5200, ambulanceMovement.base_time_min * 220))
    let simulatedElapsed = 0
    let previousFrame = start
    let frame = 0
    let lastProgressUpdate = 0
    const animate = (now: number) => {
      simulatedElapsed += (now - previousFrame) * playbackSpeedRef.current
      previousFrame = now
      const progress = Math.min(simulatedElapsed / duration, 1)
      const eased = progress < .5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2
      const target = total * eased
      let index = 1
      while (index < distances.length - 1 && distances[index] < target) index++
      const segmentStart = distances[index - 1]
      const local = (target - segmentStart) / Math.max(distances[index] - segmentStart, .0000001)
      const from = coordinates[index - 1]
      const to = coordinates[index]
      const position = [from[0] + (to[0] - from[0]) * local, from[1] + (to[1] - from[1]) * local]
      source.setData(featureCollection([{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: position } }]))
      if (now - lastProgressUpdate > 120 || progress === 1) {
        ambulanceProgressRef.current({ position: position as [number, number], segmentIndex: index, remainingRatio: Math.max(0, (total - target) / total) })
        lastProgressUpdate = now
      }
      if (progress < 1) frame = requestAnimationFrame(animate)
      else ambulanceCompletionRef.current(ambulanceMovement.target)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [mapReady, ambulanceMovement])

  useEffect(() => {
    const map = mapRef.current
    const paths = [movement?.path, ambulanceMovement?.path].filter(Boolean) as [number, number][][]
    if (!mapReady || !map || !paths.length || autoFocusUsed.current) return
    const coordinates = paths.flat()
    const bounds = coordinates.reduce((result, coordinate) => result.extend(coordinate), new maplibregl.LngLatBounds(coordinates[0], coordinates[0]))
    map.fitBounds(bounds, { padding: 95, maxZoom: 12.4, duration: 700 })
    autoFocusUsed.current = true
  }, [mapReady, movement, ambulanceMovement])

  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !overview || overviewVisible.current) return
    overviewVisible.current = true
    autoFocusUsed.current = false
    const ids = [...new Set([baseStation, hospital, currentNode, ambulanceNode, ...requiredSites, ...compromisedSites, ...medicalSites])]
    const points = ids.map((id) => graph.nodes.find((node) => node.id === id)).filter(Boolean) as RoadGraph['nodes']
    if (!points.length) return
    const bounds = points.reduce((result, node) => result.extend([node.longitude, node.latitude]), new maplibregl.LngLatBounds([points[0].longitude, points[0].latitude], [points[0].longitude, points[0].latitude]))
    map.fitBounds(bounds, { padding: 90, maxZoom: 12.2, duration: 700 })
  }, [mapReady, overview, graph, baseStation, hospital, currentNode, ambulanceNode, requiredSites, compromisedSites, medicalSites])

  useEffect(() => {
    if (!overview) overviewVisible.current = false
  }, [overview])

  return <div className="palisades-map" ref={container} />
}
