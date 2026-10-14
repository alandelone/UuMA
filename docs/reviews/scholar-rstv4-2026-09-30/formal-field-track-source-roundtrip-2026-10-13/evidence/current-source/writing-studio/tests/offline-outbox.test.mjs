import assert from 'node:assert/strict';
import { test } from 'node:test';
import { sameDocument } from '../lib/offline-outbox.ts';

// Controlled storage fixture, not a browser/runtime acceptance claim. Writes
// commit only on transaction completion and can abort after request success.
function storageFixture({ abortWrites = false, failCheckpoint = false } = {}) {
  const local = new Map();
  const records = new Map();
  globalThis.window = { localStorage: {
    get length() { return local.size; },
    key: (index) => [...local.keys()][index] ?? null,
    getItem: (key) => local.get(key) ?? null,
    setItem: (key, value) => {
      if (failCheckpoint) throw new Error('Controlled local storage failure');
      local.set(key, value);
    },
    removeItem: (key) => local.delete(key),
  } };
  globalThis.indexedDB = { open: () => {
    const request = {};
    queueMicrotask(() => {
      request.result = {
        objectStoreNames: { contains: () => true }, close() {},
        transaction: (_name, mode) => {
          const transaction = {};
          const working = new Map(records);
          let pending = 0;
          const operation = (execute) => {
            const result = {};
            pending += 1;
            queueMicrotask(() => {
              result.result = execute();
              result.onsuccess?.();
              pending -= 1;
              queueMicrotask(() => {
                if (pending) return;
                if (mode === 'readwrite' && abortWrites) {
                  transaction.error = new Error('Controlled transaction abort');
                  transaction.onabort?.();
                } else {
                  if (mode === 'readwrite') {
                    records.clear();
                    for (const entry of working) records.set(...entry);
                  }
                  transaction.oncomplete?.();
                }
              });
            });
            return result;
          };
          transaction.objectStore = () => ({
            put: (value) => operation(() => {
              working.set(value.manuscriptId, structuredClone(value));
              return value.manuscriptId;
            }),
            get: (key) => operation(() => working.get(key)),
            getAll: () => operation(() => [...working.values()]),
            delete: (key) => operation(() => working.delete(key)),
          });
          return transaction;
        },
      };
      request.onsuccess?.();
    });
    return request;
  } };
  return { records, local };
}

async function client() {
  const url = new URL('../lib/offline-outbox.ts', import.meta.url);
  url.searchParams.set('client', crypto.randomUUID());
  return (await import(url.href)).outbox;
}

function draft(operationId, text = operationId) {
  return {
    manuscriptId: 'manuscript-isolated-storage-test', baseRevision: 7,
    operationId, operationKind: 'EDIT', commentIds: ['original-opinion'],
    queuedAt: '2026-10-03T00:00:00.000Z',
    document: { schema_version: 1, manuscript_id: 'manuscript-isolated-storage-test',
      title: 'Controlled author copy', abstract: '', venue: '',
      sections: [{ id: 'section-stable', title: 'Section', role: 'INTRODUCTION', paragraphs: [
        { id: 'paragraph-stable', purpose: 'Purpose', paradigm: 'Motivation', asset_ids: [], intents: [
          { id: 'intent-stable', label: 'Claim', thoughts: [
            { id: 'thought-stable', text, citation_mode: 'SELECTED', citations: [{ evidence_id: 'source-stable', selected: true }] },
          ] },
        ] },
      ] }] },
  };
}

test('backend key ordering is equivalent but text, citations and block order remain significant', () => {
  const original = draft('payload-order').document;
  const section = original.sections[0];
  const paragraph = section.paragraphs[0];
  const intent = paragraph.intents[0];
  const thought = intent.thoughts[0];
  const server = {
    abstract: original.abstract, manuscript_id: original.manuscript_id, schema_version: 1,
    sections: [{ id: section.id, paragraphs: [{
      asset_ids: [], id: paragraph.id,
      intents: [{ id: intent.id, label: intent.label, thoughts: [{
        citation_mode: thought.citation_mode,
        citations: [{ evidence_id: 'source-stable', selected: true }], id: thought.id, text: thought.text,
      }] }], paradigm: paragraph.paradigm, purpose: paragraph.purpose,
    }], role: section.role, title: section.title }], title: original.title, venue: '',
  };
  assert.notEqual(JSON.stringify(server), JSON.stringify(original));
  assert.equal(sameDocument(server, original), true);
  const textChange = structuredClone(server);
  textChange.sections[0].paragraphs[0].intents[0].thoughts[0].text = 'Later server edit';
  assert.equal(sameDocument(textChange, original), false);
  const citationChange = structuredClone(server);
  citationChange.sections[0].paragraphs[0].intents[0].thoughts[0].citations[0].selected = false;
  assert.equal(sameDocument(citationChange, original), false);
  const reordered = structuredClone(server);
  reordered.sections.push({ ...structuredClone(section), id: 'another-section' });
  const reversed = structuredClone(reordered);
  reversed.sections.reverse();
  assert.equal(sameDocument(reordered, reversed), false);
});

test('checkpoint restores the last input without starting a network save', async () => {
  storageFixture();
  const first = await client();
  const pending = draft('last-keystroke');
  first.checkpoint(pending);
  const reloaded = await client();
  const copies = await reloaded.list(pending.manuscriptId);
  assert.equal(copies.length, 1);
  assert.deepEqual(copies[0].document, pending.document);
  assert.deepEqual(copies[0].commentIds, pending.commentIds);
});

test('two tabs and a retained conflict copy cannot overwrite one another', async () => {
  storageFixture();
  const a = await client();
  const b = await client();
  const one = await a.put(draft('operation-a'));
  const two = await b.put(draft('operation-b'));
  assert.notEqual(one.draftKey, two.draftKey);
  await a.keep(draft('retained-conflict'));
  const reader = await client();
  assert.deepEqual(new Set((await reader.list(one.manuscriptId)).map((item) => item.operationId)),
    new Set(['operation-a', 'operation-b', 'retained-conflict']));
});

test('acknowledging an older save preserves input entered while it was in flight', async () => {
  storageFixture();
  const a = await client();
  const old = await a.put(draft('operation-in-flight'));
  const latest = draft('operation-after-request', 'Newest unsynchronised author input');
  a.checkpoint(latest);
  await a.remove(old);
  const reloaded = await client();
  const copies = await reloaded.list(latest.manuscriptId);
  assert.equal(copies.length, 1);
  assert.equal(copies[0].operationId, latest.operationId);
  assert.deepEqual(copies[0].document, latest.document);
});

test('request success followed by abort is not reported as a durable save', async () => {
  const { records } = storageFixture({ abortWrites: true, failCheckpoint: true });
  const a = await client();
  await assert.rejects(a.put(draft('aborted-write')), /Controlled transaction abort/);
  assert.equal(records.size, 0);
});

test('an IndexedDB abort still retains the synchronous recovery copy', async () => {
  storageFixture({ abortWrites: true });
  const a = await client();
  const pending = draft('checkpoint-fallback');
  await a.put(pending);
  const reloaded = await client();
  assert.deepEqual((await reloaded.list(pending.manuscriptId))[0].document, pending.document);
});

test('legacy manuscript-keyed saves remain discoverable and remove conditionally', async () => {
  const { records } = storageFixture();
  const pending = draft('legacy-operation');
  records.set(pending.manuscriptId, pending);
  const a = await client();
  assert.equal((await a.list(pending.manuscriptId))[0].operationId, pending.operationId);
  await a.remove({ ...pending, operationId: 'different-operation' });
  assert.equal((await a.list(pending.manuscriptId)).length, 1);
  await a.remove(pending);
  assert.deepEqual(await a.list(pending.manuscriptId), []);
});
