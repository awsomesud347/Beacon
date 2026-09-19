import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import { VoiceControl } from './VoiceControl'
import type { BeaconVoice } from '../hooks/useBeaconVoice'

const voice = (overrides: Partial<BeaconVoice> = {}): BeaconVoice => ({
  active: false,
  connecting: false,
  speaking: false,
  muted: false,
  error: null,
  start: vi.fn(),
  stop: vi.fn(),
  toggleMute: vi.fn(),
  ...overrides,
})

describe('VoiceControl', () => {
  it('has no axe violations', async () => {
    const { container } = render(<VoiceControl voice={voice()} />)
    expect((await axe(container)).violations).toEqual([])
  })

  it('states voice mode in words, not just aria-pressed', () => {
    const { rerender } = render(<VoiceControl voice={voice()} />)
    const off = screen.getByRole('button', { name: 'Turn voice on' })
    expect(off).toHaveAttribute('aria-pressed', 'false')

    rerender(<VoiceControl voice={voice({ active: true })} />)
    const on = screen.getByRole('button', { name: 'Turn voice off' })
    expect(on).toHaveAttribute('aria-pressed', 'true')
  })

  it('offers muting only while voice is running', () => {
    const { rerender } = render(<VoiceControl voice={voice()} />)
    expect(screen.getByRole('button', { name: 'Mute microphone' })).toBeDisabled()

    rerender(<VoiceControl voice={voice({ active: true })} />)
    expect(screen.getByRole('button', { name: 'Mute microphone' })).toBeEnabled()
  })

  it('says how to interrupt while the agent speaks', () => {
    render(<VoiceControl voice={voice({ active: true, speaking: true })} />)
    expect(screen.getByText(/Talk over it to interrupt/)).toBeInTheDocument()
  })

  it('shows a voice failure as a sentence', () => {
    render(<VoiceControl voice={voice({ error: 'Microphone permission denied' })} />)
    expect(screen.getByText('Microphone permission denied')).toBeInTheDocument()
  })
})
