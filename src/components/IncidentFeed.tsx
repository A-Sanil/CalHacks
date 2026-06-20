import type { FeedItem } from '../types'
import { PanelTitle } from './Shared'

export function IncidentFeed({ items }: { items: FeedItem[] }) {
  return <aside className="panel feed-panel">
    <PanelTitle eyebrow="LIVE INTELLIGENCE" title="Incident feed" count={items.length} />
    <div className="feed-list">
      {items.map((item, index) => (
        <article className={`feed-item ${item.tone}`} key={`${item.time}-${item.message}`} style={{ animationDelay: `${index * 40}ms` }}>
          <div><time>{item.time}</time><span>{item.source}</span></div>
          <p>{item.message}</p>
        </article>
      ))}
    </div>
    <div className="signal"><i /><span>Receiving live telemetry</span></div>
  </aside>
}
