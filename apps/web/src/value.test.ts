import { describe, expect, it } from 'vitest'

const recomputeInv = (amount: number, actionProbability: number, baselineProbability: number, directCost: number, downstreamCost: number) =>
  Math.round((actionProbability - baselineProbability) * amount - directCost - downstreamCost)

describe('displayed future values', () => {
  it('are recomputable from persisted inputs', () => {
    expect(recomputeInv(499_900, 0.71, 0.18, 3_800, 0)).toBe(261_147)
  })

  it('never credits natural recovery to the intervention', () => {
    expect(recomputeInv(100_000, 0.2, 0.2, 0, 0)).toBe(0)
  })
})

