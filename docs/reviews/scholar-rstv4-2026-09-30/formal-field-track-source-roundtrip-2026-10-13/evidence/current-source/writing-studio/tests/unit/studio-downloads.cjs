const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require('typescript');
const file = path.resolve(__dirname, '../../lib/studio-downloads.ts');
const mod = new Module(file, module); mod.filename=file; mod.paths=module.paths;
mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText, file);
const {serveStudioFile, studioFileUrl} = mod.exports;
const root='http://127.0.0.1:3004/api/studio-files';
const request=(suffix='',origin='http://127.0.0.1:3004',method='GET')=>new Request(root+suffix,{method,headers:{Origin:origin}});
const base='http://127.0.0.1:8877/api';
const segments=['manuscripts','manuscript_1','packages','submission_package_1','download'];
let count=0;
async function test(name, fn){await fn();count++;console.log('PASS '+name);}
(async()=>{
await test('ZIP bytes, length and fixed filename stream unchanged through same-origin delivery',async()=>{
  const bytes=Uint8Array.from([80,75,0,255,65]);let calls=0;
  const out=await serveStudioFile(request(),segments,base,async(url,init)=>{
    calls++;assert.equal(url,base+'/manuscripts/manuscript_1/packages/submission_package_1/download');
    assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');assert.equal(init.method,'GET');
    return new Response(bytes,{headers:{'Content-Type':'application/zip','Content-Length':String(bytes.length),'Content-Disposition':'attachment; filename="fixed.zip"','Set-Cookie':'secret=not-forwarded'}});
  });
  assert.equal(calls,1);assert.equal(out.status,200);assert.deepEqual(new Uint8Array(await out.arrayBuffer()),bytes);
  assert.equal(out.headers.get('content-disposition'),'attachment; filename="fixed.zip"');
  assert.equal(out.headers.get('content-length'),String(bytes.length));assert.equal(out.headers.get('set-cookie'),null);
  assert.equal(out.headers.get('cache-control'),'no-store');
});
await test('package PDF and generated artifact use only fixed file routes',async()=>{
  for (const parts of [['manuscripts','ms','packages','pkg','files','clean-manuscript.pdf'],['artifacts','artifact_1'],['manuscripts','ms','generated-versions','v1','sources','evidence_1','pdf']]) {
    const response=await serveStudioFile(request(),parts,base,async(url)=>{assert.equal(url,base+'/'+parts.join('/'));return new Response('PDF exact bytes',{headers:{'Content-Type':'application/pdf'}});});
    assert.equal(await response.text(),'PDF exact bytes');
  }
  assert.equal(studioFileUrl('/artifacts/artifact_1'),'/api/studio-files/artifacts/artifact_1');
});
await test('unavailable fixed files preserve 410 and backend explanation',async()=>{
  const out=await serveStudioFile(request(),segments,base,async()=>Response.json({detail:'Immutable package file digest mismatch'},{status:410}));
  assert.equal(out.status,410);assert.deepEqual(await out.json(),{detail:'Immutable package file digest mismatch'});
});
await test('arbitrary API, path traversal, URL and query requests never reach backend',async()=>{
  const forbidden=async()=>{throw new Error('must not fetch');};
  for(const parts of [['manuscripts','ms','workspace'],['artifacts','../state.db'],['manuscripts','ms','packages','pkg','files','../secret'],['http:','remote'],['manuscripts','ms','packages','pkg','files','x.pdf','extra']]) {
    assert.equal((await serveStudioFile(request(),parts,base,forbidden)).status,404);
  }
  assert.equal((await serveStudioFile(request('?url=http://remote/'),segments,base,forbidden)).status,404);
});
await test('foreign origins and writes do not reach file service',async()=>{
  const forbidden=async()=>{throw new Error('must not fetch');};
  assert.equal((await serveStudioFile(request('','http://foreign.example'),segments,base,forbidden)).status,403);
  assert.equal((await serveStudioFile(request('','http://127.0.0.1:3004','POST'),segments,base,forbidden)).status,405);
});
await test('server destination is configured loopback API only',async()=>{
  const forbidden=async()=>{throw new Error('must not fetch');};
  for(const address of ['http://remote.example/api','http://127.0.0.1:8877/api?url=secret','http://user:secret@localhost/api','file:///api','http://localhost/other','invalid']) assert.equal((await serveStudioFile(request(),segments,address,forbidden)).status,503);
});
await test('empty responses and redirects cannot become apparently successful downloads',async()=>{
  for(const status of [204,302]) {
    const out=await serveStudioFile(request(),segments,base,async()=>new Response(null,{status}));
    assert.equal(out.status,502);assert.match((await out.json()).detail,/未返回文件/);
  }
  assert.equal((await serveStudioFile(request(),segments,base,async()=>{throw new Error('failed');})).status,502);
});
await test('current Evidence PDF binds a full original context digest without query forwarding',async()=>{
  const digest='a'.repeat(64);
  const parts=['manuscripts','ms','sources','evidence','contexts',digest,'pdf'];
  let calls=0;
  const reply=await serveStudioFile(request(),parts,base,async url=>{
    calls++; assert.equal(url,base+'/'+parts.join('/'));
    return new Response('original bytes',{headers:{'Content-Type':'application/pdf'}});
  });
  assert.equal(reply.status,200); assert.equal(await reply.text(),'original bytes'); assert.equal(calls,1);
  const forbidden=async()=>{throw new Error('must not fetch');};
  for(const invalid of ['','short','../other','A'.repeat(64),'a'.repeat(65)]) {
    const bad=[...parts]; bad[5]=invalid;
    assert.equal((await serveStudioFile(request(),bad,base,forbidden)).status,404);
  }
  assert.equal((await serveStudioFile(request('?context_sha256='+digest),parts,base,forbidden)).status,404);
});
console.log(`${count} fixed-file delivery contracts passed; controlled requests, no browser used.`);
})().catch(e=>{console.error(e);process.exitCode=1;});
