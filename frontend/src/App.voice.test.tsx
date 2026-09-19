/** Voice wiring, with the ElevenLabs SDK faked: the real one opens a websocket. */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { DatasetInfo, Health, Turn } from './api/types'

const startSession = vi.fn()
const endSession = vi.fn()
const conversation = { status: 'disconnected', isSpeaking: false, isMuted: false }

vi.mock('@elevenlabs/react', () => ({
  ConversationProvider: ({ children }: { children: React.ReactNode }) => children,
  useConversation: () => ({
    ...conversation,
    startSession,
    endSession,
    setMuted: vi.fn(),
  }),
}))

const health: Health = {
  status: 'ok',
  contract_version: '1',
  narrator: 'local',
  demo_mode: false,
  stub_mode: false,
}

const dataset: DatasetInfo = {
  source: 'fixture',
  name: 'demo_persona.csv',
  row_count: 1009,
  date_min: '2025-08-01',
  date_max: '2026-09-30',
  current_period: 'September 2026',
}

const voiceTurn: Turn = {
  turn_id: 'voice-1',
  created_at: '2026-09-19T17:00:00Z',
  channel: 'voice',
  query_text: "what's unusual",
  intent: 'anomalies',
  narration: 'Three new subscriptions totaling $47.',
  narration_source: 'model',
  fact_bundle: null,
  guard: { passed: true, attempts: 1, rejected_tokens: [] },
  latency_ms: { analysis: 10, narration: 500, total: 515 },
  audio_url: null,
}

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response

/** jsdom has no EventSource; this one lets a test push a turn down the live feed. */
class FakeEventSource extends EventTarget {
  static last: FakeEventSource | null = null
  static readonly CLOSED = 2
  readyState = 1
  url: string
  constructor(url: string) {
    super()
    this.url = url
    FakeEventSource.last = this
    queueMicrotask(() => this.dispatchEvent(new Event('open')))
  }
  close() {
    this.readyState = FakeEventSource.CLOSED
  }
  emit(event: string, data: unknown) {
    this.dispatchEvent(new MessageEvent(event, { data: JSON.stringify(data) }))
  }
}

beforeEach(() => {
  conversation.status = 'disconnected'
  conversation.isSpeaking = false
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/health') return Promise.resolve(ok(health))
      if (url === '/api/dataset') return Promise.resolve(ok(dataset))
      if (url === '/api/voice/session')
        return Promise.resolve(ok({ agent_id: 'agent_1', signed_url: 'wss://signed' }))
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })
  )
  vi.stubGlobal('navigator', {
    ...navigator,
    mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({}) },
  })
  FakeEventSource.last = null
  vi.stubGlobal('EventSource', FakeEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

const liveRegion = (container: HTMLElement) =>
  container.querySelector('[aria-live="polite"]') as HTMLElement

describe('voice mode', () => {
  it('asks the backend for a signed URL and never handles the API key', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Turn voice on' }))

    await waitFor(() =>
      expect(startSession).toHaveBeenCalledWith({
        signedUrl: 'wss://signed',
        connectionType: 'websocket',
      })
    )
    const calls = vi.mocked(fetch).mock.calls.map(([url]) => String(url))
    expect(calls).toContain('/api/voice/session')
  })

  it('requests the microphone only after the user asks for voice', async () => {
    const user = userEvent.setup()
    render(<App />)
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Turn voice on' }))
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled()
  })

  it('ends the session when voice is turned off', async () => {
    conversation.status = 'connected'
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Turn voice off' }))
    expect(endSession).toHaveBeenCalled()
  })

  /** Hard rule §5.4: the agent is already saying it, so the screen reader must not. */
  it('stays silent when a voice turn arrives while voice is live', async () => {
    conversation.status = 'connected'
    const { container } = render(<App />)
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull())

    FakeEventSource.last!.emit('turn', voiceTurn)

    // The transcript carries it; the live region does not.
    await within(container.querySelector('[role="log"]') as HTMLElement).findByText(
      voiceTurn.narration
    )
    expect(liveRegion(container)).toBeEmptyDOMElement()
  })

  it('announces a voice turn when voice is off (text-only user)', async () => {
    const { container } = render(<App />)
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull())

    FakeEventSource.last!.emit('turn', voiceTurn)

    await waitFor(() => expect(liveRegion(container)).toHaveTextContent(voiceTurn.narration))
  })

  it('announces a voice turn when the user opted in to hearing both', async () => {
    conversation.status = 'connected'
    const user = userEvent.setup()
    const { container } = render(<App />)
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull())

    await user.click(screen.getByLabelText(/Also read voice answers/))
    FakeEventSource.last!.emit('turn', voiceTurn)

    await waitFor(() => expect(liveRegion(container)).toHaveTextContent(voiceTurn.narration))
  })

  it('Alt+V toggles voice from the keyboard', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.keyboard('{Alt>}v{/Alt}')
    await waitFor(() => expect(startSession).toHaveBeenCalled())
  })

  it('lists the voice shortcut alongside a visible button', () => {
    render(<App />)
    const shortcuts = within(screen.getByRole('region', { name: 'Keyboard shortcuts' }))
    expect(shortcuts.getByText('Alt + V')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Turn voice on' })).toBeInTheDocument()
  })
})
