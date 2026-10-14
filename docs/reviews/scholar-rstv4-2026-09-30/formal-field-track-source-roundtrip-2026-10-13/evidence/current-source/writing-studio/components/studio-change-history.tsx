'use client';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { ApiError, studioApi } from '@/lib/studio-api';
import type { ChangeAssociationRequest, ReviewComment, StudioChange } from '@/lib/studio-types';

export function StudioChangeHistory({ manuscriptId, savedRevision, comments, focusedChange, onReload, onError }: {
  manuscriptId: string;
  savedRevision: number;
  comments: ReviewComment[];
  focusedChange: { id: string } | null;
  onReload: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [changes, setChanges] = useState<StudioChange[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [target, setTarget] = useState<StudioChange | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [prepared, setPrepared] = useState<ChangeAssociationRequest | null>(null);
  const [reverseId, setReverseId] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const handledFocus = useRef<{ id: string } | null>(null);

  useEffect(() => {
    let active = true;
    void studioApi.changes(manuscriptId).then((rows) => {
      if (active) { setChanges(rows); setError(''); }
    }).catch((caught) => {
      if (active) setError(caught instanceof Error ? caught.message : '修改历史读取失败');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [manuscriptId, savedRevision]);

  useEffect(() => {
    if (!focusedChange || handledFocus.current === focusedChange || !changes.some((item) => item.change_id === focusedChange.id)) return;
    handledFocus.current = focusedChange;
    setFilter('all');
    const frame = requestAnimationFrame(() => {
      const element = document.getElementById(`change-${focusedChange.id}`);
      element?.scrollIntoView({ block: 'nearest' });
      element?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [focusedChange, changes]);

  const label = (id: string) => {
    const comment = comments.find((item) => item.comment_id === id);
    return comment ? `${comment.display_label} · 第 ${comment.round_number || '?'} 轮${comment.archived_at ? '（已删除）' : ''}` : '原意见暂不可用';
  };
  const labels = (ids: string[]) => ids.length ? ids.map(label).join('、') : '未关联意见';
  const refresh = async () => {
    const rows = await studioApi.changes(manuscriptId);
    setChanges(rows);
    setError('');
    return rows;
  };
  const begin = (change: StudioChange, undo = false) => {
    if (prepared) {
      setOpen(true);
      setNotice('上次关联的保存结果尚待核对，请先重试或刷新核对。');
      return;
    }
    const latest = change.association_events.at(-1);
    setTarget(change);
    setSelected(undo && latest ? latest.before_comment_ids : change.comment_ids);
    setReverseId(undo && latest ? latest.event_id : null);
    setNotice('');
    setOpen(true);
  };
  const submit = async () => {
    if (!target || busy) return;
    const request = prepared || { request_id: crypto.randomUUID(),
      expected_link_revision: target.association_revision, comment_ids: selected,
      reverses_event_id: reverseId };
    setPrepared(request);
    setBusy(true);
    try {
      const result = await studioApi.setChangeAssociations(manuscriptId, target.change_id, request);
      setPrepared(null);
      setChanges((rows) => rows.map((item) => item.change_id === target.change_id ? result.change : item));
      setTarget(result.change);
      setSelected(result.change.comment_ids);
      setNotice('关联决定已记录。');
      setOpen(false);
      try { await refresh(); await onReload(); }
      catch (caught) { onError(`关联决定已记录；历史或意见刷新失败，请刷新核对。${caught instanceof Error ? ` ${caught.message}` : ''}`); }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status >= 400 && caught.status < 500) {
        // An explicit rejection confirms this request was not newly applied. Re-read current
        // links before preparing another decision; an uncertain transport failure retains its id.
        try {
          const rows = await refresh();
          const fresh = rows.find((item) => item.change_id === target.change_id);
          if (fresh) { setTarget(fresh); setSelected(fresh.comment_ids); setReverseId(null); }
          setPrepared(null);
        } catch { /* Keep the same request for explicit retry if the refresh also fails. */ }
      }
      setNotice(caught instanceof Error ? caught.message : '关联保存结果未确认；请重试或刷新核对。');
    } finally { setBusy(false); }
  };
  const verifyPending = async () => {
    if (!target) return;
    setBusy(true);
    try {
      const rows = await refresh();
      const fresh = rows.find((item) => item.change_id === target.change_id);
      if (fresh && prepared && fresh.association_events.some((item) => item.request_id === prepared.request_id)) {
        setTarget(fresh); setSelected(fresh.comment_ids); setPrepared(null); setReverseId(null);
        setNotice('原请求已记录，当前关联已重新读取。');
        await onReload();
      } else {
        setNotice('尚未找到原请求记录；保留原选择和请求，可重试同一次关联。');
      }
    } catch (caught) { setNotice(caught instanceof Error ? caught.message : '关联读取失败'); }
    finally { setBusy(false); }
  };
  const visible = changes.filter((item) => filter === 'all' || (filter === 'unassigned' ? !item.comment_ids.length : item.comment_ids.length > 0));
  return (
    <section className="studio-change-history" aria-label="已保存修改与意见关联">
      <header className="change-history-heading">
        <div><h3>已保存修改</h3><small>查看实际前后对照，分配给一条或多条意见。</small></div>
        <label>显示{' '}<select value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">全部修改</option><option value="unassigned">未关联意见</option><option value="linked">已关联意见</option>
        </select></label>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void refresh().catch((caught) => onError(caught instanceof Error ? caught.message : '历史读取失败'))}>刷新修改历史</Button>
      </header>
      {notice && !open ? <output aria-live="polite">{notice}</output> : null}
      {loading ? <output className="panel-empty" aria-live="polite">正在读取已保存修改…</output> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!loading && !error && !visible.length ? <p className="panel-empty">{filter === 'unassigned' ? '没有未关联的已保存修改。' : '此范围没有已保存修改。'}</p> : null}
      {visible.map((change) => <article key={change.change_id} id={`change-${change.change_id}`} className="saved-change" tabIndex={-1}>
        <header><strong>作者修订 r{change.base_revision} → r{change.resulting_revision}</strong>
          {change.is_compensating ? <small>作者撤销／重做记录</small> : null}
          <Button size="sm" variant="outline" disabled={busy} onClick={() => begin(change)}>分配／解除意见</Button>
          {change.association_events.length ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => begin(change, true)}>撤销上次关联</Button> : null}
        </header>
        <p>{labels(change.comment_ids)}</p>
        <details><summary>查看实际修改前后对照</summary>
          {change.author_diff ? <pre className="author-change-diff">{change.author_diff}</pre> : <p>{change.structure_changed ? '对象标识或结构发生变化，显示文字相同。' : '这次保存没有改变稿件结构或内容。'}</p>}
        </details>
        <details><summary>意见关联历史 · {change.association_events.length} 次后补决定</summary>
          <p>{change.association_origin === 'recorded_at_save' ? '保存时的原意见上下文' : '旧记录关联；原发生时间无法证明'}：{labels(change.initial_comment_ids)}</p>
          <ol>{change.association_events.map((event) => <li key={event.event_id}>
            <span>{event.reverses_event_id ? '撤销关联决定' : '作者分配／解除'} · {new Date(event.created_at).toLocaleString()}</span>
            <p>{labels(event.before_comment_ids)} → {labels(event.after_comment_ids)}</p>
          </li>)}</ol>
        </details>
      </article>)}
      <Dialog open={open} onOpenChange={(value) => { if (!busy) setOpen(value); }}>
        <DialogContent className="change-association-dialog">
          <DialogTitle>{reverseId ? '撤销上次意见关联' : '分配已保存修改'}</DialogTitle>
          <DialogDescription>作者修订 r{target?.base_revision} → r{target?.resulting_revision}。选定回应的意见；全部取消可解除关联。原稿内容和历史会保留。</DialogDescription>
          <div className="association-comment-list">
            {comments.map((comment) => <label key={comment.comment_id} aria-label={`关联意见 ${label(comment.comment_id)}`}>
              <input type="checkbox" checked={selected.includes(comment.comment_id)}
                disabled={busy || Boolean(prepared) || Boolean(reverseId) || Boolean(comment.archived_at && !target?.comment_ids.includes(comment.comment_id)) || (selected.length >= 100 && !selected.includes(comment.comment_id))}
                onChange={(event) => setSelected(event.target.checked ? [...selected, comment.comment_id] : selected.filter((id) => id !== comment.comment_id))} />
              <span><strong>{label(comment.comment_id)}</strong><span>{comment.edited_text}</span></span>
            </label>)}
            {selected.filter((id) => !comments.some((comment) => comment.comment_id === id)).map((id) => <label key={id}>
              <input type="checkbox" checked disabled={busy || Boolean(prepared) || Boolean(reverseId)} onChange={() => setSelected(selected.filter((item) => item !== id))} />原意见暂不可用；取消可解除关联
            </label>)}
            {!comments.length && !selected.length ? <p>暂无可关联意见，可以保留为未关联修改。</p> : null}
          </div>
          <output aria-live="polite">{notice || `选定 ${selected.length} 条意见`}</output>
          <div className="change-association-actions">
            {prepared ? <Button variant="outline" disabled={busy} onClick={() => void verifyPending()}>刷新核对关联</Button> : null}
            <Button disabled={busy || selected.length > 100} onClick={() => void submit()}>{busy ? '记录关联…' : prepared ? '重试同一次关联' : reverseId ? '确认撤销关联' : '确认关联决定'}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
