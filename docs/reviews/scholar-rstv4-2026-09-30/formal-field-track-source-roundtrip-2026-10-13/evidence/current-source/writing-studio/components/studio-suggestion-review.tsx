'use client';

import { useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';
import { ApiError, studioApi } from '@/lib/studio-api';
import type {
  SuggestionDecisionRequest,
  SuggestionDecisionResponse,
  SuggestionOutcome,
  SuggestionPreview,
  StudioSuggestion,
} from '@/lib/studio-types';

const KINDS = {
  STRUCTURE: '结构建议',
  SOURCE: '来源候选',
  WORDING: '措辞建议',
};
const OUTCOMES = {
  ACCEPT_ALL: '完整采纳',
  ACCEPT_PARTIAL: '部分采纳',
  REJECT: '已拒绝',
};
const FIELDS: Record<string, string> = {
  role: '章节功能',
  purpose: '段落目的',
  paradigm: '组织方式',
  label: 'Intent 标签',
  text: '作者思想',
  title: '标题',
  abstract: '摘要',
};

function beforeText(value: string | string[] | null) {
  return Array.isArray(value)
    ? `已有 ${value.length} 个结构块，保留原有内容和顺序。`
    : value || '（空）';
}

function proposedText(change: SuggestionPreview['changes'][number]) {
  if (change.action === 'ADD_SOURCE')
    return `${change.evidence?.title || change.evidence?.evidence_id}\n${change.evidence?.statement}\n${change.evidence?.excerpt || ''}`;
  if (typeof change.value === 'string')
    return change.after_preview ?? change.value;
  if (change.action === 'INSERT_INTENT')
    return `追加 Intent：${change.value?.label}\n作者思想留空。`;
  return `追加段落：${change.value?.purpose || '目的待定'}\n组织方式：${change.value?.paradigm || '待定'}\nIntent：${change.value?.intents?.map((item) => item.label).join('、') || '待作者填写'}\n作者思想留空。`;
}

export function StudioSuggestionReview({
  manuscriptId,
  messageId,
  suggestions,
  prepare,
  commentIds,
  decide,
}: {
  manuscriptId: string;
  messageId: string;
  suggestions: StudioSuggestion[];
  prepare: () => Promise<void>;
  commentIds: () => string[];
  decide: (
    request: SuggestionDecisionRequest,
    retry: boolean,
  ) => Promise<SuggestionDecisionResponse>;
}) {
  const [preview, setPreview] = useState<SuggestionPreview | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState<string[]>([]);
  const [notice, setNotice] = useState('');
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const pending = useRef<SuggestionDecisionRequest | null>(null);
  const inFlight = useRef(false);

  const load = async (suggestionId: string) => {
    const fresh = await studioApi.suggestionPreview(
      manuscriptId,
      messageId,
      suggestionId,
    );
    setPreview(fresh);
    setNeedsRefresh(false);
    setChosen(
      fresh.changes
        .filter((item) => item.available && !item.already_adopted)
        .map((item) => item.change_id),
    );
    setConfirmed([]);
  };

  const compare = async (suggestionId: string) => {
    if (inFlight.current) return;
    if (pending.current) {
      setOpen(true);
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setNotice('');
    try {
      await prepare();
      await load(suggestionId);
      setOpen(true);
    } catch (caught) {
      setNotice(
        caught instanceof Error ? caught.message : '建议比较读取失败，请重试。',
      );
    } finally {
      setBusy(false);
      inFlight.current = false;
    }
  };

  const submit = async (outcome: SuggestionOutcome, retry = false) => {
    if (!preview || inFlight.current) return;
    const request = retry
      ? pending.current
      : {
          suggestion_id: preview.suggestion.suggestion_id,
          decision_id: `suggestion_decision_${crypto.randomUUID()}`,
          outcome,
          base_revision: preview.document_revision,
          selected_change_ids: outcome === 'REJECT' ? [] : [...chosen],
          confirmed_changed_ids:
            outcome === 'REJECT'
              ? []
              : confirmed.filter((id) => chosen.includes(id)),
          comment_ids: outcome === 'REJECT' ? [] : commentIds(),
        };
    if (!request) return;
    pending.current = request;
    inFlight.current = true;
    setBusy(true);
    setNotice('正在记录作者决定…');
    try {
      const result = await decide(request, retry);
      pending.current = null;
      setUnconfirmed(false);
      setNotice(
        `${OUTCOMES[result.decision.outcome]}，决定已保存。${result.idempotent_replay ? '已核对同一次决定，未重复应用。' : ''}`,
      );
      try {
        await load(request.suggestion_id);
      } catch {
        setNeedsRefresh(true);
        setNotice('决定已保存；比较记录暂时无法刷新，请重试读取。');
      }
    } catch (caught) {
      if (
        caught instanceof ApiError &&
        [400, 404, 409, 422].includes(caught.status)
      ) {
        pending.current = null;
        setUnconfirmed(false);
        setNeedsRefresh(true);
      } else setUnconfirmed(true);
      setNotice(
        caught instanceof Error
          ? caught.message
          : '决定结果尚未确认，请核对同一次决定。',
      );
    } finally {
      setBusy(false);
      inFlight.current = false;
    }
  };

  const selected =
    preview?.changes.filter((item) => chosen.includes(item.change_id)) || [];
  const ready =
    !needsRefresh &&
    selected.length > 0 &&
    selected.every(
      (item) =>
        item.available &&
        !item.already_adopted &&
        (!item.target_changed || confirmed.includes(item.change_id)),
    );

  return (
    <section className="mt-3 space-y-2" aria-label="待作者审核的建议">
      {suggestions.map((suggestion) => (
        <div key={suggestion.suggestion_id} className="rounded-md border p-3">
          <p className="text-xs text-muted-foreground">
            {KINDS[suggestion.kind]}
          </p>
          <p className="font-medium">{suggestion.title}</p>
          <p className="text-sm">{suggestion.rationale}</p>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void compare(suggestion.suggestion_id)}
          >
            比较与决定 · {suggestion.changes.length} 项
          </Button>
        </div>
      ))}
      {!open && notice ? <output className="block">{notice}</output> : null}
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy && !unconfirmed) setOpen(value);
        }}
      >
        <DialogContent
          className="max-h-[85dvh] overflow-y-auto sm:max-w-4xl"
          showCloseButton={!busy && !unconfirmed}
        >
          <DialogTitle>
            {preview
              ? `${KINDS[preview.suggestion.kind]} · ${preview.suggestion.title}`
              : '比较建议'}
          </DialogTitle>
          <DialogDescription>
            原对象：{preview?.source.label} · 结构 r
            {preview?.source.anchor_revision}；当前保存版本 r
            {preview?.document_revision}。勾选要采用的改动，再记录决定。
          </DialogDescription>
          {preview?.changes.map((change, index) => (
            <section
              key={change.change_id}
              className="space-y-2 rounded-lg border p-3"
            >
              <div className="flex items-start gap-2">
                <Checkbox
                  id={`adopt-${change.change_id}`}
                  checked={chosen.includes(change.change_id)}
                  disabled={
                    busy ||
                    unconfirmed ||
                    !change.available ||
                    change.already_adopted
                  }
                  onCheckedChange={(checked) =>
                    setChosen((current) =>
                      checked
                        ? [...current, change.change_id]
                        : current.filter((id) => id !== change.change_id),
                    )
                  }
                />
                <label
                  htmlFor={`adopt-${change.change_id}`}
                  className="font-medium"
                >
                  {index + 1}. {change.current_label || change.target_label}
                  {change.field
                    ? ` · ${FIELDS[change.field] || change.field}`
                    : ''}
                </label>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                {[
                  ['建议依据的原文', beforeText(change.before)],
                  ['当前原文', beforeText(change.current_before)],
                  ['拟采用内容', proposedText(change)],
                ].map(([label, body]) => (
                  <div key={label} className="min-w-0">
                    <h3 className="text-xs font-medium text-muted-foreground">
                      {label}
                    </h3>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm">
                      {body}
                    </p>
                  </div>
                ))}
              </div>
              {change.already_adopted ? (
                <p>这项已采纳，原决定保留在记录中。可从编辑器撤销或重做。</p>
              ) : !change.available ? (
                <output className="block">
                  {change.range_changed
                    ? '原选区位置已经变化，请针对新选区重新讨论。'
                    : change.source_unavailable
                      ? '原来源已不可用，请重新讨论并核对来源。'
                      : '原对象已不可用，无法采用这一项。'}
                </output>
              ) : change.target_changed ? (
                <div className="flex items-start gap-2">
                  <Checkbox
                    id={`confirm-${change.change_id}`}
                    disabled={
                      busy || unconfirmed || !chosen.includes(change.change_id)
                    }
                    checked={confirmed.includes(change.change_id)}
                    onCheckedChange={(checked) =>
                      setConfirmed((current) =>
                        checked
                          ? [...current, change.change_id]
                          : current.filter((id) => id !== change.change_id),
                      )
                    }
                  />
                  <label htmlFor={`confirm-${change.change_id}`}>
                    原对象已更新；我已比较原文与当前内容，确认应用这一项。
                  </label>
                </div>
              ) : null}
              {change.action === 'ADD_SOURCE' ? (
                <p className="text-sm text-muted-foreground">
                  加入未选中的来源候选；请在思想块的引用菜单中决定是否引用。
                </p>
              ) : null}
            </section>
          ))}
          {preview?.decisions.length ? (
            <section aria-label="作者决定记录">
              <h3 className="font-medium">决定记录</h3>
              {preview.decisions.map((decision) => (
                <p key={decision.decision_id} className="text-sm">
                  {OUTCOMES[decision.outcome]} ·{' '}
                  {decision.request.selected_change_ids.length} 项 · 结构 r
                  {decision.provenance.author_revision_at_decision} ·{' '}
                  <time dateTime={decision.created_at}>
                    {new Date(decision.created_at).toLocaleString()}
                  </time>
                </p>
              ))}
            </section>
          ) : null}
          <output className="block" aria-live="polite">
            {notice}
          </output>
          {unconfirmed ? (
            <div>
              <p>上次请求的结果待确认。重试会核对同一次决定。</p>
              <Button
                disabled={busy}
                onClick={() =>
                  void submit(pending.current?.outcome || 'REJECT', true)
                }
              >
                核对并重试原决定
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button
                disabled={
                  busy || !ready || chosen.length !== preview?.changes.length
                }
                onClick={() => void submit('ACCEPT_ALL')}
              >
                完整采纳
              </Button>
              <Button
                variant="outline"
                disabled={
                  busy || !ready || chosen.length === preview?.changes.length
                }
                onClick={() => void submit('ACCEPT_PARTIAL')}
              >
                采纳勾选项（部分）
              </Button>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => void submit('REJECT')}
              >
                拒绝建议
              </Button>
              <Button
                variant="ghost"
                disabled={busy || !preview}
                onClick={() =>
                  preview && void compare(preview.suggestion.suggestion_id)
                }
              >
                刷新比较
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
