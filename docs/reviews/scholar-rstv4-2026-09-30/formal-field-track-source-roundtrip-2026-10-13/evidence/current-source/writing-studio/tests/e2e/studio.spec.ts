import { expect, test } from '@playwright/test';

const document = {
  schema_version: 1,
  manuscript_id: 'manuscript-e2e',
  title: 'Author-led browser paper',
  abstract: '',
  venue: 'Journal A',
  sections: [
    {
      id: 'section-1',
      title: 'Introduction',
      role: 'Motivation',
      paragraphs: [
        {
          id: 'paragraph-1',
          purpose: 'Establish the context',
          paradigm: 'Funnel',
          asset_ids: [],
          intents: [
            {
              id: 'intent-1',
              label: 'Research context',
              thoughts: [
                { id: 'thought-1', text: 'First author thought.', citation_mode: 'NONE', citations: [] },
                { id: 'thought-2', text: 'Second author thought.', citation_mode: 'PENDING', citations: [] },
              ],
            },
          ],
        },
      ],
    },
    {
      id: 'section-2',
      title: 'Methods',
      role: 'Method',
      paragraphs: [],
    },
  ],
};

const workspace = {
  manuscript: {
    manuscript_id: 'manuscript-e2e',
    track_id: 'track-e2e',
    title: document.title,
    workflow_stage: 'DRAFTING',
    writing_status: 'DRAFTING',
    revision: 1,
    versions: [],
    submissions: [],
  },
  workflow_stage: 'DRAFTING',
  document_revision: 0,
  document,
  active_generated_version_id: null,
  last_generated_revision: null,
  generated_is_stale: false,
  assets: [],
  latest_job: null,
  artifacts: [],
  findings: [],
};

test('opens a real Paper workspace, autosaves edits, recovers offline, and detects tab conflicts', async ({ page, context }) => {
  let revision = 0;
  let savedIntent = '';
  let serverDocument = structuredClone(document);
  let failNextSave = false;
  await context.route('http://127.0.0.1:8874/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/tracks') {
      await route.fulfill({
        json: [{
          track_id: 'track-e2e',
          title: 'Browser Test Track',
          manuscripts: [{
            manuscript_id: 'manuscript-e2e',
            title: document.title,
            workflow_stage: 'DRAFTING',
            updated_at: '2026-09-18T00:00:00Z',
          }],
        }],
      });
      return;
    }
    if (path.endsWith('/workspace')) {
      await route.fulfill({ json: { ...workspace, document_revision: revision, document: serverDocument } });
      return;
    }
    if (path.endsWith('/document') && request.method() === 'PUT') {
      if (failNextSave) {
        failNextSave = false;
        await route.fulfill({ status: 503, json: { detail: 'simulated offline save failure' } });
        return;
      }
      const body = request.postDataJSON();
      revision += 1;
      serverDocument = structuredClone(body.document);
      savedIntent = body.document.sections
        .flatMap((section: typeof document.sections[number]) => section.paragraphs)
        .flatMap((paragraph: typeof document.sections[0]['paragraphs'][number]) => paragraph.intents)
        .at(0)?.label || '';
      await route.fulfill({
        json: {
          document_revision: revision,
          document: body.document,
          saved_at: '2026-09-18T00:00:01Z',
          idempotent_replay: false,
        },
      });
      return;
    }
    if (path.endsWith('/samples') || path.endsWith('/sources') || path.endsWith('/comments')) {
      await route.fulfill({ json: [] });
      return;
    }
    if (path.endsWith('/chat')) {
      await route.fulfill({
        json: [{
          message_id: 'message-1',
          role: 'AUTHOR',
          content: 'Keep the central idea author-led.',
          anchor_type: 'paper',
          anchor_revision: 0,
          quoted: {},
          status: 'SENT',
          created_at: '2026-09-18T00:00:00Z',
        }],
      });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: `Unhandled test route: ${path}` } });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Author-led browser paper' }).click();
  await expect(page.getByText('2 Drafting')).toBeVisible();
  await expect(page.getByText('Keep the central idea author-led.')).toBeVisible();

  const secondPage = await context.newPage();
  await secondPage.goto('/?manuscript=manuscript-e2e');
  await expect(secondPage.getByText('2 Drafting')).toBeVisible();

  const sectionHandle = page.getByRole('button', { name: '拖动章节 Introduction' });
  const targetHandle = page.getByRole('button', { name: '拖动章节 Methods' });
  const sourceBox = await sectionHandle.boundingBox();
  const targetBox = await targetHandle.boundingBox();
  expect(sourceBox).not.toBeNull();
  expect(targetBox).not.toBeNull();
  await page.mouse.move(sourceBox!.x + sourceBox!.width / 2, sourceBox!.y + sourceBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox!.x + targetBox!.width / 2, targetBox!.y + targetBox!.height / 2, { steps: 12 });
  await page.mouse.up();
  await expect(page.locator('.section-title-input').first()).toHaveValue('Methods');
  await expect(secondPage.getByText('版本冲突 · 未覆盖')).toBeVisible();
  await secondPage.close();

  const intent = page.getByPlaceholder('Intent 可以暂时未定');
  await intent.fill('Literature consensus');
  await expect.poll(() => savedIntent).toBe('Literature consensus');
  await expect(page.getByText('已自动保存')).toBeVisible();

  await page.getByRole('button', { name: '显示或隐藏左侧样本' }).click();
  await expect(page.getByText('Skeleton / Samples', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '显示或隐藏左侧样本' }).click();
  await expect(page.getByText('Skeleton / Samples', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '撤销' }).click();
  await expect(intent).toHaveValue('Research context');

  failNextSave = true;
  await intent.fill('Offline draft survives reload');
  await expect(page.getByText('保存失败 · 本地已保留')).toBeVisible();
  await page.reload();
  await expect(page.getByPlaceholder('Intent 可以暂时未定')).toHaveValue('Offline draft survives reload');
  await expect.poll(() => savedIntent).toBe('Offline draft survives reload');
  await expect(page.getByText('已自动保存')).toBeVisible();
});

test('renders and edits 100 paragraphs with 1,000 author thoughts', async ({ page }) => {
  const largeDocument = {
    ...document,
    manuscript_id: 'manuscript-large',
    title: 'Large structured manuscript',
    sections: Array.from({ length: 10 }, (_, sectionIndex) => ({
      id: `large-section-${sectionIndex}`,
      title: `Section ${sectionIndex + 1}`,
      role: 'Discussion',
      paragraphs: Array.from({ length: 10 }, (_, paragraphIndex) => ({
        id: `large-paragraph-${sectionIndex}-${paragraphIndex}`,
        purpose: `Paragraph ${sectionIndex + 1}.${paragraphIndex + 1}`,
        paradigm: 'MEAL',
        asset_ids: [],
        formulas: [],
        intents: [{
          id: `large-intent-${sectionIndex}-${paragraphIndex}`,
          label: 'Explanation',
          thoughts: Array.from({ length: 10 }, (_, thoughtIndex) => ({
            id: `large-thought-${sectionIndex}-${paragraphIndex}-${thoughtIndex}`,
            text: `Author thought ${sectionIndex}.${paragraphIndex}.${thoughtIndex}`,
            citation_mode: 'NONE',
            citations: [],
          })),
        }],
      })),
    })),
  };
  let revision = 0;
  await page.route('http://127.0.0.1:8874/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/tracks') {
      await route.fulfill({ json: [] });
      return;
    }
    if (path.endsWith('/workspace')) {
      await route.fulfill({
        json: {
          ...workspace,
          document_revision: revision,
          document: largeDocument,
          manuscript: {
            ...workspace.manuscript,
            manuscript_id: 'manuscript-large',
            title: largeDocument.title,
          },
        },
      });
      return;
    }
    if (path.endsWith('/document') && request.method() === 'PUT') {
      const body = request.postDataJSON();
      revision += 1;
      await route.fulfill({
        json: {
          document_revision: revision,
          document: body.document,
          saved_at: '2026-09-18T00:00:01Z',
          idempotent_replay: false,
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });
  await page.goto('/?manuscript=manuscript-large');
  await expect(page.locator('.thought-row')).toHaveCount(1000, { timeout: 30_000 });
  const firstThought = page.getByPlaceholder('写下你要表达的原子思想…').first();
  await firstThought.fill('Edited while the long manuscript remains responsive.');
  await expect(page.getByText('已自动保存')).toBeVisible({ timeout: 10_000 });
});
