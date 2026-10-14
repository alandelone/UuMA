import { studioFileUrl } from '@/lib/studio-downloads';
import type { GeneratedReference } from '@/lib/studio-types';

export function StudioSourceContext({ reference, manuscriptId, versionId, sourcePdfUrl }: {
  reference: Pick<GeneratedReference, 'evidence_id' | 'source_context' | 'location'>;
  manuscriptId: string; versionId?: string; sourcePdfUrl?: string;
}) {
  const context = reference.source_context;
  if (!context?.available || !context.unit) return <p>原文上下文与精确文件版本不可用：此历史来源未记录完整出处。</p>;
  const selected = context.unit;
  const units = context.units || [];
  const index = units.findIndex((unit) => unit.unit_id === selected.unit_id);
  const surrounding = index < 0 ? [selected] : units.slice(Math.max(index - 1, 0), index + 2);
  const page = typeof selected.page_idx === 'number' && Number.isInteger(selected.page_idx) && selected.page_idx > 0 ? `#page=${selected.page_idx}` : '';
  const pdf = sourcePdfUrl ? sourcePdfUrl + page : versionId
    ? studioFileUrl(`/manuscripts/${manuscriptId}/generated-versions/${versionId}/sources/${reference.evidence_id}/pdf`) + page : null;
  return <div className="source-context" aria-label="固定原文与上下文">
    <p>出处：{selected.page_idx == null ? '页码未记录' : `第 ${selected.page_idx} 页`} · {selected.section || '章节未记录'} · 原文单元 {selected.seq_idx + 1}</p>
    <p>论文版本 {context.paper_version ?? '未知'} · {context.parse_run_id ? '解析版本已固定' : '解析版本未记录'} · Skeleton 版本 {context.version ?? '未知'}</p>
    <details open><summary>原文单元与前后文</summary>
      {surrounding.map((unit) => <div key={unit.unit_id} aria-label={unit.unit_id === selected.unit_id ? '引用原文单元' : '相邻原文单元'}>
        <small>{unit.page_idx == null ? '页码未记录' : `第 ${unit.page_idx} 页`} · {unit.section || '章节未记录'}</small>
        <blockquote style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{unit.raw_text}</blockquote>
      </div>)}
    </details>
    <details><summary>{context.parse_run_id ? '此解析版本的完整文字' : '此来源的全部原文单元'}</summary>
      {context.parsed_blocks?.length ? context.parsed_blocks.map((block) => <div key={block.block_id}>
        <small>{block.page_number == null ? '页码未记录' : `第 ${block.page_number} 页`} · {block.section || '章节未记录'}</small>
        <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{block.text}</p>
      </div>) : <p>完整解析文字不可用；下方保留此来源的全部原文单元。</p>}
      {!context.parsed_blocks?.length ? units.map((unit) => <blockquote key={unit.unit_id} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{unit.raw_text}</blockquote>) : null}
    </details>
    <details><summary>查看精确版本与位置记录</summary>
      <p style={{ overflowWrap: 'anywhere' }}>论文版本：{context.paper_version_id || '未记录'}<br />解析：{context.parse_run_id || '未记录'}<br />文件：{context.file_version_id || '未记录'}<br />Skeleton：{context.skeleton_id || '未记录'}</p>
      <p style={{ overflowWrap: 'anywhere' }}>位置：{JSON.stringify(reference.location || {})}</p>
    </details>
    {context.file_version && pdf ? <a target="_blank" rel="noreferrer" href={pdf}>查看此版本原始 PDF ↗</a> : null}
    {!context.full_text_available ? <p>原始 PDF 不可用：{context.file_version ? '文件缺失或未通过完整性核对；打开时会重新核对。' : '未记录精确文件版本。'}</p> : null}
  </div>;
}
