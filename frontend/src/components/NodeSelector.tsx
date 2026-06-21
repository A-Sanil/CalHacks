type Props = {
  selected: number[]
  disabled: boolean
  onToggle: (nodeId: number) => void
  onEmergencyCall: () => void
  onDispatch: () => void
  onClear: () => void
}

export function NodeSelector({ selected, disabled, onToggle, onEmergencyCall, onDispatch, onClear }: Props) {
  return <section className="node-selector">
    <div className="node-selector-title"><span>REQUIRED STOPS</span><strong>{selected.length}</strong></div>
    <p>Click any map node to add or remove it from the mission.</p>
    <div className="node-chips">
      {selected.length ? selected.map((nodeId) => <button key={nodeId} onClick={() => onToggle(nodeId)} disabled={disabled}>N{String(nodeId).padStart(2, '0')} <b>x</b></button>) : <em>No required stops</em>}
    </div>
    <div className="node-selector-actions">
      <button onClick={onEmergencyCall} disabled={disabled}>+ Incoming call</button>
      <button className="dispatch" onClick={onDispatch} disabled={disabled || !selected.length}>Dispatch</button>
      <button onClick={onClear} disabled={disabled || !selected.length}>Clear</button>
    </div>
  </section>
}
