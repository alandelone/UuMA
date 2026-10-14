import type {
  ChatMessage,
  AuthorQuote,
  ChatContext,
  GeneratedVersion,
  SuggestionDecisionRequest,
  SuggestionDecisionResponse,
  SuggestionPreview,
  ReviewComment,
  ResponseReviewContext,
  ResponseReviewRequest,
  ReviewRound,
  StudioChange,
  ChangeAssociationRequest,
  ChangeAssociationEvent,
  SampleBlock,
  SourceEvidence,
  StudioDocument,
  StudioJob,
  SubmissionPackage,
  TrackRecord,
  Workspace,
} from './studio-types';

export const API_BASE =
  process.env.NEXT_PUBLIC_RSTV4_API ?? 'http://127.0.0.1:8874/api';

export function sharedDiscussionRequest(path: string, body?: unknown): Promise<unknown> {
  const route = path.replace('/api/catalog/discussion', '/research/discussion');
  return request<unknown>(route, body === undefined ? undefined : { method: 'POST', body: JSON.stringify(body) });
}

export class ApiError extends Error {
  status: number;
  body: Record<string, unknown>;

  constructor(status: number, body: Record<string, unknown>) {
    const detail = body.detail ?? body.error;
    super(
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean).join('; ') || `Request failed (${status})`
        : detail
          ? JSON.stringify(detail)
          : `Request failed (${status})`,
    );
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    let body: Record<string, unknown> = {};
    try {
      body = await response.json();
    } catch {
      body = { detail: response.statusText };
    }
    throw new ApiError(response.status, body);
  }
  return response.json() as Promise<T>;
}

async function download(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    let body: Record<string, unknown>;
    try { body = await response.json(); }
    catch { body = { detail: response.statusText }; }
    throw new ApiError(response.status, body);
  }
  return response.blob();
}

export const studioApi = {
  tracks: () => request<TrackRecord[]>('/tracks'),
  createManuscript: (trackId: string, title: string) =>
    request<Workspace>('/manuscripts', {
      method: 'POST',
      body: JSON.stringify({ track_id: trackId, title }),
    }),
  workspace: (manuscriptId: string) =>
    request<Workspace>(`/manuscripts/${manuscriptId}/workspace`),
  saveDocument: (
    manuscriptId: string,
    baseRevision: number,
    operationId: string,
    document: StudioDocument,
    operationKind = 'EDIT',
    commentIds: string[] = [],
  ) =>
    request<{
      document_revision: number;
      document: StudioDocument;
      saved_at: string;
      idempotent_replay: boolean;
    }>(`/manuscripts/${manuscriptId}/document`, {
      method: 'PUT',
      body: JSON.stringify({
        base_revision: baseRevision,
        operation_id: operationId,
        document,
        operation_kind: operationKind,
        comment_ids: commentIds,
      }),
    }),
  setStage: (
    manuscriptId: string,
    stage: string,
    expectedRevision: number,
    reason: string,
  ) =>
    request<Workspace>(`/manuscripts/${manuscriptId}/stage`, {
      method: 'POST',
      body: JSON.stringify({
        stage,
        expected_revision: expectedRevision,
        reason,
      }),
    }),
  sources: (manuscriptId: string, query: string) =>
    request<SourceEvidence[]>(
      `/manuscripts/${manuscriptId}/sources?q=${encodeURIComponent(query)}`,
    ),
  samples: (
    manuscriptId: string,
    layer: string,
    anchorId?: string,
    role?: string,
    intent?: string,
  ) => {
    const params = new URLSearchParams({ layer });
    if (anchorId) params.set('anchor_id', anchorId);
    if (role) params.set('role', role);
    if (intent) params.set('intent', intent);
    return request<SampleBlock[]>(
      `/manuscripts/${manuscriptId}/samples?${params.toString()}`,
    );
  },
  adoptTemplate: (
    manuscriptId: string,
    sourceSkeletonId: string | undefined,
    sourceVersion: string | undefined,
    adopted: Record<string, unknown>,
  ) =>
    request<Workspace['template_instances'][number]>(
      `/manuscripts/${manuscriptId}/template-instances`,
      {
        method: 'POST',
        body: JSON.stringify({
          source_skeleton_id: sourceSkeletonId || null,
          source_version: sourceVersion || 'PaperSkeleton-L1-L4',
          adopted,
        }),
      },
    ),
  uploadAsset: (manuscriptId: string, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<Workspace['assets'][number]>(
      `/manuscripts/${manuscriptId}/assets`,
      { method: 'POST', body },
    );
  },
  chat: (manuscriptId: string, anchorId?: string, before?: string, limit = 100, filter?: { anchor_type: string; anchor_revision: number; generated_version_id?: string }, beforeMessageId?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (anchorId) params.set('anchor_id', anchorId);
    if (before) params.set('before', before);
    if (beforeMessageId) params.set('before_message_id', beforeMessageId);
    if (filter) {
      params.set('anchor_type', filter.anchor_type);
      params.set('anchor_revision', String(filter.anchor_revision));
      if (filter.generated_version_id) params.set('generated_version_id', filter.generated_version_id);
    }
    return request<ChatMessage[]>(`/manuscripts/${manuscriptId}/chat?${params.toString()}`);
  },
  discuss: (
    manuscriptId: string,
    content: string,
    anchorType: string,
    anchorId: string | undefined,
    anchorRevision: number,
    quote?: AuthorQuote,
  ) =>
    request<{ author: ChatMessage; agent: ChatMessage }>(
      `/manuscripts/${manuscriptId}/chat`,
      {
        method: 'POST',
        body: JSON.stringify({
          content,
          anchor_type: anchorType,
          anchor_id: anchorId,
          anchor_revision: anchorRevision,
          quote,
        }),
      },
    ),
  generatedVersion: (manuscriptId: string, versionId: string) =>
    request<GeneratedVersion>(`/manuscripts/${manuscriptId}/generated-versions/${versionId}`),
  chatContext: (manuscriptId: string, messageId: string) =>
    request<ChatContext>(`/manuscripts/${manuscriptId}/chat/${messageId}/context`),
  suggestionPreview: (manuscriptId: string, messageId: string, suggestionId: string) =>
    request<SuggestionPreview>(`/manuscripts/${manuscriptId}/chat/${messageId}/suggestions/${suggestionId}/preview`),
  decideSuggestion: (manuscriptId: string, messageId: string, decision: SuggestionDecisionRequest) =>
    request<SuggestionDecisionResponse>(`/manuscripts/${manuscriptId}/chat/${messageId}/decisions`, {
      method: 'POST', body: JSON.stringify(decision),
    }),
  createJob: (manuscriptId: string, kind: string, inputRevision: number, jobRequest: Record<string, unknown> = {}) =>
    request<StudioJob>(`/manuscripts/${manuscriptId}/jobs`, {
      method: 'POST',
      body: JSON.stringify({ kind, input_revision: inputRevision, request: jobRequest }),
    }),
  job: (jobId: string) => request<StudioJob>(`/jobs/${jobId}`),
  cancelJob: (jobId: string) => request<StudioJob>(`/jobs/${jobId}`, { method: 'DELETE' }),
  packages: (manuscriptId: string) => request<SubmissionPackage[]>(`/manuscripts/${manuscriptId}/packages`),
  downloadPackage: (manuscriptId: string, packageId: string, filename?: string) => download(
    `/manuscripts/${manuscriptId}/packages/${packageId}/${filename ? `files/${encodeURIComponent(filename)}` : 'download'}`,
  ),
  updateFinding: (findingId: string, status: string) =>
    request<Workspace['findings'][number]>(`/findings/${findingId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  recordSubmission: (
    manuscriptId: string,
    venue: string,
    roundNumber: number,
    status: string,
    detail: string,
  ) =>
    request<Workspace['manuscript']['submissions'][number]>(
      `/manuscripts/${manuscriptId}/submission-events`,
      {
        method: 'POST',
        body: JSON.stringify({
          venue,
          round_number: roundNumber,
          status,
          detail: detail || null,
        }),
      },
    ),
  comments: (manuscriptId: string, includeArchived = false) =>
    request<ReviewComment[]>(
      `/manuscripts/${manuscriptId}/comments?include_archived=${includeArchived}`,
    ),
  reviewRounds: (manuscriptId: string) => request<ReviewRound[]>(`/manuscripts/${manuscriptId}/review-rounds`),
  changes: (manuscriptId: string) => request<StudioChange[]>(`/manuscripts/${manuscriptId}/changes`),
  setChangeAssociations: (manuscriptId: string, changeId: string, decision: ChangeAssociationRequest) =>
    request<{ event: ChangeAssociationEvent; change: StudioChange; idempotent_replay: boolean }>(
      `/manuscripts/${manuscriptId}/changes/${changeId}/associations`,
      { method: 'POST', body: JSON.stringify(decision) },
    ),
  createReviewRound: (manuscriptId: string, roundNumber: number, venue: string, baselineVersionId?: string, expectedRevision?: number) =>
    request<ReviewRound>(
      `/manuscripts/${manuscriptId}/review-rounds`,
      {
        method: 'POST',
        body: JSON.stringify({ round_number: roundNumber, venue: venue || null, baseline_manuscript_version_id: baselineVersionId, expected_document_revision: expectedRevision }),
      },
    ),
  importComments: (
    reviewRoundId: string,
    comments: Array<{ text: string; original_text?: string; include: boolean }>,
    source = 'PASTED',
    importMetadata: Record<string, unknown> = {},
  ) =>
    request<ReviewComment[]>(`/review-rounds/${reviewRoundId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ source, comments, import_metadata: importMetadata }),
    }),
  previewCommentFile: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<{
      comments: Array<{ text: string; original_text: string; include: boolean }>;
      metadata: Record<string, unknown>;
    }>('/review-comments/preview-file', { method: 'POST', body });
  },
  importCommentFile: (reviewRoundId: string, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<ReviewComment[]>(
      `/review-rounds/${reviewRoundId}/comments/file`,
      { method: 'POST', body },
    );
  },
  updateComment: (commentId: string, changes: Record<string, unknown>) =>
    request<ReviewComment>(`/comments/${commentId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
  responseReview: (manuscriptId: string, commentId: string) => request<ResponseReviewContext>(
    `/manuscripts/${manuscriptId}/comments/${commentId}/response-review`,
  ),
  responseReviewHistory: (manuscriptId: string, commentId: string) => request<{ history: ResponseReviewContext['history'] }>(
    `/manuscripts/${manuscriptId}/comments/${commentId}/response-checks`,
  ),
  confirmResponseReview: (manuscriptId: string, commentId: string, review: ResponseReviewRequest) => request<{
    check_id: string; idempotent_replay: boolean; comment: ReviewComment; history: ResponseReviewContext['history'];
  }>(`/manuscripts/${manuscriptId}/comments/${commentId}/response-checks`, { method: 'POST', body: JSON.stringify(review) }),
  archiveComment: (commentId: string) =>
    request<ReviewComment>(`/comments/${commentId}`, { method: 'DELETE' }),
  restoreComment: (commentId: string) =>
    request<ReviewComment>(`/comments/${commentId}/restore`, { method: 'POST' }),
};
