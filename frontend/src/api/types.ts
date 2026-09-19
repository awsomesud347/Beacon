/** Convenience aliases over the generated contract. Never hand-write API shapes. */
import type { components } from './contract.gen'

export type Turn = components['schemas']['Turn']
export type FactBundle = components['schemas']['FactBundle']
export type Anomaly = components['schemas']['Anomaly']
export type GuardResult = components['schemas']['GuardResult']
export type Health = components['schemas']['Health']
export type DatasetInfo = components['schemas']['DatasetInfo']
export type VoiceSession = components['schemas']['VoiceSession']
export type ApiErrorBody = components['schemas']['ApiError']
export type Channel = components['schemas']['Channel']
export type Intent = components['schemas']['Intent']
export type NarrationSource = components['schemas']['NarrationSource']
export type ErrorCode = components['schemas']['ErrorCode']
