import { useCallback, useEffect, useRef, useState } from 'react'
import {
  errorMessage,
  getDataset,
  getHealth,
  postQuery,
  resetDataset,
  uploadDataset,
} from './api/client'
import type { DatasetInfo, Health, Turn } from './api/types'
import { AnswerPanel } from './components/AnswerPanel'
import { AskForm } from './components/AskForm'
import { DatasetPanel } from './components/DatasetPanel'
import { LiveRegion } from './components/LiveRegion'
import { PayloadInspector } from './components/PayloadInspector'
import { SettingsPanel } from './components/SettingsPanel'
import { Transcript } from './components/Transcript'
import { useAnnouncer } from './hooks/useAnnouncer'
import { useEventStream } from './hooks/useEventStream'
import { describeDataset } from './lib/describe'

function App() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [dataset, setDataset] = useState<DatasetInfo | null>(null)
  const [discreet, setDiscreet] = useState(false)
  const [readVoiceAnswers, setReadVoiceAnswers] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [focusRequest, setFocusRequest] = useState(0)

  // Voice is not wired up yet; the announcement rules already key off it.
  const [voiceActive] = useState(false)

  const { message, announce, clear } = useAnnouncer()
  const answerHeadingRef = useRef<HTMLHeadingElement>(null)
  const inspectorButtonRef = useRef<HTMLButtonElement>(null)
  const seenTurnIds = useRef(new Set<string>())

  const latestTurn = turns.length > 0 ? turns[turns.length - 1] : null

  /** Focus after the DOM has the new answer in it. */
  useEffect(() => {
    if (focusRequest > 0) answerHeadingRef.current?.focus()
  }, [focusRequest])

  /** A turn can arrive twice — once as the POST response, once over SSE. First wins. */
  const addTurn = useCallback(
    (turn: Turn) => {
      if (seenTurnIds.current.has(turn.turn_id)) return
      seenTurnIds.current.add(turn.turn_id)
      setTurns((previous) => [...previous, turn])
      setError(null)

      // Hard rule §5.4: never talk over the voice agent. A voice turn while voice is
      // live is already being spoken, so the transcript carries it and we stay quiet.
      const spokenByAgent = voiceActive && turn.channel === 'voice'
      if (!spokenByAgent || readVoiceAnswers) {
        announce(turn.narration)
        setFocusRequest((n) => n + 1)
      }
    },
    [announce, readVoiceAnswers, voiceActive]
  )

  const onDataset = useCallback(
    (info: DatasetInfo) => {
      setDataset(info)
      announce(describeDataset(info))
    },
    [announce]
  )

  const connected = useEventStream({ onTurn: addTurn, onDataset })

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
    getDataset()
      .then(setDataset)
      .catch(() => setDataset(null))
  }, [])

  const fail = useCallback(
    (err: unknown) => {
      const text = errorMessage(err)
      setError(text)
      announce(text)
      setFocusRequest((n) => n + 1)
    },
    [announce]
  )

  const ask = useCallback(
    async (text: string) => {
      setBusy(true)
      setError(null)
      try {
        addTurn(await postQuery(text, 'text', discreet))
      } catch (err) {
        fail(err)
      } finally {
        setBusy(false)
      }
    },
    [addTurn, discreet, fail]
  )

  const replay = useCallback(() => {
    if (!latestTurn) {
      announce('Nothing to replay yet.')
      return
    }
    announce(latestTurn.narration)
    setFocusRequest((n) => n + 1)
  }, [announce, latestTurn])

  /** Esc: stop talking. Clearing the live region drops anything still queued. */
  const stop = useCallback(() => clear(), [clear])

  const toggleInspector = useCallback(() => setInspectorOpen((open) => !open), [])

  const upload = useCallback(
    async (file: File) => {
      setBusy(true)
      try {
        onDataset(await uploadDataset(file))
      } catch (err) {
        fail(err)
      } finally {
        setBusy(false)
      }
    },
    [fail, onDataset]
  )

  const reset = useCallback(async () => {
    setBusy(true)
    try {
      onDataset(await resetDataset())
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }, [fail, onDataset])

  /** Alt+letter avoids NVDA's Insert/CapsLock modifiers. Every shortcut also has a
   * visible button, so nothing is reachable by keyboard alone. */
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        stop()
        return
      }
      if (!event.altKey || event.ctrlKey || event.metaKey) return
      const key = event.key.toLowerCase()
      if (key === 'r') {
        event.preventDefault()
        replay()
      } else if (key === 'p') {
        event.preventDefault()
        toggleInspector()
        inspectorButtonRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [replay, stop, toggleInspector])

  return (
    <>
      <a href="#main" className="skip-link">
        Skip to main content
      </a>

      <header className="site-header">
        <h1>Beacon</h1>
        <p className="tagline">Ask how your month is going, or what&rsquo;s unusual.</p>
      </header>

      <main id="main">
        <AnswerPanel
          turn={latestTurn}
          busy={busy}
          error={error}
          headingRef={answerHeadingRef}
        />

        <section aria-labelledby="playback-heading" className="panel">
          <h2 id="playback-heading">Playback</h2>
          <div className="button-row">
            <button type="button" onClick={replay} disabled={!latestTurn}>
              Replay answer
            </button>
            <button type="button" onClick={stop}>
              Stop speaking
            </button>
          </div>
        </section>

        <AskForm onAsk={(text) => void ask(text)} busy={busy} />

        <PayloadInspector
          turn={latestTurn}
          open={inspectorOpen}
          onToggle={toggleInspector}
          buttonRef={inspectorButtonRef}
        />

        <Transcript turns={turns} />

        <DatasetPanel
          dataset={dataset}
          busy={busy}
          onUpload={(file) => void upload(file)}
          onReset={() => void reset()}
        />

        <SettingsPanel
          discreet={discreet}
          onDiscreetChange={setDiscreet}
          readVoiceAnswers={readVoiceAnswers}
          onReadVoiceAnswersChange={setReadVoiceAnswers}
        />

        <section aria-labelledby="shortcuts-heading" className="panel">
          <h2 id="shortcuts-heading">Keyboard shortcuts</h2>
          <dl className="shortcuts">
            <dt>Alt + R</dt>
            <dd>Replay the last answer</dd>
            <dt>Alt + P</dt>
            <dd>Show or hide what was sent to the language model</dd>
            <dt>Escape</dt>
            <dd>Stop speaking</dd>
          </dl>
        </section>
      </main>

      <footer className="site-footer">
        <h2 className="visually-hidden">Status</h2>
        <p>
          {connected ? 'Live updates on' : 'Live updates reconnecting'}
          {health?.stub_mode && ' · stub data'}
          {health?.demo_mode && ' · offline demo mode'}
          {dataset && ` · ${describeDataset(dataset)}`}
        </p>
      </footer>

      <LiveRegion message={message} />
    </>
  )
}

export default App
