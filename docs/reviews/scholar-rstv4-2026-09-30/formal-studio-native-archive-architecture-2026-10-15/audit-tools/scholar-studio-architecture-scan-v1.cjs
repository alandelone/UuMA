const fs=require('node:fs');
const path=require('node:path');
const ts=require('C:/Users/Alandelone/CodeSpace_Local/writing-studio/node_modules/typescript');
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const result=[];
for(const item of input.files){
 const code=fs.readFileSync(item.path,'utf8');
 const source=ts.createSourceFile(item.path,code,ts.ScriptTarget.Latest,true,item.path.endsWith('tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);
 const imports=[],calls=[],env=[];
 function visit(n){
  const line=source.getLineAndCharacterOfPosition(n.getStart(source)).line+1;
  if(ts.isImportDeclaration(n)&&ts.isStringLiteral(n.moduleSpecifier))imports.push({module:n.moduleSpecifier.text,type_only:Boolean(n.importClause?.isTypeOnly),line});
  if(ts.isExportDeclaration(n)&&n.moduleSpecifier&&ts.isStringLiteral(n.moduleSpecifier))imports.push({module:n.moduleSpecifier.text,type_only:Boolean(n.isTypeOnly),line,export:true});
  if((ts.isCallExpression(n)||ts.isNewExpression(n))){
   const callee=n.expression.getText(source);
   if(/fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|axios|require|import|Worker|indexedDB|localStorage|sessionStorage|\.open$|eval|Function$|Database|\.connect$|\.query$|\.execute$/i.test(callee)){
    calls.push({callee,line,argument_kinds:[...(n.arguments||[])].map(a=>ts.SyntaxKind[a.kind])});
    if((callee==='require'||callee==='import')&&n.arguments?.[0]&&ts.isStringLiteral(n.arguments[0]))imports.push({module:n.arguments[0].text,type_only:false,line,dynamic:true});
   }
  }
  if(ts.isPropertyAccessExpression(n)&&n.getText(source).startsWith('process.env.'))env.push({name:n.getText(source).slice(12),line});
  ts.forEachChild(n,visit);
 }
 visit(source);
 result.push({file:item.relative,parse_diagnostics:source.parseDiagnostics.map(x=>({code:x.code,start:x.start})),imports,calls,env});
}
fs.writeFileSync(process.argv[3],JSON.stringify({typescript_version:ts.version,files:result},null,2));
process.stdout.write(JSON.stringify({files:result.length,parse_errors:result.reduce((n,f)=>n+f.parse_diagnostics.length,0)}));
