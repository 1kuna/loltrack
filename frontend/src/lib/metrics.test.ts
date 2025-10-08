import { describe, expect, it } from 'vitest'
import { computeStatus, computeTrend, type MetricMode, type MetricUnit } from './metrics'

const higher: MetricMode = 'higher_is_better'
const earlier: MetricMode = 'earlier_is_better'
const countUnit: MetricUnit = 'count'
const timeUnit: MetricUnit = 'time'

describe('computeStatus', () => {
  it('returns neutral when value or target missing', () => {
    expect(computeStatus(null, 10, higher, countUnit)).toBe('neutral')
    expect(computeStatus(10, null, higher, countUnit)).toBe('neutral')
  })

  it('flags higher metrics correctly', () => {
    expect(computeStatus(110, 100, higher, countUnit)).toBe('ok')
    expect(computeStatus(92, 100, higher, countUnit)).toBe('warn')
    expect(computeStatus(70, 100, higher, countUnit)).toBe('bad')
  })

  it('flags earlier metrics correctly', () => {
    expect(computeStatus(80, 100, earlier, timeUnit)).toBe('ok')
    expect(computeStatus(104, 100, earlier, timeUnit)).toBe('warn')
    expect(computeStatus(130, 100, earlier, timeUnit)).toBe('bad')
  })
})

describe('computeTrend', () => {
  it('returns flat without baseline', () => {
    expect(computeTrend(10, null, higher, countUnit)).toBe('flat')
  })

  it('detects upward trend for higher metrics', () => {
    expect(computeTrend(120, 100, higher, countUnit)).toBe('up')
    expect(computeTrend(98, 100, higher, countUnit)).toBe('flat')
    expect(computeTrend(70, 100, higher, countUnit)).toBe('down')
  })

  it('detects improvement for earlier metrics when values shrink', () => {
    expect(computeTrend(90, 110, earlier, timeUnit)).toBe('up')
    expect(computeTrend(115, 110, earlier, timeUnit)).toBe('down')
  })
})
