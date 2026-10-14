'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { useEditorControls } from '@/components/studio-block-controls';
import { ancestors, canPlaceOriginalSection, placeOriginalSection, sectionBreadcrumb, sectionEnd } from '@/lib/studio-blocks';

export function StudioOriginalPlacement({ sectionId }: { sectionId: string }) {
  const ui = useEditorControls();
  const [open, setOpen] = useState(false);
  const [targetId, setTargetId] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const index = ui.document.sections.findIndex((section) => section.id === sectionId);
  const tree = index < 0 ? [] : ui.document.sections.slice(index, sectionEnd(ui.document.sections, index));
  const targets = ui.document.sections.filter((section) => canPlaceOriginalSection(ui.document, sectionId, section.id));
  const target = targets.find((section) => section.id === targetId);
  const paragraphs = tree.flatMap((section) => section.paragraphs);
  const thoughts = paragraphs.flatMap((paragraph) => paragraph.intents.flatMap((intent) => intent.thoughts));
  const sourceIds = new Set(paragraphs.flatMap((paragraph) => [paragraph.id, ...paragraph.intents.flatMap((intent) => [intent.id, ...intent.thoughts.map((thought) => thought.id)])]));
  const edges = (ui.document.argument_relations || []).filter((edge) => sourceIds.has(edge.source_id) || sourceIds.has(edge.target_id));
  // A confirmation belongs to the exact reviewed source tree and destination, even after edits.
  const review = JSON.stringify({ tree, target, edges });

  return <>
    <Button size="sm" variant="outline" onClick={() => { setOpen(true); setTargetId(''); setConfirmation(''); setError(''); }}>预览安置原章节</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-2xl min-w-0 max-h-[85vh] overflow-y-auto">
        <DialogTitle>安置原章节与子项</DialogTitle>
        <DialogDescription>选择目标后，整棵原章节作为它的子章节放入。作者思想、引用、公式、附件、段落组和编号一起保留；模板空槽仍需作者填写。</DialogDescription>
        <label className="grid min-w-0 gap-1 text-sm">目标章节
          <select aria-label="原内容安置目标" className="min-w-0 w-full" value={targetId} onChange={(event) => { setTargetId(event.target.value); setConfirmation(''); setError(''); }}>
            <option value="">选择目标章节</option>
            {targets.map((section) => <option key={section.id} value={section.id}>{sectionBreadcrumb(ui.document, section.id)}</option>)}
          </select>
        </label>
        {!targets.length ? <p role="alert">当前没有可容纳整棵原章节的目标。请先添加主章节，或调整过深的层级。</p> : null}
        {target ? <p className="text-sm break-words">安置后：{sectionBreadcrumb(ui.document, target.id)} / {tree[0]?.title || '未定章节'}</p> : null}
        <p className="text-sm">保留 {tree.length} 个章节、{tree.flatMap((section) => section.paragraph_groups || []).length} 个段落组、{paragraphs.length} 个段落、{thoughts.length} 个思想、{thoughts.flatMap((thought) => thought.citations).length} 个引用候选、{paragraphs.flatMap((paragraph) => paragraph.formulas || []).length} 个公式、{paragraphs.flatMap((paragraph) => paragraph.asset_ids).length} 个附件关联、{edges.length} 条 L2 关系。</p>
        <div className="grid gap-3 text-sm" aria-label="原内容安置预览">
          {tree.map((section) => <section key={section.id} className="rounded border p-3 break-words">
            <h3>{sectionBreadcrumb(ui.document, section.id)}</h3>
            {section.paragraphs.map((paragraph) => <div key={paragraph.id} className="mt-2">
              <strong>{paragraph.purpose || '未定段落用途'}</strong>
              {paragraph.intents.map((intent) => <div key={intent.id}><p>{intent.label || '未定 Intent'}</p>{intent.thoughts.map((thought) => <blockquote key={thought.id} className="whitespace-pre-wrap">{thought.text || '空思想'}</blockquote>)}</div>)}
            </div>)}
          </section>)}
        </div>
        <label htmlFor={`placement-confirm-${sectionId}`} className="flex items-center gap-2 text-sm"><Checkbox id={`placement-confirm-${sectionId}`} checked={Boolean(target && confirmation === review)} disabled={!target} onCheckedChange={(checked) => setConfirmation(checked ? review : '')} />我已核对目标与完整原内容，确认按此位置安置</label>
        {error ? <p role="alert">{error}</p> : null}
        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={() => setOpen(false)}>取消</Button>
          <Button disabled={!target || confirmation !== review} onClick={() => {
            try {
              ui.commit((document) => Object.assign(document, placeOriginalSection(document, sectionId, targetId)), 'PLACE_ORIGINAL_TREE');
              ui.unfold([...ancestors(ui.document, targetId), targetId]);
              ui.selectBlock(sectionId); setOpen(false);
              ui.notice('已安置整棵原章节，思想、引用与编号保留；可撤销。');
            } catch (caught) { setError(caught instanceof Error ? caught.message : '原结构已变化，请重新核对。'); }
          }}>确认安置原章节</Button>
        </div>
      </DialogContent>
    </Dialog>
  </>;
}
