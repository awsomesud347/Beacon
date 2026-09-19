/** Start/stop voice mode. State is in the button text as well as aria-pressed, so it is
 * never signalled by colour or icon alone. */
import type { BeaconVoice } from '../hooks/useBeaconVoice'

export function VoiceControl({ voice }: { voice: BeaconVoice }) {
  const label = voice.active ? 'Turn voice off' : 'Turn voice on'

  return (
    <section aria-labelledby="voice-heading" className="panel">
      <h2 id="voice-heading">Voice</h2>

      <div className="button-row">
        <button
          type="button"
          className={voice.active ? undefined : 'primary'}
          aria-pressed={voice.active}
          disabled={voice.connecting}
          onClick={() => (voice.active ? voice.stop() : void voice.start())}
        >
          {voice.connecting ? 'Starting voice…' : label}
        </button>

        <button type="button" aria-pressed={voice.muted} disabled={!voice.active}
                onClick={voice.toggleMute}>
          {voice.muted ? 'Unmute microphone' : 'Mute microphone'}
        </button>
      </div>

      <p className="hint">
        {voice.active
          ? voice.speaking
            ? 'Beacon is speaking. Talk over it to interrupt.'
            : 'Listening. Ask a question out loud.'
          : 'Voice is off. Alt plus V turns it on; answers also appear as text.'}
      </p>

      {voice.error && <p className="answer-error">{voice.error}</p>}
    </section>
  )
}
