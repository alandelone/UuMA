'use client';

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, studioApi } from '@/lib/studio-api';
import { studioFileUrl } from '@/lib/studio-downloads';
import type { ReplyAssertion, ResponseReviewContext, ResponseReviewRequest, ReviewComment } from '@/lib/studio-types';

type Draft = { author_decision: string; response_text: string };
type Checkpoint = { base: ReviewComment; draft: Draft; pending?: ResponseReviewRequest; updatedAt: number };
const fields = (comment: ReviewComment): Draft => ({ author_decision: comment.author_decision || '', response_text: comment.response_text || '' });
const equal = (a: Draft, b: Draft) => a.author_decision === b.author_decision && a.response_text === b.response_text;
const verificationLabel = { NOT_REVIEWED: '回复尚未核对', LEGACY_UNVERIFIED: '原状态为已处理 · 缺少核对记录', CURRENT: '作者已核对本版回复', STALE: '回复、版本或关联已变化 · 需要重新核对' };

export function StudioResponseReview({ manuscriptId, comment, archived, onReload }: {
  manuscriptId: string; comment: ReviewComment; archived: boolean; onReload: () => Promise<void>;
}) {
  const base = useRef(comment);
  const draft = useRef(fields(comment));
  const slot = useRef('');
  const inFlight = useRef<Promise<boolean> | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const blocked = useRef(false);
  const checkBusy = useRef(false);
  const pending = useRef<ResponseReviewRequest | undefined>(undefined);
  const mounted = useRef(true);
  const [value, setValue] = useState(draft.current);
  const [server, setServer] = useState(comment);
  const [conflict, setConflict] = useState<ReviewComment | null>(null);
  const [recoveries, setRecoveries] = useState<Checkpoint[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [open, setOpen] = useState(false);
  const [context, setContext] = useState<ResponseReviewContext | null>(null);
  const [retryCheck, setRetryCheck] = useState(false);
  const [history, setHistory] = useState<ResponseReviewContext['history'] | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const label = comment.display_label;

  const persist = () => {
    if (!slot.current) return;
    try {
      if (equal(draft.current, fields(base.current)) && !pending.current) localStorage.removeItem(slot.current);
      else localStorage.setItem(slot.current, JSON.stringify({ base: base.current, draft: draft.current, pending: pending.current, updatedAt: Date.now() }));
    } catch { if (mounted.current) setMessage('本地副本无法写入；请保存回复或复制当前文字。'); }
  };

  useEffect(() => {
    mounted.current = true;
    const prefix = `studio-response:${manuscriptId}:${comment.comment_id}:`;
    try {
      let tab = sessionStorage.getItem('studio-response-tab');
      if (!tab) { tab = crypto.randomUUID(); sessionStorage.setItem('studio-response-tab', tab); }
      slot.current = `${prefix}${tab}`;
      const own = localStorage.getItem(slot.current);
      if (own) {
        const saved = JSON.parse(own) as Checkpoint;
        if (typeof saved.draft?.response_text === 'string' && typeof saved.draft?.author_decision === 'string') {
          draft.current = saved.draft; setValue(saved.draft);
          pending.current = saved.pending; setRetryCheck(Boolean(saved.pending));
          if (saved.base.content_sha256 !== base.current.content_sha256 && !equal(saved.draft, fields(base.current))) {
            blocked.current = true; setConflict(base.current); setMessage('本地回复与当前保存版本不同，请先比较。');
          }
        }
      }
      const other = Object.keys(localStorage).filter((key) => key.startsWith(prefix) && key !== slot.current)
        .flatMap((key) => { try { return [JSON.parse(localStorage.getItem(key) || '') as Checkpoint]; } catch { return []; } })
        .filter((item) => typeof item.draft?.response_text === 'string' && typeof item.draft?.author_decision === 'string' && (!equal(item.draft, fields(base.current)) || item.pending));
      setRecoveries(other.sort((a, b) => b.updatedAt - a.updatedAt));
    } catch { setMessage('无法读取本地副本；当前保存的回复仍可查看。'); }
    return () => { mounted.current = false; if (timer.current) clearTimeout(timer.current); persist(); };
    // This component is keyed by manuscript and opinion; initialize each checkpoint once.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [manuscriptId, comment.comment_id]);

  useEffect(() => {
    if (comment.content_sha256 !== base.current.content_sha256) {
      if (!equal(draft.current, fields(base.current))) { blocked.current = true; setConflict(comment); setMessage('回复在另一处发生变化，本地文字已保留。'); }
      else { base.current = comment; draft.current = fields(comment); setValue(draft.current); persist(); }
    }
    setServer(comment);
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [comment]);

  const fetchCurrent = async () => (await studioApi.comments(manuscriptId, true)).find((item) => item.comment_id === comment.comment_id);
  const flush = (): Promise<boolean> => {
    if (timer.current) clearTimeout(timer.current);
    if (inFlight.current) return inFlight.current;
    const work = async () => {
      if (blocked.current || archived) return false;
      if (mounted.current) setBusy(true);
      try {
        while (!equal(draft.current, fields(base.current))) {
          const packet = { ...draft.current };
          const previous = base.current;
          let saved: ReviewComment;
          try {
            saved = await studioApi.updateComment(comment.comment_id, { ...packet, expected_content_sha256: previous.content_sha256 });
          } catch (error) {
            const actual = await fetchCurrent().catch(() => undefined);
            if ((!(error instanceof ApiError) || error.status >= 500) && actual && equal(packet, fields(actual))) saved = actual;
            else {
              if (actual) { blocked.current = true; if (mounted.current) setConflict(actual); }
              if (mounted.current) setMessage(actual ? '回复发生冲突，本地文字已保留；请比较后再保存。' : '保存结果尚未确认，本地文字已保留；可以重试保存。');
              persist(); return false;
            }
          }
          base.current = { ...previous, ...saved };
          if (mounted.current) { setServer(base.current); setMessage('回复已保存'); }
          persist();
        }
        await onReload().catch(() => { if (mounted.current) setMessage('回复已保存；列表暂未刷新，可以重新打开查看。'); });
        return true;
      } finally { if (mounted.current) setBusy(false); }
    };
    inFlight.current = work().finally(() => { inFlight.current = null; });
    return inFlight.current;
  };

  const edit = (next: Draft) => {
    draft.current = next; setValue(next); persist(); setMessage('本地副本已保留 · 等待保存');
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { void flush().catch(() => setMessage('回复已保留，请重试保存。')); }, 650);
  };

  const openReview = async () => {
    if (checkBusy.current) return;
    checkBusy.current = true;
    setChecking(true); setMessage('');
    try {
      if (!archived && !(await flush())) return;
      const loaded = await studioApi.responseReview(manuscriptId, comment.comment_id);
      if (!archived && !equal(draft.current, { author_decision: loaded.state.author_decision || '', response_text: loaded.state.response_text || '' })) {
        const actual = await fetchCurrent(); if (actual) { blocked.current = true; setConflict(actual); }
        setMessage('回复在加载核对依据时改变，请先比较当前版本。'); return;
      }
      setContext(loaded); setOpen(true);
    } catch (error) { setMessage(error instanceof Error ? error.message : '核对依据无法加载'); }
    finally { checkBusy.current = false; setChecking(false); }
  };

  const openHistory = async () => {
    if (checkBusy.current) return;
    checkBusy.current = true; setChecking(true);
    try { setHistory((await studioApi.responseReviewHistory(manuscriptId, comment.comment_id)).history); setHistoryOpen(true); }
    catch (error) { setMessage(error instanceof Error ? error.message : '核对历史暂时无法加载'); }
    finally { checkBusy.current = false; setChecking(false); }
  };

  const confirm = async (request: ResponseReviewRequest) => {
    if (checkBusy.current) return;
    checkBusy.current = true;
    pending.current = request; setRetryCheck(true); persist(); setChecking(true);
    try {
      const result = await studioApi.confirmResponseReview(manuscriptId, comment.comment_id, request);
      pending.current = undefined; setRetryCheck(false);
      if (equal(draft.current, fields(base.current))) { draft.current = fields(result.comment); setValue(draft.current); }
      else if (!equal(draft.current, fields(result.comment))) { blocked.current = true; setConflict(result.comment); }
      base.current = { ...base.current, ...result.comment }; setServer(base.current); persist();
      setMessage(result.comment.response_verification.status === 'CURRENT' ? '核对记录已保存，作者已确认本版回复。' : '原核对记录已保留；后来发生的变化仍需重新核对。');
      setOpen(false); await onReload().catch(() => undefined);
    } catch (error) {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429) { pending.current = undefined; setRetryCheck(false); persist(); }
      setMessage(error instanceof ApiError && error.status === 409 ? '核对依据已改变；请重新打开核对窗口。原文字与记录仍保留。' : error instanceof Error ? error.message : '提交结果尚未确认；请重试原核对提交。');
    } finally { checkBusy.current = false; setChecking(false); }
  };

  const resolveConflict = (keepLocal: boolean) => {
    if (!conflict) return;
    base.current = conflict; setServer(conflict);
    if (!keepLocal) { draft.current = fields(conflict); setValue(draft.current); }
    blocked.current = false; setConflict(null); persist();
    setMessage(keepLocal ? '已选择保留本地回复，请保存后重新核对。' : '已采用当前保存的回复。');
  };

  return <div className="comment-fields min-w-0">
    <Input name={`decision-${comment.comment_id}`} aria-label={`我的决定与理由 ${label}`} value={value.author_decision} disabled={archived || checking} placeholder="我的决定与理由" onChange={(event) => edit({ ...draft.current, author_decision: event.target.value })} onBlur={() => void flush()} />
    <Textarea name={`response-${comment.comment_id}`} aria-label={`回复内容 ${label}`} value={value.response_text} disabled={archived || checking} placeholder="回复内容" onChange={(event) => edit({ ...draft.current, response_text: event.target.value })} onBlur={() => void flush()} />
    <div className="flex flex-wrap items-center gap-2">
      <select aria-label={`意见状态 ${label}`} value={server.status} disabled={archived || busy || checking || Boolean(conflict)} onChange={async (event) => {
        const status = event.target.value;
        if (!(await flush())) return;
        try { const saved = await studioApi.updateComment(comment.comment_id, { status, expected_content_sha256: base.current.content_sha256 }); base.current = { ...base.current, ...saved }; setServer(base.current); persist(); await onReload(); }
        catch { const actual = await fetchCurrent().catch(() => undefined); if (actual) { blocked.current = true; setConflict(actual); } setMessage('状态保存未完成，请核对当前版本。'); }
      }}>
        <option value="PENDING">待处理</option><option value="DECIDED">已决定回应</option><option value="MODIFYING">修改中</option><option value="VERIFY">待核对</option><option value="RESOLVED" disabled>已处理 · 需作者核对</option>
      </select>
      <Button size="sm" variant="outline" disabled={archived || busy || checking || Boolean(conflict)} onClick={() => void flush()}>保存回复</Button>
      {!archived ? <Button size="sm" variant="outline" disabled={checking || busy || Boolean(conflict)} onClick={() => void openReview()}>{checking ? '加载中…' : '核对回复'}</Button> : null}
      <Button size="sm" variant="ghost" disabled={checking} onClick={() => void openHistory()}>查看核对历史</Button>
    </div>
    <p className="text-xs text-muted-foreground" aria-live="polite">{verificationLabel[server.response_verification?.status || 'NOT_REVIEWED']}{busy ? ' · 保存中…' : ''}</p>
    {message ? <output className="text-xs whitespace-pre-wrap break-words" aria-live="polite">{message}</output> : null}
    {retryCheck ? <Button size="sm" variant="outline" disabled={checking} onClick={() => pending.current && void confirm(pending.current)}>重试原核对提交</Button> : null}
    {recoveries.length ? <details><summary>其他页面留下的本地回复（{recoveries.length}）</summary>{recoveries.map((item, index) => <div key={`${item.updatedAt}-${index}`} className="space-y-2 border-t py-2">
      <small>{new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(item.updatedAt)}</small>
      <p className="whitespace-pre-wrap break-words">{item.draft.author_decision}</p><p className="whitespace-pre-wrap break-words">{item.draft.response_text}</p>
      <Button size="sm" variant="outline" disabled={archived || checking || busy} onClick={() => { draft.current = item.draft; setValue(item.draft); blocked.current = true; setConflict(base.current); pending.current = item.pending; setRetryCheck(Boolean(item.pending)); persist(); }}>取回此副本并比较</Button>
    </div>)}</details> : null}
    {conflict ? <section aria-label={`${label} 回复冲突`} className="space-y-2 rounded border border-amber-300 p-3 text-sm">
      <p>当前保存的版本：</p><p className="whitespace-pre-wrap break-words">{conflict.edited_text}</p><p className="whitespace-pre-wrap break-words">{conflict.author_decision || '尚无决定'}</p><p className="whitespace-pre-wrap break-words">{conflict.response_text || '尚无回复'}</p>
      <p>上方输入框保留你的本地文字。</p><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => resolveConflict(false)}>采用当前保存版本</Button><Button size="sm" disabled={archived} onClick={() => resolveConflict(true)}>保留本地文字，再保存</Button></div>
    </section> : null}
    {context ? <ResponseCheckDialog key={context.context_sha256} commentId={comment.comment_id} context={context} open={open} onOpenChange={setOpen} disabled={checking || archived || retryCheck} onConfirm={confirm} /> : null}
    <Dialog open={historyOpen} onOpenChange={setHistoryOpen}><DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-2xl"><DialogTitle>{label} 的核对历史</DialogTitle><DialogDescription>保留作者当时核对的回复、理由、版本与实际改动。当前文件暂时不可用时，历史记录仍可查看。</DialogDescription><ResponseHistory history={history || []} /><Button variant="outline" onClick={() => setHistoryOpen(false)}>返回</Button></DialogContent></Dialog>
  </div>;
}

function ResponseCheckDialog({ commentId, context, open, onOpenChange, disabled, onConfirm }: {
  commentId: string; context: ResponseReviewContext; open: boolean; onOpenChange: (value: boolean) => void;
  disabled: boolean; onConfirm: (request: ResponseReviewRequest) => Promise<void>;
}) {
  const [outcome, setOutcome] = useState<ResponseReviewRequest['outcome']>('MODIFIED');
  const [claims, setClaims] = useState<ReplyAssertion[]>([]);
  const [acknowledged, setAcknowledged] = useState(false);
  const [selection, setSelection] = useState({ start: 0, end: 0 });
  const [notice, setNotice] = useState('');
  const stale = context.state.current_author_revision !== context.state.generated_input_revision;
  const addSelection = () => {
    const { start, end } = selection;
    if (end <= start || claims.some((item) => start < item.end && end > item.start)) { setNotice('请选择一段尚未核对的“已修改”回复文字。'); return; }
    setClaims((current) => [...current, { start, end, text: context.state.response_text.slice(start, end), offset_unit: 'utf16', evidence_ids: [] }]);
    setAcknowledged(false); setNotice('');
  };
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-3xl">
    <DialogTitle>作者核对回复</DialogTitle><DialogDescription>第 {context.state.round_number} 轮 · 被审稿 {context.baseline_version_number === null ? '未知' : `v${context.baseline_version_number}`} → 成文 v{context.target_version_number}。请逐条核对回复中的修改声明。</DialogDescription>
    {stale ? <p role="alert" className="text-sm text-amber-700">作者结构已变化，请生成当前版本后再完成回复核对。</p> : null}
    <p className="whitespace-pre-wrap break-words text-sm">决定与理由：{context.state.author_decision || '尚未填写'}</p>
    <label htmlFor={`review-reply-${commentId}`} className="space-y-2 text-sm">完整保存回复（可用键盘或鼠标选取修改声明）<Textarea id={`review-reply-${commentId}`} readOnly value={context.state.response_text || ''} onSelect={(event) => setSelection({ start: event.currentTarget.selectionStart, end: event.currentTarget.selectionEnd })} aria-label="选择完整回复中的修改声明" /></label>
    <fieldset disabled={disabled} className="space-y-2 text-sm"><legend>本次作者决定</legend>
      <label className="flex items-center gap-2"><input type="radio" name={`response-outcome-${commentId}`} checked={outcome === 'MODIFIED'} onChange={() => { setOutcome('MODIFIED'); setAcknowledged(false); }} />已经修改，逐条对应实际变化</label>
      <label className="flex items-center gap-2"><input type="radio" name={`response-outcome-${commentId}`} checked={outcome === 'EXPLAINED_NO_CHANGE'} onChange={() => { setOutcome('EXPLAINED_NO_CHANGE'); setAcknowledged(false); }} />决定不修改，回复中已说明理由</label>
    </fieldset>
    <details><summary>被审稿与最终稿的实际文字差异</summary><pre className="whitespace-pre-wrap break-words text-xs">{context.baseline_to_target_diff || '没有可证明的基准文字差异。'}</pre></details>
    {outcome === 'MODIFIED' ? <div className="space-y-3">
      <Button size="sm" variant="outline" disabled={disabled || selection.end <= selection.start} onClick={addSelection}>加入所选修改声明</Button>
      {claims.map((claim, index) => <fieldset disabled={disabled} key={`${claim.start}-${claim.end}`} className="space-y-2 rounded border p-3 text-sm">
        <legend>修改声明 {index + 1}</legend><p className="whitespace-pre-wrap break-words">{claim.text}</p>
        {context.evidence.map((row) => <label key={row.evidence_id} className="flex items-start gap-2">
          <Checkbox aria-label={`声明 ${index + 1} 对应 ${row.changed_text || '无法定位的变化'}`} disabled={row.status !== 'GENERATED_TEXT_CHANGED'} checked={claim.evidence_ids.includes(row.evidence_id)} onCheckedChange={(checked) => { setClaims((current) => current.map((item, i) => i === index ? { ...item, evidence_ids: checked ? [...item.evidence_ids, row.evidence_id] : item.evidence_ids.filter((id) => id !== row.evidence_id) } : item)); setAcknowledged(false); }} />
          <span className="min-w-0 whitespace-pre-wrap break-words">{row.changed_text || '结构或来源变化尚无法对应成文'}<small className="block text-muted-foreground">{row.status === 'GENERATED_TEXT_CHANGED' ? `最终 PDF 第 ${row.final_page} 页，可见文本第 ${row.final_line} 行${row.final_line_end !== row.final_line ? ` 至第 ${row.final_page_end} 页第 ${row.final_line_end} 行` : ''}` : row.status === 'EXACT_BASELINE_TEXT_RETAINED' ? '与基准稿文字相同，不能证明已修改' : '尚无足够的最终稿定位依据'}</small></span>
        </label>)}
        {!context.evidence.length ? <p>没有属于此意见的最终稿改动依据。</p> : null}
        <Button size="sm" variant="ghost" onClick={() => { setClaims((current) => current.filter((_, i) => i !== index)); setAcknowledged(false); }}>移除此声明</Button>
      </fieldset>)}
      <p className="text-xs text-muted-foreground">行号按实际 PDF 页面从上到下的可见文本计数。保留文字、已撤回改动及无法定位的变化不能作为完成依据。</p>
    </div> : <p className="text-sm">确认之前，请确保决定中保留不修改的理由，完整回复没有声称实施了未发生的修改。</p>}
    <label className="flex items-start gap-2 text-sm"><Checkbox disabled={disabled} checked={acknowledged} onCheckedChange={(checked) => setAcknowledged(Boolean(checked))} /><span>{outcome === 'MODIFIED' ? '我已检查完整回复，将每处“已修改”声明逐条列出，并核对所选实际变化。' : '我已检查完整回复，保留不修改的理由，且没有遗漏需要核对的修改声明。'}</span></label>
    {notice ? <output aria-live="polite" className="text-sm">{notice}</output> : null}
    {context.pdf_artifact_id ? <a className="text-sm underline" href={studioFileUrl(`/artifacts/${context.pdf_artifact_id}`)} target="_blank" rel="noreferrer">查看本版最终 PDF</a> : null}
    <details><summary>保留的核对历史（{context.history.length}）</summary><ResponseHistory history={context.history} /></details>
    <div className="flex flex-wrap justify-end gap-2"><Button variant="outline" onClick={() => onOpenChange(false)}>返回</Button><Button disabled={disabled || stale || !acknowledged || !context.state.response_text?.trim() || !context.state.author_decision?.trim() || (outcome === 'MODIFIED' && (!context.baseline_to_target_diff || !claims.length || claims.some((item) => !item.evidence_ids.length)))} onClick={() => {
      void onConfirm({ request_id: crypto.randomUUID(), context_sha256: context.context_sha256, outcome, claims: outcome === 'MODIFIED' ? claims : [], acknowledged_all_assertions: true });
    }}>作者确认并保存核对记录</Button></div>
    <p className="text-xs text-muted-foreground">此记录证明作者核对过所列回复与版本。研究结论是否成立，仍需正式科研验收。</p>
  </DialogContent></Dialog>;
}

function ResponseHistory({ history }: { history: ResponseReviewContext['history'] }) {
  return <div>{history.length ? history.map((check) => <section key={check.check_id} className="space-y-2 border-t py-2 text-sm">
    <p>{new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(check.created_at))} · {check.outcome === 'MODIFIED' ? '作者确认修改' : '作者确认不修改及理由'}</p>
    <p>成文 v{check.context.target_version_number}</p><p className="whitespace-pre-wrap break-words">{check.context.state.author_decision}</p><p className="whitespace-pre-wrap break-words">{check.context.state.response_text}</p>
    {check.request.claims.map((claim) => <div key={`${claim.start}-${claim.end}`}><p className="whitespace-pre-wrap break-words">已核对声明：{claim.text}</p>{claim.evidence_ids.map((id) => {
      const row = check.context.evidence.find((item) => item.evidence_id === id);
      return row ? <p key={id} className="whitespace-pre-wrap break-words text-muted-foreground">{row.changed_text} · 当时的最终 PDF 第 {row.final_page} 页，可见文本第 {row.final_line} 行</p> : null;
    })}</div>)}
  </section>) : <p className="text-sm text-muted-foreground">尚无作者核对记录。原意见和已保存回复仍保留。</p>}</div>;
}
