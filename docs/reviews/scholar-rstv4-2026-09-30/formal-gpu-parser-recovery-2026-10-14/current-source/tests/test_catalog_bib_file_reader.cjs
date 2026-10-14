const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { File } = require('node:buffer');
vm.runInThisContext(fs.readFileSync(path.join(__dirname, '../src/rstv4/catalog_collections.js'), 'utf8'));
const { createBibFileReader } = globalThis.CatalogCollections;
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve=a; reject=b; }); return {promise, resolve, reject}; };
function harness() {
  const commits=[], events=[];
  const reader=createBibFileReader({onContent:value=>commits.push(value),onState:value=>events.push({...value})});
  return {reader,commits,events};
}
async function main() {
  {
    const {reader,commits,events}=harness();
    const file=new File(['@article{a, title={Real File text}}'], 'references.bib');
    const pending=reader.read(file);
    assert.equal(reader.state().pending,true);
    assert.match(events.at(-1).message,/正在从本机读取/);
    assert.equal(await pending,true);
    assert.deepEqual(commits,['@article{a, title={Real File text}}']);
    assert.equal(reader.state().pending,false);
    assert.equal(events.at(-1).message,'已读入 references.bib；文件没有上传。');
  }
  {
    const {reader,commits}=harness(), first=deferred(), second=deferred();
    const a=reader.read({name:'same.bib',size:3,text:()=>first.promise});
    const b=reader.read({name:'same.bib',size:3,text:()=>second.promise});
    second.resolve('new');assert.equal(await b,true);
    first.resolve('old');assert.equal(await a,false);
    assert.deepEqual(commits,['new']);assert.equal(reader.state().pending,false);
  }
  for (const lateFailure of [false,true]) {
    const {reader,commits,events}=harness(), delayed=deferred();
    const pending=reader.read({name:'slow.bib',size:10,text:()=>delayed.promise});
    reader.cancel();
    const cancelled=events.at(-1);
    assert.equal(cancelled.pending,false);assert.match(cancelled.message,/当前输入保留/);
    if(lateFailure)delayed.reject(Error('late failed read'));else delayed.resolve('late old contents');
    assert.equal(await pending,false);assert.deepEqual(commits,[]);
    assert.equal(events.at(-1),cancelled); // Late error cannot overwrite a later edit/navigation notice.
  }
  {
    const {reader,commits,events}=harness(), delayed=deferred();
    const pending=reader.read({name:'old.bib',size:10,text:()=>delayed.promise});
    let oversizedRead=false;
    assert.equal(await reader.read({name:'over.bib',size:5000001,text:()=>{oversizedRead=true;throw Error('must not read oversized file');}}),false);
    assert.equal(oversizedRead,false);assert.match(events.at(-1).message,/超过本版 5 MB/);
    delayed.resolve('old');assert.equal(await pending,false);assert.deepEqual(commits,[]);
    assert.match(events.at(-1).message,/超过本版 5 MB/);
  }
  {
    const {reader,commits,events}=harness();
    assert.equal(await reader.read({name:'unreadable.bib',size:1,text:async()=>{throw Error('read denied');}}),false);
    assert.equal(reader.state().pending,false);assert.deepEqual(commits,[]);assert.match(events.at(-1).message,/无法读取文件：read denied/);
    assert.equal(await reader.read(new File(['retry'],'unreadable.bib')),true);
    assert.deepEqual(commits,['retry']);
  }
  {
    const {reader,commits}=harness();
    assert.equal(await reader.read(new File(['edge'],'edge.bib')),true);
    const exact = {name:'exact-limit.bib',size:5000000,text:async()=> 'exact-limit'};
    assert.equal(await reader.read(exact),true);
    assert.equal(await reader.read(null),false);assert.deepEqual(commits,['edge','exact-limit']);
  }
  console.log('PASS 8 asynchronous BibTeX read contracts: real File, same-name latest wins, cancelled late success/error, oversize invalidation, read-error retry and exact limit.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
