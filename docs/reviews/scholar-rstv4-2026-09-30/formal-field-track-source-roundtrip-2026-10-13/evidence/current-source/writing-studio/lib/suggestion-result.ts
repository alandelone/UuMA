import { sameDocument } from './offline-outbox';
import type {
  StudioDocument,
  SuggestionDecisionResponse,
} from './studio-types';

export function suggestionResultMode(
  result: SuggestionDecisionResponse,
  local: StudioDocument,
  localRevision: number,
  locallyDirty: boolean,
): 'rejected' | 'applied' | 'same' | 'compare' {
  if (result.decision.outcome === 'REJECT') return 'rejected';
  if (locallyDirty) return 'compare';
  const server = result.workspace;
  if (
    localRevision === server.document_revision &&
    sameDocument(local, server.document)
  )
    return 'same';
  if (
    localRevision === result.decision.request.base_revision &&
    server.document_revision ===
      result.decision.provenance.author_revision_at_decision + 1
  )
    return 'applied';
  return 'compare';
}
