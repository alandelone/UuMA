import type { StudioDocument, SectionBlock } from './studio-types';

export type BlockKind =
  | 'section'
  | 'paragraph_group'
  | 'paragraph'
  | 'intent'
  | 'thought';
export interface BlockTarget {
  kind: BlockKind | 'paper';
  id: string;
  placement: 'before' | 'after' | 'inside';
}
export interface BlockLocation {
  kind: BlockKind | 'paper';
  id: string;
  label: string;
  parentId?: string;
  sectionId?: string;
  paragraphId?: string;
  intentId?: string;
  groupId?: string;
}

export function blocks(document: StudioDocument): BlockLocation[] {
  const result: BlockLocation[] = [
    { kind: 'paper', id: document.manuscript_id, label: document.title },
  ];
  for (const section of document.sections) {
    result.push({
      kind: 'section',
      id: section.id,
      label: section.title,
      parentId: document.manuscript_id,
      sectionId: section.id,
    });
    for (const group of [...(section.paragraph_groups || [])].sort(
      (a, b) =>
        (section.block_order || []).indexOf(a.id) -
        (section.block_order || []).indexOf(b.id),
    ))
      result.push({
        kind: 'paragraph_group',
        id: group.id,
        label: `${section.title} / ${group.label || '未定段落组'}`,
        parentId: section.id,
        sectionId: section.id,
        groupId: group.id,
      });
    for (const paragraph of section.paragraphs) {
      const group = section.paragraph_groups?.find((item) =>
        item.paragraph_ids.includes(paragraph.id),
      );
      const label = `${section.title} / ${group ? `${group.label || '段落组'} / ` : ''}${paragraph.purpose || '未定段落'}`;
      result.push({
        kind: 'paragraph',
        id: paragraph.id,
        label,
        parentId: group?.id || section.id,
        sectionId: section.id,
        paragraphId: paragraph.id,
        groupId: group?.id,
      });
      for (const intent of paragraph.intents) {
        result.push({
          kind: 'intent',
          id: intent.id,
          label: `${label} / ${intent.label || '未定 Intent'}`,
          parentId: paragraph.id,
          sectionId: section.id,
          paragraphId: paragraph.id,
          intentId: intent.id,
        });
        for (const thought of intent.thoughts)
          result.push({
            kind: 'thought',
            id: thought.id,
            label: `${label} / ${intent.label || 'Intent'} / ${thought.text.slice(0, 50) || '空思想'}`,
            parentId: intent.id,
            sectionId: section.id,
            paragraphId: paragraph.id,
            intentId: intent.id,
          });
      }
    }
  }
  return result;
}

export function ancestors(document: StudioDocument, id: string): string[] {
  const index = new Map(blocks(document).map((item) => [item.id, item]));
  const result: string[] = [];
  let item = index.get(id);
  while (item?.parentId) {
    result.push(item.parentId);
    item = index.get(item.parentId);
  }
  return result;
}

function reconcileSection(section: SectionBlock) {
  if (!section.paragraph_groups && !section.block_order) return;
  const byId = new Map(section.paragraphs.map((item) => [item.id, item]));
  const groups = section.paragraph_groups || [];
  const grouped = new Set<string>();
  for (const group of groups) {
    group.paragraph_ids = group.paragraph_ids.filter((id) => byId.has(id));
    for (const id of group.paragraph_ids) {
      if (grouped.has(id)) throw new Error('一个段落不能同时属于两个段落组。');
      grouped.add(id);
    }
  }
  const roots = new Set([
    ...groups.map((item) => item.id),
    ...section.paragraphs
      .filter((item) => !grouped.has(item.id))
      .map((item) => item.id),
  ]);
  const order = [
    ...new Set(
      section.block_order || section.paragraphs.map((item) => item.id),
    ),
  ].filter((id) => roots.has(id));
  for (const group of groups)
    if (!order.includes(group.id)) order.push(group.id);
  for (const paragraph of section.paragraphs)
    if (roots.has(paragraph.id) && !order.includes(paragraph.id))
      order.push(paragraph.id);
  section.paragraph_groups = groups;
  section.block_order = order;
  section.paragraphs = order.flatMap((id) => {
    const group = groups.find((item) => item.id === id);
    return (group ? group.paragraph_ids : [id]).map((paragraphId) =>
      byId.get(paragraphId)!,
    );
  });
}

export function reconcileStructure(document: StudioDocument): void {
  for (const section of document.sections) reconcileSection(section);
}

function roots(section: SectionBlock): string[] {
  reconcileSection(section);
  if (!section.block_order)
    section.block_order = section.paragraphs.map((item) => item.id);
  if (!section.paragraph_groups) section.paragraph_groups = [];
  return section.block_order;
}

export function canMove(
  document: StudioDocument,
  sourceIds: string[],
  target: BlockTarget,
  locations?: ReadonlyMap<string, BlockLocation>,
): boolean {
  const index = locations || new Map(blocks(document).map((item) => [item.id, item]));
  const destination = index.get(target.id);
  const sources = sourceIds.map((id) => index.get(id));
  if (
    !destination ||
    destination.kind !== target.kind ||
    !sources.length ||
    new Set(sourceIds).size !== sourceIds.length ||
    sources.some((item) => !item || item.kind === 'paper') ||
    new Set(sources.map((item) => item!.kind)).size !== 1 ||
    sourceIds.includes(target.id)
  )
    return false;
  const kind = sources[0]!.kind;
  if (target.placement === 'inside')
    return (
      {
        section: ['paper'],
        paragraph_group: ['section'],
        paragraph: ['section', 'paragraph_group'],
        intent: ['paragraph'],
        thought: ['intent'],
        paper: [],
      }[kind] as string[]
    ).includes(destination.kind);
  if (kind === 'paragraph_group')
    return (
      destination.kind === 'paragraph_group' ||
      (destination.kind === 'paragraph' && !destination.groupId)
    );
  if (kind === 'paragraph')
    return (
      destination.kind === 'paragraph' || destination.kind === 'paragraph_group'
    );
  return kind === destination.kind;
}

export function moveBlocks(
  document: StudioDocument,
  sourceIds: string[],
  target: BlockTarget,
): StudioDocument {
  if (!canMove(document, sourceIds, target))
    throw new Error('这个位置不接受所选内容，请选择同类前后位置或正确的容器。');
  const result = structuredClone(document);
  reconcileStructure(result);
  const index = blocks(result);
  const sources = index.filter((item) => sourceIds.includes(item.id));
  const destination = index.find((item) => item.id === target.id)!;
  const kind = sources[0].kind;
  const sectionById = (id: string) =>
    result.sections.find((item) => item.id === id)!;
  const paragraphById = (id: string) =>
    result.sections
      .flatMap((item) => item.paragraphs)
      .find((item) => item.id === id)!;
  const intentById = (id: string) =>
    result.sections
      .flatMap((item) => item.paragraphs)
      .flatMap((item) => item.intents)
      .find((item) => item.id === id)!;
  if (kind === 'section' || kind === 'intent' || kind === 'thought') {
    const list = (location: BlockLocation) =>
      kind === 'section'
        ? result.sections
        : kind === 'intent'
          ? paragraphById(location.parentId!).intents
          : intentById(location.parentId!).thoughts;
    const moved = sources.map((source) => {
      const items = list(source);
      const position = items.findIndex((item) => item.id === source.id);
      return items.splice(position, 1)[0];
    });
    const into =
      target.placement === 'inside'
        ? kind === 'section'
          ? result.sections
          : kind === 'intent'
            ? paragraphById(target.id).intents
            : intentById(target.id).thoughts
        : list(destination);
    const at =
      target.placement === 'inside'
        ? into.length
        : into.findIndex((item) => item.id === target.id) +
          (target.placement === 'after' ? 1 : 0);
    (into as unknown[]).splice(at, 0, ...moved);
    return result;
  }
  const destinationSection = sectionById(
    destination.sectionId || destination.id,
  );
  roots(destinationSection);
  if (kind === 'paragraph_group') {
    const moved = sources.map((source) => {
      const section = sectionById(source.sectionId!);
      const group = section.paragraph_groups!.find(
        (item) => item.id === source.id,
      )!;
      const members = group.paragraph_ids.map((id) =>
        section.paragraphs.find((item) => item.id === id)!,
      );
      section.paragraph_groups = section.paragraph_groups!.filter(
        (item) => item.id !== source.id,
      );
      section.block_order = roots(section).filter((id) => id !== source.id);
      section.paragraphs = section.paragraphs.filter(
        (item) => !group.paragraph_ids.includes(item.id),
      );
      return { group, members };
    });
    // A destination is resolved after source removals, using stable identities.
    const order = roots(destinationSection);
    const at =
      target.placement === 'inside'
        ? order.length
        : order.indexOf(target.id) + (target.placement === 'after' ? 1 : 0);
    order.splice(at, 0, ...moved.map((item) => item.group.id));
    destinationSection.paragraph_groups!.push(
      ...moved.map((item) => item.group),
    );
    destinationSection.paragraphs.push(
      ...moved.flatMap((item) => item.members),
    );
  } else {
    const moved = sources.map((source) => {
      const section = sectionById(source.sectionId!);
      const paragraph = section.paragraphs.find(
        (item) => item.id === source.id,
      )!;
      section.paragraphs = section.paragraphs.filter(
        (item) => item.id !== source.id,
      );
      if (section.block_order)
        section.block_order = section.block_order.filter(
          (id) => id !== source.id,
        );
      for (const group of section.paragraph_groups || [])
        group.paragraph_ids = group.paragraph_ids.filter(
          (id) => id !== source.id,
        );
      return paragraph;
    });
    const groupId =
      target.placement === 'inside' && destination.kind === 'paragraph_group'
        ? destination.id
        : target.placement !== 'inside' && destination.kind === 'paragraph'
          ? destination.groupId
          : undefined;
    const order = groupId
      ? destinationSection.paragraph_groups!.find(
          (item) => item.id === groupId,
        )!.paragraph_ids
      : roots(destinationSection);
    const at =
      target.placement === 'inside'
        ? order.length
        : order.indexOf(target.id) + (target.placement === 'after' ? 1 : 0);
    if (at < 0) throw new Error('原目标已经不可用，请重新选择移动位置。');
    order.splice(at, 0, ...moved.map((item) => item.id));
    destinationSection.paragraphs.push(...moved);
  }
  reconcileStructure(result);
  return result;
}

export function groupParagraphs(
  document: StudioDocument,
  ids: string[],
  groupId: string,
  label: string,
): StudioDocument {
  const result = structuredClone(document);
  const selected = blocks(result).filter((item) => ids.includes(item.id));
  if (
    selected.length !== new Set(ids).size ||
    !selected.length ||
    selected.some((item) => item.kind !== 'paragraph' || item.groupId) ||
    new Set(selected.map((item) => item.sectionId)).size !== 1
  )
    throw new Error('请在同一章节选择未分组的段落；已分组内容可先移出原组。');
  if (blocks(result).some((item) => item.id === groupId))
    throw new Error('段落组编号已存在。');
  const section = result.sections.find(
    (item) => item.id === selected[0].sectionId,
  )!;
  const order = roots(section);
  const at = order.indexOf(selected[0].id);
  section.block_order = order.filter((id) => !ids.includes(id));
  section.block_order.splice(at, 0, groupId);
  section.paragraph_groups!.push({
    id: groupId,
    label,
    paragraph_ids: selected.map((item) => item.id),
  });
  reconcileStructure(result);
  return result;
}

export function ungroupParagraphs(
  document: StudioDocument,
  id: string,
): StudioDocument {
  const result = structuredClone(document);
  const location = blocks(result).find(
    (item) => item.kind === 'paragraph_group' && item.id === id,
  );
  if (!location) throw new Error('原段落组已经不可用。');
  const section = result.sections.find(
    (item) => item.id === location.sectionId,
  )!;
  const group = section.paragraph_groups!.find((item) => item.id === id)!;
  const order = roots(section);
  order.splice(order.indexOf(id), 1, ...group.paragraph_ids);
  section.paragraph_groups = section.paragraph_groups!.filter(
    (item) => item.id !== id,
  );
  reconcileStructure(result);
  return result;
}
