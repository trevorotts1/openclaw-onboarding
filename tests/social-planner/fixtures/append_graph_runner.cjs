// Execute the actual exported n8n graph; HTTP responses replace input and named
// node access fails if that branch has not executed. No network requests.
const fs=require('node:fs'), vm=require('node:vm');
const request=JSON.parse(fs.readFileSync(0,'utf8'));
const workflow=JSON.parse(fs.readFileSync(request.workflow,'utf8'));
const nodes=Object.fromEntries(workflow.nodes.map(n=>[n.name,n]));
const header=workflow.contract.posts_schema;
const state=request.state || {Posts:[header], 'Weekly Overview':[], Images:[], Videos:[]};
const ids={Posts:101,'Weekly Overview':202,Images:303,Videos:404};
const writes=[], runs=[];let afterFailureUsed=false;
function parseExpr(value,input,prior) {
 if(typeof value!=='string' || !value.startsWith('=')) return value;
 const evaluate=expr=>vm.runInNewContext(expr,{$json:input,$:(name)=>{if(!Object.hasOwn(prior,name))throw Error('UNEXECUTED NODE '+name);return {first:()=>({json:prior[name]})}},JSON,encodeURIComponent,URL});
 const exact=value.match(/^=\{\{([\s\S]*)\}\}$/);
 if(exact)return evaluate(exact[1]);
 return value.slice(1).replace(/\{\{([\s\S]*?)\}\}/g,(_,exp)=>{let v=evaluate(exp);if(v===undefined)throw Error('undefined URL value');return String(v)});
}
function http(name,p,body) {
 const url=new URL(p.url);
 if(/undefined|null/.test(url.href)) throw Error('Invalid URL '+url.href);
 if(request.failAt===name) throw Object.assign(Error('simulated failure'),{statusCode:request.statusCode||503});
 if(!url.pathname.includes('/values/') && !url.pathname.endsWith(':batchUpdate')) {
  return {spreadsheetId:'sheet_123',developerMetadata:request.metadata===undefined?[{metadataKey:'skill35_company_id',metadataValue:'company_1'}]:request.metadata,sheets:Object.entries(ids).filter(([t])=>!(request.missingTabs||[]).includes(t)).map(([title,sheetId])=>({properties:{title,sheetId}}))};
 }
 if(url.pathname.endsWith(':batchUpdate')) {
  for(const r of body.requests) {
   const d=r.updateDimensionProperties;
   if(d && (d.fields!=='pixelSize' || d.range.startIndex<0 || d.range.endIndex!==d.range.startIndex+1 || !Object.values(ids).includes(d.range.sheetId)))throw Error('invalid dimension request');
   const c=r.updateCells;
   if(c && (c.fields!=='userEnteredValue' || c.start.sheetId!==ids.Videos || c.start.rowIndex<1))throw Error('invalid video formula request');
  }
  writes.push({name,body,url:p.url});return {spreadsheetId:'sheet_123',replies:body.requests.map(()=>({}))};
 }
 const raw=decodeURIComponent(url.pathname.split('/values/')[1]);
 const [quoted,range]=raw.split('!'),tab=quoted.replace(/^'|'$/g,'');
 if(!state[tab] || (request.missingTabs||[]).includes(tab))throw Error('unknown tab '+tab);
 if(p.method==='GET') {
  const row=/^A(\d+)/.exec(range);const start=row?Number(row[1])-1:0;
  return {range:`'${tab}'!A${start+1}:N${state[tab].length}`,values:state[tab].slice(start)};
 }
 writes.push({name,body,url:p.url});
 if(range.includes(':append')) {
  if(url.searchParams.get('valueInputOption')!=='RAW')throw Error('untrusted append not RAW');
  if(!state[tab].length)state[tab].push(['header']);
  state[tab].push(body.values[0]);const row=state[tab].length;
  return {updates:{updatedRange:`'${tab}'!A${row}:N${row}`}};
 }
 const start=/^([A-Z]+)(\d+)/.exec(range);if(!start)throw Error('invalid range '+range);
 const row=Number(start[2]);
 if(start[1]==='P') {
  if(url.searchParams.get('valueInputOption')!=='USER_ENTERED')throw Error('formula must USER_ENTERED');
 } else {
  if(url.searchParams.get('valueInputOption')!=='RAW')throw Error('untrusted update not RAW');
  state[tab][row-1]=body.values[0];
 }
 return {updatedRange:`'${tab}'!${start[1]}${row}:N${row}`};
}
for(const inputBody of request.bodies) {
 const prior={},trace=[];let current='Webhook: Append Row',input={body:inputBody};let response;
 for(let i=0;i<100;i++) {
  const n=nodes[current]; if(!n)throw Error('missing node '+current);trace.push(current);
  let output=input, branch=0;
  try {
   if(n.type.endsWith('.code')) {
    output=vm.runInNewContext(`(function(){${n.parameters.jsCode}\n})()`,{$input:{first:()=>({json:input})},$:(name)=>{if(!Object.hasOwn(prior,name))throw Error('UNEXECUTED NODE '+name);return {first:()=>({json:prior[name]})}},URL,JSON})[0].json;
   } else if(n.type.endsWith('.httpRequest')) {
    const params=Object.fromEntries(Object.entries(n.parameters).map(([k,v])=>[k,parseExpr(v,input,prior)]));
    output=http(current,params,params.jsonBody?JSON.parse(params.jsonBody):undefined);
    if(request.failAfterAt===current && !afterFailureUsed){afterFailureUsed=true;throw Object.assign(Error("response lost after commit"),{statusCode:503})}
   } else if(n.type.endsWith('.if')) {
    branch=parseExpr(n.parameters.conditions.conditions[0].leftValue,input,prior)?0:1;
   } else if(n.type.endsWith('.respondToWebhook')) {
    response=JSON.parse(parseExpr(n.parameters.responseBody,input,prior));break;
   }
  } catch(e) {
   if(!n.onError)throw e;
   branch=1;output={error:{message:e.message,statusCode:e.statusCode}};
  }
  prior[current]=output;
  const edges=workflow.connections[current]?.main?.[branch];
  if(!edges || edges.length!==1)throw Error('missing/ambiguous edge '+current+' output '+branch);
  input=output;current=edges[0].node;
 }
 if(!response)throw Error('graph did not respond');
 runs.push({response,trace});
}
process.stdout.write(JSON.stringify({runs,state,writes}));
