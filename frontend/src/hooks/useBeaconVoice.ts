/** Voice mode: an ElevenLabs agent that calls our own backend as its LLM.
 *
 * The browser never sees the ElevenLabs API key — it asks our backend for a short-lived
 * signed URL (GET /api/voice/session) and opens the conversation with that.
 *
 * Answers do NOT come back through this hook. The agent speaks them, and the same turn
 * reaches the app over /api/events like every other turn, so voice and text agree.
 *
 * Barge-in is native: talking over the agent interrupts it. There is no documented way to
 * stop playback mid-sentence without ending the session, so "Stop voice" does exactly that
 * and says so. */
import { useConversation } from '@elevenlabs/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage, getVoiceSession } from '../api/client'

export interface BeaconVoice {
  active: boolean
  connecting: boolean
  speaking: boolean
  muted: boolean
  error: string | null
  start: () => Promise<void>
  stop: () => void
  toggleMute: () => void
}

export function useBeaconVoice(onStatus: (message: string) => void): BeaconVoice {
  const [error, setError] = useState<string | null>(null)
  const [connecting, setConnecting] = useState(false)
  const announced = useRef(onStatus)
  useEffect(() => {
    announced.current = onStatus
  })

  const conversation = useConversation({
    onConnect: () => announced.current('Voice on. Ask a question out loud.'),
    onDisconnect: () => announced.current('Voice off.'),
    onError: (message: string) => setError(message || 'The voice connection failed'),
  })

  const start = useCallback(async () => {
    setError(null)
    setConnecting(true)
    try {
      // Mic permission is requested here, inside a click handler — never on load.
      await navigator.mediaDevices.getUserMedia({ audio: true })
      const session = await getVoiceSession()
      if (!session.signed_url) throw new Error('The server did not return a voice session')
      conversation.startSession({ signedUrl: session.signed_url, connectionType: 'websocket' })
    } catch (err) {
      const text = errorMessage(err)
      setError(text)
      announced.current(`Voice could not start. ${text}`)
    } finally {
      setConnecting(false)
    }
  }, [conversation])

  const stop = useCallback(() => {
    conversation.endSession()
  }, [conversation])

  const toggleMute = useCallback(() => {
    const next = !conversation.isMuted
    conversation.setMuted(next)
    announced.current(next ? 'Microphone muted.' : 'Microphone on.')
  }, [conversation])

  return {
    active: conversation.status === 'connected',
    connecting: connecting || conversation.status === 'connecting',
    speaking: conversation.isSpeaking,
    muted: conversation.isMuted,
    error,
    start,
    stop,
    toggleMute,
  }
}
