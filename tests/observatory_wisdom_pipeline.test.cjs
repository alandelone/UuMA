const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(process.env.UUMA_OBSERVATORY_TEST_JS ||
  path.join(__dirname, '../src/uuma/observatory/static/app.js'), 'utf8');
const start = source.indexOf('  function getWisdomPipelineView(');
const end = source.indexOf('  function renderWisdomPreviewHtml(', start);
const context = vm.createContext({});
vm.runInContext(source.slice(start, end), context);
const view = context.getWisdomPipelineView;
const orbit = (id, status = 'STOPPED') => ({
  orbit_id: id, status, runner_live: false,
  pipeline_items: [{frontier_item_id: `${id}_past`, stage: 'PASSED_RECENT', badge: '已攻关'}],
});
const topic = (id, status, investigations) => ({
  item_id: id, kind: 'knowledge_topic', status,
  payload: {title: id, investigations},
});

test('archived-only topics retain history without any running task', () => {
  const result = view([topic('old', 'ARCHIVED', [orbit('old')])]);
  assert.equal(result.pipelineItems.length, 1);
  assert.equal(result.pipelineItems[0].owner_item_id, 'old');
  assert.equal(result.isRunnerLive, false);
});

test('all topics and earlier orbits are shown with their original detail owner', () => {
  const result = view([
    topic('first', 'ACTIVE', [orbit('a'), orbit('earlier')]),
    topic('second', 'ACTIVE', [orbit('b')]),
    topic('past', 'ARCHIVED', [orbit('c')]),
    {item_id: 'orphan', kind: 'knowledge_orbit', payload: {orbit_info: orbit('d')}},
  ]);
  assert.equal(result.pipelineItems.length, 5);
  assert.equal(result.allTopics.length, 3);
  assert.equal(result.pipelineItems.find(p => p.frontier_item_id === 'c_past').owner_item_id, 'past');
});

test('configured ACTIVE and queued state do not prove worker liveness', () => {
  const configured = orbit('active', 'ACTIVE');
  configured.pipeline_items.push({frontier_item_id: 'open', stage: 'RUNNING', badge: '正在攻关'});
  let result = view([topic('first', 'ACTIVE', [configured])]);
  assert.equal(result.isRunnerLive, false);
  assert.equal(result.pipelineItems[1].stage, 'QUEUED');
  assert.match(result.pipelineItems[1].badge, /无实时执行证据/);
  configured.runner_live = true;
  result = view([topic('first', 'ACTIVE', [configured])]);
  assert.equal(result.isRunnerLive, true);
  assert.equal(result.pipelineItems[1].stage, 'RUNNING');
});

test('duplicate orbit projections do not duplicate historical frontier rows', () => {
  const same = orbit('one');
  assert.equal(view([topic('first', 'ACTIVE', [same, same])]).pipelineItems.length, 1);
  assert.equal(view([]).pipelineItems.length, 0);
});
