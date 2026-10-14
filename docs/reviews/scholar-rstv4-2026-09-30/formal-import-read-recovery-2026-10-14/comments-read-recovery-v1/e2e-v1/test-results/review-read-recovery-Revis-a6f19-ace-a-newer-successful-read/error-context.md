# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: review-read-recovery.spec.ts >> Revision comments and rounds read recovery >> late older empty response cannot replace a newer successful read
- Location: ..\..\..\..\..\..\Alandelone\CodeSpace_Local\writing-studio\tests\e2e\review-read-recovery.spec.ts:210:5

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
      - button "✍️ Revision" [active] [ref=e22]
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
          - combobox "选择返修轮次" [ref=e45]:
            - option "请选择轮次…"
            - option "第 1 轮 · Recovery software fixture"
            - option "第 2 轮 · Recovery software fixture"
            - option "第 3 轮 · Recovery software fixture" [selected]
        - paragraph [ref=e46]: 固定被审稿 v5 / 作者结构 r62；本轮生成不会移动基线。
        - button "建立第 4 轮…" [ref=e47]
      - generic [ref=e48]:
        - textbox "审稿意见输入" [ref=e49]:
          - /placeholder: 粘贴意见；空行分条。确认前不会写入。
        - generic [ref=e50]:
          - button "👀 准备预览" [ref=e51]
          - button "➕ 单条新增" [ref=e52]
          - generic [ref=e53] [cursor=pointer]:
            - text: 📄 TXT / MD / DOCX / PDF
            - button "导入审稿意见文件" [ref=e54]
      - generic [ref=e55]:
        - article [ref=e56]:
          - button "开始修改意见 A207" [ref=e57]
          - generic "review-recovery-comment-207" [ref=e61]: A207
          - generic [ref=e62]:
            - generic [ref=e63]: 第 3 轮 · Software fixture
            - paragraph [ref=e64]: Original software opinion A207
            - group [ref=e65]:
              - generic "原意见与导入来源" [ref=e66]
            - generic [ref=e67]:
              - textbox "我的决定与理由 A207" [ref=e68]:
                - /placeholder: 我的决定与理由
              - textbox "回复内容 A207" [ref=e69]:
                - /placeholder: 回复内容
              - generic [ref=e70]:
                - combobox "意见状态 A207" [ref=e71]:
                  - option "待处理" [selected]
                  - option "已决定回应"
                  - option "修改中"
                  - option "待核对"
                  - option "已处理 · 需作者核对" [disabled]
                - button "保存回复" [ref=e72]
                - button "核对回复" [ref=e73]
                - button "查看核对历史" [ref=e74]
              - paragraph [ref=e75]: 回复尚未核对
            - generic [ref=e76]: 0 条关联修改
          - button "移入已删除 A207" [ref=e77]
        - article [ref=e78]:
          - button "开始修改意见 A208" [ref=e79]
          - generic "review-recovery-comment-208" [ref=e83]: A208
          - generic [ref=e84]:
            - generic [ref=e85]: 第 3 轮 · Software fixture
            - paragraph [ref=e86]: Original software opinion A208
            - group [ref=e87]:
              - generic "原意见与导入来源" [ref=e88]
            - generic [ref=e89]:
              - textbox "我的决定与理由 A208" [ref=e90]:
                - /placeholder: 我的决定与理由
              - textbox "回复内容 A208" [ref=e91]:
                - /placeholder: 回复内容
              - generic [ref=e92]:
                - combobox "意见状态 A208" [ref=e93]:
                  - option "待处理" [selected]
                  - option "已决定回应"
                  - option "修改中"
                  - option "待核对"
                  - option "已处理 · 需作者核对" [disabled]
                - button "保存回复" [ref=e94]
                - button "核对回复" [ref=e95]
                - button "查看核对历史" [ref=e96]
              - paragraph [ref=e97]: 回复尚未核对
            - generic [ref=e98]: 0 条关联修改
          - button "移入已删除 A208" [ref=e99]
        - article [ref=e100]:
          - button "开始修改意见 A209" [ref=e101]
          - generic "review-recovery-comment-209" [ref=e105]: A209
          - generic [ref=e106]:
            - generic [ref=e107]: 第 3 轮 · Software fixture
            - paragraph [ref=e108]: Original software opinion A209
            - group [ref=e109]:
              - generic "原意见与导入来源" [ref=e110]
            - generic [ref=e111]:
              - textbox "我的决定与理由 A209" [ref=e112]:
                - /placeholder: 我的决定与理由
              - textbox "回复内容 A209" [ref=e113]:
                - /placeholder: 回复内容
              - generic [ref=e114]:
                - combobox "意见状态 A209" [ref=e115]:
                  - option "待处理" [selected]
                  - option "已决定回应"
                  - option "修改中"
                  - option "待核对"
                  - option "已处理 · 需作者核对" [disabled]
                - button "保存回复" [ref=e116]
                - button "核对回复" [ref=e117]
                - button "查看核对历史" [ref=e118]
              - paragraph [ref=e119]: 回复尚未核对
            - generic [ref=e120]: 0 条关联修改
          - button "移入已删除 A209" [ref=e121]
        - article [ref=e122]:
          - button "开始修改意见 A210" [ref=e123]
          - generic "review-recovery-comment-210" [ref=e127]: A210
          - generic [ref=e128]:
            - generic [ref=e129]: 第 3 轮 · Software fixture
            - paragraph [ref=e130]: Original software opinion A210
            - group [ref=e131]:
              - generic "原意见与导入来源" [ref=e132]
            - generic [ref=e133]:
              - textbox "我的决定与理由 A210" [ref=e134]:
                - /placeholder: 我的决定与理由
              - textbox "回复内容 A210" [ref=e135]:
                - /placeholder: 回复内容
              - generic [ref=e136]:
                - combobox "意见状态 A210" [ref=e137]:
                  - option "待处理" [selected]
                  - option "已决定回应"
                  - option "修改中"
                  - option "待核对"
                  - option "已处理 · 需作者核对" [disabled]
                - button "保存回复" [ref=e138]
                - button "核对回复" [ref=e139]
                - button "查看核对历史" [ref=e140]
              - paragraph [ref=e141]: 回复尚未核对
            - generic [ref=e142]: 0 条关联修改
          - button "移入已删除 A210" [ref=e143]
      - region "已保存修改与意见关联" [ref=e144]:
        - generic [ref=e145]:
          - generic [ref=e146]:
            - heading "已保存修改" [level=3] [ref=e147]
            - text: 查看实际前后对照，分配给一条或多条意见。
          - generic [ref=e148]:
            - text: 显示
            - combobox "显示" [ref=e149]:
              - option "全部修改" [selected]
              - option "未关联意见"
              - option "已关联意见"
          - button "刷新修改历史" [ref=e150]
        - paragraph [ref=e151]: 此范围没有已保存修改。
      - region "已生成的投稿包" [ref=e152]:
        - generic [ref=e153]:
          - heading "投稿包" [level=3] [ref=e154]
          - button "刷新" [ref=e155]
        - paragraph [ref=e156]: 此轮还没有投稿包。按“投稿包”生成后可在这里下载。
  - status [ref=e157]
  - button [ref=e159]:
    - generic [ref=e160]: 与 Agent 讨论
    - generic [ref=e163]: 0 条 · Review read recovery fixture
```

# Test source

```ts
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
  149 |       await expect(opinion(page)).toBeVisible();
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
> 219 |       await ready(page); await expect(opinion(page)).toBeVisible();
      |                                                      ^ Error: expect(locator).toBeVisible() failed
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