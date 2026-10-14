'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ApiError, studioApi } from '@/lib/studio-api';
import type { TemplatePreview, TemplateRequest } from '@/lib/studio-types';

type TemplateTarget = Pick<TemplateRequest, 'scope_type' | 'scope_id'> & { label: string };
export type TemplateCandidate = Pick<TemplateRequest, 'base_revision' | 'operation_id' | 'skeleton_id' | 'scope_type' | 'scope_id' | 'comment_ids'> & { label: string; targets: TemplateTarget[] };
type PendingTemplate = { request: TemplateRequest; label: string };

export function StudioTemplateAdoption({ manuscriptId, candidate, onClose, onApply }: {
  manuscriptId: string;
  candidate: TemplateCandidate | null;
  onClose: () => void;
  onApply: (request: TemplateRequest) => Promise<void>;
}) {
  const storageKey = `pepper-template-pending-${manuscriptId}`;
  const [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<'INSERT' | 'REPLACE'>('INSERT');
  const [confirmed, setConfirmed] = useState(false);
  const [target, setTarget] = useState<TemplateTarget | null>(null);
  const [pending, setPending] = useState<PendingTemplate | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [rejected, setRejected] = useState(false);

  useEffect(() => {
    try {
      const value = window.localStorage.getItem(storageKey);
      if (value) { setPending(JSON.parse(value)); setOpen(true); }
    } catch { setError('待确认请求读取失败，请保留此页。'); }
  }, [storageKey]);

  useEffect(() => {
    if (!candidate) return;
    setOpen(true);
    if (pending) return;
    let alive = true;
    setPreview(null); setError(''); setMode('INSERT'); setConfirmed(false);
    setTarget(candidate.targets.find((item) => item.scope_type === candidate.scope_type && item.scope_id === candidate.scope_id) || null);
    void studioApi.templatePreview(manuscriptId, candidate.skeleton_id).then((value) => {
      if (!alive) return;
      setPreview(value);
      setSelected(value.sections.flatMap((section) => section.paragraphs.map((p) => p.unit_id)));
    }).catch((caught) => { if (alive) setError(caught instanceof Error ? caught.message : '模板读取失败'); });
    return () => { alive = false; };
  }, [candidate, manuscriptId, pending]);

  const close = () => { if (!busy) { setOpen(false); onClose(); } };
  const submit = async () => {
    const next = pending || (candidate && preview && target ? { label: target.label, request: {
      base_revision: candidate.base_revision, operation_id: candidate.operation_id,
      skeleton_id: candidate.skeleton_id, scope_type: target.scope_type, scope_id: target.scope_id,
      comment_ids: candidate.comment_ids, source_sha256: preview.source_sha256,
      selected_unit_ids: [...selected], mode, replace_confirmed: confirmed,
    } } : null);
    if (!next || busy) return;
    setBusy(true); setError(''); setRejected(false);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(next));
      setPending(next);
      await onApply(next.request);
      window.localStorage.removeItem(storageKey);
      setPending(null); setOpen(false); onClose();
    } catch (caught) {
      setRejected(caught instanceof ApiError && [400, 404, 409, 422].includes(caught.status));
      setError(caught instanceof Error ? caught.message : '结果待确认，请核对原请求。');
    } finally { setBusy(false); }
  };

  return <>
    {pending && !open ? <Button variant="outline" onClick={() => setOpen(true)}>核对待确认的模板采用</Button> : null}
    <Dialog open={open} onOpenChange={(value) => { if (!value) close(); }}>
      <DialogContent className="sm:max-w-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto" showCloseButton={!busy}>
        <DialogHeader><DialogTitle>采用模板结构</DialogTitle><DialogDescription>
          {pending?.label || target?.label || candidate?.label} · 模板提供空槽，思想由作者填写。
        </DialogDescription></DialogHeader>
        {pending ? <output>已保留原采用请求（结构 r{pending.request.base_revision}，{pending.request.mode === 'INSERT' ? '插入' : '替换'}，{pending.request.selected_unit_ids.length} 个单元）。重试核对同一操作。</output> : preview ? <>
          <p>{preview.title} · Paper v{preview.paper_version} / Skeleton v{preview.skeleton_version}</p>
          <div className="max-h-[min(18rem,35dvh)] overflow-y-auto rounded border p-3" aria-label="完整模板与部分采用">
            {preview.sections.map((section, index) => <section key={section.source_section_id || index} className="mb-4" style={{ paddingLeft: (section.depth || 0) * 16 }}>
              <h3 aria-level={(section.depth || 0) + 2}>{section.title}</h3>
              {section.source_path ? <small className="block text-muted-foreground">
                {section.source_path.length ? section.source_path.join(' / ') : '原文未标注章节'}
                {section.page_number != null ? ` · 原文第 ${section.page_number} 页` : ''}
              </small> : null}
              {section.paragraphs.map((paragraph, position) => <label key={paragraph.unit_id} className="my-2 flex items-start gap-2">
                <input type="checkbox" checked={selected.includes(paragraph.unit_id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, paragraph.unit_id] : current.filter((id) => id !== paragraph.unit_id))} />
                <span>Paragraph {position + 1} → Intent: {paragraph.intent || '待作者确定'} → 空思想槽
                  <small className="block">作用：{paragraph.role || '未定'} · L2：{JSON.stringify(paragraph.logic)}</small></span>
              </label>)}
            </section>)}
          </div>
          {preview.sections.some((section) => section.parent_source_section_id) ? <p>部分采用会保留所选内容的上级章节，按原文章节层级创建空结构。</p> : null}
          <label className="flex gap-2">采用范围
            <select aria-label="模板采用范围" value={target ? `${target.scope_type}:${target.scope_id}` : ''} onChange={(event) => {
              setTarget(candidate?.targets.find((item) => `${item.scope_type}:${item.scope_id}` === event.target.value) || null);
              setConfirmed(false);
            }}>
              {!target ? <option value="">请选择作者结构</option> : null}
              {candidate?.targets.map((item) => <option key={`${item.scope_type}:${item.scope_id}`} value={`${item.scope_type}:${item.scope_id}`}>{item.label}</option>)}
            </select>
          </label>
          <label className="flex gap-2">采用方式
            <select aria-label="模板采用方式" value={mode} onChange={(event) => { setMode(event.target.value as typeof mode); setConfirmed(false); }}>
              <option value="INSERT">插入空结构（默认）</option><option value="REPLACE">替换结构，保留原内容到待安置</option>
            </select>
          </label>
          {mode === 'REPLACE' ? <label className="flex gap-2"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            我确认替换所选结构；原思想、引用和编号保留到待安置，由我重新放置。</label> : null}
          <p>已选择 {selected.length} 个单元。段落目的与组织范式留待作者填写。</p>
        </> : <output>{error ? '模板未载入。' : '正在读取模板来源…'}</output>}
        {error ? <p role="alert">{error}</p> : null}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={close}>{pending ? '保留请求并关闭' : '取消'}</Button>
          {rejected && pending ? <Button variant="outline" onClick={() => {
            try {
              window.localStorage.setItem(`${storageKey}-rejected-${pending.request.operation_id}`, JSON.stringify({ ...pending, error }));
              window.localStorage.removeItem(storageKey); setPending(null); setRejected(false); close();
            } catch { setError('失败记录保存失败；原请求仍保留。'); }
          }}>保留失败记录，重新预览</Button> : null}
          <Button disabled={busy || (!pending && (!preview || !target || !selected.length || (mode === 'REPLACE' && !confirmed)))} onClick={() => void submit()}>
            {busy ? '核对中…' : pending ? '核对原采用请求' : mode === 'INSERT' ? '插入所选空结构' : '确认替换并保留原内容'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>;
}
