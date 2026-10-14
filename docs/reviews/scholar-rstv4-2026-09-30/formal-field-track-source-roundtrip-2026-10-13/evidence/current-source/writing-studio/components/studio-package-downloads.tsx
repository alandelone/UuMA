'use client';

import { FileDown, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { studioApi } from '@/lib/studio-api';
import type { SubmissionPackage } from '@/lib/studio-types';

const labels: Record<string, string> = {
  'clean-manuscript.pdf': '成文 PDF', 'clean-manuscript.tex': 'LaTeX 原稿',
  'clean-manuscript.md': 'Markdown 成文', 'references.bib': '参考文献',
  'response-to-reviewers.md': '审稿回复', 'marked-comparison.md': '与被审稿对照',
  'comment-change-map.csv': '意见与作者修改', 'change-location-map.csv': '最终稿位置表',
  'change-realization-map.json': '生成句子与实际位置', 'final-compiled-layout.xhtml': 'PDF 文字层位置',
  'unresolved-comments.json': '未完成意见', 'generated.json': '固定成文与来源记录',
  'author-structure.json': '固定作者结构', 'generation-model-calls.json': '生成调用记录',
  'manifest.json': '文件与版本清单',
};

export function StudioPackageDownloads({ manuscriptId, activeVersionId, selectedRoundId, refreshKey }: {
  manuscriptId: string;
  activeVersionId: string | null;
  selectedRoundId?: string;
  refreshKey: string;
}) {
  const [packages, setPackages] = useState<SubmissionPackage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [downloading, setDownloading] = useState('');
  const [opened, setOpened] = useState('');
  const loadSequence = useRef(0);
  const load = useCallback(async (signal?: AbortSignal) => {
    const sequence = ++loadSequence.current;
    setLoading(true);
    setError('');
    try {
      const rows = await studioApi.packages(manuscriptId);
      if (!signal?.aborted && sequence === loadSequence.current) setPackages(rows);
    } catch (caught) {
      if (!signal?.aborted && sequence === loadSequence.current) setError(caught instanceof Error ? caught.message : '投稿包读取失败，请刷新重试。');
    } finally {
      if (!signal?.aborted && sequence === loadSequence.current) setLoading(false);
    }
  }, [manuscriptId]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, refreshKey]);
  useEffect(() => { setOpened(new URL(window.location.href).searchParams.get('package') || ''); }, []);

  const download = async (row: SubmissionPackage, filename?: string) => {
    if (downloading) return;
    setDownloading(`${row.package_id}:${filename || 'zip'}`);
    setError('');
    setNotice('');
    try {
      const blob = await studioApi.downloadPackage(manuscriptId, row.package_id, filename);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename || `${row.package_id}.zip`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setNotice('文件已交给浏览器下载。可在浏览器下载列表查看保存结果。');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '下载失败，请检查连接后重试。原投稿包仍保留。');
    } finally {
      setDownloading('');
    }
  };
  const rows = packages.filter((row) => !selectedRoundId || row.review_round_id === selectedRoundId);

  return <section className="studio-package-downloads" aria-label="已生成的投稿包" aria-busy={loading}>
    <header><h3>投稿包</h3><Button size="sm" variant="ghost" disabled={loading} onClick={() => void load()}><RefreshCw aria-hidden="true" /> 刷新</Button></header>
    <p className="package-status" aria-live="polite">{loading ? '正在读取固定文件…' : notice || (rows.length ? '每份文件固定到生成版本和被审轮次；旧包继续保留。' : selectedRoundId ? '此轮还没有投稿包。按“投稿包”生成后可在这里下载。' : '还没有投稿包。定稿或返修时生成后可在这里下载。')}</p>
    {error ? <p role="alert">{error}</p> : null}
    {rows.map((row) => {
      const name = `${row.generated_version_number ? `成文 v${row.generated_version_number}` : '历史成文'} · ${row.round_number ? `第 ${row.round_number} 轮` : '初次投稿'} · ${new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(row.created_at))}`;
      const unavailable = row.files.some((file) => !file.available);
      return <article key={row.package_id} className="submission-package" id={`submission-package-${row.package_id}`}>
        <header><strong>{name}</strong><Button size="sm" variant="outline" disabled={Boolean(downloading) || unavailable} onClick={() => void download(row)} aria-label={`下载 ${name} 完整投稿包`}><FileDown aria-hidden="true" /> {downloading === `${row.package_id}:zip` ? '正在下载…' : '下载整包'}</Button></header>
        {row.generated_version_id !== activeVersionId ? <p>这是保留的历史成文版本。</p> : null}
        {row.unresolved_comment_ids.length ? <p>{row.unresolved_comment_ids.length} 条意见尚未完成，回复需要作者核对。</p> : null}
        {row.location_summary?.unknown_or_unattributed_rows ? <p>{row.location_summary.unknown_or_unattributed_rows} 项修改的最终位置尚未确认，详见位置表。</p> : null}
        {row.integrity_status === 'LEGACY_ORIGINAL_DIGEST_UNAVAILABLE' ? <p>历史包未保存打包时的文件摘要，不能核实原始字节是否保持不变。</p> : null}
        {unavailable ? <p role="alert">固定文件已不可用。原包保留，请核对成文版本后生成新包。</p> : null}
        <details open={opened === row.package_id} onToggle={(event) => {
          const url = new URL(window.location.href);
          if (event.currentTarget.open) { setOpened(row.package_id); url.searchParams.set('package', row.package_id); }
          else { setOpened((current) => current === row.package_id ? '' : current); if (url.searchParams.get('package') === row.package_id) url.searchParams.delete('package'); }
          window.history.replaceState(window.history.state, '', url);
        }}><summary>单独下载文件 · {row.files.length}</summary><ul>{row.files.map((file) => <li key={file.name}><Button size="sm" variant="ghost" disabled={Boolean(downloading) || unavailable} aria-label={`下载 ${name} 的${labels[file.name] || file.name}`} onClick={() => void download(row, file.name)}>{downloading === `${row.package_id}:${file.name}` ? '正在下载…' : labels[file.name] || file.name}</Button><small>{file.name}</small></li>)}</ul></details>
      </article>;
    })}
  </section>;
}
