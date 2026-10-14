// Both product views use the same fixed-source draft, retry and conversation controller.
import '../../RSTV4/src/rstv4/catalog_research_chat.js';

import type { AuthorQuote, ChatMessage, GeneratedVersion, StudioDocument } from './studio-types';

export interface DiscussionTarget {
  module: 'CATALOG' | 'FIELDKG' | 'TRACK' | 'STUDIO';
  object_kind: string;
  object_id: string;
  manuscript_id?: string;
  document_revision?: number;
  generated_version_id?: string;
  [key: string]: unknown;
}

export interface FixedContext {
  target: DiscussionTarget;
  scope_key: string;
  context_sha256: string;
  label: string;
  object_text: string;
  versions: Array<Record<string, unknown>>;
  record: { snapshot?: { revision: number; document: StudioDocument }; generated?: GeneratedVersion; [key: string]: unknown };
}

export interface DiscussionMessage {
  message_id: string;
  request_id: string;
  actor: 'AUTHOR' | 'AGENT';
  content: string;
  context: FixedContext;
  quote: AuthorQuote & { annotation?: string };
  additional_sources: Array<{ context: FixedContext; quote: AuthorQuote }>;
  scope_key: string;
}

export interface LocatedSource {
  source: { context: FixedContext; quote: AuthorQuote; current_source_state: string };
  message_id: string;
  index: number;
  scope: string;
}

export interface DiscussionReceipt {
  request_id: string;
  job?: {
    status: string;
    model_contract?: { actual_model?: string; prompt_version?: string };
    error?: { detail?: string };
    input?: { conversation?: DiscussionMessage[] };
  };
  execution_observation?: string;
  studio_messages?: ChatMessage[];
  [key: string]: unknown;
}

export interface DiscussionState {
  bound: { context: FixedContext; history_message_id?: string; history_scope?: string; history_request_id?: string; current_source_state?: string } | null;
  proposed: { bound: { context: FixedContext }; quote: AuthorQuote | null } | null;
  quote: AuthorQuote | null;
  content: string;
  annotation: string;
  pinned: boolean;
  allowCrossScope: boolean;
  extra: Array<{ bound: { context: FixedContext }; quote: AuthorQuote | null }>;
  parent: { message_id: string; label: string; conversation: DiscussionMessage[] } | null;
  pending: { kind: string; payload: { request_id: string }; scope: string } | null;
  receipt: DiscussionReceipt | null;
  inspectedReceipt: DiscussionReceipt | null;
  busy: boolean;
  status: string;
  annotations: Array<{ annotation_id: string; comment: string; context: FixedContext; quote: AuthorQuote }>;
  messages: DiscussionMessage[];
  nextAnnotationsBefore: number | null;
}

export interface DiscussionController {
  snapshot(): DiscussionState;
  choose(target: DiscussionTarget, quote?: AuthorQuote | null): Promise<void>;
  compare(choice: 'keep' | 'use' | 'add'): void;
  edit(name: string, value: string | boolean): void;
  selectQuote(quote: AuthorQuote | null): void;
  send(kind?: 'DISCUSS' | 'ANNOTATE'): Promise<void>;
  reconcile(retry?: boolean): Promise<void>;
  openHistory(messageId: string, index?: number, continueDiscussion?: boolean, owner?: string): Promise<void>;
  locateSource(messageId: string, index?: number, owner?: string): Promise<void>;
  startNew(): void;
  loadHistory(older?: boolean): Promise<void>;
  viewHistory(target: DiscussionTarget, currentOnly?: boolean): void;
  inspectCall(messageId: string): Promise<void>;
  inspectOrigin(): Promise<void>;
  removeSource(index: number): void;
  leave(): void;
}

interface FactoryOptions {
  request(path: string, body?: unknown): Promise<unknown>;
  storage: Pick<Storage, 'getItem' | 'setItem'>;
  namespace: string;
  uuid(): string;
  onChange(state: DiscussionState): void;
  onLocate?(source: LocatedSource): Promise<void>;
}

export function createSharedDiscussion(options: FactoryOptions): DiscussionController {
  const shared = globalThis as unknown as { RSTV4ResearchChat: { createController(options: FactoryOptions): DiscussionController } };
  return shared.RSTV4ResearchChat.createController(options);
}

export function discussionDestination(context: FixedContext, apps: { catalogBase: string; studioBase: string }, reference: { message_id: string; index: number; scope: string; return_url?: string }): string {
  const shared = globalThis as unknown as { RSTV4ResearchChat: { sourceDestination(context: FixedContext, apps: unknown, reference: unknown): string } };
  return shared.RSTV4ResearchChat.sourceDestination(context, apps, reference);
}

export function discussionReference(search: string): { message_id: string; index: number; scope: string } | null {
  const shared = globalThis as unknown as { RSTV4ResearchChat: { sourceReference(search: string): { message_id: string; index: number; scope: string } | null } };
  return shared.RSTV4ResearchChat.sourceReference(search);
}

export function discussionReturn(search: string, apps: { catalogBase: string; studioBase: string }): string | null {
  const shared = globalThis as unknown as { RSTV4ResearchChat: { sourceReturn(search: string, apps: unknown): string | null } };
  return shared.RSTV4ResearchChat.sourceReturn(search, apps);
}

export function discussionWithoutReference(href: string): string {
  const shared = globalThis as unknown as { RSTV4ResearchChat: { sourceWithoutReference(href: string): string } };
  return shared.RSTV4ResearchChat.sourceWithoutReference(href);
}

export function exactSelection(quote?: AuthorQuote): AuthorQuote | null {
  if (!quote?.text) return null;
  return { text: quote.text, start: quote.start, end: quote.end, offset_unit: quote.offset_unit };
}

export function studioTarget(manuscriptId: string, selected: { type: string; id?: string | null; anchorRevision?: number; quote?: AuthorQuote }, currentRevision: number): DiscussionTarget {
  return {
    module: 'STUDIO', manuscript_id: manuscriptId, object_kind: selected.type,
    object_id: selected.id || manuscriptId, document_revision: selected.anchorRevision ?? currentRevision,
    ...(selected.quote?.generated_version_id ? { generated_version_id: selected.quote.generated_version_id } : {}),
  };
}

export function readableVersions(context: FixedContext): string {
  if (context.target.module === 'STUDIO') {
    const version = context.versions[0];
    return [typeof version?.generated_version === 'number' ? `成文 v${version.generated_version}` : '',
      typeof version?.author_revision === 'number' ? `结构 r${version.author_revision}` : '结构版本未知'].filter(Boolean).join(' · ');
  }
  return context.target.module;
}
