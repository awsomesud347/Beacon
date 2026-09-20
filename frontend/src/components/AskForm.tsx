/** The text path: a labelled question box plus the four hero questions as real buttons.
 * The suggested questions matter more than the input for our primary user — they remove
 * the need to compose a question at all. */
import { useId, useState } from 'react'

const SUGGESTED_QUESTIONS = [
  "What's unusual?",
  'How am I doing this month?',
  'Where did my money go?',
  'Compare to last month',
  'How much did I spend on groceries?',
  'What subscriptions do I have?',
  'What can I ask you?',
] as const

interface AskFormProps {
  onAsk: (text: string) => void
  busy: boolean
}

export function AskForm({ onAsk, busy }: AskFormProps) {
  const inputId = useId()
  const hintId = useId()
  const [text, setText] = useState('')

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const question = text.trim()
    if (!question) return
    onAsk(question)
    setText('')
  }

  return (
    <section aria-labelledby="ask-heading" className="panel">
      <h2 id="ask-heading">Ask about your money</h2>

      <form onSubmit={submit} className="ask-form">
        <label htmlFor={inputId}>Your question</label>
        <p id={hintId} className="hint">
          For example: what&rsquo;s unusual, how much did I spend on groceries in July, what
          subscriptions do I have. You can also follow up with &ldquo;what about last
          month?&rdquo;
        </p>
        <div className="ask-row">
          <input
            id={inputId}
            aria-describedby={hintId}
            type="text"
            value={text}
            maxLength={500}
            autoComplete="off"
            onChange={(event) => setText(event.target.value)}
          />
          <button type="submit" className="primary" disabled={busy || !text.trim()}>
            Ask
          </button>
        </div>
      </form>

      <h3 id="suggested-heading">Suggested questions</h3>
      <ul aria-labelledby="suggested-heading" className="suggestions">
        {SUGGESTED_QUESTIONS.map((question) => (
          <li key={question}>
            <button type="button" onClick={() => onAsk(question)} disabled={busy}>
              {question}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
