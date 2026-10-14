const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const frontend = path.resolve(__dirname, '../..');
const ts = require(path.join(frontend, 'node_modules/typescript'));
const source = fs.readFileSync(path.join(frontend, 'components/studio-block-controls.tsx'), 'utf8');
const file = ts.createSourceFile('controls.tsx', source, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TSX);
const declaration = file.statements.find(node => ts.isVariableStatement(node) && node.declarationList.declarations.some(item => item.name.getText(file) === 'blockKeyboardCoordinates'));
assert.ok(declaration, 'Test must use the actual coordinate getter declaration');
const compiled = ts.transpileModule(declaration.getText(file), {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS}}).outputText;
const module_ = {exports: {}};
new Function('module', 'exports', compiled)(module_, module_.exports);
const move = module_.exports.blockKeyboardCoordinates;
const rect = {left: 0, top: 0, width: 20, height: 20};
function run(code, entries, collisionRect = rect) {
  let prevented = false;
  const enabled = entries.filter(item => !item.disabled).map(item => ({id: item.id, data: {current: item.ordinary ? {} : {dropTarget: {}}}}));
  const result = move({code, preventDefault() {prevented = true;}}, {currentCoordinates: {x: 40, y: 60}, context: {collisionRect, droppableContainers: {getEnabled: () => enabled}, droppableRects: new Map(entries.map(item => [item.id, item.rect]))}});
  return {result, prevented};
}
const entries = [
  {id: 'before', rect: {left: 0, top: -30, width: 20, height: 10}},
  {id: 'empty-container', rect: {left: 0, top: 40, width: 20, height: 30}},
  {id: 'farther-container', rect: {left: 0, top: 100, width: 20, height: 30}},
  {id: 'left', rect: {left: -40, top: 0, width: 20, height: 20}},
  {id: 'right', rect: {left: 40, top: 0, width: 20, height: 20}},
  {id: 'illegal-nearest', disabled: true, rect: {left: 0, top: 20, width: 20, height: 10}},
  {id: 'ordinary-sortable', ordinary: true, rect: {left: 0, top: 25, width: 20, height: 10}},
  {id: 'folded-child', rect: {left: 0, top: 25, width: 0, height: 0}},
];
assert.deepEqual(run('ArrowDown', entries), {result: {x: 40, y: 105}, prevented: true});
assert.deepEqual(run('ArrowUp', entries).result, {x: 40, y: 25});
assert.deepEqual(run('ArrowLeft', entries).result, {x: 0, y: 60});
assert.deepEqual(run('ArrowRight', entries).result, {x: 80, y: 60});
assert.deepEqual(run('Delete', entries), {result: undefined, prevented: false});
assert.deepEqual(run('ArrowDown', entries, null), {result: undefined, prevented: false});
assert.deepEqual(run('ArrowDown', entries.filter(item => item.rect.top < 20)), {result: undefined, prevented: true});
assert.deepEqual(run('ArrowDown', entries.map(item => ({...item, disabled: true}))), {result: undefined, prevented: true});
console.log('8 controlled keyboard-coordinate cases passed; actual getter; no browser used.');
