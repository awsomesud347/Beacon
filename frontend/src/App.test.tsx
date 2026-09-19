import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import App from './App'
import type { DatasetInfo, Health, Turn } from './api/types'

const NARRATION =
  'Your spending is normal except for one thing: you paid three new subscriptions ' +
  "this month that you didn't pay last month, totaling $47."

const health: Health = {
  status: 'ok',
  contract_version: '1',
  narrator: 'cloud',
  demo_mode: false,
  stub_mode: true,
}

const dataset: DatasetInfo = {
  source: 'fixture',
  name: 'demo_persona.csv',
  row_count: 1847,
  date_min: '2025-08-01',
  date_max: '2026-09-30',
  current_period: 'September 2026',
}

const turn: Turn = {
  turn_id: 'turn-1',
  created_at: '2026-09-19T17:00:00Z',
  channel: 'text',
  query_text: "What's unusual?",
  intent: 'anomalies',
  narration: NARRATION,
  narration_source: 'model',
  fact_bundle: {
    contract_version: '1',
    query_type: 'anomalies',
    period: 'September 2026',
    verdict: 'normal_with_exception',
    anomalies: [
      {
        type: 'new_recurring',
        merchants: ['Streamly Plus', 'CloudVault', 'FitTrack Pro'],
        category: 'subscriptions',
        count: 3,
        total: 47.0,
      },
    ],
    context: { month_total_out: 2914.22, prior_month_total_out: 2871.05, delta_pct: 1.5 },
  },
  guard: { passed: true, attempts: 1, rejected_tokens: [] },
  latency_ms: { analysis: 12, narration: 640, total: 655 },
  audio_url: null,
}

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/health') return Promise.resolve(ok(health))
      if (url === '/api/dataset') return Promise.resolve(ok(dataset))
      if (url === '/api/query') return Promise.resolve(ok(turn))
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    })
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/** Each panel is a <section> with an accessible name, so queries can be scoped. */
const region = (name: string) => screen.getByRole('region', { name })

/** The live region is visually hidden; find it by its aria attributes. */
const liveRegion = (container: HTMLElement) =>
  container.querySelector('[aria-live="polite"]') as HTMLElement

const transcript = (container: HTMLElement) =>
  container.querySelector('[role="log"]') as HTMLElement

const askHero = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole('button', { name: "What's unusual?" }))

describe('App', () => {
  it('has no axe violations', async () => {
    const { container } = render(<App />)
    await within(region('Your data')).findByText(/1,847 transactions/)
    expect((await axe(container)).violations).toEqual([])
  })

  it('has exactly one polite live region', async () => {
    const { container } = render(<App />)
    await within(region('Your data')).findByText(/1,847 transactions/)
    expect(container.querySelectorAll('[aria-live="polite"]')).toHaveLength(1)
  })

  it('does not let the transcript log compete with the live region', () => {
    const { container } = render(<App />)
    expect(transcript(container)).toHaveAttribute('aria-live', 'off')
  })

  it('shows the narration verbatim, announces it, and moves focus to the answer', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)

    await askHero(user)

    // Verbatim: no reformatting of any figure the backend produced.
    await within(region('Answer')).findByText(NARRATION)
    expect(liveRegion(container)).toHaveTextContent(NARRATION)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Answer' })).toHaveFocus())
  })

  it('sends the typed question to the query endpoint', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.type(screen.getByLabelText('Your question'), 'what is unusual')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    await within(region('Answer')).findByText(NARRATION)
    const call = vi.mocked(fetch).mock.calls.find(([url]) => url === '/api/query')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      text: 'what is unusual',
      channel: 'text',
      discreet: false,
    })
  })

  it('sends discreet: true once discreet mode is on', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByLabelText(/Discreet mode/))
    await askHero(user)

    await within(region('Answer')).findByText(NARRATION)
    const call = vi.mocked(fetch).mock.calls.find(([url]) => url === '/api/query')
    expect(JSON.parse(String(call?.[1]?.body)).discreet).toBe(true)
  })

  it('reveals the fact bundle and guard status in the payload inspector', async () => {
    const user = userEvent.setup()
    render(<App />)
    await askHero(user)
    await within(region('Answer')).findByText(NARRATION)

    const privacy = within(region('Privacy'))
    const toggle = privacy.getByRole('button', {
      name: /everything sent to the language model/i,
    })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(privacy.getByText(/Guard passed, 1 attempt/)).toBeInTheDocument()
    expect(privacy.getByText(/"query_type": "anomalies"/)).toBeInTheDocument()
  })

  it('re-announces the last answer on replay', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)
    await askHero(user)
    await within(region('Answer')).findByText(NARRATION)

    await user.click(screen.getByRole('button', { name: 'Stop speaking' }))
    expect(liveRegion(container)).toBeEmptyDOMElement()

    await user.click(screen.getByRole('button', { name: 'Replay answer' }))
    expect(liveRegion(container)).toHaveTextContent(NARRATION)
  })

  it('records both sides of every turn in the transcript', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)
    await askHero(user)
    await within(region('Answer')).findByText(NARRATION)

    const log = within(transcript(container))
    expect(log.getByText(/What's unusual\?/)).toBeInTheDocument()
    expect(log.getByText(NARRATION)).toBeInTheDocument()
  })

  it('shows the API error message instead of a stack when a query fails', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/health') return Promise.resolve(ok(health))
      if (url === '/api/dataset') return Promise.resolve(ok(dataset))
      return Promise.resolve({
        ok: false,
        status: 501,
        json: async () => ({
          code: 'not_implemented',
          message: 'query is not implemented yet',
          details: [],
        }),
      } as Response)
    })

    const user = userEvent.setup()
    render(<App />)
    await askHero(user)

    expect(
      await within(region('Answer')).findByText('query is not implemented yet')
    ).toBeInTheDocument()
  })
})
