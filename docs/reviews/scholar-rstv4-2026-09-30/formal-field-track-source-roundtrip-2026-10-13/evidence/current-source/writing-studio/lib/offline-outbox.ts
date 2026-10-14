import type { StudioDocument } from './studio-types';

export interface PendingSave {
  manuscriptId: string;
  baseRevision: number;
  operationId: string;
  operationKind: string;
  commentIds: string[];
  document: StudioDocument;
  queuedAt: string;
  draftKey?: string;
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, entry]) => [key, canonical(entry)]));
  }
  return value;
}

export function sameDocument(a: StudioDocument, b: StudioDocument): boolean {
  // The backend serialises object keys in sorted order. Array order and all
  // content/citation decisions remain significant.
  return JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
}

const DB_NAME = 'pepper-writing-studio';
const STORE = 'pending-saves';
const CHECKPOINT_PREFIX = 'pepper-studio-checkpoint:';
let clientId = '';
let persistenceQueue: Promise<unknown> = Promise.resolve();

function ownDraftKey(manuscriptId: string): string {
  if (!clientId) {
    // A fresh page id also distinguishes browser "Duplicate tab", which copies
    // sessionStorage. Reloaded pages discover the retained copies via list().
    clientId = crypto.randomUUID();
  }
  return `${manuscriptId}:${clientId}`;
}

interface DraftRecord {
  manuscriptId: string;
  save: PendingSave;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'manuscriptId' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  callback: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE, mode);
    const request = callback(transaction.objectStore(STORE));
    let result: T;
    request.onsuccess = () => { result = request.result; };
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => { db.close(); resolve(result); };
    transaction.onabort = () => { db.close(); reject(transaction.error); };
    transaction.onerror = () => { db.close(); reject(transaction.error); };
  });
}

function checkpoint(save: PendingSave): PendingSave {
  const draft = { ...save, draftKey: ownDraftKey(save.manuscriptId) };
  // Synchronous checkpoint precedes the delayed network save. Each tab owns a key,
  // so another tab cannot overwrite an author's unsynchronised copy.
  window.localStorage.setItem(CHECKPOINT_PREFIX + draft.draftKey, JSON.stringify(draft));
  return draft;
}

async function list(manuscriptId: string): Promise<PendingSave[]> {
  const drafts = new Map<string, PendingSave>();
  try {
    const rows = await withStore<Array<DraftRecord | PendingSave>>('readonly', (store) => store.getAll());
    for (const row of rows) {
      const save = 'save' in row ? row.save : row;
      if (save.manuscriptId === manuscriptId) {
        drafts.set(save.draftKey || manuscriptId, save);
      }
    }
  } catch {
    // The synchronous copy remains usable if IndexedDB is unavailable.
  }
  for (let i = 0; i < window.localStorage.length; i += 1) {
    const key = window.localStorage.key(i);
    if (!key?.startsWith(CHECKPOINT_PREFIX + manuscriptId + ':')) continue;
    try {
      const save = JSON.parse(window.localStorage.getItem(key) || '') as PendingSave;
      if (save.manuscriptId === manuscriptId && save.document && save.operationId) {
        drafts.set(key.slice(CHECKPOINT_PREFIX.length), save);
      }
    } catch {
      // Leave an unreadable copy intact; it must not replace a readable copy.
    }
  }
  const own = ownDraftKey(manuscriptId);
  return [...drafts.values()].sort((a, b) =>
    Number(b.draftKey === own) - Number(a.draftKey === own) || b.queuedAt.localeCompare(a.queuedAt),
  );
}

async function put(save: PendingSave): Promise<PendingSave> {
  return writeDraft({ ...save, draftKey: ownDraftKey(save.manuscriptId) });
}

async function writeDraft(draft: PendingSave): Promise<PendingSave> {
  let checkpointSaved = false;
  try {
    window.localStorage.setItem(CHECKPOINT_PREFIX + draft.draftKey, JSON.stringify(draft));
    checkpointSaved = true;
  } catch { /* Try IndexedDB. */ }
  try {
    const write = persistenceQueue.then(() =>
      withStore('readwrite', (store) => store.put({ manuscriptId: draft.draftKey, save: draft })),
    );
    persistenceQueue = write.catch(() => undefined);
    await write;
  } catch (error) {
    if (!checkpointSaved) throw error;
  }
  return draft;
}

async function remove(save: PendingSave): Promise<void> {
  const key = save.draftKey || save.manuscriptId;
  const localKey = CHECKPOINT_PREFIX + key;
  const local = window.localStorage.getItem(localKey);
  if (local && (JSON.parse(local) as PendingSave).operationId === save.operationId) {
    window.localStorage.removeItem(localKey);
  }
  const removal = persistenceQueue.then(async () => {
    const db = await openDb();
    return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE, 'readwrite');
    const store = transaction.objectStore(STORE);
    const request = store.get(key);
    request.onsuccess = () => {
      const row = request.result as DraftRecord | PendingSave | undefined;
      const current = row && ('save' in row ? row.save : row);
      if (current?.operationId === save.operationId) store.delete(key);
    };
    transaction.oncomplete = () => { db.close(); resolve(); };
    transaction.onabort = () => { db.close(); reject(transaction.error); };
    transaction.onerror = () => { db.close(); reject(transaction.error); };
    });
  });
  persistenceQueue = removal.catch(() => undefined);
  await removal;
}

export const outbox = {
  checkpoint,
  put,
  keep: (save: PendingSave) => writeDraft({ ...save, draftKey: `${save.manuscriptId}:${crypto.randomUUID()}` }),
  list,
  get: async (manuscriptId: string) => (await list(manuscriptId))[0],
  remove,
};
