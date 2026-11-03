// FlowMemo Server Function: secure signed sessions + real PowerContext memory.
// Site project data remains in the browser's localStorage; only memory uses PC.

const envGet = (key: string): string => (globalThis as any).Deno?.env?.get(key) || '';
const PC_URL = envGet('POWERCONTEXT_URL').replace(/\/$/, '');
const PC_TOKEN = envGet('POWERCONTEXT_TOKEN');
// Prefer a dedicated secret. For a low-friction migration from the existing
// deployment, the already configured server-only PC token can sign sessions.
// Never use a public/default constant secret.
const SESSION_SECRET = envGet('FLOWMEMO_SESSION_SECRET') || envGet('SIGNING_SECRET') || PC_TOKEN;
const SESSION_LIFETIME_MS = 30 * 24 * 3600 * 1000;
const enc = new TextEncoder();

type Session = {
  visitorId: string;
  projectId: string;
  scopeId: string;
  exp: number;
  prefHash?: string;
};
type PcResponse = {
  status: number;
  data: any;
  requestId: string;
  contentType: string;
  parsedJson: boolean;
  servedBy: string;
  bodyPrefix: string;
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff',
    },
  });
}

function fromBase64(value: string): Uint8Array {
  const raw = atob(value);
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}

function toBase64(buffer: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)));
}

async function signingKey(): Promise<CryptoKey> {
  if (!SESSION_SECRET || SESSION_SECRET.length < 24) throw new Error('Session signing is not configured');
  return await crypto.subtle.importKey('raw', enc.encode(SESSION_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']);
}

async function makeSession(session: Session): Promise<string> {
  // ASCII-only JSON is ensured for our generated IDs and hashes.
  const payload = btoa(JSON.stringify(session));
  const mac = await crypto.subtle.sign('HMAC', await signingKey(), enc.encode(payload));
  return `${payload}.${toBase64(mac)}`;
}

async function verifySession(value: unknown): Promise<Session | null> {
  if (typeof value !== 'string' || value.length > 4096) return null;
  const split = value.indexOf('.');
  if (split < 1) return null;
  try {
    const payload = value.slice(0, split);
    const sig = fromBase64(value.slice(split + 1));
    if (!await crypto.subtle.verify('HMAC', await signingKey(), sig, enc.encode(payload))) return null;
    const parsed = JSON.parse(atob(payload));
    if (typeof parsed.visitorId !== 'string' ||
        typeof parsed.projectId !== 'string' ||
        typeof parsed.scopeId !== 'string' ||
        typeof parsed.exp !== 'number' ||
        parsed.exp < Date.now() || parsed.exp > Date.now() + SESSION_LIFETIME_MS + 300000) return null;
    if (!/^scp_[A-Za-z0-9_-]{8,200}$/.test(parsed.scopeId)) return null;
    if (parsed.prefHash !== undefined && !/^[a-f0-9]{64}$/.test(parsed.prefHash)) return null;
    return parsed as Session;
  } catch {
    return null;
  }
}

function safeString(v: unknown, max = 200): string {
  return typeof v === 'string' ? v.trim().slice(0, max) : '';
}

async function pcCall(method: string, path: string, body?: unknown): Promise<PcResponse> {
  if (!PC_URL || !PC_TOKEN) throw new Error('PowerContext is not configured');
  const headers: Record<string, string> = {
    'accept': 'application/json',
    'authorization': `Bearer ${PC_TOKEN}`,
  };
  if (body !== undefined) headers['content-type'] = 'application/json';
  let response: Response;
  try {
    response = await fetch(PC_URL + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(12000),
    });
  } catch {
    throw new Error('PowerContext network error or timeout');
  }
  const rawBody = await response.text().catch(() => '');
  let data: any = {};
  let parsedJson = false;
  try { data = JSON.parse(rawBody); parsedJson = true; } catch { /* non-JSON upstream */ }
  const requestId = response.headers.get('x-powercontext-request-id') || '';
  const contentType = response.headers.get('content-type') || '';
  const servedBy = response.headers.get('x-served-by') || '';
  console.log('[FlowMemo PC]', method, path, response.status, requestId, contentType);
  return { status: response.status, data, requestId, contentType, parsedJson, servedBy, bodyPrefix: rawBody.slice(0, 60) };
}

class UpstreamError extends Error {
  constructor(public upstreamStatus: number, public requestId: string, public contentType = '',
              message = 'PowerContext request failed') { super(message); }
}
function requirePcOk(resp: PcResponse, purpose: string): void {
  if (resp.status < 200 || resp.status >= 300) {
    console.warn('[FlowMemo PC] upstream error', purpose, resp.status, resp.requestId);
    throw new UpstreamError(resp.status, resp.requestId, resp.contentType);
  }
  // A 2xx that is not JSON means an intermediary answered, e.g. the GitHub
  // Codespaces access-confirmation page. Never treat that as a memory write.
  if (!resp.parsedJson) {
    console.warn('[FlowMemo PC] upstream non-json', purpose, resp.status, resp.contentType, resp.requestId);
    throw new UpstreamError(resp.status, resp.requestId, resp.contentType, 'PowerContext returned a non-JSON body');
  }
}

async function hashText(s: string): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(s)))].map(c => c.toString(16).padStart(2, '0')).join('');
}

function candidateText(item: any): string {
  const v = item?.text ?? item?.memory?.text ?? item?.entry?.text ?? item?.content?.text ?? item?.entry_version?.text;
  return typeof v === 'string' ? v : '';
}

const PREF_PREFIX = 'FlowMemo weekly report preference: ';
function isPreference(item: any): boolean {
  const text = candidateText(item);
  const kind = item?.kind ?? item?.memory?.kind ?? item?.entry?.kind;
  return text.startsWith(PREF_PREFIX) ||
    (kind === 'preference' && (/weekly report/i.test(text) || /\u5468\u62a5/.test(text)));
}

function sortByTimeNewestFirst(items: any[]): any[] {
  return [...items].sort((a, b) => {
    const time = (x: any) => Date.parse(x?.updated_at || x?.created_at || x?.memory?.updated_at || x?.memory?.created_at || '') || 0;
    return time(b) - time(a);
  });
}

async function recallPreference(session: Session): Promise<{ preference: string | null; count: number; source: string; requestId: string }> {
  // The competition contract names /v1/context/prepare as the read-back step,
  // so it is always attempted first. Its `content` is an assembled text blob
  // rather than individual entries, so it is only used when the structured
  // lookup below cannot decide the answer; a prepare failure must never make
  // recall unavailable.
  let prepareText = '';
  let prepareRequestId = '';
  try {
    const prepared = await pcCall('POST', '/v1/context/prepare', {
      scope_id: session.scopeId,
      query: 'FlowMemo weekly report preference',
      max_bytes: 4000,
    });
    if (prepared.status >= 200 && prepared.status < 300) {
      prepareText = typeof prepared.data?.content === 'string' ? prepared.data.content : '';
      prepareRequestId = prepared.requestId;
    } else {
      console.warn('[FlowMemo PC] context/prepare non-2xx', prepared.status, prepared.requestId);
    }
  } catch (e) {
    console.warn('[FlowMemo PC] context/prepare unavailable', e instanceof Error ? e.message : e);
  }

  // FTS works well with ASCII labels. If a previous Chinese-only preference
  // is not indexed by this query, fall back to an exact scope inventory.
  const search = await pcCall('POST', '/v1/memory/search', {
    scope_id: session.scopeId,
    query: 'weekly report preference',
    mode: 'fts',
    limit: 50,
  });
  requirePcOk(search, 'Memory search');
  const hits = Array.isArray(search.data?.hits) ? search.data.hits : [];
  let candidates = hits.filter(isPreference);
  let source = 'search';
  let requestId = search.requestId;
  if (!candidates.length || !!session.prefHash) {
    const inventory = await pcCall('POST', '/v1/memory/entries/list', {
      scope_id: session.scopeId,
      limit: 100,
    });
    requirePcOk(inventory, 'Memory listing');
    const entries = Array.isArray(inventory.data?.entries) ? inventory.data.entries : [];
    candidates = [...candidates, ...entries.filter(isPreference)];
    source = 'entries';
    requestId = inventory.requestId;
  }
  candidates = sortByTimeNewestFirst(candidates);
  let chosen: any = null;
  if (session.prefHash) {
    for (const candidate of candidates) {
      if (await hashText(candidateText(candidate)) === session.prefHash) {
        chosen = candidate;
        break;
      }
    }
    // Do not silently substitute an older preference when the latest one
    // cannot be retrieved from PowerContext.
  } else {
    chosen = candidates[0] || null;
  }
  if (!chosen) {
    // Only the fallback can be read as raw text, so extract from prepare's blob.
    if (prepareText.includes(PREF_PREFIX)) {
      const lines = prepareText.split('\n').map(l => l.trim()).filter(l => l.startsWith(PREF_PREFIX));
      const last = lines[lines.length - 1];
      if (last && (!session.prefHash || (await hashText(last)) === session.prefHash)) {
        return {
          preference: last.slice(PREF_PREFIX.length),
          count: lines.length,
          source: 'context/prepare',
          requestId: prepareRequestId,
        };
      }
    }
    return { preference: null, count: candidates.length, source, requestId };
  }
  const actual = candidateText(chosen);
  const preference = actual.startsWith(PREF_PREFIX) ? actual.slice(PREF_PREFIX.length) : actual;
  return { preference, count: candidates.length, source, requestId };
}

async function checkedSession(body: any): Promise<Session> {
  const session = await verifySession(body?.sessionId);
  if (!session || (body?.projectId && body.projectId !== session.projectId)) {
    throw new HttpError('Invalid or expired session', 401);
  }
  return session;
}
class HttpError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function handler(req: Request): Promise<Response> {
  const pathname = new URL(req.url).pathname;
  // Qoder Sites Gateway may prefix the original route with /app-{deploymentId}.
  const path = pathname.replace(/^\/functions\/v1\/app(?=\/|$)/, '').replace(/^\/app-[^/]+/, '').replace(/^\/app(?=\/|$)/, '') || '/';
  try {
    if (req.method === 'GET' && (path === '/' || path === '/health')) {
      if (!PC_URL || !PC_TOKEN) return json({ status: 'ok', powercontext: { configured: false, health: { status: 'not_configured' } } });
      // Diagnosing an unreachable upstream needs to say *which* endpoint the
      // Secret resolves to, but the hostname is a private dev URL. The port
      // alone is enough to catch a Codespaces port-forwarding mismatch.
      // `upstream_host_kind` + `upstream_host_sha256` (first 8 hex of the
      // hostname) let the operator confirm whether a Secret edit actually
      // reached this runtime, without ever exposing the private hostname.
      const hostDiag = await (async () => {
        try {
          const u = new URL(PC_URL);
          const h = u.hostname;
          const tunnelSuffixes = ['.trycloudflare.com', '.ngrok-free.app', '.ngrok.io', '.bore.pub', '.localhost.run', '.lo.lt'];
          const kind = h.endsWith('.app.github.dev') ? 'github_codespaces_tunnel'
            : (tunnelSuffixes.some(s => h.endsWith(s)) ? 'public_tunnel'
            : (h === 'localhost' || /^\d+\.\d+\.\d+\.\d+$/.test(h) ? 'loopback_or_ip' : 'other_hosted'));
          const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(h)))].slice(0, 4).map(c => c.toString(16).padStart(2, '0')).join('');
          const forwarded = h.match(/-(\d{2,5})\.app\.github\.dev$/);
          return { kind, digest, port: forwarded ? forwarded[1] : (u.port || (u.protocol === 'https:' ? '443' : '80')) };
        } catch { return { kind: 'invalid_url', digest: '', port: 'invalid_url' }; }
      })();
      const upstreamPort = hostDiag.port;
      try {
        const health = await pcCall('GET', '/health/ready');
        // An intermediary (GitHub tunnel) can answer with HTML and still report
        // a status. Classify by the parsed body, not the status alone.
        const isJson = health.parsedJson;
        const ready = isJson && health.status === 200 && health.data?.status === 'ready';
        return json({ status: 'ok', powercontext: {
          configured: true,
          // `reachable` only means an HTTP response came back; `upstream_json`
          // says whether that response is actually PowerContext's, because a
          // dead Codespaces tunnel also answers (with HTML or an empty 404).
          reachable: true,
          upstream_port: upstreamPort,
          // Proves which Secret value this runtime actually loaded after an
          // update, without printing the private hostname.
          upstream_host_kind: hostDiag.kind,
          upstream_host_sha256: hostDiag.digest,
          health: { status: ready ? 'ready' : (isJson ? (health.data?.status || 'unavailable') : 'non_json_response') },
          upstream_status: health.status,
          upstream_content_type: health.contentType,
          upstream_json: isJson,
          upstream_served_by: health.servedBy,
          body_prefix: isJson ? '' : health.bodyPrefix,
          request_id: health.requestId,
        } });
      } catch (e) {
        // Report the real failure class instead of a bare "unavailable", but
        // never echo the upstream base URL or any credential.
        const message = e instanceof Error ? e.message : 'PowerContext request failed';
        return json({ status: 'ok', powercontext: {
          configured: true,
          reachable: false,
          upstream_port: upstreamPort,
          upstream_host_kind: hostDiag.kind,
          upstream_host_sha256: hostDiag.digest,
          health: { status: 'unavailable' },
          error: message.slice(0, 120),
        } });
      }
    }
    if (req.method !== 'POST') return json({ ok: false, error: 'not_found' }, 404);
    // No anonymous debug endpoint or arbitrary scope_id input is accepted.
    const body = await req.json().catch(() => null);
    if (!body || typeof body !== 'object') return json({ ok: false, error: 'invalid_json' }, 400);

    if (path === '/session/ensure') {
      if (!PC_URL || !PC_TOKEN || !SESSION_SECRET) return json({ ok: false, error: 'not_configured' }, 503);
      const projectId = safeString(body.projectId, 96);
      if (!/^[a-zA-Z0-9_-]{1,96}$/.test(projectId)) return json({ ok: false, error: 'invalid_projectId' }, 400);
      if (body.sessionId) {
        const existing = await checkedSession(body);
        const renewed = await makeSession({ ...existing, exp: Date.now() + SESSION_LIFETIME_MS });
        return json({ ok: true, verified: true, sessionId: renewed, scopeId: existing.scopeId });
      }
      const visitorId = crypto.randomUUID();
      const created = await pcCall('POST', '/v1/scopes', {
        title: `FlowMemo ${visitorId.slice(0, 8)}`,
        summary: 'Private weekly report preference memory for one anonymous browser session',
        idempotency_key: crypto.randomUUID(),
      });
      requirePcOk(created, 'Scope creation');
      const scopeId = created.data?.scope_id;
      if (typeof scopeId !== 'string' || !/^scp_[A-Za-z0-9_-]{8,200}$/.test(scopeId)) throw new Error('PowerContext scope response is invalid');
      const sessionId = await makeSession({ visitorId, projectId, scopeId, exp: Date.now() + SESSION_LIFETIME_MS });
      return json({ ok: true, verified: true, sessionId, scopeId, request_id: created.requestId });
    }

    if (path === '/memory/preference/save') {
      const session = await checkedSession(body);
      const preference = safeString(body.preference, 1000);
      if (!preference) return json({ ok: false, error: 'missing_preference' }, 400);
      const text = PREF_PREFIX + preference;
      const result = await pcCall('POST', '/v1/memory/remember', {
        scope_id: session.scopeId,
        kind: 'preference',
        text,
      });
      requirePcOk(result, 'Memory save');
      const confirmed = (Array.isArray(result.data?.records) && result.data.records.length > 0) ||
        result.data?.saved === true || result.data?.changed === true;
      if (!confirmed) return json({ ok: false, error: 'memory_not_confirmed', request_id: result.requestId }, 502);
      const sessionId = await makeSession({ ...session, prefHash: await hashText(text), exp: Date.now() + SESSION_LIFETIME_MS });
      return json({ ok: true, saved: true, verified: true, sessionId, request_id: result.requestId });
    }
    if (path === '/memory/preference/recall') {
      const session = await checkedSession(body);
      const r = await recallPreference(session);
      return json({ ok: true, verified: true, preference: r.preference,
        count: r.count, source: r.source, request_id: r.requestId });
    }
    return json({ ok: false, error: 'not_found' }, 404);
  } catch (e) {
    const status = e instanceof HttpError ? e.status : 502;
    const message = e instanceof Error ? e.message : 'Server error';
    console.warn('[FlowMemo]', path, status, message);
    return json({ ok: false, error: status === 502 ? 'powercontext_failed' : message,
      ...(e instanceof UpstreamError ? {
        upstream_status: e.upstreamStatus,
        request_id: e.requestId,
        upstream_content_type: e.contentType,
      } : {}),
    }, status);
  }
}
