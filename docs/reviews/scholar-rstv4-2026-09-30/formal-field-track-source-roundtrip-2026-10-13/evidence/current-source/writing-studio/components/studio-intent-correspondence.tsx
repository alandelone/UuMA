'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { useEditorControls } from '@/components/studio-block-controls';
import { ancestors, sectionBreadcrumb, sectionEnd } from '@/lib/studio-blocks';
import { correspondenceOwners, correspondenceReview, fixedTemplateSource, intentLocations, mapAuthorIntent, unmapAuthorIntent } from '@/lib/studio-correspondence';

export function StudioIntentCorrespondence({ sectionId }: { sectionId: string }) {
  const ui = useEditorControls();
  const [open, setOpen] = useState(false);
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [includeContext, setIncludeContext] = useState(false);
  const [confirmed, setConfirmed] = useState('');
  const [error, setError] = useState('');
  const locations = intentLocations(ui.document);
  const owners = correspondenceOwners(ui.document);
  const at = ui.document.sections.findIndex(section => section.id === sectionId);
  const treeIds = new Set(at < 0 ? [] : ui.document.sections.slice(at, sectionEnd(ui.document.sections, at)).map(section => section.id));
  const originals = locations.filter(item => treeIds.has(item.section.id) && item.section.placement_status === 'UNPLACED' && item.intent.thoughts.length);
  const sources = originals.filter(item => !owners.authors.has(item.intent.id));
  const targets = locations.filter(item => item.section.placement_status !== 'UNPLACED' && fixedTemplateSource(item)?.skeleton_id && fixedTemplateSource(item)?.source_sha256);
  const source = sources.find(item => item.intent.id === sourceId);
  const target = targets.find(item => item.intent.id === targetId);
  const contextOwner = source && owners.contexts.get(source.paragraph.id);
  const contextElsewhere = Boolean(contextOwner && contextOwner !== target?.paragraph.id);
  const label = (item: typeof locations[number]) => `${sectionBreadcrumb(ui.document, item.section.id)} / ${item.paragraph.purpose || '未定段落'} / ${item.intent.label || '未定 Intent'} · ${item.intent.id}`;
  const review = source && target ? correspondenceReview(ui.document, sourceId, targetId, includeContext) : '';
  return <>
    <Button size="sm" variant="outline" onClick={() => { setOpen(true); setSourceId(''); setTargetId(''); setIncludeContext(false); setConfirmed(''); setError(''); }}>对应到模板 Intent</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogTitle>原作者内容对应到模板槽位</DialogTitle>
        <DialogDescription>由你选择对应关系。原思想、引用与编号仍保存在原结构中，并呈现在指定槽位；原段落用途、组、公式、附件和 L2 关系保留，可撤销。</DialogDescription>
        <label className="grid gap-1 text-sm">原作者 Intent<select aria-label="对应的原作者 Intent" value={sourceId} onChange={event => { setSourceId(event.target.value); setIncludeContext(false); setConfirmed(''); setError(''); }}>
          <option value="">选择原 Intent</option>{sources.map(item => <option key={item.intent.id} value={item.intent.id}>{label(item)}</option>)}
        </select></label>
        <label className="grid gap-1 text-sm">模板槽位<select aria-label="对应的模板 Intent 槽位" value={targetId} onChange={event => { setTargetId(event.target.value); setIncludeContext(false); setConfirmed(''); setError(''); }}>
          <option value="">选择目标槽位</option>{targets.map(item => <option key={item.intent.id} value={item.intent.id}>{label(item)}</option>)}
        </select></label>
        {!sources.length ? <p>本范围没有尚未对应的作者 Intent。</p> : null}
        {source && target ? <section aria-label="作者 Intent 对应预览" className="grid gap-2 rounded border p-3 text-sm break-words">
          <p>原位置：{label(source)}</p><p>目标：{label(target)}</p>
          <p>模板原文路径：{fixedTemplateSource(target)?.source_path?.join(' / ') || target.section.title} · 第 {fixedTemplateSource(target)?.page_number || '?'} 页</p>
          <p>目标已有 {target.intent.thoughts.length} 条直接思想、{target.intent.author_intent_ids?.length || 0} 项对应。本次增加 {source.intent.thoughts.length} 条原思想，不替换已有内容。</p>
          {source.intent.thoughts.map(thought => <blockquote key={thought.id} className="whitespace-pre-wrap">{thought.text}<br />引用：{thought.citation_mode} · {thought.citations.filter(citation => citation.selected).length} 项已选</blockquote>)}
          <p>原段落用途：{source.paragraph.purpose}；范式：{source.paragraph.paradigm}；关系：{source.paragraph.logical_relation || '未设置'}</p>
          <p>原段落组：{source.section.paragraph_groups?.find(group => group.paragraph_ids.includes(source.paragraph.id))?.label || '未分组'}；{source.paragraph.formulas?.length || 0} 个公式，{source.paragraph.asset_ids.length} 个附件关联，全部 L2 端点与条件保留。</p>
          {source.paragraph.formulas?.map(formula => <p key={formula.id}>{formula.latex} · {formula.caption}</p>)}
          {contextElsewhere ? <p>该原段落公式、附件已有输出位置：{locations.find(item => item.paragraph.id === contextOwner) ? label(locations.find(item => item.paragraph.id === contextOwner)!) : contextOwner}。本次保持该位置。</p> : <label htmlFor={`author-context-${sectionId}`} className="flex items-center gap-2"><Checkbox id={`author-context-${sectionId}`} checked={includeContext} onCheckedChange={checked => { setIncludeContext(Boolean(checked)); setConfirmed(''); }} />同时将本原段落的公式、附件用于目标段落</label>}
          {(source.paragraph.formulas?.length || source.paragraph.asset_ids.length) && !includeContext && !contextOwner ? <p>尚未指定公式、附件的输出位置；保存对应后仍不能生成。</p> : null}
        </section> : null}
        <label htmlFor={`author-map-confirm-${sectionId}`} className="flex items-center gap-2 text-sm"><Checkbox id={`author-map-confirm-${sectionId}`} checked={Boolean(review && confirmed === review)} disabled={!review} onCheckedChange={checked => setConfirmed(checked ? review : '')} />我已核对原内容、目标和附加内容位置，确认此对应</label>
        {error ? <p role="alert">{error}</p> : null}
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setOpen(false)}>取消</Button><Button disabled={!review || confirmed !== review} onClick={() => {
          try {
            ui.commit(document => Object.assign(document, mapAuthorIntent(document, sourceId, targetId, includeContext, confirmed)), 'MAP_AUTHOR_INTENT');
            ui.unfold([...ancestors(ui.document, targetId), targetId]); ui.selectBlock(targetId); setOpen(false); ui.notice('已建立对应，正在保存；原结构保留，可撤销。');
          } catch (caught) { setError(caught instanceof Error ? caught.message : '对应失败，请重新核对。'); }
        }}>确认对应到槽位</Button></div>
        {originals.filter(item => owners.authors.has(item.intent.id)).map(item => <div key={item.intent.id} className="rounded border p-2 text-sm break-words">已对应：{label(item)} → {label(locations.find(targetItem => targetItem.intent.id === owners.authors.get(item.intent.id))!)} <Button size="sm" variant="outline" onClick={() => { ui.commit(document => Object.assign(document, unmapAuthorIntent(document, item.intent.id)), 'UNMAP_AUTHOR_INTENT'); setConfirmed(''); }}>取消此对应，保留原内容</Button></div>)}
      </DialogContent>
    </Dialog>
  </>;
}
