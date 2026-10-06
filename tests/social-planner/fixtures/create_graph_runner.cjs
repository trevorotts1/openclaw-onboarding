// Real export expressions and branch execution with replacing HTTP responses.
const fs=require('node:fs'),vm=require('node:vm');
const req=JSON.parse(fs.readFileSync(0,'utf8'));
const w=JSON.parse(fs.readFileSync(req.workflow,'utf8')), nodes=Object.fromEntries(w.nodes.map(n=>[n.name,n]));
const state=req.state || {files:[],sheets:{}};const runs=[],writes=[];let failed=false;
function execute(body){
 const prior={};let input={body},current='Webhook: Create Sheet';const trace=[];
 const get=name=>{if(!Object.hasOwn(prior,name))throw Error('UNEXECUTED NODE '+name);return {first:()=>({json:prior[name]})}};
 const evaluate=expr=>vm.runInNewContext(expr,{$json:input,$:get,JSON,encodeURIComponent,Intl});
 const expression=value=>{
  if(typeof value!=='string' || !value.startsWith('='))return value;
  const exact=value.match(/^=\{\{([\s\S]*)\}\}$/);if(exact)return evaluate(exact[1]);
  return value.slice(1).replace(/\{\{([\s\S]*?)\}\}/g,(_,x)=>{const v=evaluate(x);if(v===undefined)throw Error('undefined expression');return String(v)});
 };
 function http(name,p,b){
  const url=new URL(p.url);if(url.href.includes('undefined'))throw Error('undefined URL');
  if(req.failAt===name && !failed){failed=true;throw Object.assign(Error('injected upstream failure'),{statusCode:req.statusCode||503})}
  if(url.hostname==='www.googleapis.com'){
   if(url.pathname.endsWith('/permissions')){const f=state.files.find(x=>x.id===url.pathname.split('/').at(-2));return {permissions:f.shared?[{id:'anyone',role:'writer',type:'anyone'}]:[]};}
   if(url.pathname==='/drive/v3/files'){
    const q=url.searchParams.get('q');if(!q || q==='undefined')throw Error('invalid query');
    const key=q.match(/value='([^']+)'/)[1];return {files:state.files.filter(f=>f.appProperties.skill35_provisioning_key===key)};
   }
   if(url.pathname.endsWith('/copy')){
    if(!b.appProperties?.skill35_company_id || !b.appProperties.skill35_provisioning_key)throw Error('copy ownership not atomic');
    const id='created_'+(state.files.length+1);const file={id,name:b.name,appProperties:b.appProperties};state.files.push(file);
    state.sheets[id]={spreadsheetId:id,developerMetadata:[],sheets:(req.templateTabs||['Weekly Overview','Example (never copy)']).map((title,i)=>({properties:{title,sheetId:40+i,gridProperties:{rowCount:20,columnCount:26}},conditionalFormats:[],merges:req.templateMerged?[{sheetId:40+i,startRowIndex:0,endRowIndex:1,startColumnIndex:0,endColumnIndex:26}]:[]}))};writes.push({name,body:b});
    return structuredClone(file);
   }
   const id=url.pathname.split('/').at(-1),file=state.files.find(f=>f.id===id);
   if(p.method==='PATCH'){Object.assign(file.appProperties,b.appProperties);writes.push({name,body:b});return structuredClone(file)}
   return {id,name:'Template',mimeType:'application/vnd.google-apps.spreadsheet',...(req.templateMetadata||{})};
  }
  const id=url.pathname.split('/')[3].replace(':batchUpdate',''),sheet=state.sheets[id];
  if(!sheet)throw Error('Wrong sheet identity '+id);
  if(url.pathname.endsWith('/values:batchGet'))return {valueRanges:['Posts','Images','Videos','Weekly Overview','This Week'].map(title=>({values:[(sheet.headers||{})[title]]}))};
  if(p.method==='GET')return structuredClone(sheet);
  if(!b.requests?.length)throw Error('empty batch');
  const replies=[];
  for(const r of b.requests){
   const type=Object.keys(r)[0],op=r[type];
   if(['repeatCell','updateDimensionProperties','updateCells','updateSheetProperties','updateSpreadsheetProperties'].includes(type) && !op.fields)throw Error('missing fields '+type);
   if(r.addSheet){sheet.sheets.push({properties:op.properties});replies.push({addSheet:{properties:op.properties}});continue}
   if(r.unmergeCells){const tab=sheet.sheets.find(s=>s.properties.sheetId===op.range.sheetId);tab.merges=[];replies.push({});continue}
   if(r.deleteSheet){sheet.sheets=sheet.sheets.filter(s=>s.properties.sheetId!==op.sheetId);replies.push({});continue}
   const sid=op.range?.sheetId ?? op.start?.sheetId ?? op.properties?.sheetId;
   if(sid!==undefined && !sheet.sheets.some(s=>s.properties.sheetId===sid))throw Error('unknown numeric sheet ID');
   if(r.setDataValidation && op.range.endColumnIndex-op.range.startColumnIndex!==1)throw Error('status validation on content columns');
   if(r.updateDimensionProperties && !(op.range.endIndex>op.range.startIndex))throw Error('invalid dimension range');
   if(r.updateCells && op.start?.rowIndex===0){const title=sheet.sheets.find(x=>x.properties.sheetId===op.start.sheetId).properties.title;sheet.headers ||= {};sheet.headers[title]=op.rows[0].values.map(x=>x.userEnteredValue.stringValue);if(sheet.sheets.find(s=>s.properties.title===title).merges?.length)sheet.headers[title]=sheet.headers[title].slice(0,1);if(title==='Weekly Overview')sheet.headers[title]=sheet.headers[title].slice(0,20);if(title==='Images'||title==='Videos')sheet.headers[title]=sheet.headers[title].slice(0,14);}
   if(r.createDeveloperMetadata)sheet.developerMetadata.push({...op.developerMetadata,metadataId:sheet.developerMetadata.length+1});
   if(r.deleteDeveloperMetadata)sheet.developerMetadata=sheet.developerMetadata.filter(x=>x.metadataId!==op.dataFilter.developerMetadataLookup.metadataId);
   replies.push({});
  }
  writes.push({name,body:b});return {spreadsheetId:id,replies};
 }
 for(let step=0;step<100;step++){
  const n=nodes[current];if(!n)throw Error('unknown node '+current);trace.push(current);let output=input,branch=0;
  try {
   if(n.type.endsWith('.code'))output=vm.runInNewContext('(function(){'+n.parameters.jsCode+'\n})()',{$input:{all:()=>[{json:input}],first:()=>({json:input})},$:get,Intl,JSON})[0].json;
   else if(n.type.endsWith('.if'))branch=expression(n.parameters.conditions.conditions[0].leftValue)?0:1;
   else if(n.type.endsWith('.httpRequest')){
    const p=Object.fromEntries(Object.entries(n.parameters).map(([k,v])=>[k,expression(v)]));output=http(current,p,p.jsonBody?JSON.parse(p.jsonBody):undefined);
    if(req.failAfterAt===current&&!failed){failed=true;throw Error('response lost after remote commit')}
   }else if(n.type.endsWith('.googleDrive')){
    const id=expression(n.parameters.fileId.value);if(!state.files.some(f=>f.id===id))throw Error('share has wrong identity');
    if(req.failAt===current&&!failed){failed=true;throw Error('sharing failed')}
    state.files.find(f=>f.id===id).shared=true;writes.push({name:current,id});output={id:'permission-123',role:'writer',type:'anyone'};
   }else if(n.type.endsWith('.respondToWebhook'))return {response:JSON.parse(expression(n.parameters.responseBody)),trace};
  }catch(e){if(n.onError!=='continueErrorOutput')throw e;branch=1;output={error:{message:e.message,statusCode:e.statusCode}}}
  prior[current]=output;const edges=w.connections[current]?.main?.[branch];if(edges?.length!==1)throw Error('invalid edge '+current);current=edges[0].node;input=output;
 }
 throw Error('never responded');
}
for(const body of req.bodies)runs.push(execute(body));
process.stdout.write(JSON.stringify({runs,state,writes}));
