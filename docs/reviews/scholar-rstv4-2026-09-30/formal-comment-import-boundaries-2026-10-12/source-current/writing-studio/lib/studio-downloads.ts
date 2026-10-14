/** Fixed Studio files are delivered through the same origin as the workspace. */
export function studioFileUrl(path: string): string {
  return `/api/studio-files${path}`;
}

function fixedFilePath(segments: string[]): string | null {
  const id = /^[a-zA-Z0-9_-]{1,128}$/;
  if (segments.length === 2 && segments[0] === 'artifacts' && id.test(segments[1])) {
    return `/artifacts/${segments[1]}`;
  }
  if (segments.length === 7 && segments[0] === 'manuscripts' && id.test(segments[1]) &&
      segments[2] === 'generated-versions' && id.test(segments[3]) &&
      segments[4] === 'sources' && id.test(segments[5]) && segments[6] === 'pdf') {
    return `/${segments.join('/')}`;
  }
  if (segments[0] !== 'manuscripts' || !id.test(segments[1] || '') ||
      segments[2] !== 'packages' || !id.test(segments[3] || '')) return null;
  if (segments.length === 5 && segments[4] === 'download') return `/${segments.join('/')}`;
  const filename = segments[5] || '';
  if (segments.length === 6 && segments[4] === 'files' &&
      /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,199}$/.test(filename)) return `/${segments.join('/')}`;
  return null;
}

export async function serveStudioFile(
  request: Request,
  segments: string[],
  configuredBase: string,
  fetchFile: typeof fetch = fetch,
): Promise<Response> {
  const error = (status: number, detail: string) => Response.json({ detail }, {
    status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' },
  });
  if (request.method !== 'GET') return error(405, '文件入口只接受读取请求。');
  const origin = request.headers.get('Origin');
  if (origin && origin !== new URL(request.url).origin) return error(403, '请从本写作工作区下载文件。');
  const path = fixedFilePath(segments);
  if (!path || new URL(request.url).search) return error(404, '固定文件入口不存在。');
  let base: URL;
  try { base = new URL(configuredBase); }
  catch { return error(503, '固定文件服务地址无效。'); }
  if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(base.hostname) ||
      base.username || base.password || base.search || base.hash ||
      base.pathname.replace(/\/$/, '') !== '/api') return error(503, '固定文件服务地址无效。');
  try {
    const upstream = await fetchFile(`${base.href.replace(/\/$/, '')}${path}`, {
      method: 'GET', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(15_000),
    });
    if (upstream.status !== 200 && upstream.status < 400) {
      await upstream.body?.cancel();
      return error(502, '固定文件服务未返回文件，请稍后重试。');
    }
    const headers = new Headers({ 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    for (const name of ['Content-Type', 'Content-Length', 'Content-Disposition']) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch {
    return error(502, '固定文件服务连接失败，请检查连接后重试。原文件仍保留。');
  }
}
