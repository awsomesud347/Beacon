/** F10 — the privacy story made literal: the exact JSON the language model received.
 *
 * This is the one place in the app allowed to look technical. Everything here comes
 * straight off the Turn; nothing is recomputed. */
import type { RefObject } from 'react'
import type { GuardResult, NarrationSource, Turn } from '../api/types'

const SOURCE_LABEL: Record<NarrationSource, string> = {
  model: 'Language model, checked against the facts',
  template: 'Deterministic template (no model)',
  refusal: 'Hardcoded refusal (no model)',
  replay: 'Replay of the previous answer',
  cache: 'Pre-recorded demo cache',
}

/** Where the question's interpretation came from. The model only ever picks filters —
 * every figure below it is computed from the ledger. */
const PLAN_SOURCE: Record<string, string> = {
  pattern: 'Pattern matching (no model involved)',
  model: 'Language model, checked against the real categories and merchants',
  followup: 'Carried over from your previous question',
}

function guardLabel(guard: GuardResult): string {
  const attempts = `${guard.attempts} ${guard.attempts === 1 ? 'attempt' : 'attempts'}`
  return guard.passed ? `Guard passed, ${attempts}` : `Guard failed, ${attempts}`
}

interface PayloadInspectorProps {
  turn: Turn | null
  open: boolean
  onToggle: () => void
  buttonRef: RefObject<HTMLButtonElement | null>
}

export function PayloadInspector({ turn, open, onToggle, buttonRef }: PayloadInspectorProps) {
  const guard = turn?.guard
  const rejected = guard?.rejected_tokens ?? []

  return (
    <section aria-labelledby="inspector-heading" className="panel">
      <h2 id="inspector-heading">Privacy</h2>

      <button
        type="button"
        ref={buttonRef}
        aria-expanded={open}
        aria-controls="inspector-body"
        onClick={onToggle}
      >
        {open ? 'Hide' : 'Show'} everything sent to the language model
      </button>

      <div id="inspector-body" hidden={!open}>
        <p className="hint">
          The model never sees your transactions. It receives only the pre-computed facts
          below, and every number it says is checked back against them before you hear it.
        </p>

        {turn ? (
          <>
            <h3>This answer</h3>
            <dl className="inspector-facts">
              <dt>Question understood as</dt>
              <dd>{turn.intent.replace(/_/g, ' ')}</dd>

              <dt>Numeric fidelity guard</dt>
              <dd className={guard?.passed ? 'guard-pass' : 'guard-fail'}>
                {guard ? guardLabel(guard) : 'Not run'}
                {rejected.length > 0 && ` — rejected: ${rejected.join(', ')}`}
              </dd>

              <dt>Answer written by</dt>
              <dd>{SOURCE_LABEL[turn.narration_source]}</dd>

              <dt>Time to answer</dt>
              <dd>
                {turn.latency_ms.total} ms ({turn.latency_ms.analysis} ms analysis,{' '}
                {turn.latency_ms.narration} ms narration)
              </dd>
            </dl>

            {turn.fact_bundle?.plan && (
              <>
                <h3>How your question was understood</h3>
                <dl className="inspector-facts">
                  <dt>Looking up</dt>
                  <dd>{turn.fact_bundle.plan.metric.replace(/_/g, ' ')}</dd>
                  <dt>About</dt>
                  <dd>{turn.fact_bundle.plan.subject?.value ?? 'everything'}</dd>
                  <dt>Over</dt>
                  <dd>{turn.fact_bundle.plan.period.label}</dd>
                  <dt>Worked out by</dt>
                  <dd>{PLAN_SOURCE[turn.fact_bundle.plan.source ?? 'pattern']}</dd>
                </dl>
              </>
            )}

            <h3>Everything sent to the language model</h3>
            {turn.fact_bundle ? (
              // No max-height: the panel must survive 200% zoom without clipping text.
              <pre className="payload">{JSON.stringify(turn.fact_bundle, null, 2)}</pre>
            ) : (
              <p>
                Nothing. This answer never reached a language model — it came from{' '}
                {SOURCE_LABEL[turn.narration_source].toLowerCase()}.
              </p>
            )}
          </>
        ) : (
          <p>Ask a question first, then this shows exactly what left the machine.</p>
        )}
      </div>
    </section>
  )
}
