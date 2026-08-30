import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from './api'
import type { Analysis, AuditEvent, CaseDetail, ExecutionStatus } from './types'
import IntegrationProof from './IntegrationProof'

type JourneyStage = 'idle' | 'creating_checkout' | 'checkout_open' | 'waiting_webhook' | 'failure_received' | 'agent_running' | 'action_issued' | 'recovered' | 'error'
type JourneyMode = 'guided' | 'razorpay' | null

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => {
      open: () => void
      on: (event: string, callback: (payload: unknown) => void) => void
    }
  }
}

const money = (subunits: number, currency = 'INR') => new Intl.NumberFormat('en-IN', {
  style: 'currency', currency, maximumFractionDigits: 0,
}).format(subunits / 100)
const words = (value: string) => value.replaceAll('_', ' ')
const pct = (value: number) => `${Math.round(value * 100)}%`
const pause = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

const loadCheckout = () => new Promise<void>((resolve, reject) => {
  if (window.Razorpay) return resolve()
  const existing = document.querySelector<HTMLScriptElement>('script[data-recourse-checkout]')
  if (existing) {
    existing.addEventListener('load', () => resolve(), { once: true })
    existing.addEventListener('error', () => reject(new Error('Razorpay Checkout could not load')), { once: true })
    return
  }
  const script = document.createElement('script')
  script.src = 'https://checkout.razorpay.com/v1/checkout.js'
  script.async = true
  script.dataset.recourseCheckout = 'true'
  script.onload = () => resolve()
  script.onerror = () => reject(new Error('Razorpay Checkout could not load'))
  document.head.appendChild(script)
})

const timeline = [
  ['Failure observed', 'Provider event is signed, deduplicated, and normalized.'],
  ['Evidence diagnosed', 'The bounded model cites only evidence in the case pack.'],
  ['Futures simulated', 'Four actions are compared with natural recovery.'],
  ['Recommendation challenged', 'A second pass searches for unsupported or unsafe action.'],
  ['Policy verified', 'Deterministic guardrails make the final decision.'],
  ['Recovery issued', 'At most one signed Test Mode command is emitted.'],
  ['Outcome reconciled', 'A paid webhook or authenticated provider lookup marks the case recovered.'],
]

export default function LiveRecovery() {
  const queryClient = useQueryClient()
  const readiness = useQuery({ queryKey: ['readiness'], queryFn: api.readiness, retry: false })
  const [stage, setStage] = useState<JourneyStage>('idle')
  const [mode, setMode] = useState<JourneyMode>(null)
  const [caseId, setCaseId] = useState('')
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [execution, setExecution] = useState<ExecutionStatus | null>(null)
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [message, setMessage] = useState('')

  const refreshJourney = async (id: string) => {
    const [nextDetail, nextAudit, nextExecution] = await Promise.all([
      api.caseDetail(id), api.audit(id), api.execution(id),
    ])
    setDetail(nextDetail)
    setAudit(nextAudit)
    setExecution(nextExecution)
    if (nextDetail.state === 'RECOVERED') setStage('recovered')
    return { nextDetail, nextExecution }
  }

  const finishAgentJourney = async (id: string) => {
    setStage('agent_running')
    const nextAnalysis = await api.analyze(id)
    setAnalysis(nextAnalysis)
    await pause(300)
    await api.execute(id)
    const refreshed = await refreshJourney(id)
    if (refreshed.nextDetail.state !== 'RECOVERED') setStage('action_issued')
    queryClient.invalidateQueries({ queryKey: ['cases'] })
  }

  useEffect(() => {
    if (mode !== 'razorpay' || !caseId || stage !== 'action_issued') return
    const timer = window.setInterval(() => {
      void api.reconcileOutcome(caseId)
        .then(result => {
          if (result.found) setMessage('Recovery outcome verified directly with Razorpay Test Mode.')
          return refreshJourney(caseId)
        })
        .catch(() => setMessage('Waiting for Razorpay to confirm the recovery outcome…'))
    }, 2000)
    return () => window.clearInterval(timer)
  }, [caseId, mode, stage])

  const guided = useMutation({
    mutationFn: async () => {
      setMode('guided')
      setMessage('')
      setAnalysis(null)
      setExecution(null)
      setAudit([])
      const started = await api.startGuidedFailure()
      setCaseId(started.case_id)
      setStage('failure_received')
      await refreshJourney(started.case_id)
      await pause(450)
      await finishAgentJourney(started.case_id)
    },
    onError: (error: Error) => { setMessage(error.message); setStage('error') },
  })

  const waitForProviderCase = async (orderId: string) => {
    setStage('waiting_webhook')
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const cases = await api.listCases()
      const found = cases.find(item => item.order_id === orderId && ['razorpay_test_mode', 'razorpay_api_verified'].includes(item.source))
      if (found) {
        setCaseId(found.case_id)
        setStage('failure_received')
        await finishAgentJourney(found.case_id)
        return
      }
      if (attempt >= 4) {
        const reconciled = await api.reconcileFailure(orderId)
        if (reconciled.found && reconciled.case_id) {
          setMessage('Webhook delayed; failure verified through the authenticated Razorpay Test API.')
          setCaseId(reconciled.case_id)
          setStage('failure_received')
          await finishAgentJourney(reconciled.case_id)
          return
        }
      }
      await pause(1500)
    }
    throw new Error('Razorpay did not report a failed payment for this order. Please trigger Test Mode failure and try again.')
  }

  const live = useMutation({
    mutationFn: async () => {
      setMode('razorpay')
      setMessage('')
      setStage('creating_checkout')
      await loadCheckout()
      const order = await api.createCheckoutOrder(499900)
      if (!window.Razorpay) throw new Error('Razorpay Checkout is unavailable')
      const checkout = new window.Razorpay({
        key: order.key_id,
        order_id: order.order_id,
        amount: order.amount_subunits,
        currency: order.currency,
        name: 'RECOURSE Test Store',
        description: 'Intentional failed-payment recovery demo',
        modal: { ondismiss: () => setMessage('Checkout closed; continuing to verify the payment result with Razorpay.') },
        theme: { color: '#123f2e' },
      })
      checkout.on('payment.failed', () => {
        void waitForProviderCase(order.order_id).catch((error: Error) => {
          setMessage(error.message)
          setStage('error')
        })
      })
      checkout.open()
      setStage('checkout_open')
    },
    onError: (error: Error) => { setMessage(error.message); setStage('error') },
  })

  const recover = useMutation({
    mutationFn: async () => {
      if (!caseId) return
      await api.completeGuidedRecovery(caseId)
      await refreshJourney(caseId)
      queryClient.invalidateQueries({ queryKey: ['cases'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })

  const reset = () => {
    setStage('idle'); setMode(null); setCaseId(''); setDetail(null); setAnalysis(null)
    setExecution(null); setAudit([]); setMessage('')
  }

  const selected = analysis?.futures.find(future => future.action === analysis.decision.selected_action)
  const hypothesis = analysis?.diagnosis.hypotheses[0]
  const completedSteps = stage === 'recovered' ? 7 : analysis ? (execution?.issued ? 6 : 5) : detail ? 1 : 0
  const busy = guided.isPending || live.isPending || stage === 'waiting_webhook' || stage === 'agent_running'
  const apiVerified = detail?.case.source === 'razorpay_api_verified' || audit.some(event => event.event_type === 'PAYMENT_FAILURE_API_VERIFIED')

  return <>
    <section className="live-hero">
      <div><p className="eyebrow">The five-minute judging story</p><h1>Watch the agent<br/><em>earn the recovery.</em></h1><p>Start with lost revenue, trigger a failure, inspect the safe decision, and finish with a reconciled recovery—then verify the result across 60 frozen cases.</p></div>
      <div className="readiness-card"><span className={readiness.data?.razorpay_test_mode_configured ? 'ready-dot online' : 'ready-dot'}/><div><b>{readiness.data?.razorpay_test_mode_configured ? 'Razorpay Test Mode ready' : 'Guided demo ready'}</b><small>{readiness.data?.razorpay_test_mode_configured ? 'Provider checkout + webhook/API verification' : 'Signed fixture · identical decision path'}</small></div></div>
    </section>

    {stage === 'idle' && <><ol className="judge-story"><li><b>₹X lost</b></li><li>Payment fails</li><li>AI diagnoses</li><li>Futures compared</li><li>Challenger checks</li><li>Policy authorizes</li><li>Razorpay reconciles</li><li><b>₹Y net · 0 violations</b></li></ol><div className="journey-launch">
      <section className="panel launch-card primary-launch"><span className="launch-number">01</span><p className="eyebrow">90-second judge simulation</p><h2>See the complete decision loop now</h2><p>A fresh signed fixture travels through the same ingestion, diagnosis, challenge, policy, idempotency, and recovery state machine.</p><button data-testid="start-guided-journey" className="button-primary" onClick={() => guided.mutate()}>Run 90-second simulation</button><small>Clearly labelled signed simulation · no provider claim</small></section>
      <section className="panel launch-card"><span className="launch-number">02</span><p className="eyebrow">Authentic Razorpay Test Mode journey</p><h2>Complete a real Test payment loop</h2><p>Failed checkout → signed webhook → agent decision → payment link → Test completion → payment webhook → recovered.</p><button data-testid="start-live-checkout" className="button-secondary" disabled={!readiness.data?.razorpay_test_mode_configured} onClick={() => live.mutate()}>Start authentic Test Mode journey</button><small>{readiness.data?.razorpay_test_mode_configured ? 'Provider checkout, payment link, outcome webhook/API reconciliation · no real money' : readiness.data?.razorpay_test_mode_missing?.length ? `Missing: ${readiness.data.razorpay_test_mode_missing.join(' · ')}` : 'Checking Test Mode configuration…'}</small></section>
    </div></>}

    {stage !== 'idle' && <div className="journey-grid">
      <section className="panel journey-stage">
        <div className="panel-title"><div><p className="eyebrow">Payment attempt</p><h2>{stage === 'recovered' ? 'Recovery confirmed' : stage === 'error' ? 'Journey needs attention' : 'Agent is handling the failure'}</h2></div><span className={`label ${mode === 'guided' ? 'warning' : 'safe-label'}`}>{mode === 'guided' ? 'SIGNED GUIDED DEMO' : apiVerified ? 'RAZORPAY API VERIFIED' : 'RAZORPAY TEST MODE'}</span></div>
        <div className={`payment-pulse ${stage === 'recovered' ? 'success' : ''}`}><span>{stage === 'recovered' ? '✓' : stage === 'checkout_open' ? '↗' : busy ? '···' : '!'}</span><div><small>Current state</small><b>{words(stage)}</b><p>{stage === 'checkout_open' ? 'Complete the hosted checkout with a Test Mode failure.' : stage === 'waiting_webhook' ? 'Browser failure observed; waiting for trusted provider evidence.' : stage === 'agent_running' ? 'Diagnosis, counterfactual simulation, and challenge are running.' : stage === 'action_issued' ? 'The safest valuable next action is ready.' : stage === 'recovered' ? apiVerified ? 'Razorpay API verification moved this case to RECOVERED.' : 'The signed outcome webhook moved this case to RECOVERED.' : 'Preparing the payment journey.'}</p></div></div>
        {message && <p className="journey-message" role="alert">{message}</p>}
        {caseId && <div className="case-reference"><span>Case</span><code>{caseId}</code><Link to={`/cases/${caseId}`}>Open full workbench →</Link></div>}
        <button className="button-secondary full" onClick={reset}>Start another journey</button>
      </section>

      <section className="panel agent-timeline"><p className="eyebrow">Verifiable agent trace</p><h2>What the system is doing</h2><ol>{timeline.map(([title, description], index) => <li className={index < completedSteps ? 'complete' : index === completedSteps && busy ? 'active' : ''} key={title}><span>{index < completedSteps ? '✓' : String(index + 1).padStart(2, '0')}</span><div><b>{title}</b><p>{index === 0 && apiVerified ? 'Failure confirmed through authenticated Razorpay Test API reconciliation.' : description}</p></div></li>)}</ol></section>

      <section className="panel recommendation-panel">
        <p className="eyebrow">What should we do next?</p>
        {!analysis ? <div className="recommendation-empty"><span>◇</span><p>The recommendation appears only after verified evidence, counterfactual comparison, and policy checks complete.</p></div> : <>
          <div className="recommendation-title"><div><small>Likely cause</small><b>{words(hypothesis?.cause ?? 'unknown')}</b></div><span>{pct(hypothesis?.confidence ?? 0)} confidence</span></div>
          <div className={`next-action ${analysis.challenge.objections.length ? 'challenger-catch' : ''}`}><small>{analysis.challenge.objections.length ? 'CHALLENGER CAUGHT AN UNSAFE RECOMMENDATION' : 'Recommended next action'}</small><h2>{words(analysis.decision.selected_action)}</h2><p>{analysis.challenge.objections.length ? `Action bounded because: ${analysis.challenge.objections.map(words).join(', ')}` : 'Challenger found no supported blocking objection.'}</p></div>
          {selected && <dl className="recommendation-metrics"><div><dt>Natural recovery</dt><dd>{pct(selected.no_action_probability)}</dd></div><div><dt>With this action</dt><dd>{pct(selected.success_probability)}</dd></div><div><dt>Conservative value</dt><dd>{money(selected.conservative_incremental_value_subunits)}</dd></div><div><dt>Guardrails</dt><dd>{analysis.decision.guardrail_results.every(result => result.passed) ? 'All pass' : 'Blocked'}</dd></div></dl>}
          {execution?.short_url && <a className="button-primary full" href={execution.short_url} target="_blank" rel="noreferrer">Open recommended Test payment link</a>}
          {mode === 'guided' && execution?.issued && stage !== 'recovered' && <button data-testid="complete-guided-recovery" className="button-primary full" disabled={recover.isPending} onClick={() => recover.mutate()}>{recover.isPending ? 'Verifying signed outcome…' : 'Replay signed customer-paid outcome'}</button>}
          {stage === 'recovered' && <div className="recovered-callout"><b>Revenue recovered</b><span>{detail ? money(detail.case.amount_subunits, detail.case.currency) : ''}</span></div>}
        </>}
      </section>
    </div>}

    {audit.length > 0 && <details className="panel live-audit" open><summary><span><b>Signed audit evidence</b><small>{audit.length} append-only records from this journey</small></span><span>View trace</span></summary><div className="live-audit-grid">{audit.map(event => <article key={event.sequence}><span>{String(event.sequence).padStart(2, '0')}</span><div><b>{words(event.event_type)}</b><small>{new Date(event.created_at).toLocaleTimeString()}</small></div><code>{event.event_hash.slice(0, 12)}…</code></article>)}</div></details>}
    {caseId && <IntegrationProof caseId={caseId}/>}
  </>
}
