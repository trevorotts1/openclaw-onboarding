'use strict';
// Executes actual exported Code, If, expressions, and connections. Mock HTTP
// always replaces input so named-node lookups must reference an executed node.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {Tournament}=require(process.argv[2]),tournament=new Tournament(e=>{throw e});
const directory=process.argv[3],router=JSON.parse(fs.readFileSync(path.join(directory,'compatibility-router.json'))),creator=JSON.parse(fs.readFileSync(path.join(directory,'legacy-sheet-create.json')));
let tests=0,expressions=0;
function test(name,fn){fn();tests++;console.log('PASS '+name)}
for(const workflow of [router,creator])for(const node of workflow.nodes){
 function visit(v){if(typeof v==='string'&&v.startsWith('=')){tournament.getExpressionCode(v.slice(1));expressions++;}else if(v&&typeof v==='object')for(const [k,x]of Object.entries(v))if(k!=='jsCode')visit(x)}
 visit(node.parameters);
 if(node.type.endsWith('.httpRequest')||node.type.endsWith('.code')){
  assert.equal(node.onError,'continueErrorOutput');
  assert.equal(workflow.connections[node.name].main[1].length,1);
 }
 if(node.type.endsWith('.httpRequest')&&node.parameters.method==='POST')assert(!node.retryOnFail,'No blind copy/share/append/router retries');
}
function graph(workflow,start,body,http){
 const nodes=Object.fromEntries(workflow.nodes.map(n=>[n.name,n])),prior={},trace=[];
 let current=start,input={body};
 const lookup=name=>{assert(Object.hasOwn(prior,name),'Cannot look up unexecuted '+name);return {first:()=>({json:prior[name]})}};
 const evaluate=value=>typeof value==='string'&&value.startsWith('=')?tournament.execute(value.slice(1),{$json:input,$:lookup,JSON,encodeURIComponent}):value;
 for(let i=0;i<100;i++){
  const node=nodes[current];assert(node,'Missing graph target '+current);trace.push(current);let result=input,port=0;
  try{
   if(node.type.endsWith('.code'))result=vm.runInNewContext('(function(){'+node.parameters.jsCode+'\n})()',{$input:{first:()=>({json:input})},$:lookup})[0].json;
   else if(node.type.endsWith('.if'))port=evaluate(node.parameters.conditions.conditions[0].leftValue)===true?0:1;
   else if(node.type.endsWith('.httpRequest')){
    const params=Object.fromEntries(Object.entries(node.parameters).map(([k,v])=>[k,evaluate(v)]));
    assert(!params.url.includes('undefined'));result=http(node.name,params,prior);
   }else if(node.type.endsWith('.respondToWebhook'))return {body:JSON.parse(evaluate(node.parameters.responseBody)),status:evaluate(node.parameters.options.responseCode),trace};
  }catch(error){if(node.onError!=='continueErrorOutput')throw error;port=1;result={error:{message:error.message}}}
  prior[current]=result;const targets=workflow.connections[current]?.main?.[port];assert.equal(targets?.length,1,'One next node');current=targets[0].node;input=result;
 }
 throw Error('No response within bounded graph');
}
function route(kind,body,result={statusCode:200,body:{success:true}},options={}){
 const calls=[];
 const response=graph(router,kind+' Compatibility Hook',body,(name,p)=>{calls.push({name,...p});assert.equal(p.method,'POST');assert.equal(p.options.redirect.redirect.followRedirects,false);assert.deepEqual(JSON.parse(p.jsonBody),body);if(options.fail)throw Error('timeout');return result});
 return {...response,calls};
}
test('Exact legacy shapes select only legacy targets',()=>{for(const [kind,body]of [['Create',{brandName:'Fixture Brand',clientEmail:'fixture@example.invalid'}],['Append',{sheetId:'fixture_sheet',row:{notes:'test'}}]]){const r=route(kind,body);assert.equal(r.status,200);assert.equal(r.calls.length,1);assert.equal(r.calls[0].name,kind+' Legacy Workflow')}});
test('Any extra modern key even null selects strict route only',()=>{for(const [kind,body]of [['Create',{brandName:'Fixture Brand',clientEmail:'fixture@example.invalid'}],['Append',{sheetId:'fixture_sheet',row:{notes:'test'}}]])for(const key of ['company_id','schema_version','cycle_id','account_id'])for(const value of [null,'',false]){const r=route(kind,{...body,[key]:value},{statusCode:422,body:{success:false}});assert.equal(r.status,422);assert.equal(r.calls.length,1);assert.equal(r.calls[0].name,kind+' Strict Workflow')}});
test('Strict failure never downgrades into legacy lane',()=>{for(const statusCode of [400,403,422,500,503]){const r=route('Append',{company_id:'fixture_company',sheetId:'fixture_sheet'},{statusCode,body:{success:false}});assert.equal(r.status,statusCode);assert.equal(r.calls.length,1);assert.equal(r.calls[0].name,'Append Strict Workflow')}});
test('Malformed request makes no downstream call',()=>{for(const b of [null,[],false,'text']){const r=route('Create',b);assert.equal(r.status,502);assert.equal(r.calls.length,0)}});
test('Timeout and unverified response produce truthful failure without retry',()=>{for(const result of [{body:{success:true}},{statusCode:200,body:'not JSON'},{statusCode:200,body:null},{statusCode:999,body:{}}]){const r=route('Create',{company_id:'fixture_company'},result);assert.equal(r.status,502);assert.equal(r.calls.length,1);assert.equal(r.body.publication_verified,false)}const r=route('Create',{company_id:'fixture_company'},undefined,{fail:true});assert.equal(r.status,502);assert.equal(r.calls.length,1)});
test('Caller URL is never used as router destination',()=>{const r=route('Create',{company_id:'fixture_company',url:'https://attacker.invalid'});assert(r.calls[0].url.startsWith('https://main.blackceoautomations.com/webhook/social-planner/v1.1.0/'));assert(!r.calls[0].url.includes('attacker'))});
const mimeType='application/vnd.google-apps.spreadsheet',fixtureId='fixture_copy_12345',body={brandName:'Fixture Brand',clientEmail:'fixture@example.invalid'};
function create(options={}){
 const writes=[],initialSheets={'Weekly Overview':[['title'],['old header'],['HISTORICAL SAMPLE']],Images:[['OLD PRIVATE SAMPLE']],"Owner's Tab":[['OLDER SAMPLE']]};
 const state={id:fixtureId,appProperties:{skill35_legacy_brand:body.brandName,skill35_legacy_email:body.clientEmail,skill35_legacy_state:options.state??'initializing'},sheets:initialSheets};
 const result=graph(creator,'Legacy Create Hook',options.body??body,(name,p,prior)=>{
  if(options.failAt===name)throw Error('Mock upstream failure');
  const payload=p.jsonBody?JSON.parse(p.jsonBody):null;
  if(p.method!=='GET')writes.push({name,url:p.url,payload});
  switch(name){
   case 'Read Legacy Copies':return {files:options.files??(options.existing?[{id:state.id,mimeType,trashed:false,appProperties:state.appProperties}]:[]),...(options.nextPageToken?{nextPageToken:'more'}:{})};
   case 'Copy Legacy Template':assert(p.url.includes('__LEGACY_TEMPLATE_ID__/copy'));state.appProperties=payload.appProperties;return {id:state.id,mimeType};
   case 'Read Legacy Permissions':return {permissions:options.permissions??[{type:'user',role:'owner'}]};
   case 'Read New Copy Tabs':return {spreadsheetId:options.wrongSheet?'other_sheet':state.id,sheets:Object.keys(state.sheets).map((title,index)=>({properties:{title,sheetId:index}}))};
   case 'Clear New Copy Sample Values':assert.deepEqual(Array.from(payload.ranges),["'Weekly Overview'!A:ZZZ","'Images'!A:ZZZ","'Owner''s Tab'!A:ZZZ"]);for(const key of Object.keys(state.sheets))state.sheets[key]=[];return {spreadsheetId:state.id,clearedRanges:payload.ranges};
   case 'Write Clean Legacy Headers':assert(p.url.endsWith('A1:T2?valueInputOption=RAW'));assert.equal(payload.values[1].length,20);state.sheets['Weekly Overview']=payload.values;return {spreadsheetId:state.id,updatedRange:"'Weekly Overview'!A1:T2"};
   case 'Mark Legacy Formatted':assert(!JSON.stringify(state.sheets).includes('SAMPLE'));state.appProperties={...state.appProperties,...payload.appProperties};return {id:state.id,appProperties:state.appProperties};
   case 'Share Legacy Copy':assert.equal(state.appProperties.skill35_legacy_state,'formatted');assert.deepEqual(payload,{role:'writer',type:'anyone'});return {id:'fixture_public_permission',type:'anyone',role:'writer'};
   case 'Mark Legacy Ready':state.appProperties={...state.appProperties,...payload.appProperties};return {id:options.badReceipt?'different':state.id,appProperties:state.appProperties};
   default:throw Error('Unexpected creator HTTP '+name);
  }
 });
 return {...result,writes,state};
}
test('New legacy copy clears every tab before sharing then returns document-only receipt',()=>{const r=create();assert.equal(r.status,200);assert.equal(r.body.company_registration_verified,false);assert.equal(r.body.publication_verified,false);assert.equal(r.body.sheetId,fixtureId);assert(!JSON.stringify(r.state.sheets).includes('SAMPLE'));assert(r.trace.indexOf('Mark Legacy Formatted')<r.trace.indexOf('Share Legacy Copy'))});
test('Existing shared ready document replays without clearing or copying',()=>{const r=create({existing:true,state:'ready',permissions:[{type:'anyone',role:'writer'}]});assert.equal(r.status,200);assert.equal(r.body.deduped,true);assert(!r.trace.includes('Clear New Copy Sample Values'));assert(!r.trace.includes('Copy Legacy Template'));assert(JSON.stringify(r.state.sheets).includes('HISTORICAL SAMPLE'))});
test('Formatted replay regrants sharing without clearing client content',()=>{const r=create({existing:true,state:'formatted'});assert.equal(r.status,200);assert(r.trace.includes('Share Legacy Copy'));assert(!r.trace.includes('Clear New Copy Sample Values'))});
test('Initializing document with any non-owner access refuses destructive clear',()=>{for(const permission of [{type:'anyone',role:'writer'},{type:'user',role:'reader'},{type:'group',role:'writer'}]){const r=create({existing:true,permissions:[permission]});assert.equal(r.status,422);assert.equal(r.writes.length,0);assert(JSON.stringify(r.state.sheets).includes('SAMPLE'))}});
test('Unshared interrupted initialization resumes clean initialization',()=>{const r=create({existing:true});assert.equal(r.status,200);assert(!r.trace.includes('Copy Legacy Template'));assert(r.trace.includes('Clear New Copy Sample Values'))});
test('Share failure retains formatted checkpoint and never declares success',()=>{const r=create({failAt:'Share Legacy Copy'});assert.equal(r.status,422);assert.equal(r.state.appProperties.skill35_legacy_state,'formatted');assert.equal(r.body.success,false)});
test('Unknown state ambiguous identity and incomplete list require preserving repair',()=>{for(const options of [{existing:true,state:'unknown'},{files:[{},{}]},{nextPageToken:true},{files:[{id:fixtureId,mimeType,appProperties:{skill35_legacy_brand:'other'}}]}]){const r=create(options);assert.equal(r.status,422);assert.equal(r.writes.length,0)}});
test('Mixed modern create and injected input are rejected before lookup',()=>{for(const b of [{...body,company_id:null},{...body,templateSheetId:'other'}, {...body,brandName:'line\nbreak'}, {...body,clientEmail:'bad'}, {...body,brandName:'x'.repeat(200)}]){const r=create({body:b});assert.equal(r.status,422);assert.equal(r.writes.length,0);assert(!r.trace.includes('Read Legacy Copies'))}});
test('Wrong copied metadata or missing readiness receipt refuses success',()=>{assert.equal(create({wrongSheet:true}).body.success,false);assert.equal(create({badReceipt:true}).body.success,false)});
test('Provider errors stop downstream work; non-idempotent calls have no retries',()=>{for(const failAt of ['Read Legacy Copies','Copy Legacy Template','Read Legacy Permissions','Read New Copy Tabs','Clear New Copy Sample Values','Write Clean Legacy Headers','Mark Legacy Formatted','Mark Legacy Ready']){const r=create({failAt});assert.equal(r.status,422);assert.equal(r.body.success,false);assert.equal(r.trace.filter(x=>x===failAt).length,1)}});
console.log(JSON.stringify({passed:true,tests,expressions,liveCalls:0}));
