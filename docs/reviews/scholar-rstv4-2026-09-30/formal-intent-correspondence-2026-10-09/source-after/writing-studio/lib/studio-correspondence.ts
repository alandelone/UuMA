import type { IntentBlock, ParagraphBlock, SectionBlock, StudioDocument, Thought } from './studio-types';
import { reconcileCorrespondence } from './studio-blocks';

export interface AuthorIntentLocation { section: SectionBlock; paragraph: ParagraphBlock; intent: IntentBlock }

export function fixedTemplateSource(location: AuthorIntentLocation) {
  return location.intent.template_source || location.paragraph.template_source;
}

export function intentLocations(document: StudioDocument): AuthorIntentLocation[] {
  return document.sections.flatMap(section => section.paragraphs.flatMap(paragraph =>
    paragraph.intents.map(intent => ({ section, paragraph, intent }))));
}

export function correspondenceOwners(document: StudioDocument) {
  const locations = intentLocations(document);
  const index = new Map(locations.map(item => [item.intent.id, item]));
  const authors = new Map<string, string>();
  const contexts = new Map<string, string>();
  for (const location of locations) {
    const { section, intent } = location;
    const fixedSource = fixedTemplateSource(location);
    const refs = intent.author_intent_ids || [];
    if (new Set(refs).size !== refs.length) throw new Error('原 Intent 不能重复对应。');
    if (refs.length && (section.placement_status === 'UNPLACED' || !fixedSource?.skeleton_id || !fixedSource.source_sha256))
      throw new Error('目标须为已安置且保留固定来源的模板 Intent。');
    for (const id of refs) {
      const source = index.get(id);
      if (!source || source.section.placement_status !== 'UNPLACED' || !source.intent.thoughts.length || authors.has(id) || id === intent.id)
        throw new Error('原 Intent 不可用或已经对应，请重新核对。');
      authors.set(id, intent.id);
    }
  }
  const paragraphs = new Map(document.sections.flatMap(section => section.paragraphs.map(paragraph => [paragraph.id, { section, paragraph }] as const)));
  for (const { section, paragraph } of paragraphs.values()) {
    const refs = paragraph.author_context_paragraph_ids || [];
    if (new Set(refs).size !== refs.length) throw new Error('原段落附加内容不能重复输出。');
    for (const id of refs) {
      const source = paragraphs.get(id);
      if (!source || source.section.placement_status !== 'UNPLACED' || section.placement_status === 'UNPLACED' || contexts.has(id) ||
          !source.paragraph.intents.some(intent => index.get(authors.get(intent.id) || '')?.paragraph.id === paragraph.id))
        throw new Error('公式、附件须选择一个已有对应关系的目标段落。');
      contexts.set(id, paragraph.id);
    }
  }
  return { authors, contexts };
}

function mappingLocations(document: StudioDocument, sourceId: string, targetId: string) {
  const owners = correspondenceOwners(document);
  const locations = intentLocations(document);
  const source = locations.find(item => item.intent.id === sourceId);
  const target = locations.find(item => item.intent.id === targetId);
  if (!source || source.section.placement_status !== 'UNPLACED' || !source.intent.thoughts.length || owners.authors.has(sourceId))
    throw new Error('请选择尚未对应的原作者 Intent。');
  if (!target || target.section.placement_status === 'UNPLACED' || !fixedTemplateSource(target)?.skeleton_id || !fixedTemplateSource(target)?.source_sha256)
    throw new Error('请选择保留固定来源的模板 Intent。');
  return { source, target, owners };
}

export function correspondenceReview(document: StudioDocument, sourceId: string, targetId: string, includeContext: boolean): string {
  const { source, target, owners } = mappingLocations(document, sourceId, targetId);
  return JSON.stringify({ source, target, includeContext,
    existingContextTargetId: owners.contexts.get(source.paragraph.id),
    sectionAncestry: document.sections.map(({ id, title, role, parent_section_id }) => ({ id, title, role, parent_section_id })),
    edges: document.argument_relations || [] });
}

export function mapAuthorIntent(document: StudioDocument, sourceId: string, targetId: string, includeContext: boolean, reviewed: string): StudioDocument {
  if (reviewed !== correspondenceReview(document, sourceId, targetId, includeContext))
    throw new Error('原内容或目标已变化，请重新核对并确认。');
  const result = structuredClone(document);
  const { source, target, owners } = mappingLocations(result, sourceId, targetId);
  const contextOwner = owners.contexts.get(source.paragraph.id);
  if (includeContext && contextOwner && contextOwner !== target.paragraph.id)
    throw new Error('原段落的公式、附件已有输出位置；请保留该位置或先取消原对应。');
  target.intent.author_intent_ids = [...(target.intent.author_intent_ids || []), sourceId];
  if (includeContext) target.paragraph.author_context_paragraph_ids = [...new Set([
    ...(target.paragraph.author_context_paragraph_ids || []), source.paragraph.id,
  ])];
  correspondenceOwners(result);
  return result;
}

export function unmapAuthorIntent(document: StudioDocument, sourceId: string): StudioDocument {
  const result = structuredClone(document);
  const { authors } = correspondenceOwners(result);
  const targetId = authors.get(sourceId);
  if (!targetId) throw new Error('原对应关系不可用。');
  const target = intentLocations(result).find(item => item.intent.id === targetId)!;
  target.intent.author_intent_ids = target.intent.author_intent_ids?.filter(id => id !== sourceId);
  reconcileCorrespondence(result);
  return result;
}

export function displayedThoughts(document: StudioDocument, intent: IntentBlock): Array<{ thought: Thought; ownerIntentId: string }> {
  const index = new Map(intentLocations(document).map(item => [item.intent.id, item.intent]));
  return [intent, ...(intent.author_intent_ids || []).map(id => index.get(id)!)].flatMap(owner =>
    owner.thoughts.map(thought => ({ thought, ownerIntentId: owner.id })));
}

export function thoughtsByIntent(document: StudioDocument, id: string): Thought[] {
  const owner = intentLocations(document).find(item => item.intent.id === id);
  if (!owner) throw new Error('原作者 Intent 已不可用。');
  return owner.intent.thoughts;
}
