/* Contest: Pi selected branch includes tool events, stable identity, durable cursor. */
import { describe, expect, it } from 'vitest'
import { captureSelectedPiBranch } from '../src/session-branch.ts'
import type { PluginRuntime } from '../src/recall.ts'

describe('Pi branch incremental capture', () => {
  it('includes tool results, resumes from the acknowledged checkpoint, and scans divergent branches', async () => {
    const entries = [
      { id: 'a', type: 'message', message: { role: 'user', content: 'hello' } },
      { id: 'b', type: 'message', message: { role: 'toolResult', content: 'file created' } },
    ]
    let checkpoint: unknown = null
    const captured: string[] = []
    const requests: string[] = []
    const client = {
      request: async (operation: string, payload: unknown) => {
        requests.push(operation)
        if (operation === 'get_connector_checkpoint') return { kind: 'json', value: { checkpoint } }
        if (operation === 'capture_content_source') {
          const record = payload as { source_id: string }
          captured.push(record.source_id)
          return { kind: 'json', value: { sequence: captured.length } }
        }
        if (operation === 'commit_connector_checkpoint') {
          const change = payload as { expected: unknown, checkpoint: unknown }
          expect(change.expected).toEqual(checkpoint)
          checkpoint = change.checkpoint
          return { kind: 'json', value: { checkpoint } }
        }
        throw new Error(`unexpected operation ${operation}`)
      },
    }
    const runtime = {
      client,
      config: { captureSessionBranch: true, authorization: undefined },
      resolveScope: async () => 'scope-a',
    } as unknown as PluginRuntime
    const session = { getSessionId: () => 'session-1', getBranch: () => entries }
    expect(await captureSelectedPiBranch({ runtime, session, cwd: '/project' })).toBe(2)
    expect(captured).toHaveLength(2)
    expect(new Set(captured).size).toBe(2)
    expect(await captureSelectedPiBranch({ runtime, session, cwd: '/project' })).toBe(0)
    expect(captured).toHaveLength(2)
    entries.splice(1, 1, { id: 'c', type: 'message', message: { role: 'toolResult', content: 'new branch' } })
    expect(await captureSelectedPiBranch({ runtime, session, cwd: '/project' })).toBe(2)
    expect(captured[2]).toBe(captured[0])
    expect(captured[3]).not.toBe(captured[1])
    expect(requests.filter((name) => name === 'commit_connector_checkpoint')).toHaveLength(4)
  })
})
