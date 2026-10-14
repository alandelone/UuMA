from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1]
path = root.parent / 'writing-studio/components/studio-workspace.tsx'
audit = root / '.tmp/scholar-native-import-v1/comments-read-recovery-v1'
audit.mkdir(parents=True, exist_ok=True)
raw = path.read_bytes()
before = audit / 'studio-workspace.tsx.before.raw'
assert before.read_bytes() == raw, 'Source changed since scoped backup; inspect first'
text = raw.decode('utf-8').replace('\r\n', '\n')

def replace(old, new):
    global text
    assert text.count(old) == 1, (old[:140], text.count(old))
    text = text.replace(old, new)

replace('  const [commentsReady, setCommentsReady] = useState(false);', '''  const [commentsReady, setCommentsReady] = useState(false);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentsReadError, setCommentsReadError] = useState('');
  const [commentsSavedReadPending, setCommentsSavedReadPending] = useState(false);
  const commentsReadSerial = useRef(0);
  const commentsReadConfirmedRef = useRef(false);
  const commentsReadConfirmed = commentsReady && !commentsLoading && !commentsReadError;''')
start = text.index('  const loadComments = useCallback(async () => {')
end = text.index('\n\n  const loadChat', start)
old = text[start:end]
replace(old, '''  const loadComments = useCallback(async () => {
    const serial = ++commentsReadSerial.current;
    commentsReadConfirmedRef.current = false;
    setCommentsLoading(true);
    try {
      const [all, rounds] = await Promise.all([studioApi.comments(workspace.manuscript.manuscript_id, true), studioApi.reviewRounds(workspace.manuscript.manuscript_id)]);
      if (serial !== commentsReadSerial.current) return;
      setReviewRounds(rounds);
      setReviewRoundId((current) => rounds.some((item) => item.review_round_id === current) ? current : rounds.at(-1)?.review_round_id || '');
      setComments(all.filter((item) => !item.archived_at));
      setArchivedComments(all.filter((item) => Boolean(item.archived_at)));
      setCommentsReady(true);
      setCommentsReadError('');
      setCommentsSavedReadPending(false);
      commentsReadConfirmedRef.current = true;
      const validIds = new Set(all.filter((item) => !item.archived_at).map((item) => item.comment_id));
      setActiveCommentIds((current) => {
        const valid = current.filter((id) => validIds.has(id));
        activeCommentsRef.current = valid;
        return valid;
      });
    } catch (caught) {
      if (serial !== commentsReadSerial.current) return;
      setCommentsReadError(caught instanceof Error ? caught.message : '意见与轮次读取失败');
      throw caught;
    } finally {
      if (serial === commentsReadSerial.current) setCommentsLoading(false);
    }
  }, [workspace.manuscript.manuscript_id]);''')
replace('''    void loadComments().catch((caught) =>
      setStatusMessage(caught instanceof Error ? caught.message : '意见与修改记录读取失败'),
    );
  }, [loadComments, viewMode]);''', '''    void loadComments().catch(() => { /* Dedicated read state retains the last good data. */ });
    return () => {
      commentsReadSerial.current += 1;
      commentsReadConfirmedRef.current = false;
    };
  }, [loadComments, viewMode]);''')
replace('''          ) : (
            <RevisionView
              manuscriptId={workspace.manuscript.manuscript_id}''', '''          ) : (
            <>
            <section aria-label="意见与轮次读取状态" className="px-4 py-3">
              {commentsReadError ? <p role="alert">意见与轮次读取失败：{commentsReadError}。{commentsReady ? '当前显示上次读取的数据。' : '暂时无法确认已保存的意见与轮次。'}</p> : null}
              {commentsLoading ? <p role="status">正在读取返修轮次与意见…</p> : null}
              {commentsSavedReadPending ? <p role="status">意见或轮次已保存；读取结果暂未确认。请重新读取，无需再次提交。</p> : null}
              <Button size="sm" variant="outline" disabled={commentsLoading} onClick={() => void loadComments().catch(() => {})}>重新读取意见与轮次</Button>
            </section>
            <RevisionView
              commentsReady={commentsReadConfirmed}
              onImportSaved={() => setCommentsSavedReadPending(true)}
              manuscriptId={workspace.manuscript.manuscript_id}''')
replace('venue={document.venue} disabled={disabled} onSelect={async (id) => { if (await changeCommentContext([]))', '''venue={document.venue} disabled={disabled || !commentsReadConfirmed} onSelect={async (id) => { if (!commentsReadConfirmedRef.current) throw new Error('请先重新读取意见与轮次。'); if (await changeCommentContext([]))''')
replace('''onCreate={async (number, versionId, venue) => {
                await flushSave();''', '''onCreate={async (number, versionId, venue) => {
                if (!commentsReadConfirmedRef.current) throw new Error('请先重新读取意见与轮次。');
                await flushSave();''')
replace('''                if (!(await changeCommentContext([]))) throw new Error('原意见上下文尚未结束。');
                const row =''', '''                if (!(await changeCommentContext([]))) throw new Error('原意见上下文尚未结束。');
                if (!commentsReadConfirmedRef.current) throw new Error('请先重新读取意见与轮次。');
                const row =''')
replace('''                setReviewRoundId(row.review_round_id);
                await loadComments();''', '''                setReviewRoundId(row.review_round_id);
                setCommentsSavedReadPending(true);
                await loadComments().catch(() => {});''')
replace('''              onEnsureRound={async () => {
                if (reviewRoundId)''', '''              onEnsureRound={async () => {
                if (!commentsReadConfirmedRef.current) throw new Error('请先重新读取意见与轮次；预览与原文仍保留。');
                if (reviewRoundId)''')
replace('''              onPackage={() => void startJob('SUBMISSION_PACKAGE')}
              onError={setStatusMessage}
            />
          )}''', '''              onPackage={() => void startJob('SUBMISSION_PACKAGE')}
              onError={setStatusMessage}
            />
            </>
          )}''')
replace('''function RevisionView({
  manuscriptId,''', '''function RevisionView({
  commentsReady,
  onImportSaved,
  manuscriptId,''')
replace('''  onError,
}: {
  manuscriptId: string;
  comments: ReviewComment[];''', '''  onError,
}: {
  commentsReady: boolean;
  onImportSaved: () => void;
  manuscriptId: string;
  comments: ReviewComment[];''')
replace('if (!selectedCount || importBusy) return;', 'if (!selectedCount || importBusy || !commentsReady) return;')
replace('const round = reviewRoundId || (await onEnsureRound());', 'const round = await onEnsureRound();')
replace('''      const retained = afterCommentImport(preview);''', '''      onImportSaved();
      const retained = afterCommentImport(preview);''')
replace('''      await onReload();
      onError(retained.remaining ?''', '''      try {
        await onReload();
      } catch {
        // The import was acknowledged. Retain imported flags and retry reads only.
        return;
      }
      onError(retained.remaining ?''')
replace('disabled={importBusy || fileBusy || !selectedCount || selectedCount > 100}', 'disabled={!commentsReady || importBusy || fileBusy || !selectedCount || selectedCount > 100}')
replace("{comments.length === 0 ? <p className=\"panel-empty\">{archived ?", "{commentsReady && comments.length === 0 ? <p className=\"panel-empty\">{archived ?")
updated = text.replace('\n', '\r\n').encode('utf-8')
path.write_bytes(updated)
(audit / 'repair-v1.json').write_text(json.dumps({'path':str(path), 'before_sha256':hashlib.sha256(raw).hexdigest(), 'after_sha256':hashlib.sha256(updated).hexdigest(), 'crlf_preserved':updated.count(b'\r\n') == updated.count(b'\n')}, indent=2), encoding='utf-8')
print('PASS: exact scoped source replacements; raw backup and CRLF preserved.')
