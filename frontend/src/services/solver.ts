import { fallbackResult } from '../data/scenario'
import type { OptimizationRequest, OptimizationResult } from '../types'

const MOCK_DELAY_MS = 1100
const API_TIMEOUT_MS = 5000

function mockOptimize(): Promise<OptimizationResult> {
  return new Promise((resolve) => {
    window.setTimeout(() => resolve({
      ...fallbackResult,
      generated_at: new Date().toISOString(),
    }), MOCK_DELAY_MS)
  })
}

export async function optimizeRoute(request: OptimizationRequest): Promise<OptimizationResult> {
  const apiUrl = import.meta.env.VITE_SOLVER_API_URL
  if (!apiUrl) return mockOptimize()

  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS)

  try {
    const response = await fetch(`${apiUrl.replace(/\/$/, '')}/optimize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    })

    if (!response.ok) throw new Error(`Solver returned HTTP ${response.status}`)
    const result = await response.json() as OptimizationResult
    if (!result.routes?.length) throw new Error('Solver returned no routes')
    return result
  } finally {
    window.clearTimeout(timeout)
  }
}
