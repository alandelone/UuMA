'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, BookOpenText, FilePlus2, RefreshCw } from 'lucide-react';

import { StudioWorkspace } from '@/components/studio-workspace';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { studioApi } from '@/lib/studio-api';
import { catalogReturnUrl } from '@/lib/catalog-return';
import { manuscriptNavigationUrl } from '@/lib/studio-view-state';
import type { TrackRecord, Workspace } from '@/lib/studio-types';

const DEMO_PAPERS: Record<string, { track: string; stage: string }> = {
  'Sky Image Forecasting for Islanded Microgrids': {
    track: 'All-sky image forecasting', stage: '写作中',
  },
  'Benchmarking Solar Nowcasting Models': {
    track: 'All-sky image forecasting', stage: '返修中',
  },
  'Cloud Motion for Solar Forecasting': {
    track: 'Satellite cloud motion', stage: '规划中',
  },
  'Solar Nowcasting in Microgrid Control': {
    track: 'Islanded microgrid control', stage: '写作中',
  },
  'Hybrid System Sizing under Variable Loads': {
    track: 'Hybrid system sizing', stage: '规划中',
  },
};

export default function Home() {
  const [tracks, setTracks] = useState<TrackRecord[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selectedTrack, setSelectedTrack] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [fromCatalog, setFromCatalog] = useState(false);
  const [demoPaper, setDemoPaper] = useState<string | null>(null);

  const loadTracks = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await studioApi.tracks();
      setTracks(result);
      setSelectedTrack((current) => current || result[0]?.track_id || '');
      const manuscriptId = new URLSearchParams(window.location.search).get(
        'manuscript',
      );
      setFromCatalog(new URLSearchParams(window.location.search).get('from') === 'catalog');
      if (manuscriptId) setWorkspace(await studioApi.workspace(manuscriptId));
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Writing Studio 无法连接 RSTV4。',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      const demo = new URLSearchParams(window.location.search).get('demo');
      if (demo && DEMO_PAPERS[demo]) {
        setDemoPaper(demo);
        setLoading(false);
        return;
      }
      void loadTracks();
    });
  }, [loadTracks]);

  if (demoPaper) {
    const paper = DEMO_PAPERS[demoPaper];
    return (
      <main className="track-page">
        <div className="track-page__inner">
          <header className="track-page__header">
            <div className="flex items-center gap-3">
              <div className="track-page__mark"><BookOpenText aria-hidden="true" /></div>
              <div><h1>WRITING STUDIO</h1><p>Scholar · RSTV4 · Paper 工作区</p></div>
            </div>
            <span className="text-sm text-muted-foreground">界面示意</span>
          </header>
          <section className="paper-index">
            <Button variant="outline" onClick={() => window.location.assign(
              process.env.NEXT_PUBLIC_PAPER_CATALOG_URL || 'http://127.0.0.1:8875/',
            )}><ArrowLeft /> 研究总览</Button>
            <article className="track-card mt-6">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">{paper.track} · Paper</p>
              <h2 className="mt-3 text-2xl font-semibold">{demoPaper}</h2>
              <p className="mt-3 text-sm text-muted-foreground">当前阶段：{paper.stage}</p>
              <p className="mt-6 rounded-xl bg-muted/60 p-4 text-sm text-muted-foreground">
                这是总览导航的示例稿件；尚无真实 manuscript ID 或正文。实际稿件会打开自己的写作工作区。
              </p>
            </article>
          </section>
        </div>
      </main>
    );
  }

  const openPaper = async (manuscriptId: string) => {
    setLoading(true);
    setError('');
    try {
      const result = await studioApi.workspace(manuscriptId);
      setWorkspace(result);
      const url = manuscriptNavigationUrl(window.location.href, manuscriptId);
      window.history.replaceState({}, '', url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法打开稿件。');
    } finally {
      setLoading(false);
    }
  };

  const createPaper = async () => {
    if (!selectedTrack || !newTitle.trim()) return;
    setLoading(true);
    setError('');
    try {
      const result = await studioApi.createManuscript(
        selectedTrack,
        newTitle.trim(),
      );
      setWorkspace(result);
      setNewTitle('');
      const url = manuscriptNavigationUrl(window.location.href, result.manuscript.manuscript_id);
      window.history.replaceState({}, '', url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法创建稿件。');
    } finally {
      setLoading(false);
    }
  };

  if (workspace) {
    return (
      <StudioWorkspace
        key={workspace.manuscript.manuscript_id}
        initialWorkspace={workspace}
        backLabel={fromCatalog ? '研究总览' : 'Track'}
        onExit={() => {
          if (fromCatalog) {
            const url = catalogReturnUrl(window.location.search,
              process.env.NEXT_PUBLIC_PAPER_CATALOG_URL || 'http://127.0.0.1:8875/',
            );
            window.location.assign(url);
            return;
          }
          setWorkspace(null);
          const url = manuscriptNavigationUrl(window.location.href);
          window.history.replaceState({}, '', url);
          void loadTracks();
        }}
      />
    );
  }

  return (
    <main className="track-page">
      <div className="track-page__inner">
        <header className="track-page__header">
          <div className="flex items-center gap-3">
            <div className="track-page__mark">
              <BookOpenText aria-hidden="true" />
            </div>
            <div>
              <h1>WRITING STUDIO</h1>
              <p>Scholar · RSTV4 · Track → Paper</p>
            </div>
          </div>
          <Button
            variant="outline"
            size="icon"
            aria-label="重新读取 Track 与稿件"
            onClick={() => void loadTracks()}
          >
            <RefreshCw className={loading ? 'animate-spin' : ''} />
          </Button>
        </header>

        {error ? (
          <div className="mb-6 rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            <p>{error}</p>
            <p className="mt-1 text-foreground/65">
              请确认本机 RSTV4 Writing Studio 服务已经启动；离线时不会创建假资料。
            </p>
          </div>
        ) : null}

        <section className="new-paper-panel">
          <div className="mb-5 flex items-center gap-2">
            <FilePlus2 className="size-5 text-primary" aria-hidden="true" />
            <h2 className="text-lg font-semibold">在 Track 中开始一篇 Paper</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-[minmax(200px,0.7fr)_minmax(260px,1fr)_auto]">
            <select
              className="h-9 rounded-lg border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/40"
              value={selectedTrack}
              onChange={(event) => setSelectedTrack(event.target.value)}
              aria-label="选择 Track"
            >
              {tracks.map((track) => (
                <option key={track.track_id} value={track.track_id}>
                  {track.title}
                </option>
              ))}
            </select>
            <Input
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void createPaper();
              }}
              placeholder="Paper title"
              aria-label="新稿件标题"
            />
            <Button
              onClick={() => void createPaper()}
              disabled={!selectedTrack || !newTitle.trim() || loading}
            >
              ＋ 新 Paper
            </Button>
          </div>
        </section>

        <section className="paper-index">
          <div className="mb-4 flex items-end justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Track → Paper</p>
              <h2 className="text-xl font-semibold">写作工作区</h2>
            </div>
            <span className="text-sm text-muted-foreground">
              {tracks.reduce((count, track) => count + track.manuscripts.length, 0)}{' '}
              篇稿件
            </span>
          </div>
          {tracks.length === 0 && !loading ? (
            <div className="track-empty">
              <p className="font-medium">RSTV4 暂时没有 Track</p>
              <p className="mt-2 text-sm text-muted-foreground">
                先在 Scholar 中建立研究 Track，再从这里创建 Paper。
              </p>
            </div>
          ) : (
            <div className="track-list">
              {tracks.map((track) => (
                <article
                  key={track.track_id}
                  className="track-card"
                >
                  <div className="mb-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">
                      Track
                    </p>
                    <h3 className="mt-1 text-lg font-semibold">{track.title}</h3>
                    {track.scope ? (
                      <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                        {track.scope}
                      </p>
                    ) : null}
                  </div>
                  <div className="space-y-2">
                    {track.manuscripts.length === 0 ? (
                      <p className="rounded-xl bg-muted/60 px-3 py-4 text-sm text-muted-foreground">
                        还没有 Paper。
                      </p>
                    ) : (
                      track.manuscripts.map((paper) => (
                        <button
                          key={paper.manuscript_id}
                          type="button"
                          className="group flex w-full items-center justify-between rounded-xl border px-3 py-3 text-left transition hover:border-primary/40 hover:bg-primary/5"
                          onClick={() => void openPaper(paper.manuscript_id)}
                        >
                          <span>
                            <span className="block font-medium group-hover:text-primary">
                              {paper.title}
                            </span>
                            <span className="mt-0.5 block text-xs text-muted-foreground">
                              {paper.workflow_stage.replaceAll('_', ' ')}
                            </span>
                          </span>
                          <span aria-hidden="true">→</span>
                        </button>
                      ))
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
