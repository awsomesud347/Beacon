/** Two settings, both accessibility decisions rather than preferences.
 *
 * Discreet mode (context §6.5): saying a balance out loud on a bus is exactly the
 * disclosure this project exists to remove.
 * Read voice answers (hard rule §5.4): the override for people who want their own
 * screen reader to speak the answer even while the voice agent is running. */
import { useId } from 'react'

interface SettingsPanelProps {
  discreet: boolean
  onDiscreetChange: (value: boolean) => void
  readVoiceAnswers: boolean
  onReadVoiceAnswersChange: (value: boolean) => void
}

export function SettingsPanel({
  discreet,
  onDiscreetChange,
  readVoiceAnswers,
  onReadVoiceAnswersChange,
}: SettingsPanelProps) {
  const discreetId = useId()
  const readId = useId()

  return (
    <section aria-labelledby="settings-heading" className="panel">
      <h2 id="settings-heading">Settings</h2>

      <div className="checkbox-row">
        <input
          id={discreetId}
          type="checkbox"
          checked={discreet}
          onChange={(event) => onDiscreetChange(event.target.checked)}
        />
        <label htmlFor={discreetId}>
          Discreet mode — hold back amounts unless I ask for them
        </label>
      </div>

      <div className="checkbox-row">
        <input
          id={readId}
          type="checkbox"
          checked={readVoiceAnswers}
          onChange={(event) => onReadVoiceAnswersChange(event.target.checked)}
        />
        <label htmlFor={readId}>Also read voice answers with my screen reader</label>
      </div>
    </section>
  )
}
