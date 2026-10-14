/** Preserve the exact overview context only for the configured Catalog origin. */
export function catalogReturnUrl(search: string, catalogBase: string): string {
  const base = new URL(catalogBase);
  const params = new URLSearchParams(search);
  const fallback = new URL('/', base);
  const track = params.get('track');
  if (track) fallback.searchParams.set('track', track);
  const candidate = params.get('return');
  if (!candidate) return fallback.href;
  try {
    const url = new URL(candidate);
    if (
      url.origin !== base.origin || url.username || url.password ||
      url.pathname !== '/' || url.hash ||
      (url.searchParams.has('view') && url.searchParams.get('view') !== 'overview')
    ) return fallback.href;
    const unwanted = [...url.searchParams.keys()].filter(name => !['track', 'overview_state', 'view'].includes(name));
    for (const name of unwanted) url.searchParams.delete(name);
    return url.href;
  } catch {
    return fallback.href;
  }
}
