/** Wording for spoken status messages. These describe app state, never financial
 * figures — every number a user hears about their money comes from turn.narration. */
import type { DatasetInfo } from '../api/types'

export function describeDataset(info: DatasetInfo): string {
  return `Loaded ${info.row_count.toLocaleString()} transactions, current period ${info.current_period}`
}
