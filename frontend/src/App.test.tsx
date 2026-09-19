import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('has no axe violations', async () => {
    const { container } = render(<App />)
    const results = await axe(container)
    expect(results.violations).toEqual([])
  })
})
