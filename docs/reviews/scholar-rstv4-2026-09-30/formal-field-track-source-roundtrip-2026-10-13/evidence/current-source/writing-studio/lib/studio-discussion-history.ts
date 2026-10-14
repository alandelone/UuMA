import type { ChatContext, ChatMessage } from './studio-types';

export interface HistoryObject {
  type: string;
  id?: string | null;
  anchorRevision?: number;
  quote?: { generated_version_id?: string };
}

export interface HistoryFilter {
  anchor_type: string;
  anchor_revision: number;
  generated_version_id?: string;
}

export function historyFilter(selected: HistoryObject, revision: number): HistoryFilter {
  return { anchor_type: selected.type, anchor_revision: selected.anchorRevision ?? revision,
    ...(selected.quote?.generated_version_id ? { generated_version_id: selected.quote.generated_version_id } : {}) };
}

export function matchesHistory(message: ChatMessage, selected: HistoryObject, revision: number): boolean {
  const filter = historyFilter(selected, revision);
  const source = message.quoted.source as { generated_version_id?: string } | undefined;
  const version = source?.generated_version_id || message.quoted.generated_version_id;
  return message.anchor_type === filter.anchor_type && (message.anchor_id || null) === (selected.id || null) &&
    message.anchor_revision === filter.anchor_revision &&
    (!filter.generated_version_id || version === filter.generated_version_id);
}

export function legacySelection(context: ChatContext, manuscriptId: string): HistoryObject & { label: string; authorRevisionKnown: boolean; quote: ChatContext['quote'] } {
  const source = context.quote.source;
  if (source.manuscript_id !== manuscriptId) throw new Error('原讨论不属于当前稿件。');
  if (!Number.isInteger(source.anchor_revision) || source.anchor_revision < 0) throw new Error('原修订记录不可用。');
  if (source.anchor_type.startsWith('generated_') && (!source.generated_version_id || context.generated?.generated_version_id !== source.generated_version_id || context.block?.anchor_id !== source.anchor_id)) throw new Error('原成文对象记录不可用。');
  return { type: source.anchor_type, id: source.anchor_id, label: source.label,
    anchorRevision: source.anchor_revision, authorRevisionKnown: source.author_revision_known !== false,
    quote: { ...context.quote, ...(source.generated_version_id ? { generated_version_id: source.generated_version_id } : {}) } };
}
