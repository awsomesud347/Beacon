/** F1 — load a ledger. A labelled file input plus a way back to the demo data, so a
 * mis-uploaded CSV can never strand someone who can't see what went wrong. */
import { useId, useRef } from 'react'
import type { DatasetInfo } from '../api/types'
import { describeDataset } from '../lib/describe'

interface DatasetPanelProps {
  dataset: DatasetInfo | null
  busy: boolean
  onUpload: (file: File) => void
  onReset: () => void
}

export function DatasetPanel({ dataset, busy, onUpload, onReset }: DatasetPanelProps) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)

  const change = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) onUpload(file)
    // Allow re-selecting the same file after a reset.
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <section aria-labelledby="dataset-heading" className="panel">
      <h2 id="dataset-heading">Your data</h2>

      <p>{dataset ? describeDataset(dataset) : 'No data loaded yet.'}</p>
      {dataset && (
        <p className="hint">
          {dataset.source === 'upload' ? 'From your upload' : 'Demo data'}: {dataset.name}
        </p>
      )}

      <div className="dataset-controls">
        <div className="field">
          <label htmlFor={inputId}>Upload a transactions CSV file</label>
          <input
            id={inputId}
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={change}
          />
        </div>
        <button type="button" onClick={onReset} disabled={busy}>
          Reset to demo data
        </button>
      </div>
    </section>
  )
}
