const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require('typescript');
const file = path.resolve(__dirname, '../../lib/review-comment-preview.ts');
const mod = new Module(file, module); mod.filename = file; mod.paths = module.paths;
mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText, file);
const {afterCommentImport} = mod.exports;
const items = Array.from({length:101}, (_,i)=>({text:`original opinion ${i+1}`,original_text:`original opinion ${i+1}`,include:i<100}));
const original = structuredClone(items);
const first = afterCommentImport(items);
assert.equal(first.remaining,1);assert.equal(first.draft,'original opinion 101');assert.equal(first.preview.length,101);
assert.deepEqual(items,original);
for(let i=0;i<100;i++) {assert.equal(first.preview[i].imported,true);assert.equal(first.preview[i].include,false);assert.equal(first.preview[i].original_text,original[i].original_text);}
assert.deepEqual(first.preview[100],original[100]);
console.log('PASS a real 100-of-101 batch keeps the remaining opinion and original source positions');
const lastSelected=first.preview.map((item,i)=>i===100?{...item,include:true}:item);
assert.deepEqual(afterCommentImport(lastSelected),{preview:[],draft:'',remaining:0});
assert.equal(lastSelected.filter(item=>!item.imported&&item.include).length,1);
console.log('PASS the second batch contains only opinion 101 and completion clears the finished preview');
const edited=afterCommentImport([{text:'accepted',original_text:'accepted',include:true},{text:'edited pending\n\nparagraph',original_text:'unmodified original',include:false}]);
assert.equal(edited.draft,'edited pending\n\nparagraph');assert.equal(edited.preview[1].original_text,'unmodified original');assert.equal(edited.preview[1].include,false);
const normalized=afterCommentImport([{text:'prior imported',original_text:'prior imported',include:true,imported:true},{text:'pending',original_text:'pending',include:false}]);
assert.equal(normalized.preview[0].include,false);assert.equal(normalized.remaining,1);
console.log('PASS an excluded edited opinion keeps both texts and imported rows cannot be submitted twice');
