/** The answer sentence — the biggest thing on screen.
 *
 * `turn.narration` is rendered verbatim: the backend already decided every word and
 * every figure, and reformatting here would break the numeric-fidelity guarantee.
 * This panel is deliberately NOT a live region; LiveRegion owns all announcements. */
import type { RefObject } from 'react'
import type { Turn } from '../api/types'

interface AnswerPanelProps {
  turn: Turn | null
  busy: boolean
  error: string | null
  headingRef: RefObject<HTMLHeadingElement | null>
}

export function AnswerPanel({ turn, busy, error, headingRef }: AnswerPanelProps) {
  return (
    <section aria-labelledby="answer-heading" className="panel answer-panel">
      <h2 id="answer-heading" tabIndex={-1} ref={headingRef}>
        Answer
      </h2>

      {error ? (
        <p className="answer-text answer-error">{error}</p>
      ) : turn ? (
        <>
          <p className="answer-question">You asked: {turn.query_text}</p>
          <p className="answer-text">{turn.narration}</p>
        </>
      ) : (
        <p className="answer-text answer-placeholder">
          {busy ? 'Working on it…' : 'Ask a question and the answer appears here.'}
        </p>
      )}
    </section>
  )
}
