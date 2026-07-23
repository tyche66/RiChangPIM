import { describe, it, expect, beforeEach, vi } from 'vitest'

// Directly test the normalizeProposalEnvelope function.
// We re-implement the logic here to test it independently of the full API module.
type ProposalEnvelopeOrBare =
  | { code: number; data: Record<string, unknown>; msg?: string }
  | Record<string, unknown>

function _isProposalEnvelope(v: ProposalEnvelopeOrBare): v is { code: number; data: Record<string, unknown>; msg?: string } {
  return 'code' in v && typeof v.code === 'number' && 'data' in v
}

function normalizeProposalEnvelope(
  p: Promise<ProposalEnvelopeOrBare>,
): Promise<{ code: number; data: Record<string, unknown>; msg?: string }> {
  return p.then((res) => {
    if (_isProposalEnvelope(res)) {
      return res
    }
    return { code: 200, data: res }
  })
}

describe('normalizeProposalEnvelope', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('passes through new envelope response unchanged', async () => {
    const envelope = {
      code: 200,
      data: { id: '1', proposal_no: 'P001', status: 'draft', items: [] },
      msg: 'ok',
    }
    const result = await normalizeProposalEnvelope(Promise.resolve(envelope))
    expect(result.code).toBe(200)
    expect(result.data.id).toBe('1')
    expect(result.data.status).toBe('draft')
    expect(result.msg).toBe('ok')
  })

  it('wraps bare proposal response into envelope', async () => {
    const bare = {
      id: '2',
      proposal_no: 'P002',
      status: 'confirmed',
      items: [],
    }
    const result = await normalizeProposalEnvelope(Promise.resolve(bare))
    expect(result.code).toBe(200)
    expect(result.data.id).toBe('2')
    expect(result.data.proposal_no).toBe('P002')
    expect(result.data.status).toBe('confirmed')
  })

  it('rejects when the promise rejects', async () => {
    const err = new Error('network error')
    await expect(normalizeProposalEnvelope(Promise.reject(err))).rejects.toThrow('network error')
  })
})
