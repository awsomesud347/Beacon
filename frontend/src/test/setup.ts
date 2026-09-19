import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, expect } from 'vitest'
import * as matchers from 'vitest-axe/matchers'

expect.extend(matchers)

// vitest runs without `globals`, so Testing Library's automatic cleanup never
// registers and every render would pile up in the same document.
afterEach(cleanup)
