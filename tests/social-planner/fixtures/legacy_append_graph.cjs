'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {Tournament}=require(process.argv[2]);
const tournament=new Tournament(e=>{throw e});
const w=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const bound=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));
const nodes=Object.fromEntries(w.nodes.map(n=>[n.name,n]));
const headers=['Week Of','Theme of the Week','Research','Core Content','Images','Videos','Facebook','Instagram','LinkedIn','YouTube','TikTok','Pinterest','Carousels','Blog','Podcast','Email','QC','Scheduled','Overall','Notes'];
let assertions=0,expressions=0;
function test(name,fn){fn();assertions++;console.log('PASS '+name)}
for(const n of w.nodes){
 function visit(v){if(typeof v==='string'&&v.startsWith('=')){tournament.getExpressionCode(v.slice(1));expressions++;}else if(v&&typeof v==='object')for(const[k,x]of Object.entries(v))if(k!=='jsCode')visit(x)}
 visit(n.parameters);
 if(n.type.endsWith('.code'))assert.equal(vm.runInNewContext('typeof URL'),'undefined');
}
function run(body={sheetId:'sheet_123',row:{theme:'Test',notes:'=IMPORTXML("https://example.invalid", "*")'}},options={}){
 const prior={},trace=[],writes=[];let current='Legacy Row Webhook',input={body};
 const get=name=>{if(!Object.hasOwn(prior,name))throw Error('Unexecuted named node '+name);return {first:()=>({json:prior[name]})}};
 const evaluate=(value)=>typeof value==='string'&&value.startsWith('=')?tournament.execute(value.slice(1),{$json:input,$:get,JSON}):value;
 for(let i=0;i<50;i++){
  const n=nodes[current];trace.push(current);let result=input,branch=0;
  try{
   if(n.type.endsWith('.code'))result=vm.runInNewContext('(function(){'+n.parameters.jsCode+'\n})()',{$input:{first:()=>({json:input})},$:get})[0].json;
   else if(n.type.endsWith('.httpRequest')){
    const params=Object.fromEntries(Object.entries(n.parameters).map(([k,v])=>[k,evaluate(v)]));
    const url=new URL(params.url);assert(!url.href.includes('undefined'));
    if(options.failAt===current)throw Error('upstream failure');
    switch(current){
     case 'Read Public Document':result={id:body.sheetId,mimeType:'application/vnd.google-apps.spreadsheet',trashed:false,...options.document};break;
     case 'Read Public Edit Permission':result={permissions:options.permissions??[{id:'anyone',type:'anyone',role:'writer'}],...(options.nextPageToken?{nextPageToken:'page2'}:{})};break;
     case 'Read Legacy Sheet Metadata':result={spreadsheetId:body.sheetId,sheets:options.tabs??[{properties:{title:'Weekly Overview',sheetId:432}}]};break;
     case 'Read Legacy Headers':assert.equal(url.pathname,`/v4/spreadsheets/${body.sheetId}/values/Weekly%20Overview!A1:T10`);result={range:"'Weekly Overview'!A1:T10",values:options.headerRows??[options.headers??headers]};break;
     case 'Append Legacy Overview RAW':
      assert.equal(url.pathname,`/v4/spreadsheets/${body.sheetId}/values/Weekly%20Overview!A${prior['Validate Legacy Headers'].headerRow}:T:append`);
      assert.equal(url.searchParams.get('valueInputOption'),'RAW');assert(!n.retryOnFail);
      const data=JSON.parse(params.jsonBody);assert.equal(data.values.length,1);assert.equal(data.values[0].length,20);
      writes.push(data);if(options.failAfterAppend)throw Error('Response lost after write');
      result={spreadsheetId:body.sheetId,updates:{updatedRange:`'Weekly Overview'!A${prior['Validate Legacy Headers'].headerRow+1}:T${prior['Validate Legacy Headers'].headerRow+1}`,updatedRows:1},...options.receipt};break;
     default:throw Error('Unexpected HTTP node '+current);
    }
   }else if(n.type.endsWith('.respondToWebhook'))return {response:JSON.parse(evaluate(n.parameters.responseBody)),status:evaluate(n.parameters.options.responseCode),trace,writes};
  }catch(e){if(n.onError!=='continueErrorOutput')throw e;result={error:{message:e.message}};branch=1;}
  prior[current]=result;
  const edge=w.connections[current]?.main?.[branch];assert.equal(edge?.length,1,'one edge per output');current=edge[0].node;input=result;
 }
 throw Error('Graph did not respond');
}
test('Public document exact20RAWwrite returns truthful receipt',()=>{const r=run();assert.equal(r.status,200);assert.equal(r.response.success,true);assert.equal(r.response.publication_verified,false);assert.equal(r.response.company_ownership_claimed,false);assert.equal(r.writes[0].values[0][19],'=IMPORTXML("https://example.invalid", "*")');});
test('Modern top-level keys reject even empty/null and never write',()=>{for(const key of ['company_id','companyId','schema_version','cycle_id','account_id','asset'])for(const value of [null,'',false]){const r=run({sheetId:'sheet_123',row:{notes:'test'},[key]:value});assert.equal(r.status,422);assert.equal(r.writes.length,0)}});
test('Modern nested row keys cannot bypass strict identity lane',()=>{for(const key of ['company_id','schema_version','account_id','cycle_id']){const r=run({sheetId:'sheet_123',row:{notes:'test',[key]:null}});assert.equal(r.writes.length,0);assert.equal(r.response.success,false)}});
test('Private reader deleted and expired capabilities reject',()=>{for(const p of [{type:'user',role:'writer'},{type:'anyone',role:'reader'},{type:'anyone',role:'writer',deleted:true},{type:'anyone',role:'writer',expirationTime:'2000-01-01T00:00:00Z'},{type:'anyone',role:'writer',expirationTime:'invalid'},{type:'anyone',role:'writer',expirationTime:123}]){const r=run(undefined,{permissions:[p]});assert.equal(r.writes.length,0);assert.equal(r.response.success,false)}});
test('Unexpired writer capability is accepted',()=>assert.equal(run(undefined,{permissions:[{type:'anyone',role:'writer',expirationTime:'2099-01-01T00:00:00Z'}]}).response.success,true));
test('Permission pagination requires complete proof',()=>assert.equal(run(undefined,{nextPageToken:true}).writes.length,0));
test('Trashed nonSheet and mismatched identity refuse writes',()=>{for(const document of [{trashed:true},{mimeType:'text/plain'},{id:'different_sheet'},{trashed:null}])assert.equal(run(undefined,{document}).writes.length,0)});
test('Missing tab or merged/wrong headers refuse writes',()=>{assert.equal(run(undefined,{tabs:[]}).writes.length,0);for(const h of [headers.slice(0,1),headers.slice(0,19),[...headers.slice(0,19),'Different']])assert.equal(run(undefined,{headers:h}).writes.length,0)});
test('Title row preserved and unique row2 headers anchor append',()=>{const rows=[['SOCIAL MEDIA PLANNER - WEEKLY OVERVIEW'],headers,['old content']];const before=JSON.stringify(rows);const r=run(undefined,{headerRows:rows});assert.equal(r.status,200);assert.equal(r.response.updatedRange,"'Weekly Overview'!A3:T3");assert.equal(JSON.stringify(rows),before);assert.equal(r.writes.length,1)});
test('Header search allows row10 but rejects missing duplicate and beyond bound',()=>{const rows=Array.from({length:9},()=>[]).concat([headers]);assert.equal(run(undefined,{headerRows:rows}).status,200);for(const headerRows of [[headers,headers],[['title']],Array.from({length:10},()=>[]).concat([headers])]){const r=run(undefined,{headerRows});assert.equal(r.status,422);assert.equal(r.writes.length,0)}});
test('Receipt cannot target verified title or header row',()=>{for(const row of [1,2]){const r=run(undefined,{headerRows:[['title'],headers],receipt:{updates:{updatedRange:`'Weekly Overview'!A${row}:T${row}`,updatedRows:1}}});assert.equal(r.response.success,false)}});
test('SheetURL/path injection and nonScalar cells reject before any write',()=>{for(const sheetId of ['sheet/other','../x','sheet?range=Private'])assert.equal(run({sheetId,row:{notes:'test'}}).writes.length,0);for(const notes of [{formula:'bad'},['bad']])assert.equal(run({sheetId:'sheet_123',row:{notes}}).writes.length,0)});
test('Aliases retain zero false and no generic platform→TikTok',()=>{const r=run({sheetId:'sheet_123',row:{weekOf:'2026-09-09',theme:'test',research:0,qc:false,platform:'LinkedIn'}});assert.equal(r.writes[0].values[0][2],0);assert.equal(r.writes[0].values[0][16],false);assert.equal(r.writes[0].values[0][10],'');assert.equal(r.response.warnings.length,1)});
test('HTTP errors are non-success and prevent dependentwrites',()=>{for(const failAt of ['Read Public Document','Read Public Edit Permission','Read Legacy Sheet Metadata','Read Legacy Headers','Append Legacy Overview RAW']){const r=run(undefined,{failAt});assert.equal(r.status,502);assert.equal(r.response.success,false);assert.equal(r.writes.length,0)}});
test('Lost append response is not retried and not declared success',()=>{const r=run(undefined,{failAfterAppend:true});assert.equal(r.status,502);assert.equal(r.writes.length,1);assert.equal(r.trace.filter(x=>x==='Append Legacy Overview RAW').length,1)});
test('Unproven or wrong appendedRange fails closed',()=>{for(const receipt of [{spreadsheetId:'other'}, {updates:{updatedRange:'appended',updatedRows:1}}, {updates:{updatedRange:"'Private'!A2:T2",updatedRows:1}}, {updates:{updatedRange:"'Weekly Overview'!A1:T1",updatedRows:1}}])assert.equal(run(undefined,{receipt}).response.success,false)});
test('Only one fixedRAWmutatingnode no registry ownership or Posts writes',()=>{const mutations=w.nodes.filter(n=>n.type.endsWith('.httpRequest')&&n.parameters.method!=='GET');assert.equal(mutations.length,1);assert.equal(mutations[0].name,'Append Legacy Overview RAW');assert(!JSON.stringify(mutations).includes('USER_ENTERED'))});
test('Canonical credentials absent deploy refs correctlybound',()=>{assert(w.nodes.every(n=>!n.credentials));for(const n of bound.nodes.filter(n=>n.type.endsWith('.httpRequest'))){const type=n.parameters.nodeCredentialType;assert.deepEqual(Object.keys(n.credentials),[type]);assert.deepEqual(Object.keys(n.credentials[type]).sort(),['id','name'])}});
console.log(JSON.stringify({passed:true,tests:assertions,expressions,codeRuntime:'VM without URL or crypto injection',liveCalls:0}));
