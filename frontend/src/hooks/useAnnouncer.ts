/** Drives the app's single aria-live region.
 *
 * Re-announcing identical text (Replay) needs the DOM text to actually change, or the
 * screen reader has nothing to react to. Alternating an invisible zero-width space does
 * that without altering what is spoken. */
import { useCallback, useRef, useState } from 'react'

const ZERO_WIDTH_SPACE = '​'

export interface Announcer {
  message: string
  announce: (text: string) => void
  clear: () => void
}

export function useAnnouncer(): Announcer {
  const [message, setMessage] = useState('')
  const parity = useRef(0)

  const announce = useCallback((text: string) => {
    parity.current += 1
    setMessage(parity.current % 2 === 0 ? text : text + ZERO_WIDTH_SPACE)
  }, [])

  const clear = useCallback(() => setMessage(''), [])

  return { message, announce, clear }
}
