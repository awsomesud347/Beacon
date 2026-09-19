/** Every turn, question and answer, reviewable at the reader's own speed.
 *
 * role="log" carries an implicit aria-live="polite", which would make the transcript
 * compete with LiveRegion and double-speak every answer. aria-live="off" keeps the log
 * semantics while leaving announcements to the single live region. */
import type { Turn } from '../api/types'

function formatTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export function Transcript({ turns }: { turns: Turn[] }) {
  return (
    <section aria-labelledby="transcript-heading" className="panel">
      <h2 id="transcript-heading">Transcript</h2>
      <div role="log" aria-live="off" aria-labelledby="transcript-heading">
        {turns.length === 0 ? (
          <p className="hint">Nothing yet.</p>
        ) : (
          <ol className="transcript">
            {turns.map((turn) => (
              <li key={turn.turn_id}>
                <p className="transcript-question">
                  <span className="transcript-label">You asked</span> {turn.query_text}
                </p>
                <p className="transcript-answer">
                  <span className="transcript-label">Beacon</span> {turn.narration}
                </p>
                <p className="transcript-meta">
                  {turn.channel === 'voice' ? 'By voice' : 'By text'}
                  {formatTime(turn.created_at) && ` at ${formatTime(turn.created_at)}`}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  )
}
