import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type { EvaluationReplay, EvaluationReport, ReplayCase } from './types'

const money = (value: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value / 100)
const pct = (value: number) => `${Math.round(value * 100)}%`
const words = (value: string) => value.replaceAll('_', ' ')

function ReplayConsole({ replay }: { replay: EvaluationReplay }) {
  const [processed, setProcessed] = useState(0)
  const [running, setRunning] = useState(false)
  useEffect(() => {
    if (!running || processed >= replay.case_count) { if (processed >= replay.case_count) setRunning(false); return }
    const timer = window.setTimeout(() => setProcessed(value => value + 1), 55)
    return () => window.clearTimeout(timer)
  }, [running, processed, replay.case_count])
  const visible = replay.cases.slice(0, processed)
  const totals = useMemo(() => visible.reduce((acc, item) => {
    acc.natural += item.natural_recovery_subunits; acc.incremental += item.incremental_recovered_subunits
    acc.cost += item.action_cost_subunits; acc.net += item.net_value_subunits
    acc.actions[item.full_action] = (acc.actions[item.full_action] ?? 0) + 1
    if (item.status === 'HUMAN_REVIEW' || item.status === 'ABSTAIN') acc.refused += 1
    return acc
  }, { natural: 0, incremental: 0, cost: 0, net: 0, refused: 0, actions: {} as Record<string, number> }), [visible])
  const download = () => {
    const blob = new Blob([JSON.stringify({ run_hash: replay.run_hash, label: replay.label, cases: replay.cases }, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob); const anchor = document.createElement('a')
    anchor.href = url; anchor.download = 'recourse-60-case-replay.json'; anchor.click(); URL.revokeObjectURL(url)
  }
  return <section className="panel batch-console">
    <div className="panel-title"><div><p className="eyebrow">Runnable batch demonstration</p><h2>Replay all 60 frozen cases</h2></div><span className="label">DETERMINISTIC · NO EXTERNAL CALLS</span></div>
    <p className="muted">Replays the sealed per-case artifact in canonical order. Natural recovery is subtracted before Recourse receives credit.</p>
    <div className="batch-actions"><button data-testid="run-batch" className="button-primary" onClick={() => { setProcessed(0); setRunning(true) }} disabled={running}>{running ? `Replaying ${processed}/${replay.case_count}…` : processed ? 'Replay again' : 'Replay 60 cases'}</button><button className="button-secondary" onClick={download}>Download run artifact</button></div>
    <div className="progress-track" aria-label={`Processed ${processed} of ${replay.case_count}`}><span style={{ width: `${processed / replay.case_count * 100}%` }}/></div>
    <div className="batch-metrics"><div><small>Processed</small><b>{processed}/{replay.case_count}</b></div><div><small>Natural recovery excluded</small><b>{money(totals.natural)}</b></div><div><small>Incremental recovered</small><b>{money(totals.incremental)}</b></div><div><small>Action costs</small><b>{money(totals.cost)}</b></div><div><small>Net value</small><b>{money(totals.net)}</b></div><div><small>Review / refused</small><b>{totals.refused}</b></div></div>
    <div className="batch-bottom"><div><small>Action distribution</small><div className="action-distribution">{['NO_ACTION','RETRY_LATER','STANDARD_PAYMENT_LINK','ONE_BOUNDED_NUDGE'].map(action => <span key={action}><i style={{ height: `${Math.max(2, ((totals.actions[action] ?? 0) / Math.max(processed, 1)) * 70)}px` }}/><b>{totals.actions[action] ?? 0}</b><small>{words(action)}</small></span>)}</div></div><div className="run-log"><small>Latest cases</small>{visible.slice(-5).reverse().map(item => <div key={item.case_id}><code>{item.case_id}</code><span>{words(item.full_action)}</span><b>{money(item.net_value_subunits)}</b></div>)}</div></div>
    <div className="run-hash"><small>Deterministic run SHA-256</small><code>{replay.run_hash}</code></div>
  </section>
}

export default function EvaluationLab() {
  const report = useQuery<EvaluationReport>({ queryKey: ['evaluation'], queryFn: api.evaluation })
  const replay = useQuery<EvaluationReplay>({ queryKey: ['evaluation-replay'], queryFn: api.evaluationReplay })
  if (report.isLoading || replay.isLoading) return <div className="page-state loading"><span>◌</span><p>Loading sealed evaluation evidence…</p></div>
  if (!report.data || !replay.data) return <div className="page-state error"><span>!</span><p>Evaluation artifacts are unavailable.</p></div>
  const r = report.data, u = replay.data.ai_uplift
  return <>
    <section className="evaluation-head"><div><p className="eyebrow">Evaluation Lab · same-case causal comparison</p><h1>What AI changed<br/><em>beyond rules.</em></h1><p>The complexity earns its place only where the calibrated agent changes a decision, protects a case, or creates verified incremental value.</p></div><div className="artifact-stamp"><b>{r.artifact_file}</b><span>60 frozen cases · seed {r.seed}</span><span>SHA {replay.data.run_hash.slice(0, 16)}…</span></div></section>
    <section className="ai-proof-grid"><article className="panel lead-proof"><small>ADDITIONAL NET VALUE FROM CHANGED DECISIONS</small><b>{money(u.additional_net_value_subunits)}</b><span>above rules-only, after natural recovery and action costs</span></article><article className="panel"><small>DECISIONS CHANGED</small><b>{u.decisions_changed}/{r.case_count}</b><span>same cases, same realized outcomes</span></article><article className="panel"><small>CHALLENGER CATCHES</small><b>{u.challenger_catches}</b><span>unsafe recommendations · {u.challenger_scope}</span></article><article className="panel"><small>SAFER OVERRIDES</small><b>{u.safety_overrides}</b><span>rules action → full-agent no action</span></article><article className="panel"><small>CORRECT NO-ACTION</small><b>{u.correct_no_action}</b><span>matched evaluator-only oracle</span></article><article className="panel"><small>HUMAN REVIEWS</small><b>{u.human_reviews}</b><span>uncertainty stopped automation</span></article><article className="panel"><small>P95 / EXTERNAL COST</small><b>{u.latency_p95_ms.toFixed(2)} ms · ${u.external_model_cost_usd}</b><span>frozen local-policy evaluation</span></article></section>
    <section className="panel uncertainty-card"><div><p className="eyebrow">Uncertainty, stated first</p><h2>{money(u.full_net_value_subunits)} full-agent net value</h2><p>95% seeded bootstrap interval: <b>{money(u.confidence_interval_95.lower_95)} to {money(u.confidence_interval_95.upper_95)}</b>. The point estimate is {money(u.additional_net_value_subunits)} above rules-only ({money(u.rules_net_value_subunits)}).</p></div><div className="comparison-bar"><span className="rules-bar" style={{width:`${u.rules_net_value_subunits / u.full_net_value_subunits * 100}%`}}>Rules only</span><span className="agent-bar">Full agent</span></div><small>{u.attribution_note}</small></section>
    <ReplayConsole replay={replay.data}/>
    <details className="panel technical-evidence"><summary><span><b>Technical evidence</b><small>Brier scores, ablations, regret, hashes, and full variant comparison</small></span><span>Open +</span></summary><div className="metric-cards">{['rules','single_model','full_recourse','oracle'].map(name => { const m=r.variants[name]; return <article className="panel" key={name}><small>{words(name)}</small><b>{money(m.realized_incremental_net_value_subunits)}</b><span>realized incremental net value</span><dl><div><dt>Macro Brier</dt><dd>{m.macro_brier?.toFixed(3) ?? 'N/A'}</dd></div><div><dt>Violations</dt><dd>{m.guardrail_violation_count}/{m.case_count}</dd></div><div><dt>p90 regret</dt><dd>{money(m.regret.p90_subunits)}</dd></div><div><dt>Review</dt><dd>{pct(m.review_rate)}</dd></div></dl></article>})}</div><div className="evaluation-grid"><section><h3>Ablation ledger</h3>{Object.entries(r.ablations).map(([name, values]) => <details className="ablation" key={name}><summary>{words(name)}</summary><pre>{JSON.stringify(values, null, 2)}</pre></details>)}</section><section className="failure-card"><h3>Honest failure: {r.failure_analysis.case_id}</h3><p>{r.failure_analysis.explanation}</p><p>Agent chose <b>{words(r.failure_analysis.selected_action)}</b>; oracle chose <b>{words(r.failure_analysis.oracle_action)}</b>. Regret: {money(r.failure_analysis.regret_subunits)}.</p></section></div><div className="integrity"><div><small>Dataset SHA-256</small><code>{r.dataset_sha256}</code></div><div><small>Model manifest SHA-256</small><code>{r.model_manifest_sha256}</code></div><div><small>Policy SHA-256</small><code>{r.policy_hash}</code></div><div><small>Pinned model</small><code>{r.freeze.openrouter_model}</code></div></div></details>
  </>
}
