'use client';

import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  ArrowLeft,
  BookCopy,
  Bookmark,
  Check,
  ChevronDown,
  CircleAlert,
  FileDown,
  GripVertical,
  LibraryBig,
  LoaderCircle,
  MessageSquareText,
  PanelLeft,
  PanelRight,
  Paperclip,
  Pencil,
  Plus,
  Redo2,
  Search,
  Send,
  Sparkles,
  Trash2,
  Undo2,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Textarea } from '@/components/ui/textarea';
import { StudioSuggestionReview } from '@/components/studio-suggestion-review';
import { StudioReviewRounds } from '@/components/studio-review-rounds';
import { StudioChangeHistory } from '@/components/studio-change-history';
import { StudioSourceContext } from '@/components/studio-source-context';
import { StudioPackageDownloads } from '@/components/studio-package-downloads';
import { StudioResponseReview } from '@/components/studio-response-review';
import { StudioTemplateAdoption, type TemplateCandidate } from '@/components/studio-template-adoption';
import { StudioArgumentRelations } from '@/components/studio-argument-relations';
import { StudioOriginalPlacement } from '@/components/studio-original-placement';
import { StudioIntentCorrespondence } from '@/components/studio-intent-correspondence';
import { correspondenceOwners, displayedThoughts, intentLocations, thoughtsByIntent } from '@/lib/studio-correspondence';
import { BlockControls, BlockMove, DropZone, EditorControls, Ungroup, blockKeyboardCoordinates, useEditorControls, type EditorUi } from '@/components/studio-block-controls';
import { ApiError, API_BASE, sharedDiscussionRequest, studioApi } from '@/lib/studio-api';
import { studioFileUrl } from '@/lib/studio-downloads';
import { createSharedDiscussion, discussionDestination, discussionReference, discussionReturn, discussionWithoutReference, exactSelection, readableVersions, studioTarget, type DiscussionController, type DiscussionState, type LocatedSource } from '@/lib/shared-discussion';
import { historyFilter, legacySelection, matchesHistory } from '@/lib/studio-discussion-history';
import { outbox, sameDocument, type PendingSave } from '@/lib/offline-outbox';
import { suggestionResultMode } from '@/lib/suggestion-result';
import { restoreUndoHistory, serializeUndoHistory } from '@/lib/studio-undo-history';
import { addSubsection, ancestors, canDropTemplate, canMove, deleteSectionTree, moveBlocks, reconcileStructure, sectionBreadcrumb, sectionDepth, sectionEnd, type BlockTarget } from '@/lib/studio-blocks';
import type {
  AuthorQuote,
  ChatContext,
  ChatMessage,
  CitationCandidate,
  IntentBlock,
  GeneratedBlock,
  GeneratedReference,
  GeneratedVersion,
  ParagraphBlock,
  ReviewComment,
  ReviewRound,
  SampleBlock,
  SectionBlock,
  SourceEvidence,
  StudioDocument,
  StudioJob,
  StudioSuggestion,
  SuggestionDecisionRequest,
  Thought,
  TemplateRequest,
  WorkflowStage,
  Workspace,
} from '@/lib/studio-types';

const STAGE_LABELS: Array<[WorkflowStage, string]> = [
  ['PLANNING', '1 Planning'],
  ['DRAFTING', '2 Drafting'],
  ['WHOLE_PAPER_REVIEW', '3 全文检查'],
  ['FINALIZATION_SUBMISSION', '4 定稿／投稿'],
  ['REVISION', '5 Revision'],
  ['PUBLICATION', '6 Publication'],
];

type SaveState = 'saved' | 'pending' | 'saving' | 'failed' | 'conflict' | 'recovery';
type ViewMode = 'structure' | 'reading' | 'revision';

interface Selection {
  type: 'paper' | 'section' | 'paragraph_group' | 'paragraph' | 'intent' | 'thought' | 'generated_title' | 'generated_heading' | 'generated_paragraph';
  id?: string;
  label: string;
  role?: string;
  intent?: string;
  anchorRevision?: number;
  authorRevisionKnown?: boolean;
  quote?: AuthorQuote;
}

interface WebModelContext {
  registerTool: (
    tool: {
      name: string;
      title: string;
      description: string;
      inputSchema: Record<string, unknown>;
      annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
      execute: (input: unknown) => unknown;
    },
    options?: { signal?: AbortSignal },
  ) => void | Promise<void>;
}

const sameLayerClosestCenter: CollisionDetection = (arguments_) => {
  return closestCenter({
    ...arguments_,
    droppableContainers: arguments_.droppableContainers.filter(
      (container) => {
        const rect = arguments_.droppableRects.get(container.id);
        return Boolean(container.data.current?.dropTarget && rect?.width && rect.height);
      },
    ),
  });
};

function uid(prefix: string) {
  return `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`;
}

function TemplateDragHandle({ sample, disabled }: { sample: SampleBlock; disabled: boolean }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `template-${sample.skeleton_id || sample.unit_id}`,
    disabled: disabled || !sample.skeleton_id,
    data: { type: 'template', skeletonId: sample.skeleton_id },
  });
  return <button type="button" ref={setNodeRef} {...attributes} {...listeners}
    disabled={disabled || !sample.skeleton_id} aria-label={`拖入完整模板 ${sample.title}`}
    className="inline-flex items-center gap-2 rounded border px-3 py-2 text-sm cursor-grab touch-none" style={{ transform: CSS.Translate.toString(transform), opacity: isDragging ? 0.7 : 1 }}>
    <GripVertical /> 拖入模板
  </button>;
}

function cloneDocument(document: StudioDocument): StudioDocument {
  return structuredClone(document);
}

function locateThought(document: StudioDocument, thoughtId: string) {
  for (let sectionIndex = 0; sectionIndex < document.sections.length; sectionIndex += 1) {
    const section = document.sections[sectionIndex];
    for (let paragraphIndex = 0; paragraphIndex < section.paragraphs.length; paragraphIndex += 1) {
      const paragraph = section.paragraphs[paragraphIndex];
      for (let intentIndex = 0; intentIndex < paragraph.intents.length; intentIndex += 1) {
        const intent = paragraph.intents[intentIndex];
        const thoughtIndex = intent.thoughts.findIndex((item) => item.id === thoughtId);
        if (thoughtIndex >= 0) {
          return { sectionIndex, paragraphIndex, intentIndex, thoughtIndex, intent };
        }
      }
    }
  }
  return null;
}

function latestGeneratedContent(workspace: Workspace) {
  const id = workspace.active_generated_version_id;
  if (!id) return '';
  return (
    workspace.manuscript.versions.find(
      (version) => version.manuscript_version_id === id,
    )?.content ?? ''
  );
}

function commentLabel(comment: ReviewComment) {
  return comment.display_label || comment.comment_id;
}

function messageAnchorLabel(message: ChatMessage) {
  const source = message.quoted.source as Record<string, unknown> | undefined;
  if (source?.author_revision_known === false) return '原对象 · 历史成文（结构版本未知）';
  return typeof source?.generated_version === 'number'
    ? `原对象 · 成文 v${source.generated_version} / 结构 r${message.anchor_revision}`
    : `原对象 · 结构 r${message.anchor_revision}`;
}

function documentSelection(document: StudioDocument, id?: string): Selection | undefined {
  if (!id) return { type: 'paper', label: document.title };
  for (const section of document.sections) {
    if (section.id === id) return { type: 'section', id, label: section.title, role: section.role };
    const group = section.paragraph_groups?.find((item) => item.id === id);
    if (group) return { type: 'paragraph_group', id, label: `${section.title} / ${group.label || '未定段落组'}`, role: section.role };
    for (const paragraph of section.paragraphs) {
      if (paragraph.id === id) return { type: 'paragraph', id, label: paragraph.purpose || 'Paragraph', role: section.role };
      for (const intent of paragraph.intents) {
        if (intent.id === id) return { type: 'intent', id, label: intent.label || '未定 Intent', role: section.role, intent: intent.label };
        const thought = intent.thoughts.find((item) => item.id === id);
        if (thought) return { type: 'thought', id, label: thought.text.slice(0, 40) || '空思想', role: section.role, intent: intent.label };
      }
    }
  }
  return undefined;
}

function SortableThought({
  thought,
  onText,
  onEnter,
  onDelete,
  onCitation,
  onDropEvidence,
  onSelect,
}: {
  thought: Thought;
  onText: (value: string) => void;
  onEnter: () => void;
  onDelete: () => void;
  onCitation: (mode: Thought['citation_mode'], citations: CitationCandidate[]) => void;
  onDropEvidence: (source: SourceEvidence) => void;
  onSelect: (quote?: AuthorQuote) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: thought.id, data: { type: 'thought' } });
  const selectedCount = thought.citations.filter((item) => item.selected).length;

  return (
    <>
    <DropZone target={{ kind: 'thought', id: thought.id, placement: 'before' }} />
    <div
      ref={setNodeRef}
      data-block-id={thought.id}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`thought-row ${isDragging ? 'thought-row--dragging' : ''}`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const encoded = event.dataTransfer.getData('application/x-rstv4-evidence');
        if (encoded) onDropEvidence(JSON.parse(encoded) as SourceEvidence);
      }}
    >
      <BlockControls id={thought.id} kind="thought" label={thought.text.slice(0, 40) || '空思想'}><button
        type="button"
        className="drag-handle"
        aria-label="拖动思想块"
        onFocus={() => onSelect()}
        {...attributes}
        {...listeners}
        onKeyDown={(event) => {
          if (event.key === 'Delete') {
            event.preventDefault();
            onDelete();
          } else listeners?.onKeyDown?.(event);
        }}
      >
        <GripVertical />
      </button></BlockControls>
      <Textarea
        inert={isDragging}
        value={thought.text}
        rows={1}
        className="min-h-9 resize-none border-0 bg-transparent px-1 py-1.5 text-[15px] leading-6 shadow-none focus-visible:ring-0"
        placeholder="写下你要表达的原子思想…"
        aria-label="作者思想"
        onFocus={() => onSelect()}
        onSelect={(event) => {
          const input = event.currentTarget;
          if (input.selectionEnd > input.selectionStart) onSelect({
            text: input.value.slice(input.selectionStart, input.selectionEnd),
            start: input.selectionStart, end: input.selectionEnd, offset_unit: 'utf16',
          });
        }}
        onChange={(event) => onText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            onEnter();
          }
        }}
      />
      <Popover>
        <PopoverTrigger
          inert={isDragging}
          aria-label="选择引用"
          className={`citation-bookmark ${
            thought.citation_mode === 'PENDING' ? 'citation-bookmark--pending' : ''
          }`}
        >
          <Bookmark />
          <span>{selectedCount || (thought.citation_mode === 'NONE' ? '0' : '·')}</span>
        </PopoverTrigger>
        <PopoverContent align="end" side="bottom" className="w-80">
          <PopoverHeader>
            <PopoverTitle>引用决定</PopoverTitle>
          </PopoverHeader>
          <div className="flex items-center gap-2 rounded-lg px-2 py-2 hover:bg-muted">
            <Checkbox
              aria-label="这条思想不需要外部引用"
              checked={thought.citation_mode === 'NONE'}
              onCheckedChange={(checked) => {
                if (checked) onCitation('NONE', thought.citations.map((item) => ({ ...item, selected: false })));
              }}
            />
            <span>这条思想明确不需要外部引用</span>
          </div>
          <div className="max-h-64 space-y-1 overflow-auto">
            {thought.citations.length === 0 ? (
              <p className="px-2 py-3 text-sm text-muted-foreground">
                从右侧资料区拖入证据后，再决定是否采用。
              </p>
            ) : (
              thought.citations.map((citation) => (
                <div
                  key={citation.evidence_id}
                  className="flex items-start gap-2 rounded-lg px-2 py-2 hover:bg-muted"
                >
                  <Checkbox
                    aria-label={`选择引用 ${citation.title || citation.evidence_id}`}
                    checked={citation.selected}
                    onCheckedChange={(checked) => {
                      const citations = thought.citations.map((item) =>
                        item.evidence_id === citation.evidence_id
                          ? { ...item, selected: Boolean(checked) }
                          : item,
                      );
                      onCitation(
                        citations.some((item) => item.selected) ? 'SELECTED' : 'PENDING',
                        citations,
                      );
                    }}
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium">
                      {citation.title || citation.evidence_id}
                    </span>
                    <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">
                      {citation.statement}
                    </span>
                  </span>
                </div>
              ))
            )}
          </div>
        </PopoverContent>
      </Popover>
      <details className="block-menu" inert={isDragging}>
        <summary aria-label="思想块菜单">•••</summary>
        <BlockMove id={thought.id} />
        <button type="button" onClick={onDelete}>
          <Trash2 /> 删除思想块
        </button>
      </details>
    </div>
    <DropZone target={{ kind: 'thought', id: thought.id, placement: 'after' }} />
    </>
  );
}

function draftPreview(document: StudioDocument): string {
  const lines = [document.title, document.abstract, document.venue ? `投稿目标：${document.venue}` : ''];
  for (const section of document.sections) {
    lines.push(`\n${section.title}（${section.role}）`);
    for (const paragraph of section.paragraphs) {
      lines.push(`段落目的：${paragraph.purpose}`, `结构标签：${paragraph.paradigm}`);
      for (const intent of paragraph.intents) {
        lines.push(`意图：${intent.label}`);
        for (const thought of intent.thoughts) {
          const citation = thought.citation_mode === 'NONE' ? '无需引用'
            : thought.citation_mode === 'PENDING' ? '引用待决定'
              : `已选 ${thought.citations.filter((item) => item.selected).length} 条引用`;
          lines.push(thought.text, `引用决定：${citation}`);
          lines.push(...thought.citations.filter((item) => item.selected).map((item) => item.title || item.statement || '已选来源'));
        }
      }
      for (const formula of paragraph.formulas || []) lines.push(`公式：${formula.latex}`, formula.caption);
      if (paragraph.asset_ids.length) lines.push(`图表／附件：${paragraph.asset_ids.length} 项`);
    }
  }
  return lines.filter(Boolean).join('\n');
}

export function StudioWorkspace({
  initialWorkspace,
  onExit,
  backLabel = 'Track',
}: {
  initialWorkspace: Workspace;
  onExit: () => void;
  backLabel?: string;
}) {
  const [workspace, setWorkspace] = useState(initialWorkspace);
  const [document, setDocument] = useState(() => cloneDocument(initialWorkspace.document));
  const [revision, setRevision] = useState(initialWorkspace.document_revision);
  const [saveState, setSaveState] = useState<SaveState>('saved');
  const [statusMessage, setStatusMessage] = useState('');
  const [selection, setSelection] = useState<Selection>({
    type: 'paper',
    label: initialWorkspace.manuscript.title,
  });
  const stage = workspace.workflow_stage;
  const initialMode: ViewMode =
    stage === 'REVISION'
      ? 'revision'
      : stage === 'WHOLE_PAPER_REVIEW' || stage === 'FINALIZATION_SUBMISSION' || stage === 'PUBLICATION'
        ? 'reading'
        : 'structure';
  const [viewMode, setViewMode] = useState<ViewMode>(initialMode);
  const [showLeft, setShowLeft] = useState(initialMode === 'structure');
  const [showRight, setShowRight] = useState(initialMode === 'structure');
  const [samples, setSamples] = useState<SampleBlock[]>([]);
  const [sampleIndex, setSampleIndex] = useState(0);
  const [sources, setSources] = useState<SourceEvidence[]>([]);
  const [sourceQuery, setSourceQuery] = useState('');
  const [pinnedReference, setPinnedReference] = useState<GeneratedReference | null>(null);
  const [pinnedReferenceVersion, setPinnedReferenceVersion] = useState<{ manuscriptId: string; id: string; version: number } | null>(null);
  const sourcePreviewRequestRef = useRef(0);
  const [generatedVersion, setGeneratedVersion] = useState<GeneratedVersion | null>(null);
  const [historicalContext, setHistoricalContext] = useState<ChatContext | null>(null);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [chatDraft, setChatDraft] = useState('');
  const [draftContext, setDraftContext] = useState<Selection | null>(null);
  const draftContextRef = useRef<Selection | null>(null);
  const draftBindingBusyRef = useRef(false);
  const [draftBindingBusy, setDraftBindingBusy] = useState(false);
  const chatDraftRef = useRef('');
  const [annotation, setAnnotation] = useState('');
  const annotationRef = useRef('');
  const [chatDraftReady, setChatDraftReady] = useState(false);
  const [chatOpen, setChatOpen] = useState(true);
  const [chatFilter, setChatFilter] = useState<'paper' | 'selection'>('paper');
  const [chatHasMore, setChatHasMore] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [sharedDiscussion, setSharedDiscussion] = useState<DiscussionState | null>(null);
  const [sharedDiscussionReady, setSharedDiscussionReady] = useState(false);
  const discussionRef = useRef<DiscussionController | null>(null);
  const locateDiscussionRef = useRef<(source: LocatedSource) => Promise<void>>(null);
  const deepDiscussionRef = useRef('');
  const [locatedSource, setLocatedSource] = useState<LocatedSource | null>(null);
  const [legacyLocated, setLegacyLocated] = useState(false);
  const originalReadSerial = useRef(0);
  const readOriginalRef = useRef<(messageId: string, locate?: boolean) => Promise<void>>(null);
  const [readingVersionId, setReadingVersionId] = useState<string | null>(null);
  const [discussionBack, setDiscussionBack] = useState<string | null>(null);
  const chatReadSerial = useRef(0);
  const chatViewRef = useRef({ filter: chatFilter, selection, revision });
  chatViewRef.current = { filter: chatFilter, selection, revision };
  const [job, setJob] = useState<StudioJob | null>(initialWorkspace.latest_job);
  const [jobIssues, setJobIssues] = useState<Array<{ path: string; message: string }>>([]);
  const jobValidationMessageRef = useRef<string | null>(null);
  const clearJobValidation = useCallback(() => {
    const previous = jobValidationMessageRef.current;
    setJobIssues([]);
    if (previous) setStatusMessage((current) => current === previous ? '' : current);
    jobValidationMessageRef.current = null;
  }, []);
  const [templateCandidate, setTemplateCandidate] = useState<TemplateCandidate | null>(null);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [focusedChange, setFocusedChange] = useState<{ id: string } | null>(null);
  const [commentsReady, setCommentsReady] = useState(false);
  const [archivedComments, setArchivedComments] = useState<ReviewComment[]>([]);
  const [activeCommentIds, setActiveCommentIds] = useState<string[]>([]);
  const [reviewRoundId, setReviewRoundId] = useState('');
  const [reviewRounds, setReviewRounds] = useState<ReviewRound[]>([]);
  const [commentDraft, setCommentDraft] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [showLeaveGuard, setShowLeaveGuard] = useState(false);
  const [localDrafts, setLocalDrafts] = useState<PendingSave[]>([]);
  const [rebaseConfirmation, setRebaseConfirmation] = useState<Workspace | null>(null);
  const [invalidCommentIds, setInvalidCommentIds] = useState<string[]>([]);
  const dirtyRef = useRef(false);
  const conflictRef = useRef(false);
  const draftViewRef = useRef(false);
  const draftBaseRef = useRef(revision);
  const recoveredDraftRef = useRef<PendingSave | null>(null);
  const savingRef = useRef(false);
  const inFlightSaveRef = useRef<Promise<void> | null>(null);
  const documentRef = useRef(document);
  const revisionRef = useRef(revision);
  const operationIdRef = useRef('');
  const operationKindRef = useRef('EDIT');
  const activeCommentsRef = useRef<string[]>([]);
  const pendingCommentIdsRef = useRef<string[]>([]);
  const undoRef = useRef<StudioDocument[]>([]);
  const redoRef = useRef<StudioDocument[]>([]);
  const [historyCounts, setHistoryCounts] = useState({ undo: 0, redo: 0 });
  const [historyWarning, setHistoryWarning] = useState('');
  const historyReadyRef = useRef(false);
  const historyChangedRef = useRef(false);
  const retainedHistoryRef = useRef<string | null>(null);
  const historyKey = `pepper-studio-history:${API_BASE}:${workspace.manuscript.manuscript_id}`;
  const channelRef = useRef<BroadcastChannel | null>(null);
  const canvasRef = useRef<HTMLElement | null>(null);
  const viewScrollRef = useRef<Record<ViewMode, number>>({ structure: 0, reading: 0, revision: 0 });
  const pageScrollRef = useRef<Record<ViewMode, number>>({ structure: 0, reading: 0, revision: 0 });
  const scrollRestoredRef = useRef(false);
  const [viewReady, setViewReady] = useState(false);
  const [foldedIds, setFoldedIds] = useState<string[]>([]);
  const [railDirection, setRailDirection] = useState<EditorUi['direction']>('upright');
  const viewStateKey = `pepper-studio-view-${workspace.manuscript.manuscript_id}`;

  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(historyKey);
      if (raw) {
        retainedHistoryRef.current = raw;
        const restored = restoreUndoHistory(raw, documentRef.current.manuscript_id, revisionRef.current, documentRef.current);
        undoRef.current = restored.undo; redoRef.current = restored.redo;
        retainedHistoryRef.current = null;
      }
    } catch (caught) { setHistoryWarning(caught instanceof Error ? caught.message : '撤销记录暂时无法读取，请保留此页。'); }
    finally { historyReadyRef.current = true; }
  }, [historyKey]);

  useEffect(() => {
    if (!historyReadyRef.current) return;
    setHistoryCounts((current) => current.undo === undoRef.current.length && current.redo === redoRef.current.length ? current
      : { undo: undoRef.current.length, redo: redoRef.current.length });
    if (retainedHistoryRef.current && !historyChangedRef.current) return;
    try {
      if (retainedHistoryRef.current) {
        window.sessionStorage.setItem(`${historyKey}-retained-${uid('history')}`, retainedHistoryRef.current);
        retainedHistoryRef.current = null;
      }
      // sessionStorage survives reload while keeping each tab's stack independent.
      window.sessionStorage.setItem(historyKey, serializeUndoHistory(documentRef.current, revisionRef.current, undoRef.current, redoRef.current));
    } catch { setHistoryWarning('本页撤销仍可用，但刷新后的撤销记录暂时无法保存，请保留此页。'); }
  }, [document, revision, historyKey]);

  const persistChatDraft = useCallback(() => {
    const key = `pepper-chat-draft-${workspace.manuscript.manuscript_id}`;
    try {
      if (chatDraftRef.current || annotationRef.current) window.localStorage.setItem(key, JSON.stringify({
        content: chatDraftRef.current, context: draftContextRef.current, annotation: annotationRef.current,
      }));
      else window.localStorage.removeItem(key);
    } catch { setStatusMessage('讨论草稿暂时无法保存在此浏览器，请保留当前页面。'); }
  }, [workspace.manuscript.manuscript_id]);

  const pendingSnapshot = useCallback((): PendingSave => ({
    manuscriptId: workspace.manuscript.manuscript_id,
    baseRevision: draftBaseRef.current,
    operationId: operationIdRef.current || uid('operation'),
    operationKind: operationKindRef.current,
    commentIds: [...pendingCommentIdsRef.current],
    document: cloneDocument(documentRef.current),
    queuedAt: new Date().toISOString(),
  }), [workspace.manuscript.manuscript_id]);

  const persistDraft = useCallback(() => {
    const pending = pendingSnapshot();
    try {
      outbox.checkpoint(pending);
    } catch {
      setStatusMessage('即时本地保存不可用，正在尝试备用存储。请等待保存结果再离开。');
    }
    void outbox.put(pending).catch(() =>
      setStatusMessage('本地副本写入失败。请留在此页，先导出副本或恢复连接完成保存。'),
    );
  }, [pendingSnapshot]);

  const openLocalDraft = useCallback(async (pending: PendingSave, resume = false) => {
    if (dirtyRef.current) {
      try {
        const retained = await outbox.keep(pendingSnapshot());
        setLocalDrafts((current) => [...current, retained]);
      } catch {
        setStatusMessage('当前本地修改无法另存。请先导出，暂不切换副本。');
        return;
      }
    }
    recoveredDraftRef.current = pending;
    retainedHistoryRef.current ||= serializeUndoHistory(documentRef.current, revisionRef.current, undoRef.current, redoRef.current);
    historyChangedRef.current = false;
    undoRef.current = []; redoRef.current = [];
    documentRef.current = cloneDocument(pending.document);
    setDocument(documentRef.current);
    draftBaseRef.current = pending.baseRevision;
    operationIdRef.current = pending.operationId;
    operationKindRef.current = pending.operationKind;
    pendingCommentIdsRef.current = [...pending.commentIds];
    dirtyRef.current = true;
    draftViewRef.current = !resume;
    conflictRef.current = !resume || pending.baseRevision !== revisionRef.current;
    setSaveState(!resume ? 'recovery' : conflictRef.current ? 'conflict' : 'pending');
    void studioApi.comments(pending.manuscriptId, true).then((all) => {
      if (operationIdRef.current !== pending.operationId) return;
      const valid = new Set(all.filter((item) => !item.archived_at).map((item) => item.comment_id));
      const active = pending.commentIds.filter((id) => valid.has(id));
      activeCommentsRef.current = active;
      setActiveCommentIds(active);
      setInvalidCommentIds(pending.commentIds.filter((id) => !valid.has(id)));
    }).catch(() => undefined);
    setStatusMessage(!resume
      ? '正在查看本地副本，尚未保存到服务器。可导出，或核对后确认继续编辑。'
      : conflictRef.current ? '已打开本地副本。服务器版本已变化；可查看服务器、导出副本，或核对后继续编辑。'
      : '已恢复未同步的本地副本，保留原对象和引用决定。');
  }, [pendingSnapshot]);

  const exportLocalDraft = (pending: PendingSave) => {
    const blob = new Blob([JSON.stringify(pending, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = window.document.createElement('a');
    link.href = url;
    link.download = `${pending.manuscriptId}-local-draft.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(viewStateKey) || '{}');
      const url = new URL(window.location.href);
      const savedRound = url.searchParams.get('round') || saved.reviewRoundId;
      if (typeof savedRound === 'string') setReviewRoundId(savedRound);
      const savedFolds = url.searchParams.has('folds') ? JSON.parse(url.searchParams.get('folds')!) : saved.foldedIds;
      if (Array.isArray(savedFolds)) setFoldedIds([...new Set(savedFolds.filter((id): id is string => typeof id === 'string'))]);
      if (['upright', 'rotated', 'horizontal'].includes(saved.railDirection)) setRailDirection(saved.railDirection);
      const requestedMode = url.searchParams.get('view') || saved.viewMode;
      if (['structure', 'reading', 'revision'].includes(requestedMode)) setViewMode(requestedMode);
      const booleanPreference = (name: string, value: unknown) => {
        const parameter = url.searchParams.get(name);
        return parameter === '1' ? true : parameter === '0' ? false : typeof value === 'boolean' ? value : undefined;
      };
      const left = booleanPreference('left', saved.showLeft);
      const right = booleanPreference('right', saved.showRight);
      const chatExpanded = booleanPreference('chat', saved.chatOpen);
      if (left !== undefined) setShowLeft(left);
      if (right !== undefined) setShowRight(right);
      if (chatExpanded !== undefined) setChatOpen(chatExpanded);
      const selectedId = url.searchParams.get('object') || saved.selectionId;
      const savedSelection = saved.selection as Selection | undefined;
      const restored = savedSelection?.type?.startsWith('generated_') && savedSelection.id === selectedId
        ? savedSelection : documentSelection(documentRef.current, typeof selectedId === 'string' ? selectedId : undefined);
      if (restored) setSelection(restored);
      else setStatusMessage('上次选中的对象已不可用，已返回本稿；没有改到其他对象。');
      if (saved.chatFilter === 'selection' && restored?.id) setChatFilter('selection');
      if (typeof saved.sourceQuery === 'string') setSourceQuery(saved.sourceQuery);
      const scroll = JSON.parse(window.localStorage.getItem(`${viewStateKey}-scroll`) || '{}');
      const pageScroll = JSON.parse(window.localStorage.getItem(`${viewStateKey}-page-scroll`) || '{}');
      for (const mode of ['structure', 'reading', 'revision'] as const) {
        if (typeof scroll[mode] === 'number' && Number.isFinite(scroll[mode]) && scroll[mode] >= 0) viewScrollRef.current[mode] = scroll[mode];
        if (typeof pageScroll[mode] === 'number' && Number.isFinite(pageScroll[mode]) && pageScroll[mode] >= 0) pageScrollRef.current[mode] = pageScroll[mode];
      }
    } catch {
      setStatusMessage('无法读取上次的界面位置；稿件内容仍从服务器读取。');
    } finally {
      setViewReady(true);
    }
  }, [viewStateKey]);

  useEffect(() => {
    if (!viewReady) return;
    try {
      window.localStorage.setItem(viewStateKey, JSON.stringify({
        viewMode, showLeft, showRight, chatOpen, selectionId: selection.id, selection, chatFilter, sourceQuery, foldedIds, railDirection, reviewRoundId,
      }));
      const url = new URL(window.location.href);
      url.searchParams.set('view', viewMode);
      url.searchParams.set('left', showLeft ? '1' : '0');
      url.searchParams.set('right', showRight ? '1' : '0');
      url.searchParams.set('chat', chatOpen ? '1' : '0');
      if (foldedIds.length) url.searchParams.set('folds', JSON.stringify(foldedIds));
      else url.searchParams.delete('folds');
      if (reviewRoundId) url.searchParams.set('round', reviewRoundId);
      else url.searchParams.delete('round');
      if (selection.id) url.searchParams.set('object', selection.id);
      else url.searchParams.delete('object');
      window.history.replaceState(window.history.state, '', url);
    } catch {
      setStatusMessage('无法保存界面位置；刷新后可能需要重新选择，稿件保存状态见右上角。');
    }
  }, [viewReady, viewStateKey, viewMode, showLeft, showRight, chatOpen, selection, chatFilter, sourceQuery, foldedIds, railDirection, reviewRoundId]);

  useEffect(() => {
    scrollRestoredRef.current = false;
    if (!viewReady || !canvasRef.current || (viewMode === 'revision' && !commentsReady)) return;
    const frame = window.requestAnimationFrame(() => {
      if (canvasRef.current) canvasRef.current.scrollTop = viewScrollRef.current[viewMode];
      window.scrollTo({ top: pageScrollRef.current[viewMode], behavior: 'instant' });
      scrollRestoredRef.current = true;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [viewReady, viewMode, commentsReady, comments.length]);

  useEffect(() => {
    if (!viewReady) return;
    const rememberScroll = () => {
      if (!scrollRestoredRef.current) return;
      pageScrollRef.current[viewMode] = window.scrollY;
      try {
        window.localStorage.setItem(`${viewStateKey}-page-scroll`, JSON.stringify(pageScrollRef.current));
      } catch {
        // A missing scroll preference does not change the manuscript save state.
      }
    };
    window.addEventListener('scroll', rememberScroll, { passive: true });
    return () => window.removeEventListener('scroll', rememberScroll);
  }, [viewReady, viewMode, viewStateKey]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: blockKeyboardCoordinates }),
  );

  useEffect(() => {
    documentRef.current = document;
  }, [document]);
  useEffect(() => {
    revisionRef.current = revision;
  }, [revision]);
  useEffect(() => {
    activeCommentsRef.current = activeCommentIds;
  }, [activeCommentIds]);

  useEffect(() => {
    const key = `pepper-chat-draft-${workspace.manuscript.manuscript_id}`;
    try {
      const raw = window.localStorage.getItem(key) || '';
      let saved: { content: string; context: Selection | null; annotation: string };
      try {
        const parsed = JSON.parse(raw);
        saved = typeof parsed.content === 'string' ? parsed : { content: raw, context: null, annotation: '' };
      } catch { saved = { content: raw, context: null, annotation: '' }; }
      setChatDraft(saved.content);
      chatDraftRef.current = saved.content;
      setDraftContext(saved.context || null);
      draftContextRef.current = saved.context || null;
      setAnnotation(saved.annotation || '');
      annotationRef.current = saved.annotation || '';
    } catch { setStatusMessage('讨论草稿读取失败，请保留此页面。'); }
    setChatDraftReady(true);
  }, [workspace.manuscript.manuscript_id]);

  useEffect(() => {
    if (!chatDraftReady) return;
    persistChatDraft();
  }, [chatDraftReady, persistChatDraft]);

  useEffect(() => {
    if (!chatDraftReady) return;
    let alive = true;
    const manuscriptId = workspace.manuscript.manuscript_id;
    const legacy = { content: chatDraftRef.current, annotation: annotationRef.current, context: draftContextRef.current };
    let tabId: string;
    try {
      tabId = window.sessionStorage.getItem('scholar-discussion-tab') || uid('discussion-tab');
      window.sessionStorage.setItem('scholar-discussion-tab', tabId);
    } catch { tabId = uid('discussion-tab'); }
    const apply = (state: DiscussionState) => {
      if (!alive) return;
      setSharedDiscussion(state);
      setChatBusy(state.busy);
      chatDraftRef.current = state.content; setChatDraft(state.content);
      annotationRef.current = state.annotation; setAnnotation(state.annotation);
      const context = state.bound?.context;
      const generated = context?.record.generated;
      const selected: Selection | null = context?.target.module === 'STUDIO' ? {
        type: context.target.object_kind as Selection['type'],
        id: context.target.object_kind === 'paper' ? undefined : context.target.object_id,
        label: context.label, anchorRevision: generated?.input_revision ?? context.target.document_revision ?? 0,
        authorRevisionKnown: generated ? generated.input_revision !== null : true,
        quote: { ...state.quote, ...(context.target.generated_version_id ? { generated_version_id: context.target.generated_version_id } : {}) },
      } : !context ? legacy.context : null;
      draftContextRef.current = selected; setDraftContext(selected);
      persistChatDraft();
      if (state.receipt?.studio_messages?.length) {
        const rows = state.receipt.studio_messages;
        const view = chatViewRef.current;
        const visible = rows.filter((message) => view.filter === 'paper' || matchesHistory(message, view.selection, view.revision));
        if (visible.length) {
          setChat((current) => [...new Map([...current, ...visible].map((message) => [message.message_id, message])).values()].sort((left, right) => left.created_at.localeCompare(right.created_at)));
        }
      }
    };
    let storage: Pick<Storage, 'getItem' | 'setItem'>;
    try { storage = window.localStorage; }
    catch { storage = { getItem: () => { throw new Error('本机存储不可用'); }, setItem: () => { throw new Error('本机存储不可用'); } }; }
    const controller = createSharedDiscussion({ request: sharedDiscussionRequest, storage,
      namespace: `scholar-discussion:${API_BASE}:${tabId}:${manuscriptId}`, uuid: () => uid('discussion-request'), onChange: apply,
      onLocate: async (source) => { if (locateDiscussionRef.current) await locateDiscussionRef.current(source); } });
    discussionRef.current = controller;
    const restored = controller.snapshot();
    if (restored.bound) { apply(restored); setSharedDiscussionReady(true); }
    else void (async () => {
      if (legacy.context || !(legacy.content || legacy.annotation)) {
        const selected: Selection = legacy.context || { type: 'paper', label: '整篇稿件' };
        await controller.choose(studioTarget(manuscriptId, selected, revisionRef.current), exactSelection(selected.quote));
      }
      if (!alive) return;
      controller.edit('content', legacy.content); controller.edit('annotation', legacy.annotation);
      apply(controller.snapshot()); setSharedDiscussionReady(true);
    })();
    return () => { alive = false; controller.leave(); if (discussionRef.current === controller) discussionRef.current = null; };
  }, [chatDraftReady, workspace.manuscript.manuscript_id, persistChatDraft]);

  useEffect(() => {
    const state = sharedDiscussion;
    if (!state?.pending || state.busy || !['QUEUED', 'RUNNING'].includes(state.receipt?.job?.status || '') || state.receipt?.execution_observation !== 'LIVE_WORKER') return;
    const timer = window.setTimeout(() => void discussionRef.current?.reconcile(false), 2000);
    return () => window.clearTimeout(timer);
  }, [sharedDiscussion]);

  useEffect(() => {
    if (!sharedDiscussionReady || !discussionRef.current || locatedSource || legacyLocated) return;
    const current = discussionRef.current.snapshot();
    if (!current.bound && (current.content || current.annotation)) return;
    if (!selection.type.startsWith('generated_') && (dirtyRef.current || conflictRef.current)) return;
    void discussionRef.current.choose(studioTarget(workspace.manuscript.manuscript_id, selection, revisionRef.current), exactSelection(selection.quote));
  }, [sharedDiscussionReady, selection, revision, workspace.manuscript.manuscript_id, locatedSource, legacyLocated]);

  useEffect(() => {
    if (!sharedDiscussionReady) return;
    discussionRef.current?.viewHistory(studioTarget(workspace.manuscript.manuscript_id, selection, revision), chatFilter === 'selection');
  }, [sharedDiscussionReady, selection, revision, workspace.manuscript.manuscript_id, chatFilter]);

  useEffect(() => () => { originalReadSerial.current += 1; }, [selection, workspace.manuscript.manuscript_id]);

  useEffect(() => {
    if (!sharedDiscussionReady || !viewReady) return;
    setDiscussionBack(discussionReturn(window.location.search, { catalogBase: process.env.NEXT_PUBLIC_PAPER_CATALOG_URL || 'http://127.0.0.1:8875/', studioBase: window.location.origin + '/' }));
    const reference = discussionReference(window.location.search);
    if (!reference) {
      const legacyId = new URLSearchParams(window.location.search).get('studio_discussion');
      if (!legacyId || legacyId.length > 200 || deepDiscussionRef.current === `studio:${legacyId}`) return;
      deepDiscussionRef.current = `studio:${legacyId}`;
      void readOriginalRef.current?.(legacyId, true);
      return;
    }
    const key = JSON.stringify(reference);
    if (deepDiscussionRef.current === key) return;
    deepDiscussionRef.current = key;
    void discussionRef.current?.locateSource(reference.message_id, reference.index, reference.scope);
  }, [sharedDiscussionReady, viewReady]);

  useEffect(() => {
    let cancelled = false;
    setGeneratedVersion(null);
    const id = readingVersionId || workspace.active_generated_version_id;
    if (id) void studioApi.generatedVersion(workspace.manuscript.manuscript_id, id).then((value) => {
      if (!cancelled) setGeneratedVersion(value);
    }).catch((caught) => {
      if (!cancelled) setStatusMessage(caught instanceof Error ? caught.message : '成文版本读取失败');
    });
    return () => { cancelled = true; };
  }, [readingVersionId, workspace.active_generated_version_id, workspace.manuscript.manuscript_id]);

  useEffect(() => {
    if ((!locatedSource && !legacyLocated) || !readingVersionId || generatedVersion?.generated_version_id !== readingVersionId || !selection.id) return;
    const frame = window.requestAnimationFrame(() => {
      const element = globalThis.document.querySelector<HTMLElement>(`[data-generated-anchor="${globalThis.CSS.escape(selection.id!)}"]`);
      if (!element) return;
      element.tabIndex = -1;
      element.focus({ preventScroll: true });
      element.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [generatedVersion, selection, readingVersionId, locatedSource, legacyLocated]);

  const refreshWorkspace = useCallback(async () => {
    if (dirtyRef.current) await outbox.put(pendingSnapshot());
    const fresh = await studioApi.workspace(workspace.manuscript.manuscript_id);
    if (fresh.document_revision !== revisionRef.current || !sameDocument(fresh.document, documentRef.current)) {
      retainedHistoryRef.current ||= serializeUndoHistory(documentRef.current, revisionRef.current, undoRef.current, redoRef.current);
      historyChangedRef.current = false;
      undoRef.current = []; redoRef.current = [];
    }
    setWorkspace(fresh);
    clearJobValidation();
    setDocument(cloneDocument(fresh.document));
    documentRef.current = cloneDocument(fresh.document);
    setRevision(fresh.document_revision);
    revisionRef.current = fresh.document_revision;
    draftBaseRef.current = fresh.document_revision;
    dirtyRef.current = false;
    conflictRef.current = false;
    draftViewRef.current = false;
    operationIdRef.current = '';
    pendingCommentIdsRef.current = [];
    const drafts = await outbox.list(workspace.manuscript.manuscript_id);
    setLocalDrafts(drafts);
    if (drafts.length) setStatusMessage('已载入服务器版本；未同步的本地副本仍可打开或导出。');
    setSaveState('saved');
  }, [pendingSnapshot, workspace.manuscript.manuscript_id, clearJobValidation]);

  const loadComments = useCallback(async () => {
    const [all, rounds] = await Promise.all([studioApi.comments(workspace.manuscript.manuscript_id, true), studioApi.reviewRounds(workspace.manuscript.manuscript_id)]);
    setReviewRounds(rounds);
    setReviewRoundId((current) => rounds.some((item) => item.review_round_id === current) ? current : rounds.at(-1)?.review_round_id || '');
    setComments(all.filter((item) => !item.archived_at));
    setArchivedComments(all.filter((item) => Boolean(item.archived_at)));
    setCommentsReady(true);
    const validIds = new Set(all.filter((item) => !item.archived_at).map((item) => item.comment_id));
    setActiveCommentIds((current) => {
      const valid = current.filter((id) => validIds.has(id));
      activeCommentsRef.current = valid;
      return valid;
    });
  }, [workspace.manuscript.manuscript_id]);

  const loadChat = useCallback(async (before?: string, beforeMessageId?: string) => {
    const serial = ++chatReadSerial.current;
    const anchorId = chatFilter === 'selection' ? selection.id : undefined;
    const selectedKey = JSON.stringify({ id: selection.id, ...historyFilter(selection, revision) });
    const rows = await studioApi.chat(
      workspace.manuscript.manuscript_id,
      anchorId,
      before,
      100,
      chatFilter === 'selection' ? historyFilter(selection, revision) : undefined,
      beforeMessageId,
    );
    if (serial !== chatReadSerial.current || chatViewRef.current.filter !== chatFilter) return;
    if (chatFilter === 'selection' && selectedKey !== JSON.stringify({ id: chatViewRef.current.selection.id, ...historyFilter(chatViewRef.current.selection, chatViewRef.current.revision) })) return;
    setChat((current) => before ? [...new Map([...rows, ...current].map((message) => [message.message_id, message])).values()] : rows);
    setChatHasMore(rows.length === 100);
  }, [chatFilter, selection, revision, workspace.manuscript.manuscript_id]);

  useEffect(() => {
    setChat([]); setChatHasMore(false);
    void loadChat()
      .catch((caught) => setStatusMessage(caught instanceof Error ? caught.message : '讨论历史读取失败'));
  }, [loadChat]);

  useEffect(() => {
    void loadComments().catch((caught) =>
      setStatusMessage(caught instanceof Error ? caught.message : '意见与修改记录读取失败'),
    );
  }, [loadComments, viewMode]);

  useEffect(() => {
    let cancelled = false;
    void outbox.list(workspace.manuscript.manuscript_id).then((drafts) => {
      if (cancelled) return;
      setLocalDrafts(drafts);
      if (drafts.length === 1) void openLocalDraft(drafts[0], true);
      else if (drafts.length > 1) setStatusMessage(`发现 ${drafts.length} 份本地副本。请选择要查看的副本；服务器内容保持可见。`);
    }).catch(() => setStatusMessage('本地副本读取失败，请保留当前页面并重试。'));
    return () => { cancelled = true; };
  }, [openLocalDraft, workspace.manuscript.manuscript_id]);

  useEffect(() => {
    const channel = new BroadcastChannel(`pepper-studio-${workspace.manuscript.manuscript_id}`);
    channelRef.current = channel;
    channel.onmessage = (event: MessageEvent<{ revision: number }>) => {
      if (event.data.revision > revisionRef.current) {
        conflictRef.current = true;
        draftViewRef.current = false;
        setSaveState('conflict');
        setStatusMessage('另一标签页已经保存了更新；当前标签页不会自动覆盖它。');
      }
    };
    return () => channel.close();
  }, [workspace.manuscript.manuscript_id]);

  const performSave = useCallback(async () => {
    if (!dirtyRef.current || savingRef.current || conflictRef.current) return;
    savingRef.current = true;
    setSaveState('saving');
    const snapshot = cloneDocument(documentRef.current);
    const baseRevision = draftBaseRef.current;
    const operationId = operationIdRef.current || uid('operation');
    operationIdRef.current = operationId;
    const pending = {
      manuscriptId: workspace.manuscript.manuscript_id,
      baseRevision,
      operationId,
      operationKind: operationKindRef.current,
      commentIds: [...pendingCommentIdsRef.current],
      document: snapshot,
      queuedAt: new Date().toISOString(),
    };
    try {
      const stored = await outbox.put(pending);
      if (pending.commentIds.length) {
        const all = await studioApi.comments(pending.manuscriptId, true);
        const valid = new Set(all.filter((item) => !item.archived_at).map((item) => item.comment_id));
        const invalid = pending.commentIds.filter((id) => !valid.has(id));
        if (invalid.length) {
          setInvalidCommentIds(invalid);
          setSaveState('failed');
          setStatusMessage('这份本地修改关联的意见已归档或不可用。内容已保留；请确认解除这些关联后重试。');
          return;
        }
      }
      const result = await studioApi.saveDocument(
        pending.manuscriptId,
        baseRevision,
        operationId,
        snapshot,
        pending.operationKind,
        pending.commentIds,
      );
      if (!sameDocument(result.document, snapshot)) {
        conflictRef.current = true;
        draftViewRef.current = false;
        setSaveState('conflict');
        setStatusMessage('这次操作已保存，但服务器已有后续修改。本地副本已保留，请核对版本。');
        return;
      }
      revisionRef.current = result.document_revision;
      draftBaseRef.current = result.document_revision;
      setRevision(result.document_revision);
      channelRef.current?.postMessage({ revision: result.document_revision });
      const unchanged = operationIdRef.current === operationId;
      if (unchanged) {
        dirtyRef.current = false;
        operationIdRef.current = '';
        operationKindRef.current = 'EDIT';
        pendingCommentIdsRef.current = [];
        await outbox.remove(stored).catch(() => setStatusMessage('稿件已保存；旧本地副本暂时无法清理，仍可导出。'));
        if (recoveredDraftRef.current) {
          await outbox.remove(recoveredDraftRef.current).catch(() => undefined);
          recoveredDraftRef.current = null;
        }
        setLocalDrafts(await outbox.list(pending.manuscriptId));
        if (!dirtyRef.current) setSaveState('saved');
      } else {
        await outbox.put(pendingSnapshot());
        setSaveState('pending');
      }
      if (pending.commentIds.length) {
        void loadComments().catch((caught) =>
          setStatusMessage(caught instanceof Error ? caught.message : '修改已保存，意见记录暂时无法刷新'),
        );
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        conflictRef.current = true;
        draftViewRef.current = false;
        setSaveState('conflict');
        setStatusMessage('服务器稿件已经变化；当前本地修改已保留，但不会静默覆盖。');
      } else {
        setSaveState('failed');
        setStatusMessage(caught instanceof Error ? caught.message : '保存失败，本地修改仍在。');
      }
    } finally {
      savingRef.current = false;
    }
  }, [loadComments, pendingSnapshot, workspace.manuscript.manuscript_id]);

  const flushSave = useCallback(() => {
    if (inFlightSaveRef.current) return inFlightSaveRef.current;
    const promise = performSave();
    inFlightSaveRef.current = promise;
    void promise.finally(() => {
      if (inFlightSaveRef.current === promise) inFlightSaveRef.current = null;
    });
    return promise;
  }, [performSave]);

  const prepareSuggestion = async () => {
    await flushSave();
    if (dirtyRef.current || savingRef.current || conflictRef.current) {
      throw new ApiError(409, { detail: '请先保存当前修改或核对版本，再比较和采用建议。本地内容已保留。' });
    }
  };

  const decideSuggestion = async (messageId: string, request: SuggestionDecisionRequest, retry: boolean) => {
    if (!retry) await prepareSuggestion();
    if (savingRef.current) throw new ApiError(409, { detail: '当前保存仍在进行，请等待完成后重试。' });
    const before = cloneDocument(documentRef.current);
    savingRef.current = true;
    try {
      const result = await studioApi.decideSuggestion(workspace.manuscript.manuscript_id, messageId, request);
      const mode = suggestionResultMode(result, documentRef.current, revisionRef.current, dirtyRef.current);
      if (mode === 'applied') {
        historyChangedRef.current = true;
        undoRef.current.push(before);
        if (undoRef.current.length > 100) undoRef.current.shift();
        redoRef.current = [];
        const fresh = result.workspace;
        documentRef.current = cloneDocument(fresh.document);
        setDocument(documentRef.current);
        setWorkspace(fresh);
        revisionRef.current = fresh.document_revision;
        draftBaseRef.current = fresh.document_revision;
        setRevision(fresh.document_revision);
        operationIdRef.current = '';
        pendingCommentIdsRef.current = [];
        conflictRef.current = false;
        draftViewRef.current = false;
        setSaveState('saved');
        setStatusMessage('已保存所选改动和作者决定；可从编辑器撤销或重做。');
      } else if (mode === 'compare') {
        if (dirtyRef.current) persistDraft();
        conflictRef.current = true;
        draftViewRef.current = false;
        setSaveState('conflict');
        setStatusMessage('作者决定已保存；当前本地内容或服务器已有后续修改，请核对版本。本地内容已保留。');
      } else {
        if (mode === 'same') {
          conflictRef.current = false;
          draftViewRef.current = false;
          setSaveState('saved');
        }
        setStatusMessage(mode === 'rejected' ? '拒绝决定已保存，稿件内容保留。' : '已核对原决定，稿件保留当前内容。');
      }
      if (result.decision.outcome !== 'REJECT') {
        channelRef.current?.postMessage({ revision: result.workspace.document_revision });
        void loadComments().catch(() => setStatusMessage('决定已保存，意见关联记录暂时无法刷新。'));
      }
      return result;
    } catch (caught) {
      if (request.outcome !== 'REJECT' && (!(caught instanceof ApiError) || ![400, 404, 422].includes(caught.status))) {
        conflictRef.current = true;
        setSaveState('conflict');
      } else if (dirtyRef.current) setSaveState('failed');
      setStatusMessage(caught instanceof Error ? caught.message : '决定结果待确认，请核对原决定。');
      throw caught;
    } finally { savingRef.current = false; }
  };

  const changeCommentContext = async (ids: string[]) => {
    await flushSave();
    if (dirtyRef.current || savingRef.current) {
      setStatusMessage('当前修改仍待同步；保存后再切换意见关联，本地内容已保留。');
      return false;
    }
    activeCommentsRef.current = ids;
    setActiveCommentIds(ids);
    return true;
  };

  const archiveComment = async (commentId: string) => {
    if (!(await changeCommentContext(activeCommentIds.filter((id) => id !== commentId)))) return;
    try {
      await studioApi.archiveComment(commentId);
      await loadComments();
    } catch (caught) {
      setStatusMessage(caught instanceof Error ? caught.message : '意见删除失败，请重试。');
    }
  };

  useEffect(() => {
    const protect = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current && !savingRef.current) return;
      event.preventDefault();
    };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, []);

  const requestExit = async () => {
    await flushSave();
    if (dirtyRef.current || savingRef.current) setShowLeaveGuard(true);
    else onExit();
  };

  useEffect(() => {
    if (!dirtyRef.current || saveState !== 'pending') return;
    const timer = window.setTimeout(() => void flushSave(), 650);
    return () => window.clearTimeout(timer);
  }, [document, flushSave, saveState]);

  const commit = useCallback(
    (
      change: (draft: StudioDocument) => void,
      operationKind = 'EDIT',
      recordHistory = true,
    ) => {
      const previous = cloneDocument(documentRef.current);
      const next = cloneDocument(previous);
      change(next);
      reconcileStructure(next);
      if (recordHistory) {
        historyChangedRef.current = true;
        undoRef.current.push(previous);
        if (undoRef.current.length > 100) undoRef.current.shift();
        redoRef.current = [];
      }
      documentRef.current = next;
      clearJobValidation();
      setDocument(next);
      if (!dirtyRef.current) {
        pendingCommentIdsRef.current = [...activeCommentsRef.current];
        draftBaseRef.current = revisionRef.current;
      }
      dirtyRef.current = true;
      // A queued network operation has an immutable payload. New input always
      // gets a different id, including input entered while a save is in flight.
      operationIdRef.current = uid('operation');
      operationKindRef.current = operationKind;
      persistDraft();
      setSaveState(conflictRef.current ? draftViewRef.current ? 'recovery' : 'conflict' : 'pending');
      if (workspace.last_generated_revision !== null) {
        setWorkspace((current) => ({ ...current, generated_is_stale: true }));
      }
    },
    [persistDraft, workspace.last_generated_revision, clearJobValidation],
  );

  useEffect(() => {
    const modelContext = (
      globalThis.document as Document & { modelContext?: WebModelContext }
    ).modelContext;
    if (!modelContext?.registerTool) return;
    const lifecycle = new AbortController();
    const register = async () => {
      await modelContext.registerTool(
        {
          name: 'get_writing_context',
          title: 'Read writing context',
          description:
            'Read the active paper stage, selected object, save state, and document revision without changing the manuscript.',
          inputSchema: { type: 'object', properties: {}, additionalProperties: false },
          annotations: { readOnlyHint: true, untrustedContentHint: false },
          execute: () => ({
            manuscriptId: workspace.manuscript.manuscript_id,
            stage,
            revision: revisionRef.current,
            selection,
            saveState,
          }),
        },
        { signal: lifecycle.signal },
      );
      await modelContext.registerTool(
        {
          name: 'add_author_thought',
          title: 'Add author thought',
          description:
            'Add an author-supplied atomic thought to an existing intent. The new thought keeps citation status pending and is autosaved through the same visible editor flow.',
          inputSchema: {
            type: 'object',
            properties: {
              intentId: { type: 'string' },
              text: { type: 'string', minLength: 1, maxLength: 12000 },
            },
            required: ['intentId', 'text'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: true },
          execute: (input) => {
            const value = input as { intentId?: unknown; text?: unknown };
            if (
              typeof value.intentId !== 'string' ||
              typeof value.text !== 'string' ||
              !value.text.trim()
            ) {
              throw new Error('intentId and non-empty text are required');
            }
            const found = documentRef.current.sections.some((section) =>
              section.paragraphs.some((paragraph) =>
                paragraph.intents.some((item) => item.id === value.intentId),
              ),
            );
            if (!found) throw new Error(`Unknown intent: ${value.intentId}`);
            const thoughtId = uid('thought');
            const text = value.text.trim();
            commit((draft) => {
              for (const section of draft.sections) {
                for (const paragraph of section.paragraphs) {
                  const intent = paragraph.intents.find(
                    (item) => item.id === value.intentId,
                  );
                  if (intent) {
                    intent.thoughts.push({
                      id: thoughtId,
                      text,
                      citation_mode: 'PENDING',
                      citations: [],
                    });
                  }
                }
              }
            }, 'ADD_THOUGHT');
            return { thoughtId, intentId: value.intentId, saveState: 'pending' };
          },
        },
        { signal: lifecycle.signal },
      );
    };
    void register().catch(() => undefined);
    return () => lifecycle.abort();
  }, [commit, saveState, selection, stage, workspace.manuscript.manuscript_id]);

  const undo = useCallback(() => {
    const previous = undoRef.current.pop();
    if (!previous) return;
    redoRef.current.push(cloneDocument(documentRef.current));
    documentRef.current = previous;
    clearJobValidation();
    setDocument(previous);
    if (!dirtyRef.current) pendingCommentIdsRef.current = [...activeCommentsRef.current];
    dirtyRef.current = true;
    operationIdRef.current = uid('operation');
    operationKindRef.current = 'UNDO';
    persistDraft();
    setSaveState(conflictRef.current ? draftViewRef.current ? 'recovery' : 'conflict' : 'pending');
  }, [persistDraft, clearJobValidation]);

  const redo = useCallback(() => {
    const next = redoRef.current.pop();
    if (!next) return;
    undoRef.current.push(cloneDocument(documentRef.current));
    documentRef.current = next;
    clearJobValidation();
    setDocument(next);
    if (!dirtyRef.current) pendingCommentIdsRef.current = [...activeCommentsRef.current];
    dirtyRef.current = true;
    operationIdRef.current = uid('operation');
    operationKindRef.current = 'REDO';
    persistDraft();
    setSaveState(conflictRef.current ? draftViewRef.current ? 'recovery' : 'conflict' : 'pending');
  }, [persistDraft, clearJobValidation]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.target instanceof Element && event.target.closest('.chat-dock, [role="dialog"], [role="alertdialog"]')) return;
      if (event.key.toLowerCase() === 'z' && !event.shiftKey) {
        event.preventDefault();
        undo();
      } else if (event.key.toLowerCase() === 'y' || (event.key.toLowerCase() === 'z' && event.shiftKey)) {
        event.preventDefault();
        redo();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [redo, undo]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void studioApi
        .samples(
          workspace.manuscript.manuscript_id,
          selection.type,
          selection.id,
          selection.role,
          selection.intent,
        )
        .then((items) => {
          setSamples(items);
          setSampleIndex(0);
        })
        .catch(() => setSamples([]));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [selection, workspace.manuscript.manuscript_id]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void studioApi
        .sources(workspace.manuscript.manuscript_id, sourceQuery)
        .then(setSources)
        .catch(() => setSources([]));
    }, 280);
    return () => window.clearTimeout(timer);
  }, [sourceQuery, workspace.manuscript.manuscript_id]);

  useEffect(() => {
    if (!job || !['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'].includes(job.status)) return;
    const timer = window.setInterval(() => {
      void studioApi.job(job.job_id).then((next) => {
        setJob(next);
        if (next.status === 'SUCCEEDED') {
          window.clearInterval(timer);
          void refreshWorkspace();
        }
        if (next.status === 'FAILED') {
          window.clearInterval(timer);
          const issues = next.error?.issues || [];
          setJobIssues(issues);
          setStatusMessage(issues.map((item) => item.message).join(' · ') || next.error?.message || '任务失败');
        }
      });
    }, 900);
    return () => window.clearInterval(timer);
  }, [job, refreshWorkspace]);

  const startJob = async (kind: string, jobRequest: Record<string, unknown> = {}) => {
    await flushSave();
    if (dirtyRef.current) {
      setStatusMessage('稿件仍未同步，暂时不能开始任务。');
      return;
    }
    const submittedRevision = revisionRef.current;
    const submittedDocument = cloneDocument(documentRef.current);
    try {
      const next = await studioApi.createJob(
        workspace.manuscript.manuscript_id,
        kind,
        submittedRevision,
        kind === 'SUBMISSION_PACKAGE' && reviewRoundId ? { review_round_id: reviewRoundId, ...jobRequest } : jobRequest,
      );
      setJob(next);
      clearJobValidation();
      setStatusMessage('');
    } catch (caught) {
      if (caught instanceof ApiError) {
        const issues = (caught.body.issues as Array<{ path: string; message: string }> | undefined) || [];
        const current = !dirtyRef.current && revisionRef.current === submittedRevision
          && sameDocument(documentRef.current, submittedDocument);
        setJobIssues(current ? issues : []);
        const message = `结构 r${submittedRevision}：${issues.map((item) => item.message).join(' · ') || caught.message}${current ? '' : '；当前稿件已有修改，请重新检查。'}`;
        jobValidationMessageRef.current = message;
        setStatusMessage(message);
      } else setStatusMessage(caught instanceof Error ? caught.message : '任务无法开始');
    }
  };

  const switchMode = (mode: ViewMode) => {
    scrollRestoredRef.current = false;
    setViewMode(mode);
    if (mode === 'structure') {
      setShowLeft(true);
      setShowRight(true);
    } else {
      setShowLeft(false);
      setShowRight(false);
    }
  };

  const focusBlock = (path: string) => {
    switchMode('structure');
    const found = documentSelection(documentRef.current, path);
    if (!found) { setStatusMessage('原对象已不可用；历史原文仍保留。'); return; }
    setSelection(found);
    unfoldBlocks([path]);
    window.setTimeout(() => {
      globalThis.document.querySelector(`[data-block-id="${globalThis.CSS.escape(path)}"]`)?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' });
    }, 0);
  };

  const unfoldBlocks = (ids: string[]) => {
    const open = new Set(ids.flatMap((id) => [id, ...ancestors(documentRef.current, id)]));
    setFoldedIds((current) => current.filter((id) => !open.has(id)));
  };

  locateDiscussionRef.current = async (reference) => {
    const context = reference.source.context;
    const target = context.target;
    if (target.module === 'STUDIO' && target.manuscript_id === workspace.manuscript.manuscript_id) {
      setLocatedSource(reference); setHistoricalContext(null); setLegacyLocated(false); setChatOpen(true);
      if (!target.object_kind.startsWith('generated_')) setReadingVersionId(null);
      if (target.object_kind.startsWith('generated_')) {
        setReadingVersionId(target.generated_version_id || null);
        switchMode('reading');
        setSelection({ type: target.object_kind as Selection['type'], id: target.object_id, label: context.label,
          anchorRevision: target.document_revision, quote: { ...reference.source.quote, generated_version_id: target.generated_version_id } });
      } else if (target.object_kind === 'paper') {
        switchMode('structure'); setSelection({ type: 'paper', label: context.label });
      } else if (documentSelection(documentRef.current, target.object_id)) focusBlock(target.object_id);
      else setStatusMessage('原对象已删除，保留当时原文与选区；未选中其他对象。');
      await discussionRef.current?.openHistory(reference.message_id, reference.index, false, reference.scope);
      return;
    }
    await flushSave();
    if (dirtyRef.current || conflictRef.current) throw new Error('稿件尚未同步，原讨论仍保留；请先处理本地副本。');
    const url = discussionDestination(context, { catalogBase: process.env.NEXT_PUBLIC_PAPER_CATALOG_URL || 'http://127.0.0.1:8875/', studioBase: window.location.origin + '/' }, { ...reference, return_url: window.location.href });
    window.location.assign(url);
  };

  const closeSourceLocation = () => {
    originalReadSerial.current += 1;
    window.history.replaceState(window.history.state, '', discussionWithoutReference(window.location.href));
    deepDiscussionRef.current = '';
    setReadingVersionId(null); setLocatedSource(null); setHistoricalContext(null); setLegacyLocated(false);
    const current = selection.type.startsWith('generated_') ? null : documentSelection(documentRef.current, selection.id);
    setSelection(current || { type: 'paper', label: document.title });
    if (!current?.id) setChatFilter('paper');
  };

  const readOriginal = async (messageId: string, locate = false) => {
    const serial = ++originalReadSerial.current;
    try {
      const original = await studioApi.chatContext(workspace.manuscript.manuscript_id, messageId);
      if (serial !== originalReadSerial.current) return;
      const selected = legacySelection(original, workspace.manuscript.manuscript_id) as Selection;
      setHistoricalContext(original);
      if (!locate) return;
      setLocatedSource(null); setLegacyLocated(true); setChatOpen(true);
      setReadingVersionId(original.generated?.generated_version_id || null);
      if (original.generated) { switchMode('reading'); setSelection(selected); }
      else if (selected.type === 'paper') { switchMode('structure'); setSelection(selected); }
      else if (selected.id && documentSelection(documentRef.current, selected.id)) { focusBlock(selected.id); setSelection(selected); }
      else setStatusMessage('原对象已删除；当时原文与选区保留，未选中邻居对象。');
      const url = new URL(discussionWithoutReference(window.location.href));
      url.searchParams.set('studio_discussion', messageId);
      window.history.replaceState(window.history.state, '', url);
    } catch (caught) {
      if (serial === originalReadSerial.current) setStatusMessage(caught instanceof Error ? caught.message : '原讨论对象读取失败');
    }
  };

  const chooseOriginalSource = async () => {
    if (!historicalContext || !discussionRef.current) return;
    const selected = legacySelection(historicalContext, workspace.manuscript.manuscript_id);
    await discussionRef.current.choose(studioTarget(workspace.manuscript.manuscript_id, selected, revision), exactSelection(selected.quote));
  };
  readOriginalRef.current = readOriginal;

  const bindDraft = async (target = selection) => {
    const controller = discussionRef.current;
    if (!controller || !sharedDiscussionReady || controller.snapshot().pending || draftBindingBusyRef.current) return;
    draftBindingBusyRef.current = true;
    setDraftBindingBusy(true);
    try {
    if (!target.type.startsWith('generated_')) {
      await flushSave();
      if (dirtyRef.current || conflictRef.current) {
        setStatusMessage('结构尚未保存；讨论草稿已保留，请先完成同步后绑定对象。');
        return;
      }
      if (target.id && !documentSelection(documentRef.current, target.id)) {
        setStatusMessage('原对象已删除；请选择实际对象后绑定草稿。');
        return;
      }
    }
    const previous = controller.snapshot();
    await controller.choose(studioTarget(workspace.manuscript.manuscript_id, target, revisionRef.current), exactSelection(target.quote));
    if (controller.snapshot().proposed) controller.compare('use');
    if (!previous.bound) {
      controller.edit('content', previous.content);
      controller.edit('annotation', previous.annotation);
    }
    } finally { draftBindingBusyRef.current = false; setDraftBindingBusy(false); }
  };

  const updateChatDraft = (content: string) => {
    discussionRef.current?.edit('content', content);
  };

  const discussGenerated = (block: GeneratedBlock, quote?: AuthorQuote) => {
    if (!generatedVersion) return;
    setSelection({
      type: `generated_${block.kind}`, id: block.anchor_id, label: `${block.label} · 成文 v${generatedVersion.version}`,
      anchorRevision: generatedVersion.input_revision ?? 0,
      authorRevisionKnown: generatedVersion.input_revision !== null,
      quote: { ...quote, generated_version_id: generatedVersion.generated_version_id },
    });
    setChatOpen(true);
  };

  const openGeneratedSource = (evidenceId: string) => {
    sourcePreviewRequestRef.current += 1;
    const reference = generatedVersion?.references.find((item) => item.evidence_id === evidenceId);
    setPinnedReference(reference || null);
    setPinnedReferenceVersion(reference && generatedVersion ? { manuscriptId: workspace.manuscript.manuscript_id, id: generatedVersion.generated_version_id, version: generatedVersion.version } : null);
    if (!reference) setSourceQuery(evidenceId);
    setShowRight(true);
  };

  const openDiscussionSource = async (messageId: string, evidenceId: string) => {
    const request = ++sourcePreviewRequestRef.current;
    setPinnedReference(null);
    setPinnedReferenceVersion(null);
    setShowRight(true);
    try {
      const original = await studioApi.chatContext(workspace.manuscript.manuscript_id, messageId);
      if (request !== sourcePreviewRequestRef.current) return;
      if (original.generated) {
        const reference = original.generated.references.find((item) => item.evidence_id === evidenceId);
        if (!reference) throw new Error('原讨论没有保存这条引用的来源快照；无法回查原来源。');
        setPinnedReference(reference);
        setPinnedReferenceVersion({ manuscriptId: workspace.manuscript.manuscript_id,
          id: original.generated.generated_version_id, version: original.generated.version });
      } else setSourceQuery(evidenceId);
    } catch (error) {
      if (request === sourcePreviewRequestRef.current) {
        setStatusMessage(error instanceof Error ? error.message : '原讨论来源读取失败。');
      }
    }
  };

  const editGeneratedObject = (block: GeneratedBlock) => {
    if (generatedVersion?.structure_mapping_available && documentSelection(documentRef.current, block.object_id)) {
      focusBlock(block.object_id);
    } else setStatusMessage('此成文对象的原始结构已删除或没有历史映射；原文与讨论仍保留。');
  };

  const focusFinding = (anchor: Record<string, unknown>) => {
    for (const key of ['thought_id', 'intent_id', 'paragraph_id', 'section_id']) {
      if (typeof anchor[key] === 'string') {
        focusBlock(anchor[key]);
        return;
      }
    }
    if (typeof anchor.paragraph_index === 'number') {
      const paragraphs = documentRef.current.sections.flatMap((section) => section.paragraphs);
      const paragraph = paragraphs[anchor.paragraph_index];
      if (paragraph) focusBlock(paragraph.id);
    }
  };

  const onDragEnd = (event: DragEndEvent) => {
    const activeId = String(event.active.id);
    const target = event.over?.data.current?.dropTarget as BlockTarget | undefined;
    if (!target) return;
    if (event.active.data.current?.type === 'template') {
      const skeletonId: unknown = event.active.data.current.skeletonId;
      if (typeof skeletonId !== 'string' || !canDropTemplate(documentRef.current, target)) return;
      const chosen = documentSelection(documentRef.current, target.kind === 'paper' ? undefined : target.id);
      if (chosen) void previewTemplate(skeletonId, chosen);
      return;
    }
    try {
      const next = moveBlocks(documentRef.current, [activeId], target);
      if (sameDocument(next, documentRef.current)) return;
      commit((draft) => Object.assign(draft, next), 'MOVE_BLOCKS');
      const moved = documentSelection(next, activeId);
      if (moved) setSelection(moved);
      unfoldBlocks([target.id]);
      setStatusMessage('已移动原内容，引用与编号保留；可撤销。');
    } catch (error) { setStatusMessage(error instanceof Error ? error.message : '这个位置无法放入所选内容。'); }
  };

  const addSourceToSelectedThought = (source: SourceEvidence) => {
    if (selection.type !== 'thought' || !selection.id) {
      setStatusMessage('先选择一个思想块，再按 Enter 加入引用候选；也可以直接拖入思想块。');
      return;
    }
    commit((draft) => {
      const location = locateThought(draft, selection.id!);
      if (!location) return;
      const thought =
        draft.sections[location.sectionIndex].paragraphs[location.paragraphIndex]
          .intents[location.intentIndex].thoughts[location.thoughtIndex];
      if (!thought.citations.some((item) => item.evidence_id === source.evidence_id)) {
        thought.citations.push({
          evidence_id: source.evidence_id,
          selected: false,
          statement: source.statement,
          title: source.title,
        });
      }
      thought.citation_mode = 'PENDING';
    }, 'ADD_CITATION_CANDIDATE');
  };

  const adoptCurrentSample = async () => {
    const sample = samples[sampleIndex];
    if (!sample?.skeleton_id || !['paper', 'section', 'paragraph', 'intent'].includes(selection.type)) {
      setStatusMessage('先选择整篇、章节、段落或 Intent，再预览有固定来源的模板。');
      return;
    }
    await previewTemplate(sample.skeleton_id, selection);
  };

  const previewTemplate = async (skeletonId: string, chosen: Selection) => {
    await flushSave();
    if (dirtyRef.current || savingRef.current || conflictRef.current) {
      setStatusMessage('请先保存当前修改或核对版本，再预览模板。本地内容已保留。');
      return;
    }
    const targets: TemplateCandidate['targets'] = [{ scope_type: 'paper', scope_id: workspace.manuscript.manuscript_id, label: '整篇论文' }];
    documentRef.current.sections.filter((section) => section.placement_status !== 'UNPLACED').forEach((section, sectionIndex) => {
      const sectionLabel = `${section.parent_section_id ? '子章节' : '章节'} ${sectionIndex + 1}：${sectionBreadcrumb(documentRef.current,section.id)}`;
      targets.push({ scope_type: 'section', scope_id: section.id, label: sectionLabel });
      section.paragraphs.forEach((paragraph, paragraphIndex) => {
        const paragraphLabel = `${sectionLabel} / 段落 ${paragraphIndex + 1}`;
        targets.push({ scope_type: 'paragraph', scope_id: paragraph.id, label: paragraphLabel });
        paragraph.intents.forEach((intent, intentIndex) => targets.push({ scope_type: 'intent', scope_id: intent.id,
          label: `${paragraphLabel} / Intent ${intentIndex + 1}：${intent.label || '未定'}` }));
      });
    });
    if (!targets.some((target) => target.scope_type === chosen.type && target.scope_id === (chosen.id || workspace.manuscript.manuscript_id))) {
      setStatusMessage('请选择待安置区域以外的作者结构，再预览模板。');
      return;
    }
    setTemplateCandidate({ skeleton_id: skeletonId, scope_type: chosen.type as TemplateCandidate['scope_type'],
      scope_id: chosen.id || workspace.manuscript.manuscript_id, label: chosen.label,
      base_revision: revisionRef.current, operation_id: uid('template'), comment_ids: [...activeCommentsRef.current], targets });
  };

  const applyReviewedTemplate = async (request: TemplateRequest) => {
    await flushSave();
    if (dirtyRef.current || savingRef.current) throw new Error('当前修改尚未同步；原模板请求仍保留。');
    const before = cloneDocument(documentRef.current);
    const beforeRevision = revisionRef.current;
    savingRef.current = true;
    try {
      const result = await studioApi.applyTemplate(workspace.manuscript.manuscript_id, request);
      const instance = result.template_instance;
      setWorkspace((current) => ({ ...current, document_revision: result.document_revision,
        document: result.document, generated_is_stale: current.last_generated_revision !== null,
        template_instances: [...current.template_instances.filter((item) => item.template_instance_id !== instance.template_instance_id), instance] }));
      channelRef.current?.postMessage({ revision: result.document_revision });
      if (!sameDocument(documentRef.current, before) || dirtyRef.current) {
        await outbox.put(pendingSnapshot());
        conflictRef.current = true; draftViewRef.current = false; setSaveState('conflict');
        setStatusMessage('模板已保存；期间输入的本地修改仍保留，请核对版本。');
        return;
      }
      if (beforeRevision === request.base_revision && result.document_revision === result.operation.resulting_revision) {
        historyChangedRef.current = true;
        undoRef.current.push(before); redoRef.current = [];
      }
      documentRef.current = cloneDocument(result.document); setDocument(cloneDocument(result.document));
      clearJobValidation();
      revisionRef.current = result.document_revision; draftBaseRef.current = result.document_revision;
      setRevision(result.document_revision); dirtyRef.current = false; conflictRef.current = false;
      draftViewRef.current = false; operationIdRef.current = ''; pendingCommentIdsRef.current = [];
      recoveredDraftRef.current = null; setSaveState('saved');
      setStatusMessage(result.idempotent_replay && result.document_revision !== result.operation.resulting_revision
        ? `原采用已记录在结构 r${result.operation.resulting_revision}；当前显示服务器 r${result.document_revision}，后续编辑与撤销保持。`
        : request.mode === 'REPLACE' ? '已采用所选空结构；原内容保留在待安置区域，可移动或撤销。' : '已插入所选空结构，原思想、引用和编号保持。');
      if (request.comment_ids.length) void loadComments();
    } finally { savingRef.current = false; }
  };

  const generatedContent = generatedVersion?.content || latestGeneratedContent(workspace);
  const reviewResult = job?.job_kind === 'WHOLE_PAPER_REVIEW' && job.status === 'SUCCEEDED' ? job.result : null;
  const saveLabel = {
    saved: '已自动保存',
    pending: '等待同步',
    saving: '保存中…',
    failed: '保存失败 · 请重试',
    conflict: '版本冲突 · 未覆盖',
    recovery: '本地副本 · 等待确认',
  }[saveState];

  return (
    <main className="studio-app">
      <header className="studio-topbar">
        <div className="studio-brand">
          <span className="studio-wordmark">WRITING STUDIO</span>
          <span className="studio-context">{document.title} · RSTV4</span>
        </div>
        <div className="studio-actions">
          <output className={`save-state save-state--${saveState}`} aria-live="polite">{saveLabel}</output>
          {saveState === 'failed' ? <>
            <Button size="sm" variant="outline" onClick={() => void flushSave()}>重试保存</Button>
            <Button size="sm" variant="outline" onClick={() => exportLocalDraft(pendingSnapshot())}>导出本地副本</Button>
          </> : null}
          <Button variant="ghost" size="icon" aria-label="撤销" disabled={!historyCounts.undo} onClick={undo}><Undo2 /></Button>
          <Button variant="ghost" size="icon" aria-label="重做" disabled={!historyCounts.redo} onClick={redo}><Redo2 /></Button>
          {viewMode === 'structure' ? (
            <>
            {stage === 'WHOLE_PAPER_REVIEW' && workspace.active_generated_version_id ? (
              <Button variant="secondary" onClick={() => switchMode('reading')}><Check /> Done</Button>
            ) : null}
            <Button onClick={() => void startJob('GENERATE')} disabled={job?.status === 'RUNNING'}>
              {job && ['QUEUED', 'RUNNING'].includes(job.status) ? <LoaderCircle className="animate-spin" /> : <Sparkles />}
              Generate
            </Button>
            </>
          ) : (
            <Button variant="secondary" onClick={() => switchMode('reading')}><Check /> Done</Button>
          )}
          {job && ['QUEUED', 'RUNNING'].includes(job.status) ? (
            <Button size="icon" variant="ghost" aria-label="取消当前任务" onClick={() => void studioApi.cancelJob(job.job_id).then(setJob)}>⏹</Button>
          ) : null}
        </div>
      </header>
      {historyWarning ? <output className="status-banner">{historyWarning}</output> : null}

      {reviewResult ? <section className="stale-banner" aria-label="本次全文检查状态" aria-live="polite">
        <p>{reviewResult.semantic_status === 'AVAILABLE' ? '规则与模型检查已完成；检查意见仍需作者判断。' : '模型检查未完成，规则结果已保留。可以重新检查。'}</p>
        {reviewResult.generated_version_id !== workspace.active_generated_version_id ? <p>本次检查属于保留的历史成文，当前新成文尚未完成这次检查。</p> : null}
        <details><summary>查看检查依据</summary><p>作者输入修订：{typeof reviewResult.author_input_revision === 'number' ? reviewResult.author_input_revision : '历史记录未知'}；实际模型：{reviewResult.model_contract && typeof reviewResult.model_contract === 'object' && typeof (reviewResult.model_contract as Record<string, unknown>).actual_model === 'string' ? String((reviewResult.model_contract as Record<string, unknown>).actual_model) : '未记录'}</p></details>
      </section> : null}

      <nav className="studio-subbar" aria-label="稿件视图">
        <Button variant="outline" size="sm" aria-label={`返回 ${backLabel}`} onClick={() => void requestExit()}>
          <ArrowLeft /> {backLabel}
        </Button>
        <div className="stage-strip" aria-label="Paper workflow stage">
          {STAGE_LABELS.map(([value, label]) => (
            <span key={value} className={value === stage ? 'stage-pill stage-pill--active' : 'stage-pill'}>
              {label}
            </span>
          ))}
        </div>
        <div className="view-switch" aria-label="稿件内容视图">
          <button className={viewMode === 'structure' ? 'active' : ''} onClick={() => switchMode('structure')}>🧩 结构</button>
          <button className={viewMode === 'reading' ? 'active' : ''} onClick={() => switchMode('reading')}>📄 成文</button>
          <button className={viewMode === 'revision' ? 'active' : ''} onClick={() => switchMode('revision')}>✍️ Revision</button>
        </div>
        <div className="panel-switches" aria-label="面板显示">
          <Button variant={showLeft ? 'secondary' : 'ghost'} size="icon" aria-label="显示或隐藏左侧样本" onClick={() => setShowLeft((value) => !value)}>
            <PanelLeft />
            {showLeft ? <span className="panel-dot" /> : null}
          </Button>
          <Button variant={showRight ? 'secondary' : 'ghost'} size="icon" aria-label="显示或隐藏右侧资料" onClick={() => setShowRight((value) => !value)}>
            <PanelRight />
            {showRight ? <span className="panel-dot" /> : null}
          </Button>
        </div>
        {workspace.generated_is_stale ? <span className="ml-auto text-xs font-medium text-amber-700">结构已变化 · 旧成文保留</span> : null}
      </nav>

      {statusMessage ? (
        <div className="status-banner" role="alert">
          <CircleAlert />
          <div>
            <span>{statusMessage}</span>
            {jobIssues.length ? (
              <div className="issue-links">
                {jobIssues.map((issue) => <button key={`${issue.path}-${issue.message}`} type="button" onClick={() => focusBlock(issue.path)}>↳ {issue.path}</button>)}
              </div>
            ) : null}
          </div>
          {saveState === 'conflict' || saveState === 'recovery' ? (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => void refreshWorkspace().catch((caught) => setStatusMessage(caught instanceof Error ? caught.message : '服务器版本读取失败'))}>重新载入服务器版本</Button>
              {dirtyRef.current ? <>
                <Button size="sm" variant="outline" onClick={() => exportLocalDraft(pendingSnapshot())}>导出当前本地副本</Button>
                <Button size="sm" variant="outline" onClick={() => void studioApi.workspace(workspace.manuscript.manuscript_id).then(setRebaseConfirmation).catch((caught) => setStatusMessage(caught instanceof Error ? caught.message : '服务器版本读取失败'))}>核对后继续本地编辑</Button>
              </> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {invalidCommentIds.length ? (
        <div className="status-banner" role="alert">
          <p>待同步修改有 {invalidCommentIds.length} 条意见关联已失效。解除关联会保留全部稿件内容和原意见历史。</p>
          <Button size="sm" variant="outline" onClick={() => {
            pendingCommentIdsRef.current = pendingCommentIdsRef.current.filter((id) => !invalidCommentIds.includes(id));
            operationIdRef.current = uid('operation');
            setInvalidCommentIds([]);
            persistDraft();
            setSaveState(conflictRef.current ? draftViewRef.current ? 'recovery' : 'conflict' : 'pending');
          }}>确认解除失效关联</Button>
        </div>
      ) : null}

      {localDrafts.length ? (
        <details className="local-drafts" open={saveState === 'conflict' || saveState === 'recovery'}>
          <summary>未同步的本地副本（{localDrafts.length}）</summary>
          <p>每份副本保留完整结构、引用决定及意见关联。查看或导出不会替换服务器稿件。</p>
          {localDrafts.map((draft) => (
            <div key={draft.draftKey || draft.operationId} className="flex flex-wrap items-center gap-2 py-1">
              <span>基于 v{draft.baseRevision}，{new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(draft.queuedAt))}</span>
              <Button size="sm" variant="outline" onClick={() => void openLocalDraft(draft)}>查看本地副本</Button>
              <Button size="sm" variant="ghost" onClick={() => exportLocalDraft(draft)}>导出此副本</Button>
            </div>
          ))}
        </details>
      ) : null}

      {rebaseConfirmation ? (
        <section className="local-drafts" aria-label="核对本地与服务器版本">
          <p>本地副本基于 v{draftBaseRef.current}；服务器当前为 v{rebaseConfirmation.document_revision}。
            确认后，会以本地结构和引用决定继续编辑并保存。服务器现有内容仍保留在修改历史中。</p>
          <details><summary>查看两份内容与引用决定</summary>
            <div className="draft-comparison">
              <div><label htmlFor="local-draft-preview">本地副本</label><Textarea id="local-draft-preview" aria-label="待恢复本地内容" readOnly value={draftPreview(document)} /></div>
              <div><label htmlFor="server-draft-preview">服务器版本</label><Textarea id="server-draft-preview" aria-label="当前服务器内容" readOnly value={draftPreview(rebaseConfirmation.document)} /></div>
            </div>
          </details>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => setRebaseConfirmation(null)}>取消，保留两份内容</Button>
            <Button size="sm" disabled={invalidCommentIds.length > 0} onClick={async () => {
              try {
                const fresh = await studioApi.workspace(workspace.manuscript.manuscript_id);
                if (fresh.document_revision !== rebaseConfirmation.document_revision) {
                  setRebaseConfirmation(fresh);
                  setStatusMessage('服务器又有新修改。已更新对照，请重新核对。');
                  return;
                }
                revisionRef.current = fresh.document_revision;
                draftBaseRef.current = fresh.document_revision;
                setRevision(fresh.document_revision);
                conflictRef.current = false;
                draftViewRef.current = false;
                dirtyRef.current = true;
                operationIdRef.current = uid('operation');
                persistDraft();
                setRebaseConfirmation(null);
                setSaveState('pending');
                setStatusMessage('已确认使用本地副本继续编辑，正在保存。');
              } catch (caught) {
                setStatusMessage(caught instanceof Error ? caught.message : '核对失败，两份内容均保留。');
              }
            }}>确认以本地副本继续编辑</Button>
          </div>
        </section>
      ) : null}

      {showLeaveGuard ? (
        <div className="status-banner" role="alert">
          <p>修改仍待同步。你可以留在这里重试，或确认保留本地副本后返回。</p>
          <Button size="sm" onClick={() => setShowLeaveGuard(false)}>留在此页</Button>
          <Button size="sm" variant="outline" onClick={async () => {
            try {
              await outbox.put(pendingSnapshot());
              onExit();
            } catch {
              setStatusMessage('本地副本保存失败，请留在此页或先导出内容。');
            }
          }}>保留本地副本并返回</Button>
        </div>
      ) : null}

      <StudioTemplateAdoption key={workspace.manuscript.manuscript_id} manuscriptId={workspace.manuscript.manuscript_id}
        candidate={templateCandidate} onClose={() => setTemplateCandidate(null)} onApply={applyReviewedTemplate} />
      {comments.length || activeCommentIds.length ? (
        <div className="revision-context" aria-label="当前意见关联">
          <div aria-live="polite">
            <strong>{activeCommentIds.length ? '正在回应' : '普通编辑'}</strong>
            {activeCommentIds.length ? activeCommentIds.map((id) => {
              const comment = comments.find((item) => item.comment_id === id);
              if (!comment) return null;
              return <Button key={id} size="sm" variant="secondary" title={comment.edited_text}
                aria-label={`解除关联 ${commentLabel(comment)}`}
                onClick={() => void changeCommentContext(activeCommentIds.filter((item) => item !== id))}>
                {commentLabel(comment)} · 移除
              </Button>;
            }) : <span>后续修改不关联审稿意见</span>}
          </div>
          <Popover>
            <PopoverTrigger className="revision-context-trigger">关联意见</PopoverTrigger>
            <PopoverContent className="max-h-80 overflow-y-auto">
              <PopoverHeader><PopoverTitle>选择回应的意见</PopoverTitle></PopoverHeader>
              {comments.map((comment) => (
                <label key={comment.comment_id} className="revision-context-option">
                  <Checkbox checked={activeCommentIds.includes(comment.comment_id)}
                    onCheckedChange={(checked) => void changeCommentContext(checked
                      ? [...activeCommentIds, comment.comment_id]
                      : activeCommentIds.filter((id) => id !== comment.comment_id))} />
                  <span><strong>{commentLabel(comment)}</strong> {comment.edited_text}</span>
                </label>
              ))}
            </PopoverContent>
          </Popover>
          {activeCommentIds.length ? <Button size="sm" variant="ghost"
            onClick={() => void changeCommentContext([])}>结束本次关联</Button> : null}
        </div>
      ) : null}

      <DndContext sensors={sensors} collisionDetection={sameLayerClosestCenter} onDragEnd={onDragEnd}>
      <div className={`studio-grid ${showLeft ? '' : 'studio-grid--no-left'} ${showRight ? '' : 'studio-grid--no-right'}`}>
        {showLeft ? (
          <aside className="studio-panel studio-panel--left">
            <div className="panel-heading">
              <span><BookCopy /> Skeleton / Samples</span>
              <small>{selection.label}</small>
            </div>
            <p className="panel-guidance">拖入结构，或点击采用 · 内容仍由作者填写</p>
            {samples.length ? (
              <div className="sample-card">
                <div className="sample-meta"><span>{sampleIndex + 1} / {samples.length}</span><span>{samples[sampleIndex]?.layer4 || selection.type}</span></div>
                <blockquote>{samples[sampleIndex]?.raw_text}</blockquote>
                <p>{samples[sampleIndex]?.title}</p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setSampleIndex((value) => (value - 1 + samples.length) % samples.length)}>←</Button>
                  <Button size="sm" variant="outline" onClick={() => setSampleIndex((value) => (value + 1) % samples.length)}>→</Button>
                  <Button size="sm" variant="outline" onClick={() => void adoptCurrentSample()}>＋ 预览完整模板</Button>
                </div>
                {samples[sampleIndex] ? <TemplateDragHandle sample={samples[sampleIndex]} disabled={viewMode !== 'structure'} /> : null}
                <p className="text-xs">放到整篇入口，或章节、段落、Intent 后方；先预览，确认后再采用。</p>
              </div>
            ) : (
              <p className="panel-empty">这个层级暂时没有可追溯的相似样本。</p>
            )}
          </aside>
        ) : null}

        <section className="studio-canvas" ref={canvasRef} onScroll={(event) => {
          if (!viewReady) return;
          viewScrollRef.current[viewMode] = event.currentTarget.scrollTop;
          try {
            window.localStorage.setItem(`${viewStateKey}-scroll`, JSON.stringify(viewScrollRef.current));
          } catch {
            // Scroll position is optional; manuscript save failures are reported separately.
          }
        }}>
          {readingVersionId ? <div className="status-banner"><span>正在查看原讨论固定的成文版本，当前稿件仍保留。</span><Button size="sm" variant="outline" onClick={closeSourceLocation}>返回当前成文</Button></div> : null}
          {viewMode === 'structure' ? (
            <StructureEditor
              document={document}
              selection={selection}
              setSelection={(value) => { setSelection(value); if (value.quote) setChatOpen(true); }}
              commit={commit}
              editorUi={{ document, folded: foldedIds, toggleFold: (id) => setFoldedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]), selectBlock: (id) => { const target = documentSelection(documentRef.current, id); if (target) setSelection(target); }, unfold: unfoldBlocks, direction: railDirection, setDirection: setRailDirection, commit }}
              assets={workspace.assets}
              onUpload={async (paragraphId, file) => {
                try {
                  const asset = await studioApi.uploadAsset(workspace.manuscript.manuscript_id, file);
                  setWorkspace((current) => ({ ...current, assets: [...current.assets, asset] }));
                  commit((draft) => {
                    for (const section of draft.sections) {
                      const paragraph = section.paragraphs.find((item) => item.id === paragraphId);
                      if (paragraph && !paragraph.asset_ids.includes(asset.asset_id)) paragraph.asset_ids.push(asset.asset_id);
                    }
                  }, 'ATTACH_ASSET');
                } catch (caught) {
                  setStatusMessage(caught instanceof Error ? caught.message : '附件导入失败');
                }
              }}
            />
          ) : viewMode === 'reading' ? (
            <ReadingView
              manuscriptId={workspace.manuscript.manuscript_id}
              content={generatedContent}
              generated={generatedVersion}
              selectedAnchor={selection.id}
              stale={workspace.generated_is_stale}
              artifacts={generatedVersion?.artifacts || []}
              packageDownloads={<StudioPackageDownloads key={workspace.manuscript.manuscript_id} manuscriptId={workspace.manuscript.manuscript_id} activeVersionId={workspace.active_generated_version_id} refreshKey={`${workspace.latest_job?.job_id}:${workspace.latest_job?.status}`} />}
              submissions={workspace.manuscript.submissions || []}
              publicationFiles={workspace.assets.filter((item) => item.asset_kind === 'DOCUMENT')}
              defaultVenue={document.venue}
              findings={workspace.findings.filter(
                (item) => item.generated_version_id === workspace.active_generated_version_id,
              )}
              onEdit={() => switchMode('structure')}
              onDiscuss={discussGenerated}
              onEditObject={editGeneratedObject}
              onReview={() => void startJob('WHOLE_PAPER_REVIEW')}
              onPackage={() => void startJob('SUBMISSION_PACKAGE')}
              onWorkspaceRefresh={refreshWorkspace}
              onArchiveFile={async (file) => {
                try {
                  const asset = await studioApi.uploadAsset(workspace.manuscript.manuscript_id, file);
                  setWorkspace((current) => ({
                    ...current,
                    assets: current.assets.some((item) => item.asset_id === asset.asset_id)
                      ? current.assets
                      : [...current.assets, asset],
                  }));
                } catch (caught) {
                  setStatusMessage(caught instanceof Error ? caught.message : '出版文件归档失败');
                }
              }}
              onCitation={openGeneratedSource}
              onFindingStatus={async (findingId, findingStatus) => {
                try {
                  await studioApi.updateFinding(findingId, findingStatus);
                  await refreshWorkspace();
                } catch (caught) {
                  setStatusMessage(caught instanceof Error ? caught.message : '检查项更新失败');
                }
              }}
              onFindingLocate={focusFinding}
              onStage={async (nextStage) => {
                try {
                  const next = await studioApi.setStage(workspace.manuscript.manuscript_id, nextStage, workspace.manuscript.revision, `Author moved paper to ${nextStage}`);
                  setWorkspace(next);
                  if (nextStage === 'REVISION') switchMode('revision');
                } catch (caught) {
                  setStatusMessage(caught instanceof Error ? caught.message : '阶段更新失败');
                }
              }}
              stage={stage}
            />
          ) : (
            <RevisionView
              manuscriptId={workspace.manuscript.manuscript_id}
              comments={(showArchived ? archivedComments : comments).filter((item) => item.review_round_id === reviewRoundId)}
              archived={showArchived}
              activeCommentIds={activeCommentIds}
              onChangeContext={changeCommentContext}
              onArchive={archiveComment}
              existingComments={[...comments, ...archivedComments]}
              changeHistory={<StudioChangeHistory key={workspace.manuscript.manuscript_id} manuscriptId={workspace.manuscript.manuscript_id} savedRevision={workspace.document_revision} comments={[...comments, ...archivedComments]} focusedChange={focusedChange} onReload={loadComments} onError={setStatusMessage} />}
              packageDownloads={<StudioPackageDownloads key={workspace.manuscript.manuscript_id} manuscriptId={workspace.manuscript.manuscript_id} activeVersionId={workspace.active_generated_version_id} selectedRoundId={reviewRoundId} refreshKey={`${workspace.latest_job?.job_id}:${workspace.latest_job?.status}`} />}
              onShowChange={(id) => setFocusedChange({ id })}
              showArchived={showArchived}
              setShowArchived={setShowArchived}
              commentDraft={commentDraft}
              setCommentDraft={setCommentDraft}
              reviewRoundId={reviewRoundId}
              roundPicker={(disabled) => <StudioReviewRounds rounds={reviewRounds} selectedId={reviewRoundId} versions={workspace.manuscript.versions} activeVersionId={workspace.active_generated_version_id} venue={document.venue} disabled={disabled} onSelect={async (id) => { if (await changeCommentContext([])) setReviewRoundId(id); else throw new Error('当前修改尚未保存，暂不切换轮次。'); }} onCreate={async (number, versionId, venue) => {
                await flushSave();
                if (dirtyRef.current) throw new Error('当前修改尚未保存，暂不能固定被审版本。');
                if (!(await changeCommentContext([]))) throw new Error('原意见上下文尚未结束。');
                const row = await studioApi.createReviewRound(workspace.manuscript.manuscript_id, number, venue, versionId, revisionRef.current);
                setReviewRoundId(row.review_round_id);
                await loadComments();
              }} onError={setStatusMessage} />}
              onEnsureRound={async () => {
                if (reviewRoundId) return reviewRoundId;
                throw new Error('请先选择真实被审稿，明确建立返修轮次。预览和原文仍保留。');
              }}
              onReload={loadComments}
              onEditStructure={() => switchMode('structure')}
              onPackage={() => void startJob('SUBMISSION_PACKAGE')}
              onError={setStatusMessage}
            />
          )}
        </section>

        {showRight ? (
          <aside className="studio-panel studio-panel--right">
            <div className="panel-heading"><span><LibraryBig /> FieldKG / Evidence</span><small>真实资料</small></div>
            <div className="source-search"><Search /><Input value={sourceQuery} onChange={(event) => setSourceQuery(event.target.value)} placeholder="找资料、依据、反证…" /></div>
            <div className="source-list">
              {pinnedReference ? <section className="source-card source-card--snapshot" aria-label="此生成版本的固定引用来源">
                <header><strong>[{pinnedReference.citation_index}] {pinnedReference.title || pinnedReference.statement || '未提供题名'}</strong>
                  <Button size="sm" variant="ghost" onClick={() => { sourcePreviewRequestRef.current += 1; setPinnedReference(null); setPinnedReferenceVersion(null); }}>关闭来源</Button></header>
                <p>{pinnedReference.authors?.join(', ')} {pinnedReference.published_year || ''}</p>
                <p>{pinnedReference.statement}</p><blockquote>{pinnedReference.excerpt}</blockquote>
                <small>此版本的来源快照{pinnedReference.source_snapshot_available ? '' : ' · 历史来源资料不完整'}</small>
                {pinnedReferenceVersion ? <><p>固定于成文 v{pinnedReferenceVersion.version}</p><StudioSourceContext reference={pinnedReference} manuscriptId={pinnedReferenceVersion.manuscriptId} versionId={pinnedReferenceVersion.id} /></> : null}
                {pinnedReference.landing_url || pinnedReference.doi ? <a target="_blank" rel="noreferrer" href={pinnedReference.landing_url || `https://doi.org/${pinnedReference.doi}`}>题录网页 ↗</a> : null}
              </section> : null}
              {sources.map((source) => (
                <article
                  key={source.evidence_id}
                  className="source-card"
                >
                  <button
                    type="button"
                    className="source-card__action"
                    draggable
                    aria-label={`将证据加入当前思想：${source.statement}`}
                    onClick={() => addSourceToSelectedThought(source)}
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = 'copy';
                      event.dataTransfer.setData('application/x-rstv4-evidence', JSON.stringify(source));
                    }}
                  >
                    <span className="source-card__top"><span>{source.relation}</span><span>{Math.round(source.confidence * 100)}%</span></span>
                    <strong>{source.statement}</strong>
                    <span className="source-card__excerpt">{source.excerpt}</span>
                  </button>
                  <footer>
                    <span>{source.title || '未提供题名'}</span>
                    {source.landing_url || source.pdf_url ? (
                      <a href={source.pdf_url || source.landing_url} target="_blank" rel="noreferrer">查看原文 ↗</a>
                    ) : <span>原文不可用</span>}
                  </footer>
                </article>
              ))}
              {sources.length === 0 ? <p className="panel-empty">当前筛选没有真实 FieldKG 资料。</p> : null}
            </div>
          </aside>
        ) : null}
      </div>
      </DndContext>

      <section className={`chat-dock ${chatOpen ? 'chat-dock--open' : ''}`}>
        <button className="chat-dock__toggle" type="button" aria-expanded={chatOpen} aria-controls="studio-discussion-body" onClick={() => setChatOpen((value) => !value)}>
          <span><MessageSquareText /> 与 Agent 讨论</span>
          <span>{chat.length} 条 · {selection.label} <ChevronDown /></span>
        </button>
        {chatOpen ? (
          <div className="chat-dock__body" id="studio-discussion-body">
            <div className="chat-filterbar">
              {discussionBack ? <Button size="sm" variant="outline" onClick={async () => { await flushSave(); if (dirtyRef.current || conflictRef.current) { setStatusMessage('稿件尚未同步，请先处理本地副本后返回。'); return; } window.location.assign(discussionBack); }}>返回原讨论页面</Button> : null}
              <Button size="sm" variant={chatFilter === 'paper' ? 'secondary' : 'ghost'} onClick={() => setChatFilter('paper')}>整篇历史</Button>
              <Button size="sm" variant={chatFilter === 'selection' ? 'secondary' : 'ghost'} disabled={!selection.id} onClick={() => setChatFilter('selection')}>当前对象 · 此版本</Button>
              {chatHasMore && chat[0] ? <Button className="ml-auto" size="sm" variant="ghost" onClick={() => void loadChat(chat[0].created_at, chat[0].message_id)}>↑ 更早</Button> : null}
            </div>
            <div className="chat-history">
              {chat.map((message) => (
                <article key={message.message_id} className={`chat-message chat-message--${message.role.toLowerCase()}`}>
                  <header><span>{message.role === 'AUTHOR' ? '你' : 'Scholar'}</span><button type="button" onClick={() => void readOriginal(message.message_id)}>{messageAnchorLabel(message)}</button></header>
                  {typeof message.quoted.text === 'string' ? <blockquote>{message.quoted.text}</blockquote> : null}
                  {typeof message.quoted.annotation === 'string' && message.quoted.annotation ? <p className="chat-annotation">Annotation：{message.quoted.annotation}</p> : null}
                  <p>{message.content}</p>
                  {!message.quoted._research_discussion ? <Button size="sm" variant="ghost" onClick={() => void readOriginal(message.message_id, true)}>定位原对象</Button> : null}
                  {sharedDiscussion?.messages.filter((shared) => shared.message_id === message.message_id).map((shared) => <div key={shared.message_id} className="flex flex-wrap gap-2">
                    {[shared.context, ...shared.additional_sources.map((source) => source.context)].map((context, index) => <Button key={`${context.context_sha256}:${index}`} size="sm" variant="ghost" onClick={() => void discussionRef.current?.locateSource(shared.message_id, index, shared.scope_key)}>定位原对象 · {context.label}</Button>)}
                  </div>)}
                  {message.quoted._research_discussion ? <div className="flex flex-wrap gap-2">
                    {!sharedDiscussion?.messages.some((shared) => shared.message_id === message.message_id) ? <Button size="sm" variant="ghost" onClick={() => void discussionRef.current?.locateSource(message.message_id, 0, JSON.stringify(['STUDIO', workspace.manuscript.manuscript_id]))}>定位原对象</Button> : null}
                    {message.role === 'AGENT' || message.status === 'AGENT_FAILED' ? <Button size="sm" variant="ghost" disabled={!sharedDiscussionReady || draftBindingBusy} onClick={() => void discussionRef.current?.openHistory(message.message_id, 0, true)}>继续这段讨论</Button> : null}
                    <Button size="sm" variant="ghost" onClick={() => void discussionRef.current?.inspectCall(message.message_id)}>查看原调用记录</Button>
                  </div> : null}
                  {Array.isArray(message.quoted.evidence_ids) ? (
                    <div className="chat-evidence">
                      {(message.quoted.evidence_ids as unknown[]).filter((item): item is string => typeof item === 'string').map((evidenceId, sourceIndex) => (
                        <button key={evidenceId} type="button" aria-label={`查看此回复的第 ${sourceIndex + 1} 个引用来源`} onClick={() => void openDiscussionSource(message.message_id, evidenceId)}>📚 引用来源 {sourceIndex + 1}</button>
                      ))}
                    </div>
                  ) : null}
                  {message.role === 'AGENT' && Array.isArray(message.quoted.suggestions) && message.quoted.suggestions.length ?
                    <StudioSuggestionReview manuscriptId={workspace.manuscript.manuscript_id} messageId={message.message_id}
                      suggestions={message.quoted.suggestions as StudioSuggestion[]} prepare={prepareSuggestion}
                      commentIds={() => [...activeCommentsRef.current]}
                      decide={(request, retry) => decideSuggestion(message.message_id, request, retry)} /> : null}
                </article>
              ))}
              {chat.length === 0 ? <p className="panel-empty">讨论会固定到当前对象与版本；点击文字不会自动发送。</p> : null}
              {sharedDiscussion?.annotations.map((item) => <article key={item.annotation_id} className="chat-message">
                <strong>讨论批注 · {item.context.label} · {readableVersions(item.context)}</strong><p>{item.comment}</p>
                {item.quote.text ? <blockquote>{item.quote.text}</blockquote> : null}
                <details><summary>保存时的原文</summary><QuotedText text={item.context.object_text} quote={item.quote} /></details>
              </article>)}
              {sharedDiscussion?.nextAnnotationsBefore ? <Button size="sm" variant="ghost" onClick={() => void discussionRef.current?.loadHistory(true)}>更早的讨论批注</Button> : null}
            </div>
            {historicalContext ? <section className="chat-original" aria-label="讨论的原始版本">
              <header><strong>{historicalContext.quote.source.label}{historicalContext.generated ? ` · 成文 v${historicalContext.generated.version}` : ''} · {historicalContext.quote.source.author_revision_known === false ? '结构版本未知' : `结构 r${historicalContext.quote.source.anchor_revision}`}</strong><Button size="sm" variant="ghost" onClick={() => legacyLocated ? closeSourceLocation() : setHistoricalContext(null)}>关闭原文</Button></header>
              <p>只读原文；当前结构保留。</p>
              <p>原问题与回复保持原记录；选用这条来源会使用保存的版本和选区。</p>
              <Button size="sm" variant="ghost" onClick={() => void readOriginal(historicalContext.message_id, true)}>定位原对象</Button>
              <Button size="sm" variant="outline" disabled={!sharedDiscussionReady || !!sharedDiscussion?.pending} onClick={() => void chooseOriginalSource()}>选用这条原来源</Button>
              <QuotedText text={historicalContext.quote.object_text} quote={historicalContext.quote} />
            </section> : null}
            {locatedSource ? <section className="chat-original" aria-label="定位的历史原文与选区">
              <header><strong>{locatedSource.source.context.label} · {readableVersions(locatedSource.source.context)}</strong><Button size="sm" variant="ghost" onClick={closeSourceLocation}>关闭原来源定位</Button></header>
              <p>{locatedSource.source.current_source_state === 'OLD_VERSION' ? '这是旧版本原文；当前内容保留。' : locatedSource.source.current_source_state === 'SOURCE_UNAVAILABLE' ? '当前对象已不可用；当时原文与选区保留。' : '已定位原对象；当时原文只读。'}</p>
              <QuotedText text={locatedSource.source.context.object_text} quote={locatedSource.source.quote} />
            </section> : null}
            <div className="chat-context" aria-live="polite">
              <span>当前选择：{selection.label}</span>
              {selection.quote?.text ? <blockquote>{selection.quote.text}</blockquote> : null}
              {sharedDiscussion?.bound ? <strong>草稿对象：{sharedDiscussion.bound.context.label} · {readableVersions(sharedDiscussion.bound.context)}</strong> : null}
              {!sharedDiscussion?.bound && draftContext ? <strong>原草稿对象：{draftContext.label} · 原来源尚未核实，文字与选区保留</strong> : null}
              {sharedDiscussion?.bound?.current_source_state === 'OLD_VERSION' ? <span>对象已有新版本，当前仍引用历史原文。</span> : null}
              {sharedDiscussion?.bound?.current_source_state === 'SOURCE_UNAVAILABLE' ? <span>当前对象已不可用，历史原文仍保留。</span> : null}
              {draftContext?.quote?.text ? <blockquote>草稿引用：{draftContext.quote.text}</blockquote> : null}
              {draftContext?.quote?.text ? <Button size="sm" variant="ghost" disabled={!!sharedDiscussion?.pending || draftBindingBusy} onClick={() => discussionRef.current?.selectQuote(null)}>移除草稿选区（保留对象）</Button> : null}
              {(chatDraft || annotation) && (!draftContext || draftContext.id !== selection.id || draftContext.quote?.text !== selection.quote?.text) ? <span>点击其他对象保留草稿原对象。</span> : null}
              <Button size="sm" variant="ghost" disabled={!sharedDiscussionReady || !!sharedDiscussion?.pending || draftBindingBusy} onClick={() => void bindDraft()}>将草稿绑定到当前对象／选区</Button>
              <label htmlFor="studio-discussion-pin" className="flex items-center gap-2 text-sm"><Checkbox id="studio-discussion-pin" checked={sharedDiscussion?.pinned || false} disabled={!sharedDiscussionReady || !!sharedDiscussion?.pending || draftBindingBusy} onCheckedChange={(value) => discussionRef.current?.edit('pinned', value === true)} />固定当前讨论对象</label>
            </div>
            {sharedDiscussion?.proposed ? <section className="chat-original" aria-label="比较新选对象与原草稿">
              <p>新选：{sharedDiscussion.proposed.bound.context.label} · {readableVersions(sharedDiscussion.proposed.bound.context)}。当前问题仍绑定原对象。</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => discussionRef.current?.compare('keep')}>保留并固定原对象</Button>
                <Button size="sm" variant="outline" onClick={() => discussionRef.current?.compare('use')}>改用新对象并保留问题</Button>
                <Button size="sm" variant="outline" disabled={!!sharedDiscussion.pending} onClick={() => discussionRef.current?.compare('add')}>加入比较来源</Button>
              </div>
            </section> : null}
            {sharedDiscussion?.bound ? <details className="chat-original"><summary>固定对象的完整原文与版本</summary><p>{readableVersions(sharedDiscussion.bound.context)}</p><QuotedText text={sharedDiscussion.bound.context.object_text} quote={sharedDiscussion.quote || {}} /></details> : null}
            {sharedDiscussion?.extra.map((item, index) => <section className="chat-original" key={`${item.bound.context.context_sha256}:${index}`}>
              <p>比较来源：{item.bound.context.label} · {readableVersions(item.bound.context)}</p>
              {item.quote?.text ? <blockquote>{item.quote.text}</blockquote> : null}
              <Button size="sm" variant="ghost" disabled={!!sharedDiscussion.pending} onClick={() => discussionRef.current?.removeSource(index)}>移除此来源</Button>
            </section>)}
            {sharedDiscussion && (sharedDiscussion.extra.length > 0 || sharedDiscussion.parent) ? <label htmlFor="studio-discussion-cross" className="flex items-center gap-2 text-sm"><Checkbox id="studio-discussion-cross" checked={sharedDiscussion.allowCrossScope} disabled={!!sharedDiscussion.pending} onCheckedChange={(value) => discussionRef.current?.edit('allowCrossScope', value === true)} />明确允许比较不同研究范围的固定来源</label> : null}
            {sharedDiscussion?.parent ? <section className="chat-original" aria-label="本轮讨论的历史上下文">
              <p>继续这段讨论 · {sharedDiscussion.parent.conversation.length} 条历史消息 <Button size="sm" variant="ghost" disabled={!!sharedDiscussion.pending} onClick={() => discussionRef.current?.startNew()}>开始新讨论</Button></p>
              <details><summary>本轮会带入的问题、回复与固定来源</summary>{sharedDiscussion.parent.conversation.map((message) => <article key={message.message_id}>
                <strong>{message.actor === 'AUTHOR' ? '你' : 'Scholar · 讨论意见'}</strong><p>{message.content}</p>
                {[message.context, ...message.additional_sources.map((source) => source.context)].map((context, index) => <details key={`${context.context_sha256}:${index}`}><summary>{context.label} · {readableVersions(context)}</summary><QuotedText text={context.object_text} quote={index === 0 ? message.quote : message.additional_sources[index - 1].quote} /></details>)}
              </article>)}</details>
            </section> : null}
            <output className="block text-sm" aria-live="polite">{sharedDiscussionReady ? sharedDiscussion?.status : '正在恢复原讨论草稿…'}</output>
            <div className="chat-compose">
              <Textarea aria-label="讨论草稿" disabled={!sharedDiscussionReady || chatBusy || !!sharedDiscussion?.pending || draftBindingBusy} maxLength={12000} value={chatDraft} onChange={(event) => updateChatDraft(event.target.value)} placeholder={`讨论：${draftContext?.label || selection.label}`} />
              <Textarea aria-label="当前讨论的 annotation" disabled={!sharedDiscussionReady || chatBusy || !!sharedDiscussion?.pending || draftBindingBusy} maxLength={8000} value={annotation} onChange={(event) => discussionRef.current?.edit('annotation', event.target.value)} placeholder="Annotation（可选）" />
              <Button
                size="icon"
                aria-label="发送讨论"
                disabled={!sharedDiscussionReady || !chatDraft.trim() || chatBusy || !!sharedDiscussion?.pending || draftBindingBusy || !sharedDiscussion?.bound}
                onClick={() => void discussionRef.current?.send()}
              >
                {chatBusy ? <LoaderCircle className="animate-spin" /> : <Send />}
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={!sharedDiscussionReady || !annotation.trim() || chatBusy || !!sharedDiscussion?.pending || draftBindingBusy || !sharedDiscussion?.bound} onClick={() => void discussionRef.current?.send('ANNOTATE')}>保存讨论批注</Button>
              {sharedDiscussion?.pending ? <Button size="sm" variant="outline" disabled={chatBusy} onClick={() => void discussionRef.current?.reconcile(true)}>核对原提交</Button> : null}
              <Button size="sm" variant="ghost" onClick={() => { void loadChat(); void discussionRef.current?.loadHistory(); }}>更新讨论历史</Button>
              {sharedDiscussion?.bound?.history_request_id ? <Button size="sm" variant="ghost" onClick={() => void discussionRef.current?.inspectOrigin()}>查看原讨论与调用记录</Button> : null}
            </div>
            {sharedDiscussion?.receipt?.job ? <p className="text-xs">回复状态：{sharedDiscussion.receipt.job.status} · 实际模型：{sharedDiscussion.receipt.job.model_contract?.actual_model || '未记录'} · 契约：{sharedDiscussion.receipt.job.model_contract?.prompt_version || '未记录'}</p> : null}
            {sharedDiscussion?.inspectedReceipt ? <details className="chat-original"><summary>原调用记录：固定输入、实际响应与错误</summary><pre className="whitespace-pre-wrap break-words">{JSON.stringify(sharedDiscussion.inspectedReceipt, null, 2)}</pre></details> : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}

function StructureEditor({
  document,
  selection,
  setSelection,
  commit,
  assets,
  onUpload,
  editorUi,
}: {
  document: StudioDocument;
  selection: Selection;
  setSelection: (selection: Selection) => void;
  commit: (change: (draft: StudioDocument) => void, operationKind?: string) => void;
  assets: Workspace['assets'];
  onUpload: (paragraphId: string, file: File) => Promise<void>;
  editorUi: EditorUi;
}) {
  return (
      <EditorControls ui={editorUi}>
      <SortableContext items={document.sections.map((item) => item.id)} strategy={verticalListSortingStrategy}>
        <div className="paper-sheet" data-rail-direction={editorUi.direction}>
          <Input
            className="paper-title"
            value={document.title}
            onFocus={() => setSelection({ type: 'paper', label: document.title })}
            onChange={(event) => commit((draft) => { draft.title = event.target.value; })}
            aria-label="Paper title"
          />
          <Textarea
            className="paper-abstract"
            value={document.abstract}
            aria-label="作者摘要"
            onFocus={() => setSelection({ type: 'paper', label: document.title })}
            onChange={(event) => commit((draft) => { draft.abstract = event.target.value; })}
            placeholder="Abstract 可以现在写，也可以先留到结构完整后补。"
          />
          <DropZone target={{ kind: 'paper', id: document.manuscript_id, placement: 'inside' }} empty={!document.sections.length} />
          {document.sections.map((section, sectionIndex) => ancestors(document,section.id).some((id) => editorUi.folded.includes(id)) ? null : (
            <SectionEditor
              key={section.id}
              section={section}
              sectionIndex={sectionIndex}
              selectedId={selection.id}
              setSelection={setSelection}
              commit={commit}
              assets={assets}
              onUpload={onUpload}
            />
          ))}
          <Button
            variant="outline"
            onClick={() =>
              commit((draft) => {
                draft.sections.push({
                  id: uid('section'),
                  title: 'New section',
                  role: '',
                  paragraphs: [],
                });
              }, 'ADD_SECTION')
            }
          >
            <Plus /> 添加章节
          </Button>
        </div>
      </SortableContext>
      </EditorControls>
  );
}

function BlockRail({ kind, label, compact, onSelect, children }: {
  kind: string; label: string; compact: string; onSelect: () => void; children: ReactNode;
}) {
  const ui = useEditorControls();
  return <Popover>
    <PopoverTrigger className={`vertical-rail vertical-rail--${kind}`} aria-label={`选择并设置 ${label}`} onClick={onSelect}>{compact}</PopoverTrigger>
    <PopoverContent side="right" className="w-80 max-w-[calc(100vw-2rem)]">
      <PopoverHeader><PopoverTitle className="break-words">{label}</PopoverTitle></PopoverHeader>
      <div className="grid gap-2">{children}
        <label className="grid gap-1 text-sm">侧边标签方向
          <select value={ui.direction} onChange={(event) => ui.setDirection(event.target.value as EditorUi['direction'])}>
            <option value="upright">直排，文字正立</option><option value="rotated">直排，文字旋转</option><option value="horizontal">横排</option>
          </select>
        </label>
      </div>
    </PopoverContent>
  </Popover>;
}

function SectionEditor({
  section,
  sectionIndex,
  selectedId,
  setSelection,
  commit,
  assets,
  onUpload,
}: {
  section: SectionBlock;
  sectionIndex: number;
  selectedId?: string;
  setSelection: (selection: Selection) => void;
  commit: (change: (draft: StudioDocument) => void, operationKind?: string) => void;
  assets: Workspace['assets'];
  onUpload: (paragraphId: string, file: File) => Promise<void>;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: section.id,
    data: { type: 'section' },
  });
  const ui = useEditorControls();
  const folded = ui.folded.includes(section.id);
  const depth = sectionDepth(ui.document,section.id);
  const childCount = sectionEnd(ui.document.sections,sectionIndex) - sectionIndex - 1;
  const select = () => setSelection({ type: 'section', id: section.id, label: section.title, role: section.role });
  const title = <Input aria-label="章节标题" value={section.title} onFocus={select} onChange={(event) => commit((draft) => { draft.sections[sectionIndex].title = event.target.value; })} />;
  const role = <Input aria-label="章节作用" value={section.role} placeholder="章节作用" onFocus={select} onChange={(event) => commit((draft) => { draft.sections[sectionIndex].role = event.target.value; })} />;
  return (
    <>
    <DropZone target={{ kind: 'section', id: section.id, placement: 'before' }} />
    <section
      ref={setNodeRef}
      data-block-id={section.id}
      style={{ transform: CSS.Transform.toString(transform), transition, ...(depth ? { marginLeft:depth*18, width:`calc(100% - ${depth*18}px)` } : {}) }}
      className={`structure-section ${selectedId === section.id ? 'selected-block' : ''} ${isDragging ? 'block-dragging' : ''}`}
    >
      <BlockRail kind="section" label={section.title || '未定章节'} compact={`${depth ? 'SUBSECTION' : 'SECTION'} ${sectionIndex + 1}`} onSelect={select}>{title}{role}
        <label>父章节<select aria-label="父章节" value={section.parent_section_id || ''} onChange={(event) => commit((draft) => {
          Object.assign(draft,moveBlocks(draft,[section.id],{kind:event.target.value ? 'section' : 'paper',id:event.target.value || draft.manuscript_id,placement:'inside'}));
        },'REPARENT_SECTION')}>
          <option value="">整篇论文（主章节）</option>
          {ui.document.sections.filter((item) => canMove(ui.document,[section.id],{kind:'section',id:item.id,placement:'inside'})).map((item) => <option key={item.id} value={item.id}>{sectionBreadcrumb(ui.document,item.id)}</option>)}
        </select></label>
      </BlockRail>
      <div className="structure-content">
        {section.placement_status === 'UNPLACED' ? <div className="status-banner" aria-label="待安置的原内容">
          <output><strong>待安置</strong> · 原内容、引用与编号完整保留。可将内容移入模板；未安置时不能生成成文。</output>
          <StudioOriginalPlacement sectionId={section.id} />
          <StudioIntentCorrespondence sectionId={section.id} />
          <Button size="sm" variant="outline" onClick={() => commit((draft) => {
            for (const item of draft.sections.slice(sectionIndex,sectionEnd(draft.sections,sectionIndex))) delete item.placement_status;
          }, 'PLACE_ORIGINAL_SECTION')}>将此章节标记为已安置</Button>
        </div> : null}
        <div className="section-heading-row">
          <BlockControls id={section.id} kind="section" label={section.title || '未定章节'}><button type="button" className="block-drag-handle" aria-label={`拖动章节 ${section.title}`} {...attributes} {...listeners} onKeyDown={(event) => { if (event.key === 'Delete') { event.preventDefault(); commit((draft) => deleteSectionTree(draft,section.id), 'DELETE_SECTION_TREE'); } else listeners?.onKeyDown?.(event); }}><GripVertical /></button></BlockControls>
          {depth ? <span className="text-xs" aria-label="子章节所属父章节">子章节 · {sectionBreadcrumb(ui.document,section.id)}</span> : null}
          <Input
            aria-label="章节标题"
            value={section.title}
            className="section-title-input"
            onFocus={() => setSelection({ type: 'section', id: section.id, label: section.title, role: section.role })}
            onChange={(event) => commit((draft) => { draft.sections[sectionIndex].title = event.target.value; })}
          />
          <Input
            aria-label="章节作用"
            value={section.role}
            className="role-input"
            placeholder="章节作用"
            onFocus={select}
            onChange={(event) => commit((draft) => { draft.sections[sectionIndex].role = event.target.value; })}
          />
          <details className="block-menu"><summary aria-label="章节操作">•••</summary><BlockMove id={section.id} /><button type="button" onClick={() => commit((draft) => {
            const target = draft.sections[sectionIndex];
            target.block_order ||= target.paragraphs.map((item) => item.id);
            target.paragraph_groups ||= [];
            const id = uid('paragraph_group');
            target.paragraph_groups.push({ id, label: '', paragraph_ids: [] });
            target.block_order.push(id);
          }, 'ADD_PARAGRAPH_GROUP')}>添加空段落组</button><button type="button" onClick={() => commit((draft) => deleteSectionTree(draft,section.id), 'DELETE_SECTION_TREE')}><Trash2 /> 删除章节与子项</button></details>
        </div>
        <div id={`body-${section.id}`} inert={isDragging} hidden={folded}>
        <SortableContext items={section.block_order || section.paragraphs.map((item) => item.id)} strategy={verticalListSortingStrategy}>
          {(section.block_order || section.paragraphs.map((item) => item.id)).map((id) => {
            const group = section.paragraph_groups?.find((item) => item.id === id);
            if (group) return <ParagraphGroupEditor key={id} group={group} section={section} sectionIndex={sectionIndex} selectedId={selectedId} setSelection={setSelection} commit={commit} assets={assets} onUpload={onUpload} />;
            const paragraphIndex = section.paragraphs.findIndex((item) => item.id === id);
            const paragraph = section.paragraphs[paragraphIndex];
            if (!paragraph) return null;
            return (
            <ParagraphEditor
              key={paragraph.id}
              paragraph={paragraph}
              sectionIndex={sectionIndex}
              paragraphIndex={paragraphIndex}
              section={section}
              selectedId={selectedId}
              setSelection={setSelection}
              commit={commit}
              assets={assets}
              onUpload={onUpload}
            />
          ); })}
        </SortableContext>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => commit((draft) => { draft.sections[sectionIndex].paragraphs.push({ id: uid('paragraph'), purpose: '', paradigm: '', intents: [], asset_ids: [], formulas: [] }); }, 'ADD_PARAGRAPH')}
        >
          <Plus /> Paragraph
        </Button>
        <Button variant="ghost" size="sm" disabled={depth>=4} onClick={() => commit((draft) => addSubsection(draft,section.id,uid('section')),'ADD_SUBSECTION')}>＋ 子章节</Button>
        </div>
        {folded ? <p className="folded-summary">{section.paragraphs.length} 个段落 · {section.paragraph_groups?.length || 0} 个段落组 · {childCount} 个子章节</p> : null}
        <DropZone target={{ kind: 'section', id: section.id, placement: 'inside' }} empty={!section.paragraphs.length && !section.paragraph_groups?.length} />
      </div>
    </section>
    <DropZone target={{ kind: 'section', id: section.id, placement: 'after' }} />
    </>
  );
}

function ParagraphGroupEditor({ group, section, sectionIndex, selectedId, setSelection, commit, assets, onUpload }: {
  group: NonNullable<SectionBlock['paragraph_groups']>[number]; section: SectionBlock; sectionIndex: number; selectedId?: string;
  setSelection: (selection: Selection) => void; commit: EditorUi['commit']; assets: Workspace['assets']; onUpload: (id: string, file: File) => Promise<void>;
}) {
  const ui = useEditorControls();
  const folded = ui.folded.includes(group.id);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: group.id, data: { type: 'paragraph_group' } });
  const select = () => setSelection({ type: 'paragraph_group', id: group.id, label: group.label || '未定段落组', role: section.role });
  const remove = () => commit((draft) => {
    const target = draft.sections[sectionIndex];
    target.paragraphs = target.paragraphs.filter((item) => !group.paragraph_ids.includes(item.id));
    target.paragraph_groups = target.paragraph_groups?.filter((item) => item.id !== group.id);
    target.block_order = target.block_order?.filter((item) => item !== group.id);
  }, 'DELETE_PARAGRAPH_GROUP');
  const label = <Input aria-label="段落组用途" value={group.label} placeholder="段落组用途可以暂时未定" onFocus={select} onChange={(event) => commit((draft) => { draft.sections[sectionIndex].paragraph_groups!.find((item) => item.id === group.id)!.label = event.target.value; })} />;
  return <>
    <DropZone target={{ kind: 'paragraph_group', id: group.id, placement: 'before' }} />
    <div ref={setNodeRef} data-block-id={group.id} style={{ transform: CSS.Transform.toString(transform), transition }} className={`paragraph-group ${selectedId === group.id ? 'selected-block' : ''} ${isDragging ? 'block-dragging' : ''}`}>
      <BlockRail kind="group" label={group.label || '未定段落组'} compact="GROUP" onSelect={select}>{label}</BlockRail>
      <div className="paragraph-content">
        <div className="group-heading">
          <BlockControls id={group.id} kind="paragraph_group" label={group.label || '未定段落组'}><button type="button" className="block-drag-handle" aria-label={`拖动段落组 ${group.label}`} {...attributes} {...listeners} onKeyDown={(event) => { if (event.key === 'Delete') { event.preventDefault(); remove(); } else listeners?.onKeyDown?.(event); }}><GripVertical /></button></BlockControls>
          {label}
          <details className="block-menu"><summary aria-label="段落组操作">•••</summary><BlockMove id={group.id} /><Ungroup id={group.id} /><button type="button" onClick={remove}><Trash2 /> 删除组及其段落</button></details>
        </div>
        <div id={`body-${group.id}`} inert={isDragging} hidden={folded}>
          <SortableContext items={group.paragraph_ids} strategy={verticalListSortingStrategy}>
            {group.paragraph_ids.map((id) => {
              const paragraphIndex = section.paragraphs.findIndex((item) => item.id === id);
              return <ParagraphEditor key={id} paragraph={section.paragraphs[paragraphIndex]} section={section} sectionIndex={sectionIndex} paragraphIndex={paragraphIndex} selectedId={selectedId} setSelection={setSelection} commit={commit} assets={assets} onUpload={onUpload} />;
            })}
          </SortableContext>
          <Button variant="ghost" size="sm" onClick={() => commit((draft) => {
            const target = draft.sections[sectionIndex]; const id = uid('paragraph');
            target.paragraphs.push({ id, purpose: '', paradigm: '', intents: [], asset_ids: [], formulas: [] });
            target.paragraph_groups!.find((item) => item.id === group.id)!.paragraph_ids.push(id);
          }, 'ADD_PARAGRAPH')}><Plus /> 组内段落</Button>
        </div>
        {folded ? <p className="folded-summary">{group.paragraph_ids.length} 个段落</p> : null}
        <DropZone target={{ kind: 'paragraph_group', id: group.id, placement: 'inside' }} empty={!group.paragraph_ids.length} />
      </div>
    </div>
    <DropZone target={{ kind: 'paragraph_group', id: group.id, placement: 'after' }} />
  </>;
}

function ParagraphEditor({
  paragraph,
  sectionIndex,
  paragraphIndex,
  section,
  selectedId,
  setSelection,
  commit,
  assets,
  onUpload,
}: {
  paragraph: ParagraphBlock;
  sectionIndex: number;
  paragraphIndex: number;
  section: SectionBlock;
  selectedId?: string;
  setSelection: (selection: Selection) => void;
  commit: (change: (draft: StudioDocument) => void, operationKind?: string) => void;
  assets: Workspace['assets'];
  onUpload: (paragraphId: string, file: File) => Promise<void>;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: paragraph.id,
    data: { type: 'paragraph' },
  });
  const ui = useEditorControls();
  const folded = ui.folded.includes(paragraph.id);
  const select = () => setSelection({ type: 'paragraph', id: paragraph.id, label: paragraph.purpose || `Paragraph ${paragraphIndex + 1}`, role: section.role });
  return (
    <>
    <DropZone target={{ kind: 'paragraph', id: paragraph.id, placement: 'before' }} />
    <article
      ref={setNodeRef}
      data-block-id={paragraph.id}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`paragraph-block ${selectedId === paragraph.id ? 'selected-block' : ''} ${isDragging ? 'block-dragging' : ''}`}
    >
      <BlockRail kind="paragraph" label={paragraph.purpose || `Paragraph ${paragraphIndex + 1}`} compact={`P${paragraphIndex + 1}`} onSelect={select}>
        <Input aria-label="段落目的" value={paragraph.purpose} placeholder="段落目的" onChange={(event) => commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].purpose = event.target.value; })} />
        <Input aria-label="段落组织范式" value={paragraph.paradigm} placeholder="自定义组织范式" onChange={(event) => commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].paradigm = event.target.value; })} />
        <Input aria-label="L2 逻辑关系" value={paragraph.logical_relation || ''} placeholder="自定义逻辑关系" onChange={(event) => commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].logical_relation = event.target.value; })} />
        <StudioArgumentRelations paragraphId={paragraph.id} />
        {paragraph.logic ? <details><summary>模板来源的 L2 分析</summary><pre className="whitespace-pre-wrap break-words">{JSON.stringify(paragraph.logic, null, 2)}</pre></details> : null}
      </BlockRail>
      <div className="paragraph-content">
        <div className="paragraph-config">
          <BlockControls id={paragraph.id} kind="paragraph" label={paragraph.purpose || `Paragraph ${paragraphIndex + 1}`}><button type="button" className="block-drag-handle" aria-label={`拖动段落 ${paragraph.purpose || paragraphIndex + 1}`} {...attributes} {...listeners} onKeyDown={(event) => { if (event.key === 'Delete') { event.preventDefault(); commit((draft) => { draft.sections[sectionIndex].paragraphs.splice(paragraphIndex, 1); }, 'DELETE_PARAGRAPH'); } else listeners?.onKeyDown?.(event); }}><GripVertical /></button></BlockControls>
          <Input aria-label="段落目的" value={paragraph.purpose} placeholder="这个段落要完成什么？" onFocus={() => setSelection({ type: 'paragraph', id: paragraph.id, label: paragraph.purpose || `Paragraph ${paragraphIndex + 1}`, role: section.role })} onChange={(event) => commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].purpose = event.target.value; })} />
          <Input aria-label="段落组织范式" value={paragraph.paradigm} placeholder="范式：Funnel / MEAL / 自定义" onFocus={() => setSelection({ type: 'paragraph', id: paragraph.id, label: paragraph.purpose || `Paragraph ${paragraphIndex + 1}`, role: section.role })} onChange={(event) => commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].paradigm = event.target.value; })} />
          <details className="block-menu"><summary aria-label="段落操作">•••</summary><BlockMove id={paragraph.id} /><button type="button" onClick={() => commit((draft) => { draft.sections[sectionIndex].paragraphs.splice(paragraphIndex, 1); }, 'DELETE_PARAGRAPH')}><Trash2 /> 删除段落</button></details>
        </div>
        <div id={`body-${paragraph.id}`} inert={isDragging} hidden={folded}>
        <SortableContext items={paragraph.intents.map((item) => item.id)} strategy={verticalListSortingStrategy}>
          {paragraph.intents.map((intent, intentIndex) => (
            <IntentEditor
              key={intent.id}
              intent={intent}
              sectionIndex={sectionIndex}
              paragraphIndex={paragraphIndex}
              intentIndex={intentIndex}
              role={section.role}
              selectedId={selectedId}
              setSelection={setSelection}
              commit={commit}
            />
          ))}
        </SortableContext>
        {paragraph.formulas?.length ? (
          <div className="formula-list">
            {paragraph.formulas.map((formula, formulaIndex) => (
              <div key={formula.id} className="formula-row" data-block-id={formula.id}>
                <span>∑</span>
                <Input
                  value={formula.latex}
                  placeholder="LaTeX：E = mc^2"
                  aria-label={`公式 ${formulaIndex + 1}`}
                  onChange={(event) => commit((draft) => {
                    const target = draft.sections[sectionIndex].paragraphs[paragraphIndex];
                    if (!target.formulas) target.formulas = [];
                    target.formulas[formulaIndex].latex = event.target.value;
                  }, 'EDIT_FORMULA')}
                />
                <Input
                  aria-label={`公式 ${formulaIndex + 1} 的说明`}
                  value={formula.caption}
                  placeholder="公式说明（可选）"
                  onChange={(event) => commit((draft) => {
                    const target = draft.sections[sectionIndex].paragraphs[paragraphIndex];
                    if (!target.formulas) target.formulas = [];
                    target.formulas[formulaIndex].caption = event.target.value;
                  }, 'EDIT_FORMULA')}
                />
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`删除公式 ${formulaIndex + 1}`}
                  onClick={() => commit((draft) => {
                    draft.sections[sectionIndex].paragraphs[paragraphIndex].formulas?.splice(formulaIndex, 1);
                  }, 'DELETE_FORMULA')}
                ><Trash2 /></Button>
              </div>
            ))}
          </div>
        ) : null}
        <div className="paragraph-actions">
          <Button variant="ghost" size="sm" onClick={() => commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].intents.push({ id: uid('intent'), label: '', thoughts: [] }); }, 'ADD_INTENT')}><Plus /> Intent</Button>
          <Button variant="ghost" size="sm" onClick={() => commit((draft) => {
            const target = draft.sections[sectionIndex].paragraphs[paragraphIndex];
            if (!target.formulas) target.formulas = [];
            target.formulas.push({ id: uid('formula'), latex: '', caption: '' });
          }, 'ADD_FORMULA')}>∑ 公式</Button>
          <label className="asset-button">
            <Paperclip /> 图／表
            <input type="file" accept=".png,.jpg,.jpeg,.svg,.csv,.xlsx,.md,text/csv,image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) void onUpload(paragraph.id, file); event.currentTarget.value = ''; }} />
          </label>
        </div>
        {paragraph.asset_ids.length ? (
          <div className="asset-strip">
            {paragraph.asset_ids.map((assetId) => {
              const asset = assets.find((item) => item.asset_id === assetId);
              return asset ? <AssetPreview key={assetId} asset={asset} /> : <span key={assetId}>附件待同步</span>;
            })}
          </div>
        ) : null}
        </div>
        {folded ? <p className="folded-summary">{paragraph.intents.length} 个 Intent · {paragraph.intents.reduce((count, item) => count + item.thoughts.length, 0)} 条思想</p> : null}
        <DropZone target={{ kind: 'paragraph', id: paragraph.id, placement: 'inside' }} empty={!paragraph.intents.length} />
      </div>
    </article>
    <DropZone target={{ kind: 'paragraph', id: paragraph.id, placement: 'after' }} />
    </>
  );
}

function IntentEditor({
  intent,
  sectionIndex,
  paragraphIndex,
  intentIndex,
  role,
  selectedId,
  setSelection,
  commit,
}: {
  intent: IntentBlock;
  sectionIndex: number;
  paragraphIndex: number;
  intentIndex: number;
  role: string;
  selectedId?: string;
  setSelection: (selection: Selection) => void;
  commit: (change: (draft: StudioDocument) => void, operationKind?: string) => void;
}) {
  const thoughtsPath = (draft: StudioDocument) =>
    draft.sections[sectionIndex].paragraphs[paragraphIndex].intents[intentIndex].thoughts;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: intent.id,
    data: { type: 'intent' },
  });
  const ui = useEditorControls();
  const folded = ui.folded.includes(intent.id);
  const mappedOriginalTarget = correspondenceOwners(ui.document).authors.get(intent.id);
  const visibleThoughts = mappedOriginalTarget ? [] : displayedThoughts(ui.document, intent);
  const select = () => setSelection({ type: 'intent', id: intent.id, label: intent.label || '未定 Intent', role, intent: intent.label });
  return (
    <>
    <DropZone target={{ kind: 'intent', id: intent.id, placement: 'before' }} />
    <div
      ref={setNodeRef}
      data-block-id={intent.id}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`intent-block ${selectedId === intent.id ? 'selected-block' : ''} ${isDragging ? 'block-dragging' : ''}`}
    >
      <BlockRail kind="intent" label={intent.label || '未定 Intent'} compact="INTENT" onSelect={select}>
        <Input aria-label="自定义 Intent 标签" value={intent.label} placeholder="Intent 可以暂时未定" onChange={(event) => commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].intents[intentIndex].label = event.target.value; })} />
      </BlockRail>
      <div className="intent-content">
        <div className="intent-heading">
          <BlockControls id={intent.id} kind="intent" label={intent.label || '未定 Intent'}><button type="button" className="block-drag-handle" aria-label={`拖动 Intent ${intent.label || intentIndex + 1}`} {...attributes} {...listeners} onKeyDown={(event) => { if (event.key === 'Delete') { event.preventDefault(); commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].intents.splice(intentIndex, 1); }, 'DELETE_INTENT'); } else listeners?.onKeyDown?.(event); }}><GripVertical /></button></BlockControls>
          <Input aria-label="Intent 标签" value={intent.label} placeholder="Intent 可以暂时未定" onFocus={select} onChange={(event) => commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].intents[intentIndex].label = event.target.value; })} />
          <details className="block-menu"><summary aria-label="Intent 操作">•••</summary><BlockMove id={intent.id} /><button type="button" onClick={() => commit((draft) => { draft.sections[sectionIndex].paragraphs[paragraphIndex].intents.splice(intentIndex, 1); }, 'DELETE_INTENT')}><Trash2 /> 删除 Intent</button></details>
        </div>
        <div id={`body-${intent.id}`} inert={isDragging} hidden={folded}>
        {mappedOriginalTarget ? <div className="rounded border p-2 text-sm" aria-label="已对应的原作者 Intent">
          <p>思想已对应到模板槽位，原作者结构与编号保留。</p>
          <Button size="sm" variant="outline" onClick={() => { ui.unfold([...ancestors(ui.document, mappedOriginalTarget), mappedOriginalTarget]); ui.selectBlock(mappedOriginalTarget); }}>查看对应槽位</Button>
          {intent.thoughts.map(thought => <blockquote key={thought.id} className="whitespace-pre-wrap">{thought.text}</blockquote>)}
        </div> : null}
        {intent.author_intent_ids?.map(id => {
          const original = intentLocations(ui.document).find(item => item.intent.id === id)!;
          return <details key={id} className="text-sm" aria-label="对应的原作者上下文"><summary>原作者：{original.intent.label} · {sectionBreadcrumb(ui.document, original.section.id)}</summary>
            <p>{original.paragraph.purpose} · {original.paragraph.paradigm} · {original.paragraph.logical_relation || '未设置原段落关系'}</p>
            <p>原段落组：{original.section.paragraph_groups?.find(group => group.paragraph_ids.includes(original.paragraph.id))?.label || '未分组'}；{original.paragraph.formulas?.length || 0} 个公式，{original.paragraph.asset_ids.length} 个附件关联。</p>
          </details>;
        })}
        <SortableContext items={visibleThoughts.map(({ thought }) => thought.id)} strategy={verticalListSortingStrategy}>
          <div className="thought-list">
            {visibleThoughts.map(({ thought, ownerIntentId }) => {
              const thoughtIndex = thoughtsByIntent(ui.document, ownerIntentId).findIndex(item => item.id === thought.id);
              const authorThoughts = (draft: StudioDocument) => thoughtsByIntent(draft, ownerIntentId);
              return (
              <SortableThought
              key={thought.id}
              thought={thought}
               onSelect={(quote) => setSelection({ type: 'thought', id: thought.id, label: thought.text.slice(0, 40) || '空思想', role, intent: intent.label, quote })}
              onText={(value) => commit((draft) => { authorThoughts(draft)[thoughtIndex].text = value; })}
              onEnter={() => commit((draft) => { authorThoughts(draft).splice(thoughtIndex + 1, 0, { id: uid('thought'), text: '', citation_mode: 'PENDING', citations: [] }); }, 'ADD_THOUGHT')}
              onDelete={() => commit((draft) => { authorThoughts(draft).splice(thoughtIndex, 1); }, 'DELETE_THOUGHT')}
              onCitation={(mode, citations) => commit((draft) => { const target = authorThoughts(draft)[thoughtIndex]; target.citation_mode = mode; target.citations = citations; }, 'CITATION_DECISION')}
              onDropEvidence={(source) => commit((draft) => {
                const target = authorThoughts(draft)[thoughtIndex];
                if (!target.citations.some((item) => item.evidence_id === source.evidence_id)) {
                  target.citations.push({ evidence_id: source.evidence_id, selected: false, statement: source.statement, title: source.title });
                }
                target.citation_mode = 'PENDING';
              }, 'ADD_CITATION_CANDIDATE')}
              />
            ); })}
          </div>
        </SortableContext>
        {!mappedOriginalTarget ? <Button variant="ghost" size="sm" onClick={() => commit((draft) => { thoughtsPath(draft).push({ id: uid('thought'), text: '', citation_mode: 'PENDING', citations: [] }); }, 'ADD_THOUGHT')}><Plus /> 思想</Button> : null}
        </div>
        {folded ? <p className="folded-summary">{intent.thoughts.length} 条思想</p> : null}
        {!mappedOriginalTarget ? <DropZone target={{ kind: 'intent', id: intent.id, placement: 'inside' }} empty={!visibleThoughts.length} /> : null}
      </div>
    </div>
    <DropZone target={{ kind: 'intent', id: intent.id, placement: 'after' }} />
    </>
  );
}

function ReadingView({
  manuscriptId,
  content,
  generated,
  selectedAnchor,
  stale,
  artifacts,
  packageDownloads,
  submissions,
  publicationFiles,
  defaultVenue,
  findings,
  onEdit,
  onDiscuss,
  onEditObject,
  onReview,
  onPackage,
  onWorkspaceRefresh,
  onArchiveFile,
  onCitation,
  onFindingStatus,
  onFindingLocate,
  onStage,
  stage,
}: {
  manuscriptId: string;
  content: string;
  generated: GeneratedVersion | null;
  selectedAnchor?: string;
  stale: boolean;
  artifacts: Workspace['artifacts'];
  packageDownloads: ReactNode;
  submissions: Workspace['manuscript']['submissions'];
  publicationFiles: Workspace['assets'];
  defaultVenue: string;
  findings: Workspace['findings'];
  onEdit: () => void;
  onDiscuss: (block: GeneratedBlock, quote?: AuthorQuote) => void;
  onEditObject: (block: GeneratedBlock) => void;
  onReview: () => void;
  onPackage: () => void;
  onWorkspaceRefresh: () => Promise<void>;
  onArchiveFile: (file: File) => Promise<void>;
  onCitation: (evidenceId: string) => void;
  onFindingStatus: (findingId: string, status: string) => Promise<void>;
  onFindingLocate: (anchor: Record<string, unknown>) => void;
  onStage: (stage: WorkflowStage) => void;
  stage: WorkflowStage;
}) {
  if (!content) {
    return <div className="reading-empty"><FileDown /><h2>还没有成文版本</h2><p>回到结构编辑，补齐作者思想与引用决定后按 Generate。</p><Button onClick={onEdit}><Pencil /> 修改原始结构</Button></div>;
  }
  return (
    <article className="reading-sheet">
      {stale ? <div className="stale-banner">当前显示旧生成快照；结构修改尚未重新生成。</div> : null}
      {generated?.citation_style === 'legacy' && generated.references.length ? <p className="stale-banner">历史原文件保留当时的引用格式；阅读界面按首次出现编号以便定位来源。</p> : null}
      <div className="reading-toolbar">
        <Button variant="outline" size="sm" onClick={onEdit}><Pencil /> 修改原始结构</Button>
        <Button variant="outline" size="sm" onClick={onReview}>🔎 全文检查</Button>
        {(stage === 'FINALIZATION_SUBMISSION' || stage === 'REVISION') ? <Button variant="outline" size="sm" onClick={onPackage}>📦 投稿包</Button> : null}
        {artifacts.filter((item) => ['PDF', 'TEX', 'BIB', 'MARKDOWN', 'GENERATED_JSON'].includes(item.artifact_kind)).map((artifact) => (
          <a key={artifact.artifact_id} className="artifact-link" href={studioFileUrl(`/artifacts/${artifact.artifact_id}`)} target="_blank" rel="noreferrer">{({ PDF: '📎 PDF', TEX: 'LaTeX', BIB: '参考文献', MARKDOWN: 'Markdown', GENERATED_JSON: '成文与来源记录' } as Record<string, string>)[artifact.artifact_kind]}</a>
        ))}
        {stage === 'WHOLE_PAPER_REVIEW' ? <Button size="sm" onClick={() => onStage('FINALIZATION_SUBMISSION')}>进入定稿 →</Button> : null}
        {stage === 'FINALIZATION_SUBMISSION' ? <Button size="sm" onClick={() => onStage('REVISION')}>开始返修 →</Button> : null}
        {(stage === 'FINALIZATION_SUBMISSION' || stage === 'REVISION') ? <Button size="sm" variant="secondary" onClick={() => onStage('PUBLICATION')}>出版归档</Button> : null}
      </div>
      {['FINALIZATION_SUBMISSION', 'REVISION', 'PUBLICATION'].includes(stage) ? packageDownloads : null}
      {findings.some((item) => !['DISMISSED', 'RESOLVED'].includes(item.status)) ? (
        <section className="finding-panel" aria-label="全文检查结果">
          <header><strong>🔎 全文检查</strong><span>规则判断与模型判断分开标记；不会自动改稿。</span></header>
          {findings.filter((item) => !['DISMISSED', 'RESOLVED'].includes(item.status)).map((finding) => (
            <article key={finding.finding_id} className={`finding-item finding-item--${finding.severity.toLowerCase()}`}>
              <div>
                <span>{finding.source === 'RULE' ? '规则' : '模型'} · {finding.finding_kind}</span>
                <p>{finding.detail}</p>
              </div>
              <div className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => onFindingLocate(finding.anchor)}>定位</Button>
                <Button size="sm" variant="outline" onClick={() => void onFindingStatus(finding.finding_id, 'ACCEPTED')}>保留待改</Button>
                <Button size="sm" variant="ghost" onClick={() => void onFindingStatus(finding.finding_id, 'DISMISSED')}>忽略</Button>
                <Button size="sm" variant="ghost" onClick={() => void onFindingStatus(finding.finding_id, 'RESOLVED')}>已处理</Button>
              </div>
            </article>
          ))}
        </section>
      ) : null}
      {['FINALIZATION_SUBMISSION', 'REVISION', 'PUBLICATION'].includes(stage) ? (
        <SubmissionPanel
          manuscriptId={manuscriptId}
          submissions={submissions}
          publicationFiles={publicationFiles}
          defaultVenue={defaultVenue}
          onSaved={onWorkspaceRefresh}
          onArchiveFile={onArchiveFile}
        />
      ) : null}
      {!generated ? <p aria-live="polite">正在读取此成文版本的段落与来源…</p> : null}
      {generated?.blocks.map((block) => {
        const discuss = () => onDiscuss(block);
        const text = <CitationText text={block.text} references={generated.references} onCitation={onCitation} />;
        return (
          <section key={block.anchor_id} data-generated-anchor={block.anchor_id} className={`reading-paragraph ${selectedAnchor === block.anchor_id ? 'reading-paragraph--selected' : ''}`}>
            <div data-quote-text onPointerUp={(event) => {
              if ((event.target as Element).closest('button')) return;
              const quote = quoteFromSelection(event.currentTarget, block.display_text);
              onDiscuss(block, quote);
            }}>
              {block.kind === 'title' ? <h1>{text}</h1> : block.kind === 'heading' ? <h2 aria-level={block.heading_level || 2}>{text}</h2> : <p>{text}</p>}
            </div>
            {block.formulas?.map((formula) => <figure key={formula.id}><code>{formula.latex}</code><figcaption><CitationText text={formula.caption} references={generated.references} onCitation={onCitation} /></figcaption></figure>)}
            {block.assets?.map((asset) => {
              const base = API_BASE + '/manuscripts/' + generated.manuscript_id + '/generated-versions/' + generated.generated_version_id + '/materials/' + asset.asset_id;
              return <figure key={asset.asset_id} className="my-4" data-generated-material={asset.asset_id}>
                {asset.display_kind === 'FIGURE' ? (
                  // oxlint-disable-next-line next/no-img-element -- verified frozen local materials have explicit dimensions
                  <img src={base + '/render'} alt={asset.filename} width={asset.width} height={asset.height} loading="lazy" className="h-auto max-h-[65vh] max-w-full object-contain" />
                ) : asset.tables?.map((table, index) => <div key={asset.asset_id + '-' + index} className="my-3 overflow-x-auto">
                  <table className="w-full border-collapse text-sm">
                    <caption className="text-left font-medium">{table.title}</caption>
                    <tbody>{table.rows.map((row, rowIndex) => <tr key={rowIndex}>{Array.from({ length: table.column_count }, (_, columnIndex) => <td key={columnIndex} className="whitespace-pre-wrap border border-border px-2 py-1">{row[columnIndex] ?? ''}</td>)}</tr>)}</tbody>
                  </table>
                </div>)}
                <figcaption className="text-sm text-muted-foreground"><a href={base + '/source'} target="_blank" rel="noreferrer">原素材：{asset.filename}</a> · 此成文版本的固定素材</figcaption>
              </figure>;
            })}
            <div className="reading-paragraph__actions">
              <Button variant="ghost" size="sm" onClick={discuss}>💬 {block.kind === 'paragraph' ? '讨论此段' : '讨论此节'}</Button>
              <Button variant="ghost" size="sm" onMouseDown={(event) => event.preventDefault()} onClick={(event) => {
                const element = event.currentTarget.closest('[data-generated-anchor]')?.querySelector('[data-quote-text]');
                const quote = element ? quoteFromSelection(element, block.display_text) : undefined;
                if (quote) onDiscuss(block, quote);
              }}>讨论选区</Button>
              {generated.structure_mapping_available && block.section_id ? <Button variant="ghost" size="sm" onClick={() => onEditObject(block)}>修改此段原始结构</Button> : null}
            </div>
          </section>
        );
      })}
      {generated?.references.length ? <section className="reading-references" aria-label="此版本的固定参考文献">
        <h2>References</h2>
        <ol>{generated.references.map((reference) => <li key={reference.evidence_id}>
          <button type="button" className="inline-citation" onClick={() => onCitation(reference.evidence_id)} aria-label={`打开引用 ${reference.citation_index} 的来源`}>[{reference.citation_index}]</button>{' '}
          {reference.authors?.join(', ')}{reference.published_year ? ` (${reference.published_year}). ` : ' '}
          {reference.title || reference.statement || '历史书目信息不完整'}{reference.doi ? ` · ${reference.doi}` : ''}
        </li>)}</ol>
      </section> : null}
    </article>
  );
}

function SubmissionPanel({
  manuscriptId,
  submissions,
  publicationFiles,
  defaultVenue,
  onSaved,
  onArchiveFile,
}: {
  manuscriptId: string;
  submissions: Workspace['manuscript']['submissions'];
  publicationFiles: Workspace['assets'];
  defaultVenue: string;
  onSaved: () => Promise<void>;
  onArchiveFile: (file: File) => Promise<void>;
}) {
  const latest = submissions.at(-1);
  const [venue, setVenue] = useState(latest?.venue || defaultVenue || '');
  const [roundNumber, setRoundNumber] = useState(latest?.round || 1);
  const [status, setStatus] = useState('SUBMITTED');
  const [detail, setDetail] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <section className="submission-panel" aria-label="投稿与出版事件">
      <header><strong>📮 投稿／出版记录</strong><span>这是事件记录，不增加新的阶段轴。</span></header>
      <div className="submission-form">
        <Input value={venue} onChange={(event) => setVenue(event.target.value)} placeholder="期刊／会议" />
        <Input type="number" min={1} value={roundNumber} onChange={(event) => setRoundNumber(Math.max(1, Number(event.target.value) || 1))} aria-label="轮次" />
        <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="投稿状态">
          {['SUBMITTED', 'UNDER_REVIEW', 'REVISION_REQUESTED', 'REJECTED', 'WITHDRAWN', 'ACCEPTED', 'PUBLISHED'].map((item) => <option key={item}>{item}</option>)}
        </select>
        <Input value={detail} onChange={(event) => setDetail(event.target.value)} placeholder="稿号、DOI、校样说明或发表信息" />
        <Button
          size="sm"
          disabled={busy || !venue.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await studioApi.recordSubmission(manuscriptId, venue.trim(), roundNumber, status, detail.trim());
              setDetail('');
              await onSaved();
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <LoaderCircle className="animate-spin" /> : '＋ 记录'}
        </Button>
      </div>
      <div className="submission-events">
        {[...submissions].reverse().map((event) => (
          <article key={event.event_id}>
            <strong>{event.status}</strong><span>{event.venue} · R{event.round}</span><p>{event.detail || '无补充说明'}</p>
          </article>
        ))}
        {!submissions.length ? <p className="panel-empty">尚未记录投稿事件。</p> : null}
      </div>
      <div className="publication-files">
        <label className="asset-button">
          📚 归档校样／终稿
          <input
            type="file"
            accept=".pdf,.docx,.tex,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void onArchiveFile(file);
              event.currentTarget.value = '';
            }}
          />
        </label>
        {publicationFiles.map((asset) => (
          <a key={asset.asset_id} href={`${API_BASE}/assets/${asset.asset_id}/content`} target="_blank" rel="noreferrer">
            {asset.filename}
          </a>
        ))}
      </div>
    </section>
  );
}

function quoteFromSelection(element: Element, expectedText: string): AuthorQuote | undefined {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return;
  const range = selection.getRangeAt(0);
  if (!element.contains(range.startContainer) || !element.contains(range.endContainer)) return;
  const prefix = range.cloneRange();
  prefix.selectNodeContents(element);
  prefix.setEnd(range.startContainer, range.startOffset);
  const start = prefix.toString().length;
  const text = range.toString();
  const end = start + text.length;
  if (!text || expectedText.slice(start, end) !== text) return;
  return { text, start, end, offset_unit: 'utf16' };
}

function QuotedText({ text, quote }: { text: string; quote: AuthorQuote }) {
  if (!quote.text || quote.start === undefined || quote.end === undefined) return <p className="whitespace-pre-wrap">{text}</p>;
  return <p className="whitespace-pre-wrap">{text.slice(0, quote.start)}<mark>{text.slice(quote.start, quote.end)}</mark>{text.slice(quote.end)}</p>;
}

function CitationText({ text, onCitation, references = [] }: { text: string; onCitation: (evidenceId: string) => void; references?: GeneratedReference[] }) {
  const parts = text.split(/(\[@[^\]]+\])/g);
  return parts.map((part, index) => {
    const match = /^\[@([^\]]+)\]$/.exec(part);
    if (!match) return <span key={`${index}-${part.slice(0, 8)}`}>{part}</span>;
    const reference = references.find((item) => item.evidence_id === match[1]);
    return (
      <button key={`${index}-${match[1]}`} type="button" className="inline-citation" aria-label={reference ? `打开引用 ${reference.citation_index} 的来源` : '查看未登记引用的来源'} onClick={(event) => { event.stopPropagation(); onCitation(match[1]); }}>
        {reference ? `[${reference.citation_index}]` : '[来源未登记]'}
      </button>
    );
  });
}

function AssetPreview({ asset }: { asset: Workspace['assets'][number] }) {
  const source = `${API_BASE}/assets/${asset.asset_id}/content`;
  const preview = Array.isArray(asset.metadata.preview)
    ? asset.metadata.preview as unknown[][]
    : [];
  return (
    <figure className="asset-preview">
      {asset.asset_kind === 'FIGURE' ? (
        // oxlint-disable-next-line next/no-img-element -- local user assets are already bounded and lazily loaded
        <img src={source} alt={asset.filename} loading="lazy" />
      ) : preview.length ? (
        <div className="asset-table-wrap">
          <table>
            <tbody>
              {preview.slice(0, 6).map((row, rowIndex) => (
                <tr key={`${asset.asset_id}-${rowIndex}`}>
                  {row.slice(0, 6).map((cell, columnIndex) => (
                    <td key={`${rowIndex}-${columnIndex}`}>
                      {formatPreviewCell(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="asset-placeholder">▦</div>}
      <figcaption><a href={source} target="_blank" rel="noreferrer">{asset.filename}</a><span>{asset.status}</span></figcaption>
    </figure>
  );
}

function formatPreviewCell(cell: unknown) {
  if (cell === null || cell === undefined) return '';
  if (typeof cell === 'string') return cell;
  if (typeof cell === 'number' || typeof cell === 'boolean' || typeof cell === 'bigint') {
    return `${cell}`;
  }
  if (typeof cell === 'object') return JSON.stringify(cell);
  return `[${typeof cell}]`;
}

function RevisionView({
  manuscriptId,
  comments,
  archived,
  activeCommentIds,
  onChangeContext,
  onArchive,
  existingComments,
  changeHistory,
  packageDownloads,
  onShowChange,
  showArchived,
  setShowArchived,
  commentDraft,
  setCommentDraft,
  reviewRoundId,
  roundPicker,
  onEnsureRound,
  onReload,
  onEditStructure,
  onPackage,
  onError,
}: {
  manuscriptId: string;
  comments: ReviewComment[];
  archived: boolean;
  activeCommentIds: string[];
  onChangeContext: (ids: string[]) => Promise<boolean>;
  onArchive: (commentId: string) => Promise<void>;
  existingComments: ReviewComment[];
  changeHistory: ReactNode;
  packageDownloads: ReactNode;
  onShowChange: (id: string) => void;
  showArchived: boolean;
  setShowArchived: (value: boolean) => void;
  commentDraft: string;
  setCommentDraft: (value: string) => void;
  reviewRoundId: string;
  roundPicker: (disabled: boolean) => ReactNode;
  onEnsureRound: () => Promise<string>;
  onReload: () => Promise<void>;
  onEditStructure: () => void;
  onPackage: () => void;
  onError: (message: string) => void;
}) {
  const [preview, setPreview] = useState<Array<{
    text: string;
    original_text: string;
    include: boolean;
  }>>([]);
  const [previewMetadata, setPreviewMetadata] = useState<Record<string, unknown>>({});
  const [previewSource, setPreviewSource] = useState('PASTED');
  const [importBusy, setImportBusy] = useState(false);
  const [fileBusy, setFileBusy] = useState(false);
  const selectedCount = preview.filter((item) => item.include && item.text.trim()).length;
  const normalizedText = (text: string) => text.trim().replace(/\s+/g, ' ');

  const prepareText = () => {
    const parts = commentDraft.split(/\n\s*\n+/).map((text) => text.trim()).filter(Boolean);
    setPreview(parts.map((text) => ({ text, original_text: text, include: true })));
    setPreviewMetadata({ original_text: commentDraft });
    setPreviewSource('PASTED');
  };

  const prepareSingle = () => {
    if (!commentDraft.trim()) return;
    setPreview([{ text: commentDraft, original_text: commentDraft, include: true }]);
    setPreviewMetadata({ original_text: commentDraft });
    setPreviewSource('SINGLE');
  };

  const confirmImport = async () => {
    if (!selectedCount || importBusy) return;
    if (selectedCount > 100) {
      onError('每批最多导入 100 条已选意见。请取消部分勾选，完整原文仍保留在预览中。');
      return;
    }
    setImportBusy(true);
    try {
      const round = reviewRoundId || (await onEnsureRound());
      await studioApi.importComments(round, preview, previewSource, previewMetadata);
      setCommentDraft('');
      setPreview([]);
      setPreviewMetadata({});
      await onReload();
      onError('');
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : '意见导入失败');
    } finally {
      setImportBusy(false);
    }
  };
  return (
    <div className="revision-sheet">
      <header className="revision-header">
        <div><p>Reviewer comments</p><h2>意见 → 决定 → 修改 → 回复</h2></div>
        <div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => setShowArchived(!showArchived)}>🗃 {showArchived ? '当前意见' : '已删除'}</Button><Button size="sm" onClick={onPackage}>📦 投稿包</Button></div>
      </header>
      {roundPicker(importBusy || fileBusy || (preview.length > 0 && Boolean(reviewRoundId)))}
      {!showArchived ? (
        <div className="comment-import">
          <Textarea aria-label="审稿意见输入" name="review-comment-input" disabled={importBusy || fileBusy} value={commentDraft} onChange={(event) => setCommentDraft(event.target.value)} placeholder="粘贴意见；空行分条。确认前不会写入。" />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={importBusy || fileBusy} onClick={prepareText}>👀 准备预览</Button>
            <Button size="sm" variant="outline" disabled={importBusy || fileBusy} onClick={prepareSingle}>➕ 单条新增</Button>
            <label className="asset-button review-file-upload">
              {fileBusy ? '读取文件…' : '📄 TXT / MD / DOCX / PDF'}
              <input className="review-file-input" aria-label="导入审稿意见文件" name="review-comment-file" type="file" accept=".txt,.md,.docx,.pdf" disabled={fileBusy || importBusy} onChange={async (event) => {
                const input = event.currentTarget;
                const file = input.files?.[0];
                if (!file) return;
                setFileBusy(true);
                try {
                  const result = await studioApi.previewCommentFile(file);
                  setPreview(result.comments);
                  setPreviewMetadata(result.metadata);
                  setPreviewSource('FILE_IMPORT');
                  onError('');
                } catch (caught) {
                  onError(caught instanceof Error ? caught.message : '意见文件无法导入');
                } finally {
                  setFileBusy(false);
                  input.value = '';
                }
              }} />
            </label>
          </div>
          {preview.length ? (
            <div className="comment-preview">
              <output className="block">预览 {preview.length} 条，已选 {selectedCount} 条。每批最多 100 条。</output>
              {selectedCount > 100 ? <p className="text-sm text-amber-700" role="alert">已选超过 100 条，请取消部分勾选后导入。所有条目和原文均保留。</p> : null}
              <details><summary>原始导入全文{typeof previewMetadata.filename === 'string' ? `：${previewMetadata.filename}` : ''}</summary>
                <pre className="whitespace-pre-wrap break-words">{typeof previewMetadata.original_text === 'string' ? previewMetadata.original_text : ''}</pre>
              </details>
              {preview.map((item, index) => (
                <div key={`${index}-${item.original_text.slice(0, 20)}`} className="comment-preview__row">
                  <Checkbox
                    aria-label={`纳入意见 ${index + 1}`}
                    disabled={importBusy || fileBusy}
                    checked={item.include}
                    onCheckedChange={(checked) => setPreview((current) => current.map((row, rowIndex) => (
                      rowIndex === index ? { ...row, include: Boolean(checked) } : row
                    )))}
                  />
                  <div className="min-w-0">
                  {existingComments.some((comment) => normalizedText(comment.edited_text) === normalizedText(item.text)) ||
                    preview.some((other, otherIndex) => otherIndex !== index && normalizedText(other.text) === normalizedText(item.text)) ?
                    <p className="text-xs text-amber-700">发现相同意见，请核对。你可以保留或取消勾选，不会自动合并。</p> : null}
                  <Textarea
                    value={item.text}
                    disabled={importBusy || fileBusy}
                    onChange={(event) => setPreview((current) => current.map((row, rowIndex) => (
                      rowIndex === index ? { ...row, text: event.target.value } : row
                    )))}
                    aria-label={`编辑意见 ${index + 1}`}
                  />
                  </div>
                </div>
              ))}
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" disabled={importBusy || fileBusy} onClick={() => setPreview([])}>取消</Button>
                <Button size="sm" disabled={importBusy || fileBusy || !selectedCount || selectedCount > 100} onClick={() => void confirmImport()}>
                  {importBusy ? '导入中…' : `✓ 确认导入 ${selectedCount} 条`}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="comment-table">
        {comments.map((comment) => {
          const active = activeCommentIds.includes(comment.comment_id);
          const label = commentLabel(comment);
          return (
            <article key={comment.comment_id} className={`comment-row ${active ? 'comment-row--active' : ''}`}>
              <button
                type="button"
                className="comment-pencil"
                aria-label={`${active ? '结束关联意见' : '开始修改意见'} ${label}`}
                disabled={archived}
                onClick={async () => {
                  if (archived) return;
                  const changed = await onChangeContext(active ? activeCommentIds.filter((id) => id !== comment.comment_id) : [...activeCommentIds, comment.comment_id]);
                  if (changed && !active) onEditStructure();
                }}
              ><Pencil /></button>
              <span className="comment-id" title={comment.comment_id}>{label}</span>
              <div className="comment-main">
                <small>第 {comment.round_number || '?'} 轮 · {comment.reviewer || '提出人未填写'}</small>
                <p className="whitespace-pre-wrap">{comment.edited_text}</p>
                <details><summary>原意见与导入来源</summary><p className="whitespace-pre-wrap">{comment.original_text}</p>
                  {typeof comment.import_metadata?.filename === 'string' ? <small>{comment.import_metadata.filename}</small> : null}
                </details>
                <StudioResponseReview key={`${manuscriptId}:${comment.comment_id}`} manuscriptId={manuscriptId} comment={comment} archived={archived} onReload={onReload} />
                <small>{comment.changes?.length || 0} 条关联修改</small>
                {comment.changes?.length ? <nav aria-label={`${label} 的真实修改记录`} className="comment-change-links">{comment.changes.map((change, index) => <a key={change.change_id} href={`#change-${change.change_id}`} onClick={() => onShowChange(change.change_id)}>查看修改 {index + 1}</a>)}</nav> : null}
              </div>
              {archived ? (
                <Button size="icon-sm" variant="ghost" aria-label={`恢复意见 ${label}`} onClick={() => void studioApi.restoreComment(comment.comment_id).then(onReload).catch((caught) => onError(caught instanceof Error ? caught.message : '恢复失败'))}>↩</Button>
              ) : (
                <Button size="icon-sm" variant="ghost" aria-label={`移入已删除 ${label}`} onClick={() => void onArchive(comment.comment_id)}><Trash2 /></Button>
              )}
            </article>
          );
        })}
        {comments.length === 0 ? <p className="panel-empty">{archived ? '没有已删除意见。' : '尚未导入审稿意见。'}</p> : null}
      </div>
      {changeHistory}
      {packageDownloads}
    </div>
  );
}
