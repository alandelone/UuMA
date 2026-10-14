'use client';
import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import type { ReviewRound, Workspace } from '@/lib/studio-types';

export function StudioReviewRounds({
  rounds,
  selectedId,
  versions,
  activeVersionId,
  venue,
  disabled,
  onSelect,
  onCreate,
  onError,
}: {
  rounds: ReviewRound[];
  selectedId: string;
  versions: Workspace['manuscript']['versions'];
  activeVersionId: string | null;
  venue: string;
  disabled: boolean;
  onSelect: (id: string) => Promise<void>;
  onCreate: (number: number, versionId: string, venue: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [versionId, setVersionId] = useState('');
  const [newVenue, setNewVenue] = useState('');
  const [busy, setBusy] = useState(false);
  const venueId = useId();
  const selected = rounds.find((item) => item.review_round_id === selectedId);
  const nextNumber =
    Math.max(0, ...rounds.map((item) => item.round_number)) + 1;
  return (
    <section className="review-rounds" aria-label="返修轮次与固定被审版本">
      <label>
        返修轮次{' '}
        <select
          aria-label="选择返修轮次"
          disabled={disabled || busy || !rounds.length}
          value={selectedId}
          onChange={(event) =>
            void onSelect(event.target.value).catch((error) =>
              onError(error instanceof Error ? error.message : '轮次切换失败'),
            )
          }
        >
          <option value="">请选择轮次…</option>
          {rounds.map((item) => (
            <option value={item.review_round_id} key={item.review_round_id}>
              第 {item.round_number} 轮 · {item.venue || '未填写期刊／会议'}
            </option>
          ))}
        </select>
      </label>
      {selected ? (
        <p>
          {selected.baseline_available
            ? `固定被审稿 v${selected.baseline_version}${selected.baseline_document_revision === null ? '' : ` / 作者结构 r${selected.baseline_document_revision}`}；本轮生成不会移动基线。`
            : '此旧轮次的被审版本无法证明；保留意见，建立明确新轮次后再输出对照。'}
        </p>
      ) : (
        <p>请选择真实被审稿建立轮次，再确认导入意见。</p>
      )}
      <Button
        size="sm"
        variant="outline"
        disabled={disabled || busy || !versions.length}
        onClick={() => {
          setVersionId(activeVersionId || '');
          setNewVenue(venue);
          setOpen(true);
        }}
      >
        建立第 {nextNumber} 轮…
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value);
        }}
      >
        <DialogContent>
          <DialogTitle>建立第 {nextNumber} 轮返修</DialogTitle>
          <DialogDescription>
            明确选择这一轮实际被审的成文版本。后续编辑和生成不会更换本轮基线。
          </DialogDescription>
          <label className="grid gap-1">
            被审成文版本
            <select
              value={versionId}
              onChange={(event) => setVersionId(event.target.value)}
              disabled={busy}
            >
              <option value="">选择固定版本…</option>
              {versions.map((item) => (
                <option
                  key={item.manuscript_version_id}
                  value={item.manuscript_version_id}
                >
                  成文 v{item.version}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1" htmlFor={venueId}>
            期刊／会议
            <Input
              id={venueId}
              value={newVenue}
              disabled={busy}
              onChange={(event) => setNewVenue(event.target.value)}
            />
          </label>
          <Button
            disabled={busy || !versionId}
            onClick={async () => {
              setBusy(true);
              try {
                await onCreate(nextNumber, versionId, newVenue.trim());
                setOpen(false);
              } catch (error) {
                onError(
                  error instanceof Error ? error.message : '轮次建立失败',
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? '保存固定被审版本…' : '确认建立这一轮'}
          </Button>
        </DialogContent>
      </Dialog>
    </section>
  );
}
