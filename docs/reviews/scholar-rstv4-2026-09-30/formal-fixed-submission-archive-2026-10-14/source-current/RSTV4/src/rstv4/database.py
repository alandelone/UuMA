from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

WORKSPACE_ACTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_workspace_actions (
  action_seq INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT NOT NULL UNIQUE,
  request_json TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_workspace_actions_object
  ON research_workspace_actions(object_type, object_id, action_seq);
"""

CATALOG_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version (
  component TEXT PRIMARY KEY,
  version INTEGER NOT NULL,
  applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS papers (
  paper_id TEXT PRIMARY KEY,
  canonical_key TEXT NOT NULL UNIQUE,
  doi TEXT UNIQUE,
  normalized_title TEXT NOT NULL,
  title TEXT NOT NULL,
  authors_json TEXT NOT NULL,
  published_year INTEGER,
  abstract TEXT,
  landing_url TEXT,
  pdf_url TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_sources (
  paper_source_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  provider TEXT NOT NULL,
  external_id TEXT,
  retrieved_at TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  UNIQUE(provider, external_id)
);
CREATE TABLE IF NOT EXISTS retrieval_runs (
  retrieval_id TEXT PRIMARY KEY,
  query TEXT NOT NULL,
  provider TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  started_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE TABLE IF NOT EXISTS research_fields (
  field_id TEXT PRIMARY KEY,
  normalized_name TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topics (
  topic_id TEXT PRIMARY KEY,
  normalized_name TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS field_topics (
  field_id TEXT NOT NULL REFERENCES research_fields(field_id),
  topic_id TEXT NOT NULL REFERENCES topics(topic_id),
  created_at TEXT NOT NULL,
  PRIMARY KEY(field_id, topic_id)
);
CREATE TABLE IF NOT EXISTS foundations (
  foundation_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS foundation_versions (
  foundation_id TEXT NOT NULL REFERENCES foundations(foundation_id),
  version INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(foundation_id, version),
  UNIQUE(foundation_id, content_digest)
);
CREATE TABLE IF NOT EXISTS foundation_topics (
  foundation_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  topic_id TEXT NOT NULL REFERENCES topics(topic_id),
  PRIMARY KEY(foundation_id, version, topic_id),
  FOREIGN KEY(foundation_id, version)
    REFERENCES foundation_versions(foundation_id, version)
);
"""

RESEARCH_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version (
  component TEXT PRIMARY KEY,
  version INTEGER NOT NULL,
  applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project (
  project_id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  field TEXT NOT NULL,
  research_type TEXT NOT NULL,
  type_payload_json TEXT NOT NULL,
  scope TEXT,
  status TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_nodes (
  node_id TEXT PRIMARY KEY,
  node_type TEXT NOT NULL,
  status TEXT NOT NULL,
  statement TEXT NOT NULL,
  rationale TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_edges (
  edge_id TEXT PRIMARY KEY,
  source_node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  target_node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  relation TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(source_node_id, target_node_id, relation)
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL,
  statement TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  location TEXT NOT NULL,
  relation TEXT NOT NULL,
  confidence REAL NOT NULL,
  extractor_model TEXT,
  prompt_version TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS node_evidence (
  node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  PRIMARY KEY(node_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS decisions (
  proposal_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL UNIQUE REFERENCES research_nodes(node_id),
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  approval_phrase TEXT NOT NULL,
  expected_revision INTEGER NOT NULL,
  confirmation_text TEXT,
  rejection_reason TEXT,
  supersedes_node_id TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS approval_grants (
  grant_id TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL,
  proposal_type TEXT NOT NULL,
  project_slug TEXT NOT NULL,
  proposal_revision INTEGER NOT NULL,
  profile TEXT NOT NULL,
  session_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  user_message_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  consumed_at TEXT,
  UNIQUE(profile, session_id, message_id, proposal_id)
);
CREATE TABLE IF NOT EXISTS experiment_plans (
  plan_id TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL UNIQUE,
  method_node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  status TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  argv_json TEXT NOT NULL,
  working_directory TEXT NOT NULL,
  script_path TEXT,
  script_sha256 TEXT,
  timeout_seconds INTEGER NOT NULL,
  metrics_json_path TEXT,
  created_at TEXT NOT NULL,
  approved_at TEXT
);
CREATE TABLE IF NOT EXISTS evidence_assessments (
  assessment_id TEXT PRIMARY KEY,
  claim_node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  verdict TEXT NOT NULL,
  rationale TEXT NOT NULL,
  conditions_json TEXT NOT NULL,
  counterevidence_json TEXT NOT NULL,
  assessor_model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  evidence_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(claim_node_id, evidence_id, assessor_model, prompt_version, evidence_digest)
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  operation TEXT NOT NULL,
  status TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blueprint_snapshots (
  blueprint_id TEXT PRIMARY KEY,
  track_id TEXT,
  revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_fields (
  field_id TEXT NOT NULL,
  scope TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY(field_id)
);
CREATE TABLE IF NOT EXISTS project_topics (
  topic_id TEXT NOT NULL,
  scope TEXT,
  role TEXT NOT NULL DEFAULT 'PRIMARY',
  created_at TEXT NOT NULL,
  PRIMARY KEY(topic_id)
);
CREATE TABLE IF NOT EXISTS research_tracks (
  track_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  scope TEXT,
  research_type TEXT NOT NULL,
  status TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  is_default INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS track_topics (
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  topic_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(track_id, topic_id)
);
CREATE TABLE IF NOT EXISTS track_phase_status (
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  phase TEXT NOT NULL,
  status TEXT NOT NULL,
  blocker TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(track_id, phase)
);
CREATE TABLE IF NOT EXISTS adopted_foundations (
  adoption_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  foundation_id TEXT NOT NULL,
  foundation_version INTEGER NOT NULL,
  content_digest TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  adopted_at TEXT NOT NULL,
  UNIQUE(track_id, foundation_id, foundation_version)
);
CREATE TABLE IF NOT EXISTS manuscripts (
  manuscript_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  title TEXT NOT NULL,
  scope TEXT,
  research_type TEXT NOT NULL,
  writing_status TEXT NOT NULL,
  needs_scientific_review INTEGER NOT NULL DEFAULT 0,
  blocker TEXT,
  next_step TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manuscript_nodes (
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  section TEXT,
  node_revision INTEGER NOT NULL,
  PRIMARY KEY(manuscript_id, node_id)
);
CREATE TABLE IF NOT EXISTS manuscript_evidence (
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  evidence_digest TEXT NOT NULL,
  PRIMARY KEY(manuscript_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS manuscript_versions (
  manuscript_version_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  version INTEGER NOT NULL,
  content TEXT NOT NULL,
  inputs_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(manuscript_id, version)
);
CREATE TABLE IF NOT EXISTS manuscript_status_history (
  history_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  status TEXT NOT NULL,
  blocker TEXT,
  next_step TEXT,
  reason TEXT NOT NULL,
  revision INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submission_events (
  event_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  venue TEXT NOT NULL,
  round INTEGER NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
"""

TRACK_FIRST_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS research_tracks (
  track_id TEXT PRIMARY KEY,
  field_id TEXT REFERENCES research_fields(field_id),
  primary_topic_id TEXT REFERENCES topics(topic_id),
  title TEXT NOT NULL,
  scope TEXT,
  research_type TEXT NOT NULL,
  status TEXT NOT NULL,
  mapping_status TEXT NOT NULL DEFAULT 'MAPPED',
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS track_topics (
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  topic_id TEXT NOT NULL REFERENCES topics(topic_id),
  role TEXT NOT NULL CHECK(role IN ('PRIMARY','SECONDARY')),
  created_at TEXT NOT NULL,
  PRIMARY KEY(track_id, topic_id)
);
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  research_type TEXT NOT NULL,
  type_payload_json TEXT NOT NULL,
  scope TEXT,
  status TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS track_milestones (
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  milestone TEXT NOT NULL,
  status TEXT NOT NULL,
  blocker TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(track_id, milestone)
);
CREATE TABLE IF NOT EXISTS research_nodes (
  node_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  node_type TEXT NOT NULL,
  status TEXT NOT NULL,
  statement TEXT NOT NULL,
  rationale TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_edges (
  edge_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  source_node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  target_node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  relation TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(source_node_id, target_node_id, relation)
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  scope_kind TEXT NOT NULL CHECK(scope_kind IN ('FIELDKG','TRACK')),
  field_id TEXT REFERENCES research_fields(field_id),
  track_id TEXT REFERENCES research_tracks(track_id),
  paper_id TEXT REFERENCES papers(paper_id),
  paper_version_id TEXT,
  experiment_run_id TEXT,
  statement TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  location_json TEXT NOT NULL,
  relation TEXT NOT NULL,
  confidence REAL NOT NULL,
  extractor_model TEXT,
  prompt_version TEXT,
  content_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS node_evidence (
  node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  PRIMARY KEY(node_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS decisions (
  proposal_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  node_id TEXT NOT NULL UNIQUE REFERENCES research_nodes(node_id),
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  approval_phrase TEXT NOT NULL,
  expected_revision INTEGER NOT NULL,
  confirmation_text TEXT,
  rejection_reason TEXT,
  supersedes_node_id TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS approval_grants (
  grant_id TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL,
  proposal_type TEXT NOT NULL,
  track_id TEXT NOT NULL,
  project_id TEXT,
  proposal_revision INTEGER NOT NULL,
  profile TEXT NOT NULL,
  session_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  user_message_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  consumed_at TEXT,
  UNIQUE(profile, session_id, message_id, proposal_id)
);
CREATE TABLE IF NOT EXISTS experiment_plans (
  plan_id TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL UNIQUE,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  project_id TEXT REFERENCES projects(project_id),
  method_node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  status TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  argv_json TEXT NOT NULL,
  working_directory TEXT NOT NULL,
  script_path TEXT,
  script_sha256 TEXT,
  timeout_seconds INTEGER NOT NULL,
  metrics_json_path TEXT,
  created_at TEXT NOT NULL,
  approved_at TEXT
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  project_id TEXT REFERENCES projects(project_id),
  operation TEXT NOT NULL,
  status TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blueprint_snapshots (
  blueprint_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(track_id, revision)
);
CREATE TABLE IF NOT EXISTS manuscripts (
  manuscript_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  title TEXT NOT NULL,
  scope TEXT,
  research_type TEXT NOT NULL,
  writing_status TEXT NOT NULL,
  needs_scientific_review INTEGER NOT NULL DEFAULT 0,
  blocker TEXT,
  next_step TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manuscript_projects (
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  PRIMARY KEY(manuscript_id, project_id)
);
CREATE TABLE IF NOT EXISTS manuscript_nodes (
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  node_id TEXT NOT NULL REFERENCES research_nodes(node_id),
  section TEXT,
  node_revision INTEGER NOT NULL,
  PRIMARY KEY(manuscript_id, node_id)
);
CREATE TABLE IF NOT EXISTS manuscript_evidence (
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  evidence_digest TEXT NOT NULL,
  PRIMARY KEY(manuscript_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS manuscript_versions (
  manuscript_version_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  version INTEGER NOT NULL,
  content TEXT NOT NULL,
  inputs_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(manuscript_id, version)
);
CREATE TABLE IF NOT EXISTS manuscript_status_history (
  history_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  status TEXT NOT NULL,
  blocker TEXT,
  next_step TEXT,
  reason TEXT NOT NULL,
  revision INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submission_events (
  event_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  venue TEXT NOT NULL,
  round INTEGER NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_versions (
  paper_version_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  version INTEGER NOT NULL,
  pdf_path TEXT,
  pdf_digest TEXT,
  parsed_path TEXT,
  parsed_digest TEXT,
  source_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(paper_id, version),
  UNIQUE(paper_id, pdf_digest, parsed_digest)
);
CREATE TABLE IF NOT EXISTS paper_skeletons (
  skeleton_id TEXT PRIMARY KEY,
  paper_version_id TEXT NOT NULL REFERENCES paper_versions(paper_version_id),
  version INTEGER NOT NULL,
  extractor_model TEXT,
  prompt_version TEXT,
  content_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(paper_version_id, version),
  UNIQUE(paper_version_id, content_digest)
);
CREATE TABLE IF NOT EXISTS skeleton_units (
  unit_id TEXT PRIMARY KEY,
  skeleton_id TEXT NOT NULL REFERENCES paper_skeletons(skeleton_id),
  seq_idx INTEGER NOT NULL,
  page_idx INTEGER,
  section TEXT,
  raw_text TEXT NOT NULL,
  layer1_json TEXT NOT NULL,
  layer2_json TEXT NOT NULL,
  layer3_json TEXT NOT NULL,
  layer4 TEXT,
  content_digest TEXT NOT NULL,
  UNIQUE(skeleton_id, seq_idx)
);
CREATE TABLE IF NOT EXISTS skeleton_triplets (
  triplet_id TEXT PRIMARY KEY,
  unit_id TEXT NOT NULL REFERENCES skeleton_units(unit_id),
  subject TEXT NOT NULL,
  predicate TEXT NOT NULL,
  object TEXT NOT NULL,
  content_digest TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fieldkg_builds (
  build_id TEXT PRIMARY KEY,
  field_id TEXT NOT NULL REFERENCES research_fields(field_id),
  status TEXT NOT NULL,
  retrieval_scope_json TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fieldkg_build_papers (
  build_id TEXT NOT NULL REFERENCES fieldkg_builds(build_id),
  paper_version_id TEXT NOT NULL REFERENCES paper_versions(paper_version_id),
  skeleton_id TEXT REFERENCES paper_skeletons(skeleton_id),
  status TEXT NOT NULL,
  detail TEXT,
  PRIMARY KEY(build_id, paper_version_id)
);
CREATE TABLE IF NOT EXISTS fieldkg_evidence_candidates (
  candidate_id TEXT PRIMARY KEY,
  build_id TEXT NOT NULL REFERENCES fieldkg_builds(build_id),
  field_id TEXT NOT NULL REFERENCES research_fields(field_id),
  unit_id TEXT NOT NULL REFERENCES skeleton_units(unit_id),
  statement TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  relation TEXT NOT NULL,
  confidence REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'PROPOSED',
  rationale TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS fieldkg_candidate_gaps (
  candidate_gap_id TEXT PRIMARY KEY,
  build_id TEXT NOT NULL REFERENCES fieldkg_builds(build_id),
  field_id TEXT NOT NULL REFERENCES research_fields(field_id),
  statement TEXT NOT NULL,
  rationale TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL,
  counterevidence_ids_json TEXT NOT NULL,
  conditions_json TEXT NOT NULL,
  generator_model TEXT,
  prompt_version TEXT,
  status TEXT NOT NULL DEFAULT 'PROPOSED',
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS fieldkg_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  field_id TEXT REFERENCES research_fields(field_id),
  version INTEGER NOT NULL,
  build_id TEXT REFERENCES fieldkg_builds(build_id),
  status TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  mapping_status TEXT NOT NULL DEFAULT 'MAPPED',
  created_at TEXT NOT NULL,
  UNIQUE(field_id, version),
  UNIQUE(field_id, content_digest)
);
CREATE TABLE IF NOT EXISTS fieldkg_snapshot_members (
  snapshot_id TEXT NOT NULL REFERENCES fieldkg_snapshots(snapshot_id),
  member_type TEXT NOT NULL,
  member_id TEXT NOT NULL,
  member_digest TEXT NOT NULL,
  PRIMARY KEY(snapshot_id, member_type, member_id)
);
CREATE TABLE IF NOT EXISTS track_snapshot_adoptions (
  adoption_id TEXT PRIMARY KEY,
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  snapshot_id TEXT NOT NULL REFERENCES fieldkg_snapshots(snapshot_id),
  snapshot_digest TEXT NOT NULL,
  adopted_at TEXT NOT NULL,
  UNIQUE(track_id, snapshot_id)
);
CREATE TABLE IF NOT EXISTS projection_outbox (
  job_id TEXT PRIMARY KEY,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  field_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projection_watermarks (
  projection_name TEXT PRIMARY KEY,
  last_job_id TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS legacy_migration_sources (
  source_path TEXT PRIMARY KEY,
  source_digest TEXT NOT NULL,
  project_id TEXT,
  default_track_id TEXT,
  status TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  migrated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tracks_field ON research_tracks(field_id);
CREATE INDEX IF NOT EXISTS idx_projects_track ON projects(track_id);
CREATE INDEX IF NOT EXISTS idx_nodes_track ON research_nodes(track_id);
CREATE INDEX IF NOT EXISTS idx_evidence_field ON evidence(field_id);
CREATE INDEX IF NOT EXISTS idx_fieldkg_build_field ON fieldkg_builds(field_id);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON projection_outbox(status, created_at);
"""

ACQUISITION_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_identities (
  identity_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  scheme TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  status TEXT NOT NULL,
  source TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  UNIQUE(scheme, normalized_value)
);
CREATE TABLE IF NOT EXISTS metadata_observations (
  observation_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  provider TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  UNIQUE(paper_id, provider, payload_digest)
);
CREATE TABLE IF NOT EXISTS source_file_versions (
  file_version_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  mime_type TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  acquisition_method TEXT NOT NULL,
  source_url TEXT,
  identity_status TEXT NOT NULL,
  validation_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(paper_id, sha256)
);
CREATE TABLE IF NOT EXISTS parse_runs (
  parse_run_id TEXT PRIMARY KEY,
  file_version_id TEXT NOT NULL REFERENCES source_file_versions(file_version_id),
  parser_name TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  config_digest TEXT NOT NULL,
  status TEXT NOT NULL,
  artifact_manifest_json TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  UNIQUE(file_version_id, parser_name, parser_version, config_digest)
);
CREATE TABLE IF NOT EXISTS document_blocks (
  block_id TEXT PRIMARY KEY,
  parse_run_id TEXT NOT NULL REFERENCES parse_runs(parse_run_id),
  sequence INTEGER NOT NULL,
  page_number INTEGER,
  section TEXT,
  block_type TEXT NOT NULL,
  text TEXT NOT NULL,
  location_json TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  UNIQUE(parse_run_id, sequence)
);
CREATE TABLE IF NOT EXISTS skeleton_runs (
  skeleton_run_id TEXT PRIMARY KEY,
  parse_run_id TEXT NOT NULL REFERENCES parse_runs(parse_run_id),
  model_tier TEXT NOT NULL,
  model_name TEXT,
  prompt_version TEXT NOT NULL,
  context_builder_version TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE TABLE IF NOT EXISTS skeleton_checkpoints (
  checkpoint_id TEXT PRIMARY KEY,
  skeleton_run_id TEXT NOT NULL REFERENCES skeleton_runs(skeleton_run_id),
  section_key TEXT NOT NULL,
  layer INTEGER NOT NULL CHECK(layer BETWEEN 1 AND 4),
  input_digest TEXT NOT NULL,
  output_json TEXT,
  status TEXT NOT NULL,
  model_name TEXT,
  prompt_version TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(skeleton_run_id, section_key, layer, input_digest)
);
CREATE TABLE IF NOT EXISTS collections (
  collection_id TEXT PRIMARY KEY,
  field_id TEXT NOT NULL REFERENCES research_fields(field_id),
  track_id TEXT REFERENCES research_tracks(track_id),
  name TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  scope_version INTEGER NOT NULL,
  status TEXT NOT NULL,
  revision INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_seeds (
  seed_id TEXT PRIMARY KEY,
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  seed_type TEXT NOT NULL,
  raw_value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  paper_id TEXT REFERENCES papers(paper_id),
  created_at TEXT NOT NULL,
  UNIQUE(collection_id, seed_type, normalized_value)
);
CREATE TABLE IF NOT EXISTS collection_memberships (
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  discovery_kind TEXT NOT NULL,
  discovered_from_paper_id TEXT REFERENCES papers(paper_id),
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(collection_id, paper_id)
);
CREATE TABLE IF NOT EXISTS reference_entries (
  reference_entry_id TEXT PRIMARY KEY,
  citing_paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  file_version_id TEXT NOT NULL REFERENCES source_file_versions(file_version_id),
  raw_text TEXT NOT NULL,
  page_number INTEGER,
  location_json TEXT NOT NULL,
  target_paper_id TEXT REFERENCES papers(paper_id),
  resolution_status TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(file_version_id, content_digest)
);
CREATE TABLE IF NOT EXISTS citation_observations (
  citation_id TEXT PRIMARY KEY,
  citing_paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  cited_paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  reference_entry_id TEXT NOT NULL REFERENCES reference_entries(reference_entry_id),
  role TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(citing_paper_id, cited_paper_id, reference_entry_id)
);
CREATE TABLE IF NOT EXISTS paper_assessments (
  assessment_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  field_id TEXT NOT NULL REFERENCES research_fields(field_id),
  track_id TEXT REFERENCES research_tracks(track_id),
  assessment_type TEXT NOT NULL,
  status TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  model_tier TEXT,
  model_name TEXT,
  prompt_version TEXT,
  input_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(paper_id, field_id, track_id, assessment_type, rule_version, input_digest)
);
CREATE TABLE IF NOT EXISTS journal_metric_observations (
  metric_id TEXT PRIMARY KEY,
  issn TEXT NOT NULL,
  source TEXT NOT NULL,
  metric_year INTEGER NOT NULL,
  category TEXT NOT NULL,
  quartile TEXT,
  metric_name TEXT NOT NULL,
  metric_value REAL,
  payload_json TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  UNIQUE(issn, source, metric_year, category, metric_name)
);
CREATE TABLE IF NOT EXISTS paper_journal_links (
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  issn TEXT NOT NULL,
  provider TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  PRIMARY KEY(paper_id, issn, provider)
);
CREATE TABLE IF NOT EXISTS core_rankings (
  ranking_id TEXT PRIMARY KEY,
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  scope_kind TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  rank INTEGER NOT NULL,
  relevance_group TEXT NOT NULL,
  seed_coverage REAL NOT NULL,
  direct_citations INTEGER NOT NULL,
  quartile TEXT,
  labels_json TEXT NOT NULL,
  explanation_json TEXT NOT NULL,
  graph_digest TEXT NOT NULL,
  algorithm_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(collection_id, paper_id, scope_kind, scope_id, graph_digest, algorithm_version)
);
CREATE TABLE IF NOT EXISTS acquisition_jobs (
  job_id TEXT PRIMARY KEY,
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  paper_id TEXT REFERENCES papers(paper_id),
  job_type TEXT NOT NULL,
  queue_class TEXT NOT NULL,
  status TEXT NOT NULL,
  priority INTEGER NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  input_json TEXT NOT NULL,
  input_digest TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  available_at TEXT NOT NULL,
  lease_owner TEXT,
  lease_expires_at TEXT,
  fencing_token INTEGER NOT NULL DEFAULT 0,
  last_error_code TEXT,
  last_error_detail TEXT,
  result_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS acquisition_attempts (
  attempt_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES acquisition_jobs(job_id),
  fencing_token INTEGER NOT NULL,
  worker_id TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  detail_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS provider_cooldowns (
  provider TEXT PRIMARY KEY,
  cooldown_until TEXT NOT NULL,
  reason TEXT NOT NULL,
  failure_count INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS browser_acquisition_requests (
  request_id TEXT PRIMARY KEY,
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  idempotency_key TEXT NOT NULL UNIQUE,
  action_id TEXT,
  action_version TEXT,
  execution_id TEXT,
  status TEXT NOT NULL,
  expected_identity_json TEXT NOT NULL,
  target_directory TEXT NOT NULL,
  output_refs_json TEXT NOT NULL,
  error_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS legacy_paper_mappings (
  source_database TEXT NOT NULL,
  legacy_id INTEGER NOT NULL,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  file_version_id TEXT REFERENCES source_file_versions(file_version_id),
  status TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  PRIMARY KEY(source_database, legacy_id)
);
CREATE TABLE IF NOT EXISTS local_pdf_imports (
  source_path TEXT PRIMARY KEY,
  root_path TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  sha256 TEXT,
  title_candidate TEXT NOT NULL,
  doi_candidate TEXT,
  paper_id TEXT REFERENCES papers(paper_id),
  file_version_id TEXT REFERENCES source_file_versions(file_version_id),
  status TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_quarantine (
  paper_id TEXT PRIMARY KEY REFERENCES papers(paper_id),
  reason TEXT NOT NULL,
  source_path TEXT NOT NULL,
  quarantined_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_local_pdf_imports_status
  ON local_pdf_imports(status, source_path);
CREATE INDEX IF NOT EXISTS idx_acq_jobs_claim
  ON acquisition_jobs(status, queue_class, available_at, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_collection_members_paper
  ON collection_memberships(paper_id, collection_id);
CREATE INDEX IF NOT EXISTS idx_reference_target
  ON reference_entries(target_paper_id, citing_paper_id);
CREATE INDEX IF NOT EXISTS idx_citation_cited
  ON citation_observations(cited_paper_id, citing_paper_id);
"""

CATALOG_REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS manuscript_scientific_review_requests (
  review_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  track_id TEXT NOT NULL REFERENCES research_tracks(track_id),
  expected_revision INTEGER NOT NULL,
  request_json TEXT NOT NULL,
  context_json TEXT NOT NULL,
  context_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manuscript_scientific_review_events (
  event_id TEXT PRIMARY KEY,
  review_id TEXT NOT NULL UNIQUE REFERENCES manuscript_scientific_review_requests(review_id),
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  grant_id TEXT NOT NULL REFERENCES approval_grants(grant_id),
  before_json TEXT NOT NULL,
  after_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_review_actions (
  action_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  case_id TEXT NOT NULL,
  file_version_id TEXT NOT NULL REFERENCES source_file_versions(file_version_id),
  action_kind TEXT NOT NULL,
  reviewer_label TEXT NOT NULL,
  reason TEXT NOT NULL,
  request_json TEXT NOT NULL,
  context_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  supersedes_action_id TEXT REFERENCES catalog_review_actions(action_id),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_review_actions_case
  ON catalog_review_actions(case_id,created_at);
CREATE TABLE IF NOT EXISTS catalog_review_findings (
  finding_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL UNIQUE,
  case_id TEXT NOT NULL,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  file_version_id TEXT REFERENCES source_file_versions(file_version_id),
  issue_type TEXT NOT NULL,
  assessment TEXT NOT NULL,
  proposed_value TEXT,
  evidence_page INTEGER,
  evidence_quote TEXT,
  note TEXT,
  reviewer_label TEXT NOT NULL,
  supersedes_finding_id TEXT REFERENCES catalog_review_findings(finding_id),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_review_findings_case
  ON catalog_review_findings(case_id, issue_type, created_at);
CREATE TABLE IF NOT EXISTS catalog_review_annotations (
  annotation_id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL UNIQUE,
  case_id TEXT NOT NULL,
  paper_id TEXT NOT NULL REFERENCES papers(paper_id),
  file_version_id TEXT NOT NULL REFERENCES source_file_versions(file_version_id),
  field_name TEXT NOT NULL,
  decision TEXT NOT NULL,
  selected_text TEXT,
  page_number INTEGER,
  word_start INTEGER,
  word_end INTEGER,
  comment TEXT NOT NULL DEFAULT '',
  value_before TEXT,
  value_after TEXT,
  canonical_key_before TEXT,
  canonical_key_after TEXT,
  reviewer_label TEXT NOT NULL,
  supersedes_annotation_id TEXT REFERENCES catalog_review_annotations(annotation_id),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_review_annotations_case
  ON catalog_review_annotations(case_id, field_name, created_at);
"""

STUDIO_SCHEMA = """
CREATE TABLE IF NOT EXISTS studio_documents (
  manuscript_id TEXT PRIMARY KEY REFERENCES manuscripts(manuscript_id),
  revision INTEGER NOT NULL DEFAULT 0,
  document_json TEXT NOT NULL,
  active_generated_version_id TEXT,
  last_generated_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_operations (
  operation_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  base_revision INTEGER NOT NULL,
  resulting_revision INTEGER NOT NULL,
  operation_kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  inverse_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_template_instances (
  template_instance_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  source_skeleton_id TEXT,
  source_version TEXT,
  adopted_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_sample_candidates (
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  anchor_id TEXT NOT NULL,
  document_revision INTEGER NOT NULL,
  query_key TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  sample_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(manuscript_id, anchor_id, query_key, candidate_id)
);
CREATE TABLE IF NOT EXISTS studio_assets (
  asset_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  filename TEXT NOT NULL,
  media_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  asset_kind TEXT NOT NULL,
  status TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(manuscript_id, sha256)
);
CREATE TABLE IF NOT EXISTS studio_chat_messages (
  message_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  parent_message_id TEXT REFERENCES studio_chat_messages(message_id),
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  anchor_type TEXT NOT NULL,
  anchor_id TEXT,
  anchor_revision INTEGER NOT NULL,
  quoted_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_jobs (
  job_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  job_kind TEXT NOT NULL,
  status TEXT NOT NULL,
  input_revision INTEGER NOT NULL,
  request_json TEXT NOT NULL,
  result_json TEXT,
  error_json TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT
);
CREATE TABLE IF NOT EXISTS studio_model_calls (
  call_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  job_id TEXT REFERENCES studio_jobs(job_id),
  message_id TEXT REFERENCES studio_chat_messages(message_id),
  task TEXT NOT NULL,
  input_revision INTEGER NOT NULL,
  input_sha256 TEXT NOT NULL,
  input_json TEXT NOT NULL,
  output_json TEXT,
  contract_json TEXT,
  status TEXT NOT NULL,
  error_json TEXT,
  started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_studio_model_calls_owner
  ON studio_model_calls(manuscript_id,job_id,started_at);
CREATE TABLE IF NOT EXISTS studio_artifacts (
  artifact_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES studio_jobs(job_id),
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  document_revision INTEGER NOT NULL,
  artifact_kind TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_findings (
  finding_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  generated_version_id TEXT NOT NULL,
  finding_kind TEXT NOT NULL,
  severity TEXT NOT NULL,
  anchor_json TEXT NOT NULL,
  detail TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS review_rounds (
  review_round_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  round_number INTEGER NOT NULL,
  baseline_artifact_id TEXT REFERENCES studio_artifacts(artifact_id),
  venue TEXT,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(manuscript_id, round_number)
);
CREATE TABLE IF NOT EXISTS studio_review_round_baselines (
  review_round_id TEXT PRIMARY KEY REFERENCES review_rounds(review_round_id),
  baseline_manuscript_version_id TEXT REFERENCES manuscript_versions(manuscript_version_id),
  content_sha256 TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_comments (
  comment_id TEXT PRIMARY KEY,
  review_round_id TEXT NOT NULL REFERENCES review_rounds(review_round_id),
  source TEXT NOT NULL,
  reviewer TEXT,
  original_text TEXT NOT NULL,
  edited_text TEXT NOT NULL,
  author_decision TEXT,
  response_text TEXT,
  status TEXT NOT NULL,
  archived_at TEXT,
  import_metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_changes (
  change_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  operation_id TEXT NOT NULL REFERENCES studio_operations(operation_id),
  before_json TEXT NOT NULL,
  after_json TEXT NOT NULL,
  is_compensating INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comment_changes (
  comment_id TEXT NOT NULL REFERENCES review_comments(comment_id),
  change_id TEXT NOT NULL REFERENCES studio_changes(change_id),
  PRIMARY KEY(comment_id, change_id)
);
CREATE TABLE IF NOT EXISTS studio_change_link_state (
  change_id TEXT PRIMARY KEY REFERENCES studio_changes(change_id),
  initial_comment_ids_json TEXT NOT NULL,
  initial_origin TEXT NOT NULL,
  link_revision INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_change_link_events (
  event_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  change_id TEXT NOT NULL REFERENCES studio_changes(change_id),
  base_link_revision INTEGER NOT NULL,
  resulting_link_revision INTEGER NOT NULL,
  before_comment_ids_json TEXT NOT NULL,
  after_comment_ids_json TEXT NOT NULL,
  reverses_event_id TEXT REFERENCES studio_change_link_events(event_id),
  request_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_studio_change_link_events_change
  ON studio_change_link_events(change_id,resulting_link_revision);
CREATE TABLE IF NOT EXISTS studio_suggestion_decisions (
  decision_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  message_id TEXT NOT NULL REFERENCES studio_chat_messages(message_id),
  suggestion_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  operation_id TEXT REFERENCES studio_operations(operation_id),
  request_json TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_studio_suggestion_decisions_message
  ON studio_suggestion_decisions(message_id, created_at);
CREATE TABLE IF NOT EXISTS studio_submission_packages (
  package_id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  review_round_id TEXT REFERENCES review_rounds(review_round_id),
  job_id TEXT NOT NULL REFERENCES studio_jobs(job_id),
  manifest_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_response_checks (
  check_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(manuscript_id),
  comment_id TEXT NOT NULL REFERENCES review_comments(comment_id),
  generated_version_id TEXT NOT NULL REFERENCES manuscript_versions(manuscript_version_id),
  state_sha256 TEXT NOT NULL,
  context_sha256 TEXT NOT NULL,
  outcome TEXT NOT NULL,
  request_json TEXT NOT NULL,
  context_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_studio_response_checks_comment ON studio_response_checks(comment_id);
CREATE TABLE IF NOT EXISTS studio_comment_response_state (
  comment_id TEXT PRIMARY KEY REFERENCES review_comments(comment_id),
  revision INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_studio_operations_manuscript
  ON studio_operations(manuscript_id, resulting_revision);
CREATE INDEX IF NOT EXISTS idx_studio_chat_manuscript
  ON studio_chat_messages(manuscript_id, created_at);
CREATE INDEX IF NOT EXISTS idx_studio_samples_anchor
  ON studio_sample_candidates(manuscript_id, anchor_id, document_revision);
CREATE INDEX IF NOT EXISTS idx_studio_jobs_status
  ON studio_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_review_comments_round
  ON review_comments(review_round_id, status, created_at);
"""

CATALOG_VERSION = 14
RESEARCH_VERSION = 2


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


SCREENING_INPUT_SCHEMA = """
CREATE TABLE IF NOT EXISTS screening_input_snapshots (
  assessment_id TEXT PRIMARY KEY REFERENCES paper_assessments(assessment_id),
  collection_id TEXT NOT NULL REFERENCES collections(collection_id),
  context_sha256 TEXT NOT NULL,
  context_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def _migrate_skeleton_run_history(conn: sqlite3.Connection) -> None:
    """Preserve legacy runs and foreign keys while permitting additional immutable generations."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='skeleton_runs'").fetchone()
    constraint = r",\s*UNIQUE\s*\(\s*parse_run_id\s*,\s*prompt_version\s*,\s*context_builder_version\s*\)"
    if row is None or re.search(constraint, row[0]) is None:
        return
    if conn.in_transaction:
        raise RuntimeError("Skeleton history migration requires an idle connection")
    definition = row[0].replace("skeleton_runs", "skeleton_runs_history_v11", 1)
    definition = re.sub(constraint, "", definition)
    objects = conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name='skeleton_runs' AND sql IS NOT NULL AND type!='table'").fetchall()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(definition)
        conn.execute("INSERT INTO skeleton_runs_history_v11 SELECT * FROM skeleton_runs")
        conn.execute("DROP TABLE skeleton_runs")
        conn.execute("ALTER TABLE skeleton_runs_history_v11 RENAME TO skeleton_runs")
        for saved in objects:
            conn.execute(saved[0])
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Skeleton history migration broke an existing foreign key")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def initialize_catalog(path: Path) -> None:
    from .acquisition_model_calls import SCHEMA as MODEL_CALL_SCHEMA
    from .collection_runtime import SCHEMA as COLLECTION_RUNTIME_SCHEMA
    from .fieldkg_semantics import SCHEMA as FIELDKG_SEMANTIC_SCHEMA
    from .skeleton_outline import SCHEMA as SKELETON_OUTLINE_SCHEMA
    from .studio_publication import SCHEMA as STUDIO_PUBLICATION_SCHEMA

    _backup_legacy(path, "papers", CATALOG_VERSION)
    with closing(connect(path)) as conn, conn:
        conn.executescript(CATALOG_SCHEMA)
        conn.executescript(TRACK_FIRST_SCHEMA)
        conn.executescript(WORKSPACE_ACTION_SCHEMA)
        conn.executescript(ACQUISITION_SCHEMA)
        conn.executescript(CATALOG_REVIEW_SCHEMA)
        conn.executescript(SCREENING_INPUT_SCHEMA)
        conn.executescript(COLLECTION_RUNTIME_SCHEMA)
        conn.executescript(MODEL_CALL_SCHEMA)
        conn.executescript(FIELDKG_SEMANTIC_SCHEMA)
        conn.executescript(STUDIO_SCHEMA)
        conn.executescript(SKELETON_OUTLINE_SCHEMA)
        conn.executescript(STUDIO_PUBLICATION_SCHEMA)
        _ensure_column(conn, "collections", "topic_id", "TEXT REFERENCES topics(topic_id)")
        _ensure_column(conn, "collections", "creation_request_json", "TEXT")
        _ensure_column(
            conn,
            "manuscripts",
            "workflow_stage",
            "TEXT NOT NULL DEFAULT 'PLANNING'",
        )
        _migrate_skeleton_run_history(conn)
        _record_version(conn, "catalog", CATALOG_VERSION)


def initialize_project(path: Path) -> None:
    _backup_legacy(path, "project", RESEARCH_VERSION)
    with closing(connect(path)) as conn, conn:
        conn.executescript(RESEARCH_SCHEMA)
        _ensure_column(conn, "research_nodes", "track_id", "TEXT")
        _ensure_column(conn, "experiment_plans", "track_id", "TEXT")
        _ensure_column(conn, "pipeline_runs", "track_id", "TEXT")
        _ensure_column(conn, "blueprint_snapshots", "track_id", "TEXT")
        _migrate_default_track(conn)
        _record_version(conn, "research", RESEARCH_VERSION)


def migrate_legacy_projects(catalog_path: Path, projects_root: Path) -> list[dict[str, str]]:
    """Import project-first databases into the v3 global store without deleting the sources."""
    initialize_catalog(catalog_path)
    migrated: list[dict[str, str]] = []
    for source_path in sorted(projects_root.glob("*/research.db")):
        source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        with connect(catalog_path) as target:
            prior = target.execute(
                "SELECT source_digest,status FROM legacy_migration_sources WHERE source_path=?",
                (str(source_path.resolve()),),
            ).fetchone()
        if prior is not None and prior["source_digest"] == source_digest and prior["status"] == "IMPORTED":
            continue

        backup = source_path.with_suffix(".pre-track-first-v3.bak")
        if not backup.exists():
            shutil.copy2(source_path, backup)
        initialize_project(source_path)
        with connect(source_path) as source, transaction(catalog_path) as target:
            project = source.execute("SELECT * FROM project LIMIT 1").fetchone()
            if project is None:
                continue
            timestamp = project["updated_at"]
            normalized_field = " ".join(str(project["field"]).casefold().split())
            field = target.execute(
                "SELECT field_id FROM research_fields WHERE normalized_name=?", (normalized_field,)
            ).fetchone()
            if field is None:
                field_id = f"field_{hashlib.sha256(normalized_field.encode()).hexdigest()[:32]}"
                target.execute(
                    "INSERT INTO research_fields VALUES(?,?,?,?,?,?)",
                    (field_id, normalized_field, project["field"], None, project["created_at"], timestamp),
                )
            else:
                field_id = field["field_id"]

            tracks = source.execute(
                "SELECT * FROM research_tracks ORDER BY is_default DESC,created_at"
            ).fetchall()
            if not tracks:
                raise RuntimeError(f"Legacy project has no migration track: {source_path}")
            default_track_id = tracks[0]["track_id"]
            for track in tracks:
                topic_rows = source.execute(
                    "SELECT topic_id FROM track_topics WHERE track_id=? ORDER BY created_at",
                    (track["track_id"],),
                ).fetchall()
                topic_ids = [row["topic_id"] for row in topic_rows]
                primary_topic_id = topic_ids[0] if len(topic_ids) == 1 else None
                mapping_status = "MAPPED" if primary_topic_id else "NEEDS_TOPIC_MAPPING"
                target.execute(
                    """INSERT OR IGNORE INTO research_tracks(
                       track_id,field_id,primary_topic_id,title,scope,research_type,status,
                       mapping_status,revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        track["track_id"], field_id, primary_topic_id, track["title"], track["scope"],
                        track["research_type"], track["status"], mapping_status, track["revision"],
                        track["created_at"], track["updated_at"],
                    ),
                )
                for topic_id in topic_ids:
                    if target.execute("SELECT 1 FROM topics WHERE topic_id=?", (topic_id,)).fetchone():
                        target.execute(
                            "INSERT OR IGNORE INTO track_topics VALUES(?,?,?,?)",
                            (
                                track["track_id"], topic_id,
                                "PRIMARY" if topic_id == primary_topic_id else "SECONDARY",
                                track["created_at"],
                            ),
                        )
            target.execute(
                """INSERT OR IGNORE INTO projects(
                   project_id,track_id,slug,title,research_type,type_payload_json,scope,status,
                   revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    project["project_id"], default_track_id, project["slug"], project["title"],
                    project["research_type"], project["type_payload_json"], project["scope"],
                    project["status"], project["revision"], project["created_at"], project["updated_at"],
                ),
            )

            node_tracks: dict[str, str] = {}
            for row in source.execute("SELECT * FROM research_nodes").fetchall():
                track_id = row["track_id"] or default_track_id
                node_tracks[row["node_id"]] = track_id
                target.execute(
                    """INSERT OR IGNORE INTO research_nodes(
                       node_id,track_id,node_type,status,statement,rationale,payload_json,revision,
                       created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row["node_id"], track_id, row["node_type"], row["status"], row["statement"],
                        row["rationale"], row["payload_json"], row["revision"], row["created_at"],
                        row["updated_at"],
                    ),
                )
            for row in source.execute("SELECT * FROM research_edges").fetchall():
                target.execute(
                    "INSERT OR IGNORE INTO research_edges VALUES(?,?,?,?,?,?)",
                    (
                        row["edge_id"], node_tracks[row["source_node_id"]], row["source_node_id"],
                        row["target_node_id"], row["relation"], row["created_at"],
                    ),
                )

            evidence_tracks: dict[str, str] = {}
            for row in source.execute("SELECT * FROM evidence").fetchall():
                link = source.execute(
                    """SELECT n.track_id FROM node_evidence ne JOIN research_nodes n
                       ON n.node_id=ne.node_id WHERE ne.evidence_id=? AND n.track_id IS NOT NULL LIMIT 1""",
                    (row["evidence_id"],),
                ).fetchone()
                track_id = link["track_id"] if link else default_track_id
                evidence_tracks[row["evidence_id"]] = track_id
                digest = hashlib.sha256(
                    json.dumps(
                        [row["statement"], row["excerpt"], row["location"]],
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()
                paper_id = row["paper_id"]
                if target.execute("SELECT 1 FROM papers WHERE paper_id=?", (paper_id,)).fetchone() is None:
                    paper_id = None
                target.execute(
                    """INSERT OR IGNORE INTO evidence(
                       evidence_id,scope_kind,field_id,track_id,paper_id,paper_version_id,
                       experiment_run_id,statement,excerpt,location_json,relation,confidence,
                       extractor_model,prompt_version,content_digest,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row["evidence_id"], "TRACK", field_id, track_id, paper_id, None,
                        row["paper_id"].removeprefix("run:") if row["paper_id"].startswith("run:") else None,
                        row["statement"], row["excerpt"], json.dumps({"legacy": row["location"]}),
                        row["relation"], row["confidence"], row["extractor_model"],
                        row["prompt_version"], digest, row["created_at"],
                    ),
                )
            for row in source.execute("SELECT * FROM node_evidence").fetchall():
                target.execute("INSERT OR IGNORE INTO node_evidence VALUES(?,?)", tuple(row))
            for row in source.execute("SELECT * FROM decisions").fetchall():
                track_id = node_tracks[row["node_id"]]
                target.execute(
                    """INSERT OR IGNORE INTO decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row["proposal_id"], track_id, row["node_id"], row["kind"], row["status"],
                        row["approval_phrase"], row["expected_revision"], row["confirmation_text"],
                        row["rejection_reason"], row["supersedes_node_id"], row["created_at"],
                        row["resolved_at"],
                    ),
                )
            for row in source.execute("SELECT * FROM approval_grants").fetchall():
                decision = target.execute(
                    "SELECT track_id FROM decisions WHERE proposal_id=?", (row["proposal_id"],)
                ).fetchone()
                track_id = decision["track_id"] if decision else default_track_id
                target.execute(
                    "INSERT OR IGNORE INTO approval_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["grant_id"], row["proposal_id"], row["proposal_type"], track_id,
                        project["project_id"] if track_id == default_track_id else None,
                        row["proposal_revision"], row["profile"], row["session_id"], row["message_id"],
                        row["user_message_digest"], row["created_at"], row["consumed_at"],
                    ),
                )

            for row in source.execute("SELECT * FROM experiment_plans").fetchall():
                track_id = row["track_id"] or node_tracks[row["method_node_id"]]
                target.execute(
                    "INSERT OR IGNORE INTO experiment_plans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["plan_id"], row["proposal_id"], track_id,
                        project["project_id"] if track_id == default_track_id else None,
                        row["method_node_id"], row["status"], row["revision"], row["argv_json"],
                        row["working_directory"], row["script_path"], row["script_sha256"],
                        row["timeout_seconds"], row["metrics_json_path"], row["created_at"],
                        row["approved_at"],
                    ),
                )
            for row in source.execute("SELECT * FROM pipeline_runs").fetchall():
                track_id = row["track_id"] or default_track_id
                target.execute(
                    "INSERT OR IGNORE INTO pipeline_runs VALUES(?,?,?,?,?,?,?,?)",
                    (
                        row["run_id"], track_id,
                        project["project_id"] if track_id == default_track_id else None,
                        row["operation"], row["status"], row["detail_json"], row["created_at"],
                        row["updated_at"],
                    ),
                )
            for row in source.execute("SELECT * FROM blueprint_snapshots").fetchall():
                target.execute(
                    "INSERT OR IGNORE INTO blueprint_snapshots VALUES(?,?,?,?,?)",
                    (row["blueprint_id"], row["track_id"] or default_track_id, row["revision"], row["payload_json"], row["created_at"]),
                )
            for row in source.execute("SELECT * FROM manuscripts").fetchall():
                target.execute(
                    "INSERT OR IGNORE INTO manuscripts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", tuple(row)
                )
            for table in (
                "manuscript_nodes", "manuscript_evidence", "manuscript_versions",
                "manuscript_status_history", "submission_events",
            ):
                if _table_exists(source, table):
                    placeholders = ",".join("?" for _ in source.execute(f"PRAGMA table_info({table})"))
                    for row in source.execute(f"SELECT * FROM {table}").fetchall():
                        target.execute(f"INSERT OR IGNORE INTO {table} VALUES({placeholders})", tuple(row))
            for row in source.execute("SELECT * FROM track_phase_status").fetchall():
                target.execute(
                    "INSERT OR IGNORE INTO track_milestones VALUES(?,?,?,?,?,?)",
                    (
                        row["track_id"], f"LEGACY_PHASE_{row['phase']}", row["status"], row["blocker"],
                        row["revision"], row["updated_at"],
                    ),
                )
            target.execute(
                """INSERT OR REPLACE INTO legacy_migration_sources
                   VALUES(?,?,?,?,?,?,datetime('now'))""",
                (
                    str(source_path.resolve()), source_digest, project["project_id"], default_track_id,
                    "IMPORTED", json.dumps({"backup": str(backup), "track_count": len(tracks)}),
                ),
            )
        migrated.append({"source": str(source_path), "project_id": project["project_id"]})
    return migrated


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _backup_legacy(path: Path, marker_table: str, target_version: int) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return
    with closing(sqlite3.connect(path)) as conn:
        present = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (marker_table,)
        ).fetchone()
        version_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
        version = None
        if version_table:
            row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            version = row[0]
    backup = path.with_suffix(f".pre-v{target_version}.bak")
    if present and (version or 1) < target_version and not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _record_version(conn: sqlite3.Connection, component: str, version: int) -> None:
    conn.execute(
        """INSERT INTO schema_version(component,version,applied_at)
            VALUES(?,?,datetime('now'))
            ON CONFLICT(component) DO UPDATE SET version=excluded.version,
            applied_at=excluded.applied_at
            WHERE schema_version.version <> excluded.version""",
        (component, version),
    )


def _migrate_default_track(conn: sqlite3.Connection) -> None:
    project = conn.execute("SELECT * FROM project LIMIT 1").fetchone()
    if project is None:
        return
    track = conn.execute("SELECT track_id FROM research_tracks ORDER BY is_default DESC LIMIT 1").fetchone()
    if track is None:
        track_id = f"track_default_{project['project_id']}"
        timestamp = project["created_at"]
        conn.execute(
            """INSERT INTO research_tracks(
               track_id,title,scope,research_type,status,revision,is_default,created_at,updated_at)
               VALUES(?,?,?,?,?,1,1,?,?)""",
            (
                track_id,
                project["title"],
                project["scope"],
                project["research_type"],
                "ACTIVE",
                timestamp,
                project["updated_at"],
            ),
        )
    else:
        track_id = track["track_id"]
    conn.execute("UPDATE research_nodes SET track_id=? WHERE track_id IS NULL", (track_id,))
    conn.execute("UPDATE experiment_plans SET track_id=? WHERE track_id IS NULL", (track_id,))
    conn.execute("UPDATE pipeline_runs SET track_id=? WHERE track_id IS NULL", (track_id,))
    conn.execute("UPDATE blueprint_snapshots SET track_id=? WHERE track_id IS NULL", (track_id,))


@contextmanager
def transaction(path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
