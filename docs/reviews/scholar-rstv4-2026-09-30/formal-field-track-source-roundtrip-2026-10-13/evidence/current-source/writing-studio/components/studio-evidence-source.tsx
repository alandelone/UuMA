'use client';

import { useEffect, useState } from 'react';
import { studioApi } from '@/lib/studio-api';
import { studioFileUrl } from '@/lib/studio-downloads';
import type { EvidenceSourceDetails } from '@/lib/studio-types';
import { StudioSourceContext } from '@/components/studio-source-context';

export function StudioEvidenceSource({ manuscriptId, evidenceId }: {
  manuscriptId: string; evidenceId: string;
}) {
  const [open, setOpen] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [source, setSource] = useState<EvidenceSourceDetails | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setSource(null);
    setError('');
    void studioApi.source(manuscriptId, evidenceId).then((value) => {
      if (!cancelled) setSource(value);
    }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : '原来源读取失败。');
    });
    return () => { cancelled = true; };
  }, [open, attempt, manuscriptId, evidenceId]);
  const context = source?.source_context;
  const pdf = context?.context_sha256 ? studioFileUrl(
    `/manuscripts/${encodeURIComponent(manuscriptId)}/sources/${encodeURIComponent(evidenceId)}/contexts/${encodeURIComponent(context.context_sha256)}/pdf`,
  ) : undefined;
  return <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>查看完整来源</summary>
    {open ? <div aria-label="当前资料的精确原来源">
      {!source && !error ? <output>正在读取原文与精确版本…</output> : null}
      {error ? <><p role="alert">原来源不可用：{error}</p><button type="button" onClick={() => setAttempt((value) => value + 1)}>重试读取原来源</button></> : null}
      {source ? <>
        <strong>{source.title || '未提供题名'}</strong>
        <p>{source.authors.join(', ')} {source.published_year || ''}</p>
        <p>{source.statement}</p>
        <blockquote style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{source.excerpt}</blockquote>
        <StudioSourceContext reference={source} manuscriptId={manuscriptId} sourcePdfUrl={pdf} />
      </> : null}
    </div> : null}
  </details>;
}
