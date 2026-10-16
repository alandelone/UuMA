export type CitationMode = 'PENDING' | 'NONE' | 'SELECTED';

export interface CitationCandidate {
  evidence_id: string;
  selected: boolean;
  statement?: string;
  title?: string;
}

export interface Thought {
  id: string;
  text: string;
  citation_mode: CitationMode;
  citations: CitationCandidate[];
}

export interface IntentBlock {
  id: string;
  label: string;
  thoughts: Thought[];
  template_source?: TemplateSource;
  author_intent_ids?: string[];
}

export interface TemplateSource {
  skeleton_id: string;
  source_sha256: string;
  unit_id?: string;
  source_section_id?: string;
  source_path?: string[];
  heading_location?: Record<string, unknown> | null;
  page_number?: number | null;
}

export interface ParagraphBlock {
  id: string;
  purpose: string;
  paradigm: string;
  logical_relation?: string;
  logic?: Record<string, unknown>;
  template_source?: TemplateSource;
  author_context_paragraph_ids?: string[];
  intents: IntentBlock[];
  asset_ids: string[];
  formulas?: Array<{
    id: string;
    latex: string;
    caption: string;
  }>;
}

export interface SectionBlock {
  id: string;
  title: string;
  role: string;
  placement_status?: 'UNPLACED';
  parent_section_id?: string;
  unplaced_parent_section_id?: string;
  template_source?: TemplateSource;
  paragraphs: ParagraphBlock[];
  paragraph_groups?: Array<{ id: string; label: string; paragraph_ids: string[] }>;
  block_order?: string[];
}

export interface StudioDocument {
  layout?: { page_margin: 'standard' | 'narrow' };
  schema_version: 1;
  manuscript_id: string;
  title: string;
  abstract: string;
  venue: string;
  sections: SectionBlock[];
  argument_relations?: ArgumentRelation[];
}

export interface ArgumentRelation {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
  condition: string;
}

export interface TemplatePreview {
  skeleton_id: string;
  skeleton_version: number;
  paper_id: string;
  paper_version: number;
  title: string;
  source_sha256: string;
  author_text_copied: false;
  sections: Array<{ title: string;
    source_section_id?: string;
    parent_source_section_id?: string | null;
    depth?: number;
    source_path?: string[];
    heading_location?: Record<string, unknown> | null;
    page_number?: number | null;
    paragraphs: Array<{
    unit_id: string; intent: string; role: string; logic: Record<string, unknown>;
  }> }>;
}

export interface TemplateRequest {
  base_revision: number;
  operation_id: string;
  skeleton_id: string;
  source_sha256: string;
  selected_unit_ids: string[];
  scope_type: 'paper' | 'section' | 'paragraph' | 'intent';
  scope_id: string | null;
  mode: 'INSERT' | 'REPLACE';
  replace_confirmed: boolean;
  comment_ids: string[];
}

export interface Manuscript {
  manuscript_id: string;
  track_id: string;
  title: string;
  workflow_stage: WorkflowStage;
  writing_status: string;
  revision: number;
  versions: Array<{
    manuscript_version_id: string;
    version: number;
    content: string;
    created_at: string;
  }>;
  submissions: SubmissionEvent[];
  needs_scientific_review?: boolean | 0 | 1;
}

export interface PublicationFile {
  asset_id: string;
  filename: string;
  sha256: string;
  byte_size: number;
  media_type: string;
}

export interface SubmissionEvent {
  event_id: string;
  venue: string;
  round: number;
  status: string;
  detail?: string | null;
  created_at: string;
  binding?: {
    status: 'BOUND' | 'UNBOUND';
    snapshot?: {
      generated_version: {
        manuscript_version_id: string;
        version: number;
        document_revision: number;
        content_sha256: string;
        inputs_sha256: string;
        job_id: string;
        template_manifest: unknown;
      };
      parent_event_id: string | null;
      accepted_event_id: string | null;
      files?: { final: PublicationFile; proof: PublicationFile };
    };
    snapshot_sha256?: string;
  };
}

export interface PublicationState {
  accepted_event_id: string | null;
  accepted_generated_version_id: string | null;
  completion: null | {
    event_id: string;
    generated_version_id: string;
    status: 'CURRENT' | 'STALE' | 'UNAVAILABLE';
    files: { final: PublicationFile; proof: PublicationFile };
  };
}

export type WorkflowStage =
  | 'PLANNING'
  | 'DRAFTING'
  | 'WHOLE_PAPER_REVIEW'
  | 'FINALIZATION_SUBMISSION'
  | 'REVISION'
  | 'PUBLICATION';

export interface AssetRecord {
  asset_id: string;
  filename: string;
  media_type: string;
  asset_kind: 'FIGURE' | 'TABLE' | 'DOCUMENT';
  status: string;
  metadata: Record<string, unknown>;
}

export interface StudioJob {
  job_id: string;
  job_kind: string;
  status: string;
  input_revision: number;
  result?: Record<string, unknown>;
  error?: { message?: string; issues?: Array<{ path: string; message: string }> };
}

export interface SubmissionPackage {
  package_id: string;
  manuscript_id: string;
  job_id: string;
  created_at: string;
  input_revision: number;
  generated_version_id: string;
  generated_version_number: number | null;
  review_round_id: string | null;
  round_number: number | null;
  baseline_manuscript_version_id: string | null;
  unresolved_comment_ids: string[];
  location_summary: { unknown_or_unattributed_rows?: number } | null;
  integrity_status: 'RECORDED_AT_PACKAGING' | 'LEGACY_ORIGINAL_DIGEST_UNAVAILABLE';
  files: Array<{ name: string; available: boolean; size_bytes: number | null; sha256: string | null }>;
}

export interface Workspace {
  publication?: PublicationState;
  manuscript: Manuscript;
  workflow_stage: WorkflowStage;
  document_revision: number;
  document: StudioDocument;
  active_generated_version_id: string | null;
  last_generated_revision: number | null;
  generated_is_stale: boolean;
  assets: AssetRecord[];
  latest_job: StudioJob | null;
  artifacts: Array<{
    artifact_id: string;
    artifact_kind: string;
    storage_path: string;
    created_at: string;
  }>;
  findings: Array<{
    finding_id: string;
    generated_version_id: string;
    finding_kind: string;
    severity: string;
    anchor: Record<string, unknown>;
    detail: string;
    source: string;
    status: string;
  }>;
  template_instances: Array<{
    template_instance_id: string;
    source_skeleton_id?: string;
    source_version?: string;
    adopted: Record<string, unknown>;
  }>;
}

export interface SourceEvidence {
  evidence_id: string;
  statement: string;
  excerpt: string;
  relation: string;
  confidence: number;
  title?: string;
  authors: string[];
  published_year?: number;
  landing_url?: string;
  pdf_url?: string;
}

export interface SampleBlock {
  unit_id: string;
  skeleton_id?: string;
  version?: number;
  section?: string;
  raw_text: string;
  layer: string;
  layer3: Record<string, unknown>;
  layer4?: string;
  title: string;
  paper_id: string;
}

export interface ChatMessage {
  message_id: string;
  role: 'AUTHOR' | 'AGENT';
  content: string;
  anchor_type: string;
  anchor_id?: string;
  anchor_revision: number;
  quoted: Record<string, unknown>;
  status: string;
  created_at: string;
}

export type SuggestionOutcome = 'ACCEPT_ALL' | 'ACCEPT_PARTIAL' | 'REJECT';

export interface StudioSuggestionChange {
  change_id: string;
  action: 'SET_FIELD' | 'REPLACE_TEXT' | 'ADD_SOURCE' | 'INSERT_INTENT' | 'INSERT_PARAGRAPH';
  target_type: string;
  target_id: string;
  target_label: string;
  field?: string;
  before: string | string[];
  value?: string | { label?: string; purpose?: string; paradigm?: string; intents?: Array<{ label: string }> };
  quote?: AuthorQuote;
  evidence?: SourceEvidence;
}

export interface StudioSuggestion {
  suggestion_id: string;
  kind: 'STRUCTURE' | 'SOURCE' | 'WORDING';
  title: string;
  rationale: string;
  changes: StudioSuggestionChange[];
}

export interface SuggestionDecisionRequest {
  suggestion_id: string;
  decision_id: string;
  outcome: SuggestionOutcome;
  base_revision: number;
  selected_change_ids: string[];
  confirmed_changed_ids: string[];
  comment_ids: string[];
}

export interface SuggestionDecision {
  decision_id: string;
  outcome: SuggestionOutcome;
  operation_id: string | null;
  request: Omit<SuggestionDecisionRequest, 'decision_id'> & { manuscript_id: string; message_id: string };
  provenance: { author_revision_at_decision: number; source: ChatContext['quote']['source'] };
  created_at: string;
}

export interface SuggestionPreview {
  suggestion: StudioSuggestion;
  source: ChatContext['quote']['source'];
  document_revision: number;
  changes: Array<StudioSuggestionChange & {
    available: boolean;
    already_adopted: boolean;
    target_changed: boolean;
    current_before: string | string[] | null;
    current_label?: string;
    after_preview?: string;
    range_changed?: boolean;
    source_unavailable?: boolean;
  }>;
  decisions: SuggestionDecision[];
}

export interface SuggestionDecisionResponse {
  decision: SuggestionDecision;
  workspace: Workspace;
  idempotent_replay: boolean;
}

export interface AuthorQuote {
  text?: string;
  start?: number;
  end?: number;
  offset_unit?: 'utf16';
  annotation?: string;
  generated_version_id?: string;
}

export interface GeneratedReference extends Partial<SourceEvidence> {
  evidence_id: string;
  citation_index: number;
  source_snapshot_available: boolean;
  source_context?: {
    available: boolean;
    reason?: string;
    paper_version_id?: string;
    paper_version?: number;
    skeleton_id?: string;
    version?: number;
    file_version_id?: string;
    parse_run_id?: string;
    context_sha256?: string;
    unit?: OriginalSourceUnit;
    units?: OriginalSourceUnit[];
    parsed_blocks?: Array<{ block_id: string; text: string; page_number?: number; section?: string }>;
    full_text_available?: boolean;
    full_text_reason?: string | null;
    file_version?: { file_version_id: string; sha256: string; size_bytes: number } | null;
  };
  doi?: string;
  location?: Record<string, unknown>;
}

export interface EvidenceSourceDetails extends SourceEvidence {
  location?: Record<string, unknown>;
  source_context?: GeneratedReference['source_context'];
}

export interface OriginalSourceUnit {
  unit_id: string;
  raw_text: string;
  page_idx?: number;
  section?: string;
  seq_idx: number;
}

export interface GeneratedMaterial {
  asset_id: string;
  filename: string;
  media_type: string;
  asset_kind: string;
  sha256: string;
  size_bytes: number;
  display_kind: 'FIGURE' | 'TABLE' | 'ATTACHMENT';
  source_file: string;
  render_file?: string;
  render_sha256?: string;
  width?: number;
  height?: number;
  tables?: Array<{ title: string; rows: string[][]; row_count: number; column_count: number }>;
}

export interface GeneratedBlock {
  kind: 'title' | 'heading' | 'paragraph';
  object_id: string;
  anchor_id: string;
  text: string;
  display_text: string;
  label: string;
  section_id?: string;
  group_id?: string;
  heading_level?: number;
  thought_ids?: string[];
  formulas?: ParagraphBlock['formulas'];
  assets?: GeneratedMaterial[];
}

export interface GeneratedVersion {
  manuscript_id: string;
  generated_version_id: string;
  version: number;
  input_revision: number | null;
  structure_mapping_available: boolean;
  content: string;
  blocks: GeneratedBlock[];
  references: GeneratedReference[];
  citation_style: 'numeric_first_use' | 'legacy';
  artifacts: Workspace['artifacts'];
}

export interface ChatContext {
  message_id: string;
  quote: AuthorQuote & {
    object_text: string;
    source: { label: string; manuscript_id: string; anchor_type: string; anchor_id: string | null; anchor_revision: number; generated_version_id?: string; generated_version?: number; author_revision_known?: boolean };
  };
  generated?: GeneratedVersion;
  block?: GeneratedBlock;
  snapshot?: { manuscript_id: string; revision: number; document: StudioDocument };
}

export interface ReviewComment {
  content_sha256: string;
  response_state_sha256: string;
  response_verification: ResponseVerification;
  round_number?: number;
  reviewer?: string | null;
  comment_id: string;
  display_label: string;
  review_round_id: string;
  original_text: string;
  edited_text: string;
  author_decision?: string;
  response_text?: string;
  status: string;
  archived_at?: string;
  import_metadata?: Record<string, unknown>;
  changes: Array<{
    change_id: string;
    operation_id: string;
    before_json: string;
    after_json: string;
  }>;
}

export interface ResponseVerification {
  status: 'NOT_REVIEWED' | 'LEGACY_UNVERIFIED' | 'CURRENT' | 'STALE';
  checked_at?: string;
  outcome?: 'MODIFIED' | 'EXPLAINED_NO_CHANGE';
  generated_version_id?: string;
}

export interface ReplyAssertion {
  start: number;
  end: number;
  text: string;
  offset_unit: 'utf16';
  evidence_ids: string[];
}

export interface ResponseReviewRequest {
  request_id: string;
  context_sha256: string;
  outcome: 'MODIFIED' | 'EXPLAINED_NO_CHANGE';
  claims: ReplyAssertion[];
  acknowledged_all_assertions: boolean;
}

export interface ReviewCitationSource {
  citation_index: number;
  title: string;
  page: number | null;
  section: string | null;
  unit_number: number | null;
  paper_version: number | null;
}

export interface ResponseReviewContext {
  context_sha256: string;
  state: {
    response_text: string;
    author_decision: string;
    current_author_revision: number;
    generated_input_revision: number | null;
    archived_at: string | null;
    round_number: number;
  };
  baseline_available: boolean;
  baseline_version_number: number | null;
  pdf_artifact_id: string | null;
  target_version_number: number;
  baseline_to_target_diff: string;
  baseline_to_target_display_diff?: string;
  baseline_citation_sources?: ReviewCitationSource[];
  target_citation_sources?: ReviewCitationSource[];
  evidence: Array<{
    evidence_id: string;
    change_id: string;
    status: string;
    changed_text: string;
    display_changed_text?: string;
    reason: string;
    final_page: number | null;
    final_line: number | null;
    final_page_end: number | null;
    final_line_end: number | null;
  }>;
  history: Array<{
    check_id: string;
    created_at: string;
    outcome: string;
    context: Omit<ResponseReviewContext, 'history' | 'verification'>;
    request: ResponseReviewRequest;
  }>;
  verification: ResponseVerification;
}

export interface ReviewRound {
  review_round_id: string;
  manuscript_id: string;
  round_number: number;
  venue: string | null;
  status: string;
  baseline_manuscript_version_id: string | null;
  baseline_version: number | null;
  baseline_document_revision: number | null;
  baseline_available: boolean;
  baseline_origin: string;
  baseline_content_sha256?: string;
}

export interface ChangeAssociationRequest {
  request_id: string;
  expected_link_revision: number;
  comment_ids: string[];
  reverses_event_id?: string | null;
}

export interface ChangeAssociationEvent {
  event_id: string;
  request_id: string;
  base_link_revision: number;
  resulting_link_revision: number;
  before_comment_ids: string[];
  after_comment_ids: string[];
  reverses_event_id: string | null;
  created_at: string;
}

export interface StudioChange {
  change_id: string;
  operation_id: string;
  base_revision: number;
  resulting_revision: number;
  operation_kind: string;
  is_compensating: number;
  before_json: string;
  after_json: string;
  author_diff: string;
  structure_changed: boolean;
  comment_ids: string[];
  initial_comment_ids: string[];
  association_revision: number;
  association_origin: string;
  association_events: ChangeAssociationEvent[];
  created_at: string;
}

export interface TrackRecord {
  track_id: string;
  title: string;
  scope?: string;
  manuscripts: Array<{
    manuscript_id: string;
    title: string;
    workflow_stage: WorkflowStage;
    updated_at: string;
  }>;
}
