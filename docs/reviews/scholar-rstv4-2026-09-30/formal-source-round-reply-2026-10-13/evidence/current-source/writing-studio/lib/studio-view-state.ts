import type { LocatedSource } from './shared-discussion';

export type SourceLocation =
  | { kind: 'shared'; reference: Pick<LocatedSource, 'message_id' | 'index' | 'scope'> }
  | { kind: 'legacy'; messageId: string };

export function restoredSourceLocation(value: unknown, manuscriptId: string): SourceLocation | null {
  if (!value || typeof value !== 'object') return null;
  const location = value as Record<string, unknown>;
  if (location.kind === 'legacy') {
    return typeof location.messageId === 'string' && location.messageId.length > 0 && location.messageId.length <= 200
      ? { kind: 'legacy', messageId: location.messageId } : null;
  }
  if (location.kind !== 'shared' || !location.reference || typeof location.reference !== 'object') return null;
  const reference = location.reference as Record<string, unknown>;
  if (typeof reference.message_id !== 'string' || !reference.message_id || reference.message_id.length > 200
    || !Number.isInteger(reference.index) || (reference.index as number) < 0 || (reference.index as number) > 8
    || typeof reference.scope !== 'string' || reference.scope.length > 2200) return null;
  try {
    const scope = JSON.parse(reference.scope);
    if (!Array.isArray(scope) || scope.length !== 2 || scope[0] !== 'STUDIO' || scope[1] !== manuscriptId) return null;
  } catch { return null; }
  return { kind: 'shared', reference: { message_id: reference.message_id, index: reference.index as number, scope: reference.scope } };
}

export function restoredReadingVersion(value: unknown, selection?: { type: string; id?: string; quote?: { generated_version_id?: string } }): string | null {
  if (typeof value === 'string' && value.length > 0 && value.length <= 200) return value;
  if (!selection?.type.startsWith('generated_')) return null;
  const version = selection.quote?.generated_version_id;
  if (version && selection.id?.startsWith(`${version}:`)) return version;
  const anchorVersion = selection.id?.split(':')[0];
  return anchorVersion?.startsWith('manuscript_version_') ? anchorVersion : null;
}

// Ordinary Track navigation restores each manuscript's own saved view. Explicit deep links
// are consumed at initial load; they must not be carried into a different manuscript.
export function manuscriptNavigationUrl(href: string, manuscriptId?: string): URL {
  const url = new URL(href);
  for (const name of ['view', 'left', 'right', 'chat', 'folds', 'round', 'object', 'reading_version',
    'discussion', 'discussion_scope', 'discussion_source', 'studio_discussion', 'discussion_return']) url.searchParams.delete(name);
  if (manuscriptId) url.searchParams.set('manuscript', manuscriptId);
  else url.searchParams.delete('manuscript');
  return url;
}
