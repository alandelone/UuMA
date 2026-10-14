# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: review-read-recovery.spec.ts >> Revision comments and rounds read recovery >> cold comments failure cannot masquerade as empty or permit round creation; retry reads only
- Location: ..\..\..\..\..\..\Alandelone\CodeSpace_Local\writing-studio\tests\e2e\review-read-recovery.spec.ts:140:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('Original software opinion A210', { exact: true })
Expected: visible
Error: strict mode violation: getByText('Original software opinion A210', { exact: true }) resolved to 2 elements:
    1) <p class="whitespace-pre-wrap">Original software opinion A210</p> aka getByRole('paragraph').filter({ hasText: 'Original software opinion A210' })
    2) <p class="whitespace-pre-wrap">Original software opinion A210</p> aka getByText('Original software opinion A210').nth(1)

Call log:
  - Expect "toBeVisible" getByText('Original software opinion A210', { exact: true }) with timeout 5000ms
  - waiting for getByText('Original software opinion A210', { exact: true })

```

# Page snapshot

```yaml
- main [ref=e2]:
  - generic [ref=e3]:
    - generic [ref=e4]:
      - generic [ref=e5]: WRITING STUDIO
      - generic [ref=e6]: Review read recovery fixture · RSTV4
    - generic [ref=e7]:
      - status [ref=e8]: 已自动保存
      - button "撤销" [disabled]
      - button "重做" [disabled]
      - button "Done" [ref=e9]
  - navigation "稿件视图" [ref=e10]:
    - button "返回 Track" [ref=e11]: Track
    - generic "Paper workflow stage" [ref=e12]:
      - generic [ref=e13]: 1 Planning
      - generic [ref=e14]: 2 Drafting
      - generic [ref=e15]: 3 全文检查
      - generic [ref=e16]: 4 定稿／投稿
      - generic [ref=e17]: 5 Revision
      - generic [ref=e18]: 6 Publication
    - generic "稿件内容视图" [ref=e19]:
      - button "🧩 结构" [ref=e20]
      - button "📄 成文" [ref=e21]
      - button "✍️ Revision" [ref=e22]
    - generic "面板显示" [ref=e23]:
      - button "显示或隐藏左侧样本" [ref=e24]
      - button "显示或隐藏右侧资料" [ref=e25]
  - generic "当前意见关联" [ref=e26]:
    - generic [ref=e27]:
      - strong [ref=e28]: 普通编辑
      - generic [ref=e29]: 后续修改不关联审稿意见
    - button "关联意见" [ref=e30]
  - generic [ref=e32]:
    - region "意见与轮次读取状态" [ref=e33]:
      - button "重新读取意见与轮次" [ref=e34]
    - generic [ref=e35]:
      - generic [ref=e36]:
        - generic [ref=e37]:
          - paragraph [ref=e38]: Reviewer comments
          - heading "意见 → 决定 → 修改 → 回复" [level=2] [ref=e39]
        - generic [ref=e40]:
          - button "🗃 已删除" [ref=e41]
          - button "📦 投稿包" [ref=e42]
      - region "返修轮次与固定被审版本" [ref=e43]:
        - generic [ref=e44]:
          - text: 返修轮次
          - combobox "选择返修轮次" [disabled] [ref=e45]:
            - option "请选择轮次…"
            - option "第 1 轮 · Recovery software fixture"
            - option "第 2 轮 · Recovery software fixture"
            - option "第 3 轮 · Recovery software fixture" [selected]
        - paragraph [ref=e46]: 固定被审稿 v5 / 作者结构 r62；本轮生成不会移动基线。
        - button "建立第 4 轮…" [disabled]
      - generic [ref=e47]:
        - textbox "审稿意见输入" [ref=e48]:
          - /placeholder: 粘贴意见；空行分条。确认前不会写入。
          - text: Local original preview stays available.
        - generic [ref=e49]:
          - button "👀 准备预览" [ref=e50]
          - button "➕ 单条新增" [ref=e51]
          - generic [ref=e52] [cursor=pointer]:
            - text: 📄 TXT / MD / DOCX / PDF
            - button "导入审稿意见文件" [ref=e53]
        - generic [ref=e54]:
          - status [ref=e55]: 预览 1 条，已选 1 条。每批最多 100 条。
          - group [ref=e56]:
            - generic "原始导入全文" [ref=e57]
          - generic [ref=e58]:
            - checkbox "纳入意见 1" [checked] [ref=e59]
            - checkbox [checked] [aria-hidden] [ref=e63]
            - textbox "编辑意见 1" [ref=e65]: Local original preview stays available.
          - generic [ref=e66]:
            - button "取消" [ref=e67]
            - button "✓ 确认导入 1 条" [ref=e68]
      - generic [ref=e69]:
        - article [ref=e70]:
          - button "开始修改意见 A207" [ref=e71]
          - generic "review-recovery-comment-207" [ref=e75]: A207
          - generic [ref=e76]:
            - generic [ref=e77]: 第 3 轮 · Software fixture
            - paragraph [ref=e78]: Original software opinion A207
            - group [ref=e79]:
              - generic "原意见与导入来源" [ref=e80]
            - generic [ref=e81]:
              - textbox "我的决定与理由 A207" [ref=e82]:
                - /placeholder: 我的决定与理由
              - textbox "回复内容 A207" [ref=e83]:
                - /placeholder: 回复内容
              - generic [ref=e84]:
                - combobox "意见状态 A207" [ref=e85]:
                  - option "待处理" [selected]
                  - option "已决定回应"
                  - option "修改中"
                  - option "待核对"
                  - option "已处理 · 需作者核对" [disabled]
                - button "保存回复" [ref=e86]
                - button "核对回复" [ref=e87]
                - button "查看核对历史" [ref=e88]
              - paragraph [ref=e89]: 回复尚未核对
            - generic [ref=e90]: 0 条关联修改
          - button "移入已删除 A207" [ref=e91]
        - article [ref=e92]:
          - button "开始修改意见 A208" [ref=e93]
          - generic "review-recovery-comment-208" [ref=e97]: A208
          - generic [ref=e98]:
            - generic [ref=e99]: 第 3 轮 · Software fixture
            - paragraph [ref=e100]: Original software opinion A208
            - group [ref=e101]:
              - generic "原意见与导入来源" [ref=e102]
            - generic [ref=e103]:
              - textbox "我的决定与理由 A208" [ref=e104]:
                - /placeholder: 我的决定与理由
              - textbox "回复内容 A208" [ref=e105]:
                - /placeholder: 回复内容
              - generic [ref=e106]:
                - combobox "意见状态 A208" [ref=e107]:
                  - option "待处理" [selected]
                  - option "已决定回应"
                  - option "修改中"
                  - option "待核对"
                  - option "已处理 · 需作者核对" [disabled]
                - button "保存回复" [ref=e108]
                - button "核对回复" [ref=e109]
                - button "查看核对历史" [ref=e110]
              - paragraph [ref=e111]: 回复尚未核对
            - generic [ref=e112]: 0 条关联修改
          - button "移入已删除 A208" [ref=e113]
        - article [ref=e114]:
          - button "开始修改意见 A209" [ref=e115]
          - generic "review-recovery-comment-209" [ref=e119]: A209
          - generic [ref=e120]:
            - generic [ref=e121]: 第 3 轮 · Software fixture
            - paragraph [ref=e122]: Original software opinion A209
            - group [ref=e123]:
              - generic "原意见与导入来源" [ref=e124]
            - generic [ref=e125]:
              - textbox "我的决定与理由 A209" [ref=e126]:
                - /placeholder: 我的决定与理由
              - textbox "回复内容 A209" [ref=e127]:
                - /placeholder: 回复内容
              - generic [ref=e128]:
                - combobox "意见状态 A209" [ref=e129]:
                  - option "待处理" [selected]
                  - option "已决定回应"
                  - option "修改中"
                  - option "待核对"
                  - option "已处理 · 需作者核对" [disabled]
                - button "保存回复" [ref=e130]
                - button "核对回复" [ref=e131]
                - button "查看核对历史" [ref=e132]
              - paragraph [ref=e133]: 回复尚未核对
            - generic [ref=e134]: 0 条关联修改
          - button "移入已删除 A209" [ref=e135]
        - article [ref=e136]:
          - button "开始修改意见 A210" [ref=e137]
          - generic "review-recovery-comment-210" [ref=e141]: A210
          - generic [ref=e142]:
            - generic [ref=e143]: 第 3 轮 · Software fixture
            - paragraph [ref=e144]: Original software opinion A210
            - group [ref=e145]:
              - generic "原意见与导入来源" [ref=e146]
            - generic [ref=e147]:
              - textbox "我的决定与理由 A210" [ref=e148]:
                - /placeholder: 我的决定与理由
              - textbox "回复内容 A210" [ref=e149]:
                - /placeholder: 回复内容
              - generic [ref=e150]:
                - combobox "意见状态 A210" [ref=e151]:
                  - option "待处理" [selected]
                  - option "已决定回应"
                  - option "修改中"
                  - option "待核对"
                  - option "已处理 · 需作者核对" [disabled]
                - button "保存回复" [ref=e152]
                - button "核对回复" [ref=e153]
                - button "查看核对历史" [ref=e154]
              - paragraph [ref=e155]: 回复尚未核对
            - generic [ref=e156]: 0 条关联修改
          - button "移入已删除 A210" [ref=e157]
      - region "已保存修改与意见关联" [ref=e158]:
        - generic [ref=e159]:
          - generic [ref=e160]:
            - heading "已保存修改" [level=3] [ref=e161]
            - text: 查看实际前后对照，分配给一条或多条意见。
          - generic [ref=e162]:
            - text: 显示
            - combobox "显示" [ref=e163]:
              - option "全部修改" [selected]
              - option "未关联意见"
              - option "已关联意见"
          - button "刷新修改历史" [ref=e164]
        - paragraph [ref=e165]: 此范围没有已保存修改。
      - region "已生成的投稿包" [ref=e166]:
        - generic [ref=e167]:
          - heading "投稿包" [level=3] [ref=e168]
          - button "刷新" [ref=e169]
        - paragraph [ref=e170]: 此轮还没有投稿包。按“投稿包”生成后可在这里下载。
  - status [ref=e171]
  - button [ref=e173]:
    - generic [ref=e174]: 与 Agent 讨论
    - generic [ref=e177]: 0 条 · Review read recovery fixture
```

# Test source

```ts
  49  |       if (state.holdReads) {
  50  |         await new Promise<void>((resolve, reject) => {
  51  |           state.held.push(async (mode) => {
  52  |             try {
  53  |               await json(route, mode === 'empty' ? [] : { detail: 'simulated old read failure' }, mode === 'empty' ? 200 : 503);
  54  |             } catch (error) {
  55  |               // Cancelling a superseded request also correctly rejects late data.
  56  |               if (!/aborted|closed|already handled|cancel/i.test(String(error))) { reject(error); throw error; }
  57  |             } finally { resolve(); }
  58  |           });
  59  |         });
  60  |         return;
  61  |       }
  62  |       if (state.failRead === kind) { await json(route, { detail: 'simulated ' + kind + ' read failure' }, 503); return; }
  63  |       await json(route, kind === 'comments' ? structuredClone(state.comments) : structuredClone(state.rounds)); return;
  64  |     }
  65  |     if (path === base + '/review-rounds' && method === 'POST') {
  66  |       state.createPosts++;
  67  |       const body = req.postDataJSON(), created = makeRound(body.round_number);
  68  |       state.rounds.push(created);
  69  |       if (state.failAfterCreate) state.failRead = 'comments';
  70  |       await json(route, created, 201); return;
  71  |     }
  72  |     if (/^\/api\/review-rounds\/[^/]+\/comments$/.test(path) && method === 'POST') {
  73  |       state.importPosts++;
  74  |       const body = req.postDataJSON(), owner = decodeURIComponent(path.split('/')[3]);
  75  |       const round = state.rounds.find((r) => r.review_round_id === owner)!;
  76  |       const created = body.comments.filter((r: { include: boolean }) => r.include).map((row: { text: string; original_text?: string }, i: number) => ({ ...makeComment(state.comments.length + i + 1, round.round_number, row.text), original_text: row.original_text || row.text }));
  77  |       state.comments.push(...created);
  78  |       if (state.failAfterImport) state.failRead = 'rounds';
  79  |       await json(route, created, 201); return;
  80  |     }
  81  |     if (method === 'GET' && path === '/api/tracks') { await json(route, [{ track_id: 'track-recovery', title: 'Recovery Track', manuscripts: [{ manuscript_id: manuscriptId, title: workspace.document.title, workflow_stage: 'REVISION', updated_at: at }] }]); return; }
  82  |     if (method === 'GET' && path === base + '/workspace') { await json(route, workspace); return; }
  83  |     if (method === 'GET' && path === base + '/generated-versions/' + versionId) {
  84  |       await json(route, { manuscript_id: manuscriptId, generated_version_id: versionId, version: 5, input_revision: 62, structure_mapping_available: true, content: 'Software fixture only.', blocks: [], references: [], citation_style: 'numeric_first_use', artifacts: [] }); return;
  85  |     }
  86  |     if (method === 'GET' && ['/samples', '/sources', '/changes', '/packages', '/chat', '/model-calls'].some((suffix) => path === base + suffix)) { await json(route, []); return; }
  87  |     if (method === 'POST' && path.endsWith('/research/discussion/context')) {
  88  |       const target = req.postDataJSON();
  89  |       await json(route, { target, scope_key: JSON.stringify(['STUDIO', manuscriptId]), label: 'Recovery source fixture', object_text: 'Original author software thought.', record: {}, versions: [], context_sha256: 'software-context' }); return;
  90  |     }
  91  |     if (method === 'POST' && path.endsWith('/research/discussion/history')) { await json(route, { messages: [], annotations: [], has_more: false, next_before: null, annotations_has_more: false, next_annotations_before: null }); return; }
  92  |     if (method !== 'GET' && method !== 'HEAD') state.unexpectedWrites.push({ method, path });
  93  |     await json(route, { detail: 'Unhandled isolated recovery test route: ' + method + ' ' + path }, 404);
  94  |   });
  95  |   return state;
  96  | }
  97  | const retry = (page: Page) => page.getByRole('button', { name: '重新读取意见与轮次', exact: true });
  98  | const readStatus = (page: Page) => page.getByRole('region', { name: '意见与轮次读取状态', exact: true });
  99  | const roundPicker = (page: Page) => page.getByRole('combobox', { name: '选择返修轮次', exact: true });
  100 | const createRound = (page: Page) => page.getByRole('button', { name: /^建立第 \d+ 轮…$/ });
  101 | const opinion = (page: Page, n = 210) => page.getByText('Original software opinion A' + n, { exact: true });
  102 | async function openRevision(page: Page) {
  103 |   await page.goto('/?manuscript=' + manuscriptId + '&view=revision&round=' + roundId(3) + '&chat=0&left=0&right=0');
  104 |   await expect(page.getByRole('heading', { name: '意见 → 决定 → 修改 → 回复', exact: true })).toBeVisible();
  105 | }
  106 | async function ready(page: Page, round = 3) {
  107 |   await expect(roundPicker(page)).toBeEnabled();
  108 |   await expect(roundPicker(page)).toHaveValue(roundId(round));
  109 |   await expect(createRound(page)).toBeEnabled();
  110 |   await expect(readStatus(page).getByRole('alert')).toHaveCount(0);
  111 | }
  112 | async function expectFailed(page: Page) {
  113 |   await expect(readStatus(page).getByRole('alert')).toContainText('意见与轮次读取失败');
  114 |   await expect(retry(page)).toBeEnabled();
  115 |   await expect(createRound(page)).toBeDisabled();
  116 |   await expect(roundPicker(page)).toBeDisabled();
  117 |   await expect(page.getByText('尚未导入审稿意见。', { exact: true })).toHaveCount(0);
  118 | }
  119 | async function expectReadOnlyRetry(page: Page, state: Harness, selectedRound = 3, withPreview = false) {
  120 |   const before = state.requests.length, reads = { ...state.reads };
  121 |   state.failRead = null;
  122 |   await retry(page).click();
  123 |   await expect(roundPicker(page)).toHaveValue(roundId(selectedRound));
  124 |   // A retained import preview intentionally locks round switching and creation.
  125 |   if (withPreview) {
  126 |     await expect(page.getByRole('button', { name: '✓ 确认导入 1 条', exact: true })).toBeEnabled();
  127 |     await expect(readStatus(page).getByRole('alert')).toHaveCount(0);
  128 |   } else await ready(page, selectedRound);
  129 |   expect(state.reads.comments).toBeGreaterThan(reads.comments);
  130 |   expect(state.reads.rounds).toBeGreaterThan(reads.rounds);
  131 |   const reviewTraffic = state.requests.slice(before).filter((r) => /\/review-rounds|\/comments/.test(r.path));
  132 |   expect(reviewTraffic.length).toBeGreaterThanOrEqual(2);
  133 |   expect(reviewTraffic.every((r) => r.method === 'GET')).toBe(true);
  134 |   expect(state.unexpectedWrites).toEqual([]);
  135 | }
  136 | 
  137 | test.describe('Revision comments and rounds read recovery', () => {
  138 |   test.setTimeout(60_000);
  139 |   for (const failed of ['comments', 'rounds'] as const) {
  140 |     test('cold ' + failed + ' failure cannot masquerade as empty or permit round creation; retry reads only', async ({ page }) => {
  141 |       const state = await installApi(page); state.failRead = failed;
  142 |       await openRevision(page); await expectFailed(page);
  143 |       await page.getByRole('textbox', { name: '审稿意见输入', exact: true }).fill('Local original preview stays available.');
  144 |       await page.getByRole('button', { name: '👀 准备预览', exact: true }).click();
  145 |       await expect(page.getByRole('textbox', { name: '编辑意见 1', exact: true })).toHaveValue('Local original preview stays available.');
  146 |       await expect(page.getByRole('button', { name: '✓ 确认导入 1 条', exact: true })).toBeDisabled();
  147 |       expect(state.createPosts).toBe(0); expect(state.importPosts).toBe(0);
  148 |       await expectReadOnlyRetry(page, state, 3, true);
> 149 |       await expect(opinion(page)).toBeVisible();
      |                                   ^ Error: expect(locator).toBeVisible() failed
  150 |       await expect(roundPicker(page).locator('option')).toHaveCount(4);
  151 |       await expect(page.getByRole('textbox', { name: '编辑意见 1', exact: true })).toHaveValue('Local original preview stays available.');
  152 |       expect(state.comments).toHaveLength(210); expect(state.rounds).toHaveLength(3);
  153 |     });
  154 |   }
  155 |   test('successful empty reads display a genuine empty state', async ({ page }) => {
  156 |     const state = await installApi(page); state.comments = []; state.rounds = [];
  157 |     await openRevision(page);
  158 |     await expect(page.getByText('尚未导入审稿意见。', { exact: true })).toBeVisible();
  159 |     await expect(createRound(page)).toHaveText('建立第 1 轮…');
  160 |     await expect(createRound(page)).toBeEnabled();
  161 |     await expect(readStatus(page).getByRole('alert')).toHaveCount(0);
  162 |     expect(state.createPosts).toBe(0); expect(state.importPosts).toBe(0);
  163 |   });
  164 |   test('warm failure retains opinions, current round, local input and preview; retry does not write', async ({ page }) => {
  165 |     const state = await installApi(page); await openRevision(page); await ready(page);
  166 |     await page.getByRole('textbox', { name: '审稿意见输入', exact: true }).fill('Unsaved original import draft.');
  167 |     await page.getByRole('button', { name: '👀 准备预览', exact: true }).click();
  168 |     await page.getByRole('textbox', { name: '编辑意见 1', exact: true }).fill('Edited local preview with source preserved.');
  169 |     state.failRead = 'rounds'; await retry(page).click(); await expectFailed(page);
  170 |     await expect(readStatus(page)).toContainText('当前显示上次读取的数据');
  171 |     await expect(opinion(page)).toBeVisible();
  172 |     await expect(roundPicker(page)).toHaveValue(roundId(3));
  173 |     await expect(page.getByRole('textbox', { name: '审稿意见输入', exact: true })).toHaveValue('Unsaved original import draft.');
  174 |     await expect(page.getByRole('textbox', { name: '编辑意见 1', exact: true })).toHaveValue('Edited local preview with source preserved.');
  175 |     await expect(page.getByRole('button', { name: '✓ 确认导入 1 条', exact: true })).toBeDisabled();
  176 |     await expectReadOnlyRetry(page, state, 3, true);
  177 |     await expect(opinion(page)).toBeVisible();
  178 |     await expect(page.getByRole('textbox', { name: '编辑意见 1', exact: true })).toHaveValue('Edited local preview with source preserved.');
  179 |     expect(state.createPosts).toBe(0); expect(state.importPosts).toBe(0);
  180 |   });
  181 |   test('acknowledged round creation followed by failed reload never repeats create POST', async ({ page }) => {
  182 |     const state = await installApi(page); await openRevision(page); await ready(page);
  183 |     state.failAfterCreate = true; await createRound(page).click();
  184 |     const dialog = page.getByRole('dialog');
  185 |     await dialog.getByRole('combobox').selectOption(versionId);
  186 |     await dialog.getByRole('button', { name: '确认建立这一轮', exact: true }).click();
  187 |     await expect(dialog).toHaveCount(0); await expectFailed(page);
  188 |     await expect(readStatus(page)).toContainText('意见或轮次已保存；读取结果暂未确认。');
  189 |     expect(state.createPosts).toBe(1); expect(state.rounds).toHaveLength(4);
  190 |     await expectReadOnlyRetry(page, state, 4);
  191 |     expect(state.createPosts).toBe(1); expect(state.importPosts).toBe(0);
  192 |     await expect(createRound(page)).toHaveText('建立第 5 轮…');
  193 |     expect(state.rounds.map((r) => r.round_number)).toEqual([1, 2, 3, 4]);
  194 |   });
  195 |   test('acknowledged import followed by failed reload retries GET without duplicate import', async ({ page }) => {
  196 |     const state = await installApi(page); await openRevision(page); await ready(page);
  197 |     await page.getByRole('textbox', { name: '审稿意见输入', exact: true }).fill('One acknowledged import, never replayed.');
  198 |     await page.getByRole('button', { name: '👀 准备预览', exact: true }).click();
  199 |     state.failAfterImport = true;
  200 |     await page.getByRole('button', { name: '✓ 确认导入 1 条', exact: true }).click(); await expectFailed(page);
  201 |     await expect(readStatus(page)).toContainText('意见或轮次已保存；读取结果暂未确认。');
  202 |     expect(state.importPosts).toBe(1); expect(state.comments).toHaveLength(211);
  203 |     await expect(page.getByRole('button', { name: '✓ 确认导入 1 条', exact: true })).toHaveCount(0);
  204 |     await expectReadOnlyRetry(page, state);
  205 |     await expect(page.getByText('One acknowledged import, never replayed.', { exact: true })).toBeVisible();
  206 |     expect(state.importPosts).toBe(1); expect(state.createPosts).toBe(0);
  207 |     expect(state.comments.filter((r) => r.edited_text === 'One acknowledged import, never replayed.')).toHaveLength(1);
  208 |   });
  209 |   for (const stale of ['empty', 'failure'] as const) {
  210 |     test('late older ' + stale + ' response cannot replace a newer successful read', async ({ page }) => {
  211 |       const state = await installApi(page); await openRevision(page); await ready(page);
  212 |       state.holdReads = true; await retry(page).click();
  213 |       await expect.poll(() => state.held.length).toBe(2);
  214 |       await expect(retry(page)).toBeDisabled();
  215 |       // Actual mode controls trigger new reads while the older pair remains delayed.
  216 |       state.holdReads = false;
  217 |       await page.getByRole('button', { name: '🧩 结构', exact: true }).click();
  218 |       await page.getByRole('button', { name: '✍️ Revision', exact: true }).click();
  219 |       await ready(page); await expect(opinion(page)).toBeVisible();
  220 |       const held = state.held.splice(0);
  221 |       await Promise.all(held.map((release) => release(stale)));
  222 |       // Wait for response-triggered React work before asserting retained state.
  223 |       await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  224 |       await expect(opinion(page)).toBeVisible();
  225 |       await expect(roundPicker(page)).toHaveValue(roundId(3));
  226 |       await expect(readStatus(page).getByRole('alert')).toHaveCount(0);
  227 |       await expect(createRound(page)).toHaveText('建立第 4 轮…');
  228 |       await expect(page.getByText('尚未导入审稿意见。', { exact: true })).toHaveCount(0);
  229 |       expect(state.createPosts).toBe(0); expect(state.importPosts).toBe(0);
  230 |       expect(state.unexpectedWrites).toEqual([]);
  231 |     });
  232 |   }
  233 | });
  234 | 
```