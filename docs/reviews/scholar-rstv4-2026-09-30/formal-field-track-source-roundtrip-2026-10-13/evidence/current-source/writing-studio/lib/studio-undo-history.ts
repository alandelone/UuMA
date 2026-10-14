import { sameDocument } from './offline-outbox';
import type { StudioDocument } from './studio-types';

type RecordValue = Record<string, unknown>;
const record = (value: unknown): value is RecordValue => Boolean(value && typeof value === 'object' && !Array.isArray(value));
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === 'string');
const textFields = (value: RecordValue, fields: string[]) => fields.every((field) => typeof value[field] === 'string');

function historyDocument(value: unknown, manuscriptId: string): value is StudioDocument {
  if (!record(value) || value.schema_version !== 1 || value.manuscript_id !== manuscriptId
    || !textFields(value, ['title', 'abstract', 'venue']) || !Array.isArray(value.sections)) return false;
  return value.sections.every((section: unknown) => record(section) && textFields(section, ['id', 'title', 'role'])
    && Array.isArray(section.paragraphs) && section.paragraphs.every((paragraph: unknown) => record(paragraph)
      && textFields(paragraph, ['id', 'purpose', 'paradigm']) && strings(paragraph.asset_ids)
      && Array.isArray(paragraph.intents) && paragraph.intents.every((intent: unknown) => record(intent)
        && textFields(intent, ['id', 'label']) && Array.isArray(intent.thoughts)
        && intent.thoughts.every((thought: unknown) => record(thought) && textFields(thought, ['id', 'text'])
          && ['PENDING', 'NONE', 'SELECTED'].includes(String(thought.citation_mode))
          && Array.isArray(thought.citations) && thought.citations.every((citation: unknown) => record(citation)
            && typeof citation.evidence_id === 'string' && typeof citation.selected === 'boolean')))))
    && (value.argument_relations === undefined || (Array.isArray(value.argument_relations)
      && value.argument_relations.every((edge: unknown) => record(edge) && textFields(edge, ['id', 'source_id', 'target_id', 'relation', 'condition']))));
}

export function restoreUndoHistory(raw: string, manuscriptId: string, revision: number, document: StudioDocument): { undo: StudioDocument[]; redo: StudioDocument[] } {
  const saved: unknown = JSON.parse(raw);
  if (!record(saved) || saved.version !== 1 || saved.revision !== revision
    || !historyDocument(saved.current, manuscriptId) || !sameDocument(saved.current, document)
    || !Array.isArray(saved.undo) || !Array.isArray(saved.redo) || saved.undo.length > 100 || saved.redo.length > 100
    || ![...saved.undo, ...saved.redo].every((item: unknown) => historyDocument(item, manuscriptId)))
    throw new Error('原撤销记录无法与当前稿件核对，已保留原记录；本页从当前稿件开始记录新操作。');
  return { undo: structuredClone(saved.undo) as StudioDocument[], redo: structuredClone(saved.redo) as StudioDocument[] };
}

export function serializeUndoHistory(document: StudioDocument, revision: number, undo: StudioDocument[], redo: StudioDocument[]): string {
  return JSON.stringify({ version: 1, revision, current: document, undo: undo.slice(-100), redo: redo.slice(-100) });
}
