const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname,
  '../integrations/chrome/uuma-chatgpt-bridge/chatgpt.js'), 'utf8');
const url = 'https://chatgpt.com/c/test-conversation';
const marker = '[UuMA consultation request-a]';

function element(text = '', options = {}) {
  return {
    innerText: text,
    getClientRects: () => options.hidden ? [] : [{}],
    getAttribute: name => name === 'aria-disabled' && options.disabled ? 'true' : null,
    closest: () => options.inert ? {} : null,
    matches: () => Boolean(options.legacy),
    querySelector: () => options.body || null,
    querySelectorAll: () => options.links || [],
  };
}

function fixture({composers = [], users = [element(marker)], answers = [],
  legacy = false, generating = false} = {}) {
  const document = {
    querySelectorAll(selector) {
      if (selector.startsWith('#prompt-textarea,')) {
        assert.match(selector, /form\[data-chatgpt-composer\]/);
        assert.match(selector, /\[data-composer-markdown\]\[contenteditable="true"\]\[role="textbox"\]/);
        return composers;
      }
      if (selector === '[data-message-author-role="user"]') return legacy ? users : [];
      if (selector === '[data-message-author-role="assistant"]') return legacy ? answers : [];
      if (selector === '[data-chatgpt-search-unit-key$=":user"]') return legacy ? [] : users;
      if (selector === '[data-chatgpt-search-unit-key$=":assistant"]') return legacy ? [] : answers;
      if (selector === 'button') return generating ? [element('Stop')] : [];
      throw Error(`Unexpected DOM query ${selector}`);
    },
  };
  const context = vm.createContext({document, URL, location: new URL(url), console,
    chrome: {runtime: {onMessage: {addListener() {}}}},
    fetch: async () => ({ok: true, json: async () => ({user: {email: 'test@example.com'}})}),
  });
  vm.runInContext(source, context);
  return {
    find: () => vm.runInContext('findComposer()', context),
    observe: (overrides = {}) => {
      context.payload = {identity: 'test@example.com', workspace: 'Personal',
        request_id: 'request-a', url, ...overrides};
      return vm.runInContext('observe(payload)', context);
    },
  };
}

test('hidden legacy editor cannot mask the current visible editor', () => {
  const current = element();
  assert.equal(fixture({composers: [element('', {hidden: true}), current]}).find(), current);
});

test('ambiguous editors fail closed instead of selecting a random prompt', () => {
  assert.throws(() => fixture({composers: [element(), element()]}).find(), /COMPOSER_AMBIGUOUS/);
});

test('disabled or inert editors are not ready for submission', () => {
  assert.equal(fixture({composers: [element('', {disabled: true}), element('', {inert: true})]}).find(), null);
});

test('new message units return only assistant body and citations', async () => {
  const body = element('Direct evidence is unavailable.', {links: [
    {innerText: 'Source', href: 'https://example.com/source'},
    {innerText: 'Internal', href: 'javascript:void(0)'},
  ]});
  const result = await fixture({answers: [element('ChatGPT said: UI controls', {body})]}).observe();
  assert.equal(result.answer, body.innerText);
  assert.equal(result.citations.length, 1);
  assert.equal(result.citations[0].url, 'https://example.com/source');
});

test('latest user message must belong to this request', async () => {
  await assert.rejects(fixture({users: [element(marker), element('Another prompt')]}).observe(),
    /CONVERSATION_CHANGED/);
});

test('a changed conversation URL cannot return an unrelated answer', async () => {
  await assert.rejects(fixture().observe({url: 'https://chatgpt.com/c/other'}), /CONVERSATION_CHANGED/);
});

test('streaming or missing assistant bodies remain pending', async () => {
  assert.equal((await fixture({generating: true}).observe()).pending, true);
  assert.equal((await fixture({answers: [element('ChatGPT said:')]}).observe()).pending, true);
});

test('legacy message markup still returns the answer', async () => {
  const answer = element('Legacy answer', {legacy: true});
  const result = await fixture({legacy: true, answers: [answer]}).observe();
  assert.equal(result.answer, 'Legacy answer');
});
