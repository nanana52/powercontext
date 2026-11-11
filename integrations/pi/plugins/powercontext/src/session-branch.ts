/* Copyright (c) 2026 OceanBase. Licensed under the Apache License, Version 2.0. */
/** Incrementally persist Pi's selected branch, including tool messages.
 *
 * The checkpoint is server-owned and updated only after an acknowledged
 * Source write. Restart/retry replays immutable Source IDs idempotently.
 * A changed Pi branch that no longer contains the checkpoint anchor is
 * rescanned, preserving its distinct events without losing previous history.
 */
import { createHash } from 'node:crypto'
import type { PluginRuntime } from './recall.ts'
import { MAX_SOURCE_BYTES } from './capture.ts'
import { containsSecret } from './secrets.ts'

export interface PiBranchSession {
  getSessionId(): string
  getBranch(): unknown
}

function stableJson(value: unknown): string { return JSON.stringify(value) }

function hash(value: string): string { return createHash('sha256').update(value).digest('hex') }

function anchor(entry: unknown): string {
  if (entry && typeof entry === 'object' && 'id' in entry && typeof entry.id === 'string') return entry.id
  return hash(stableJson(entry))
}

function boundedParts(text: string): string[] {
  // Preserve UTF-8 code-point boundaries so parts reconstruct the exact JSON.
  const parts: string[] = []
  let value = ''
  let bytes = 0
  for (const char of text) {
    const width = Buffer.byteLength(char, 'utf8')
    if (bytes + width > MAX_SOURCE_BYTES && value) {
      parts.push(value)
      value = ''
      bytes = 0
    }
    value += char
    bytes += width
  }
  if (value) parts.push(value)
  if (!parts.length || parts.length > 64) throw new Error('Pi event exceeds maximum capture fragments')
  return parts
}

function checkpointValue(value: unknown): { last_id: string } | null {
  if (!value || typeof value !== 'object') return null
  const last = (value as { last_id?: unknown }).last_id
  return typeof last === 'string' ? { last_id: last } : null
}

export async function captureSelectedPiBranch(input: {
  session: PiBranchSession
  cwd: string
  runtime: PluginRuntime
  signal?: AbortSignal
}): Promise<number> {
  if (!input.runtime.config.captureSessionBranch) return 0
  const sessionId = input.session.getSessionId().trim()
  const branch = input.session.getBranch()
  if (!sessionId || !Array.isArray(branch) || !branch.length) return 0
  const scopeId = await input.runtime.resolveScope(input.cwd)
  const binding = {
    scope_id: scopeId,
    binding_id: `pi-session:${hash(sessionId)}`,
    connector_name: 'pi-session-branch',
    connector_version: '1',
  }
  const client = input.runtime.client
  const checkpointResponse = await client.request('get_connector_checkpoint', { binding }, input.signal)
  let checkpoint: unknown = checkpointResponse.kind === 'json'
    && checkpointResponse.value && typeof checkpointResponse.value === 'object'
    ? (checkpointResponse.value as { checkpoint?: unknown }).checkpoint ?? null
    : null
  const lastId = checkpointValue(checkpoint)?.last_id
  const anchors = branch.map(anchor)
  // An ancestor checkpoint might no longer be present after a branch switch.
  // In that case replay all current entries, using event IDs for deduplication.
  const checkpointAt = lastId ? anchors.lastIndexOf(lastId) : -1
  const start = checkpointAt + 1
  let processed = 0
  for (let index = start; index < branch.length; index += 1) {
    const entry = branch[index]
    const encoded = stableJson(entry)
    if (!encoded || containsSecret(encoded, input.runtime.config.authorization)) {
      // Never checkpoint past an unsafe event: later replay must not skip it.
      break
    }
    const baseId = `pi-session-event:${hash([scopeId, sessionId, anchors[index]].join('\0'))}`
    const parts = boundedParts(encoded)
    for (let part = 0; part < parts.length; part += 1) {
      await client.request('capture_content_source', {
        scope_id: scopeId,
        source_id: parts.length === 1 ? baseId : `${baseId}:part:${part}`,
        content: parts[part],
        metadata: {
          origin: 'pi', event: 'session_branch', session_id: sessionId,
          event_id: anchors[index], branch_position: index,
          event_type: entry && typeof entry === 'object' && 'type' in entry ? String(entry.type) : 'unknown',
          part_index: part, part_count: parts.length, event_digest: hash(encoded),
        },
      }, input.signal)
    }
    // Only acknowledge an event when every fragment was durably accepted.
    const next = { last_id: anchors[index] }
    await client.request('commit_connector_checkpoint', {
      binding, expected: checkpoint, checkpoint: next,
    }, input.signal)
    checkpoint = next
    processed += 1
  }
  return processed
}
