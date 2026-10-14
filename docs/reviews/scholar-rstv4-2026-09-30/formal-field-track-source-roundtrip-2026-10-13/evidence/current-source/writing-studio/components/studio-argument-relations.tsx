'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useEditorControls } from '@/components/studio-block-controls';
import { ancestors, blocks } from '@/lib/studio-blocks';
import type { ArgumentRelation } from '@/lib/studio-types';

export function StudioArgumentRelations({ paragraphId }: { paragraphId: string }) {
  const ui = useEditorControls();
  const [open, setOpen] = useState(false);
  const [sourceId, setSourceId] = useState(paragraphId);
  const [targetId, setTargetId] = useState('');
  const [relation, setRelation] = useState('');
  const [condition, setCondition] = useState('');
  const [editing, setEditing] = useState('');
  const [hydrated, setHydrated] = useState(false);
  const [notice, setNotice] = useState('');
  const key = `pepper-argument-draft-${ui.document.manuscript_id}-${paragraphId}`;
  const nodes = blocks(ui.document).filter((node) => ['paragraph', 'intent', 'thought'].includes(node.kind));
  const edges = ui.document.argument_relations || [];
  const connected = nodes.filter((node) => edges.some((edge) => edge.source_id === node.id || edge.target_id === node.id));
  const valid = sourceId !== targetId && nodes.some((node) => node.id === sourceId) && nodes.some((node) => node.id === targetId) && relation.trim();

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw) {
        const draft: unknown = JSON.parse(raw);
        if (!draft || typeof draft !== 'object' || !['sourceId','targetId','relation','condition','editing'].every((name) => typeof (draft as Record<string, unknown>)[name] === 'string')) {
          setNotice('原关系草稿无法读取，仍保留在此浏览器。');
          return;
        }
        const value = draft as Record<string,string>;
        setSourceId(value.sourceId); setTargetId(value.targetId); setRelation(value.relation);
        setCondition(value.condition); setEditing(value.editing);
      }
      setHydrated(true);
    } catch { setNotice('原关系草稿无法读取，仍保留在此浏览器。'); }
  }, [key]);
  useEffect(() => {
    if (!hydrated) return;
    try { window.localStorage.setItem(key, JSON.stringify({ sourceId,targetId,relation,condition,editing })); }
    catch { setNotice('关系草稿暂时无法保存，请保留此页。'); }
  }, [key,hydrated,sourceId,targetId,relation,condition,editing]);

  const locate = (id: string) => { ui.unfold(ancestors(ui.document,id)); ui.selectBlock(id); setOpen(false); };
  const save = () => {
    if (!valid || !hydrated) return;
    if (editing && !edges.some((edge) => edge.id === editing)) { setNotice('原关系已变化，请重新选择。原草稿仍保留。'); return; }
    const next: ArgumentRelation = { id: editing || `argument_relation_${crypto.randomUUID()}`, source_id:sourceId, target_id:targetId, relation, condition };
    ui.commit((document) => {
      document.argument_relations = editing ? (document.argument_relations || []).map((edge) => edge.id === editing ? next : edge)
        : [...(document.argument_relations || []),next];
    }, editing ? 'EDIT_ARGUMENT_RELATION' : 'ADD_ARGUMENT_RELATION');
    setEditing(''); setTargetId(''); setRelation(''); setNotice('关系已加入作者结构，可撤销。');
  };
  const label = (id: string) => nodes.find((node) => node.id === id)?.label || '原块不可用';
  const position = (id: string) => { const index = connected.findIndex((node) => node.id === id); return { x:20+(index%2)*330, y:20+Math.floor(index/2)*100 }; };
  return <>
    <Button variant="outline" size="sm" onClick={() => setOpen(true)}>高级 L2 关系 · {edges.length}</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-3xl">
        <DialogTitle>作者的 L2 关系</DialogTitle>
        <DialogDescription>明确各段落、Intent 或思想之间的关系与适用条件。章节层级、段落目的和组织范式分别设置。</DialogDescription>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid min-w-0 gap-1">关系起点<select className="w-full min-w-0 max-w-full rounded border p-2" aria-label="L2 关系起点" value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
            {!nodes.some((node) => node.id===sourceId) ? <option value={sourceId}>原选块不可用</option> : null}
            {nodes.map((node) => <option key={node.id} value={node.id}>{node.kind} · {node.label}</option>)}
          </select></label>
          <label className="grid min-w-0 gap-1">关系终点<select className="w-full min-w-0 max-w-full rounded border p-2" aria-label="L2 关系终点" value={targetId} onChange={(event) => setTargetId(event.target.value)}>
            <option value="">选择另一块…</option>
            {targetId && !nodes.some((node) => node.id===targetId) ? <option value={targetId}>原选块不可用</option> : null}
            {nodes.filter((node) => node.id!==sourceId).map((node) => <option key={node.id} value={node.id}>{node.kind} · {node.label}</option>)}
          </select></label>
        </div>
        <Input aria-label="L2 关系含义" placeholder="支持、对照、先后、条件，或自定义关系" value={relation} onChange={(event) => setRelation(event.target.value)} />
        <Textarea aria-label="L2 关系适用条件" placeholder="适用范围与条件，可暂留空" value={condition} onChange={(event) => setCondition(event.target.value)} />
        <div className="flex gap-2"><Button disabled={!valid || !hydrated} onClick={save}>{editing ? '保存关系修改' : '加入关系'}</Button>
          {editing ? <Button variant="outline" onClick={() => { setEditing(''); setTargetId(''); setRelation(''); }}>保留已有关系，结束编辑</Button> : null}</div>
        <output>{notice}</output>
        {connected.length ? <svg className="w-full" aria-labelledby={`argument-title-${paragraphId}`} viewBox={`0 0 650 ${Math.ceil(connected.length/2)*100+80}`}>
          <title id={`argument-title-${paragraphId}`}>作者已保存的 L2 关系图</title>
          <defs><marker id={`argument-arrow-${paragraphId}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#687d74" /></marker></defs>
          {edges.map((edge) => { const from=position(edge.source_id),to=position(edge.target_id); const right=to.x>from.x; return <g key={edge.id}>
            <path d={`M${from.x+(right ? 260 : 0)},${from.y+25} Q325,${Math.max(from.y,to.y)+120} ${to.x+(right ? 0 : 260)},${to.y+25}`} fill="none" stroke="#687d74" markerEnd={`url(#argument-arrow-${paragraphId})`} />
            <text x="325" y={Math.max(from.y,to.y)+110} textAnchor="middle" fontSize="11">{edge.relation.slice(0,48)}</text>
          </g>; })}
          {connected.map((node,index) => { const p=position(node.id); return <g key={node.id}><rect x={p.x} y={p.y} width="260" height="50" rx="5" fill="#f4f7f3" stroke="#bcc8bf" /><text x={p.x+10} y={p.y+30} fontSize="12">{index+1}. {node.label.slice(-30)}</text></g>; })}
        </svg> : <p>尚未指定块间关系。</p>}
        <ol className="space-y-3" aria-label="已保存的作者关系">
          {edges.map((edge) => <li key={edge.id} className="min-w-0 break-words rounded border p-3">
            <p>{label(edge.source_id)} → <strong>{edge.relation}</strong> → {label(edge.target_id)}</p>
            <p className="whitespace-pre-wrap">{edge.condition || '适用条件未定'}</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" size="sm" onClick={() => locate(edge.source_id)}>定位起点</Button><Button variant="ghost" size="sm" onClick={() => locate(edge.target_id)}>定位终点</Button>
              <Button variant="outline" size="sm" onClick={() => { setSourceId(edge.source_id);setTargetId(edge.target_id);setRelation(edge.relation);setCondition(edge.condition);setEditing(edge.id);setNotice(''); }}>编辑关系</Button>
              <Button variant="ghost" size="sm" onClick={() => ui.commit((document) => { document.argument_relations=(document.argument_relations || []).filter((item) => item.id!==edge.id); },'DELETE_ARGUMENT_RELATION')}>删除关系</Button>
            </div>
          </li>)}
        </ol>
      </DialogContent>
    </Dialog>
  </>;
}
