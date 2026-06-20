export function Status({ label, value, active = false }: { label: string; value: string; active?: boolean }) {
  return <div className="status"><span>{label}</span><strong className={active ? 'active' : ''}>{active && <i />}{value}</strong></div>
}

export function PanelTitle({ eyebrow, title, count }: { eyebrow: string; title: string; count?: number }) {
  return <div className="panel-title"><div><span>{eyebrow}</span><h2>{title}</h2></div>{count !== undefined && <b>{count}</b>}</div>
}

export function FleetCard({ id, type, eta, capacity, progress, accent }: { id: string; type: string; eta: string; capacity: string; progress: number; accent: string }) {
  return <article className="fleet-card">
    <div className={`fleet-icon ${accent}`}>&gt;</div>
    <div className="fleet-info"><strong>{id}</strong><span>{type}</span><div className="progress"><i style={{ width: `${progress}%` }} /></div></div>
    <div className="fleet-meta"><strong>{eta}</strong><span>{capacity} seats</span></div>
  </article>
}
