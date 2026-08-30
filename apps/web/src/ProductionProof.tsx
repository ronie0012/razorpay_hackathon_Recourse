import { useQuery } from '@tanstack/react-query'
import { api } from './api'

const labels: Record<string, string> = { target_segment: 'Initial merchant segment', volume_threshold: 'Failed-payment threshold', expected_lift: 'Expected lift range', pricing: 'Pricing model', deployment: 'Deployment effort', payback: 'Payback period', compliance: 'Compliance boundaries', razorpay_fit: 'Why Razorpay should distribute it' }

export default function ProductionProof() {
  const proof = useQuery({ queryKey: ['production-proof'], queryFn: api.productionProof })
  if (!proof.data) return <div className="page-state loading"><span>◌</span><p>Loading production evidence…</p></div>
  const l = proof.data.load_test
  return <><section className="evaluation-head"><div><p className="eyebrow">Production & business proof</p><h1>From signed event<br/><em>to bounded action.</em></h1><p>A concise deployment architecture, measured ingress test, and a commercial wedge Razorpay can validate without granting unsafe authority.</p></div><span className="sealed">TEST MODE ONLY<br/><b>LIVE KEYS REFUSED</b></span></section>
    <section className="panel architecture"><div className="panel-title"><div><p className="eyebrow">Production architecture</p><h2>Ten controls in one path</h2></div><span className="label safe-label">MERCHANT-SCOPED</span></div><div className="architecture-flow">{proof.data.architecture.map((item,index) => <article key={item.name}><span>{String(index+1).padStart(2,'0')}</span><div><b>{item.name}</b><p>{item.detail}</p></div></article>)}</div></section>
    {l && <section className="panel load-proof"><div><p className="eyebrow">Measured synthetic load test</p><h2>{l.event_count.toLocaleString('en-IN')} signed events</h2><p>{l.label}</p></div><div className="load-metrics"><div><small>Throughput</small><b>{l.throughput_events_per_second.toLocaleString('en-IN')}/s</b></div><div><small>P95 verification</small><b>{l.p95_latency_ms} ms</b></div><div><small>Duplicates suppressed</small><b>{Math.round(l.duplicate_suppression_rate*100)}%</b></div><div><small>Accepted exactly once</small><b>{Math.round(l.accepted_once_rate*100)}%</b></div></div><p className="muted">{l.scope}</p><code>{l.run_hash}</code></section>}
    <section className="business-proof"><div><p className="eyebrow">Commercial wedge</p><h2>Start where failed payments already justify intervention.</h2><p>Charge only against reconciled incremental value, then let evidence—not projections—expand merchant coverage.</p></div><div className="business-grid">{Object.entries(proof.data.business_case).map(([key,value]) => <article className="panel" key={key}><small>{labels[key] ?? key}</small><p>{value}</p></article>)}</div></section>
  </>
}
