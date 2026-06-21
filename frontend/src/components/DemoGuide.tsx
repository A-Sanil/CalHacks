export type DemoStep = {
  index: number
  title: string
  body: string
}

type Props = {
  step: DemoStep
  running: boolean
  onStop: () => void
  onClose: () => void
}

export function DemoGuide({ step, running, onStop, onClose }: Props) {
  return <section className="demo-guide" aria-live="polite">
    <div className="demo-guide-head">
      <span>GUIDED DEMO {step.index + 1}/5</span>
      <div className="demo-dots">
        {Array.from({ length: 5 }, (_, index) => <i key={index} className={index <= step.index ? 'active' : ''} />)}
      </div>
    </div>
    <strong>{step.title}</strong>
    <p>{step.body}</p>
    <button onClick={running ? onStop : onClose}>{running ? 'Stop demo' : 'Close'}</button>
  </section>
}
