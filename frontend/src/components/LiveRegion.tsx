/** The one and only aria-live="polite" region in the app (hard rule §5.3).
 *
 * It is visually hidden and separate from the visible answer so we can decide per turn
 * whether the screen reader should speak — when the voice agent is already saying it,
 * we stay silent here and let the transcript carry it. */
export function LiveRegion({ message }: { message: string }) {
  return (
    <div className="visually-hidden" aria-live="polite" aria-atomic="true">
      {message}
    </div>
  )
}
