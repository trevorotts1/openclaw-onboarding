// Run ONLY on a privately initializing copy, never a ready client planner.
const ctx=$('Sheet Context').first().json;
if(ctx.formatted) throw new Error('Refusing to reset an existing ready planner');
const metadata=$input.first().json;
const templates=SCHEMA.tabs;
const current=metadata.sheets || [];
const ids=new Set(current.map(s=>s.properties.sheetId));
const byTitle=Object.fromEntries(current.map(s=>[s.properties.title,s]));
const numeric={}; const newSheetRequests=[]; const formatRequests=[];
const order=['This Week','Weekly Overview','Posts','Images','Videos'];
let nextId=1;
for(const title of order){
  const existing=byTitle[title];
  while(ids.has(nextId))nextId++;
  const id=existing ? existing.properties.sheetId : nextId++;
  ids.add(id); numeric[title]=id;
  const columns=title==='Images'?16:title==='Videos'?19:title==='Weekly Overview'?21:templates[title].headings.length;
  if(!existing)newSheetRequests.push({addSheet:{properties:{sheetId:id,title,gridProperties:{rowCount:1000,columnCount:columns}}}});
  const grid=existing?.properties.gridProperties || {};
  formatRequests.push({updateSheetProperties:{properties:{sheetId:id,index:order.indexOf(title),gridProperties:{frozenRowCount:1,frozenColumnCount:templates[title].frozen_columns||0,rowCount:Math.max(grid.rowCount||0,1000),columnCount:Math.max(grid.columnCount||0,columns)}},fields:'index,gridProperties'}});
  // Template content (including sample publication claims) is never client content.
  formatRequests.push({updateCells:{range:{sheetId:id},fields:'userEnteredValue,note,dataValidation'}});
  for(let i=(existing?.conditionalFormats||[]).length-1;i>=0;i--)formatRequests.push({deleteConditionalFormatRule:{sheetId:id,index:i}});
  const headings=[...templates[title].headings];
  if(title==='Weekly Overview')headings[20]='cycle_id';
  if(title==='Images')headings[15]='Image preview';
  if(title==='Videos'){headings[17]='Video poster';headings[18]='Watch video';}
  formatRequests.push({updateCells:{start:{sheetId:id,rowIndex:0,columnIndex:0},rows:[{values:Array.from(headings,h=>({userEnteredValue:{stringValue:h||''}}))}],fields:'userEnteredValue'}});
  formatRequests.push({repeatCell:{range:{sheetId:id},cell:{userEnteredFormat:{wrapStrategy:'WRAP',verticalAlignment:'TOP'}},fields:'userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment'}});
  formatRequests.push({repeatCell:{range:{sheetId:id,startRowIndex:0,endRowIndex:1},cell:{userEnteredFormat:{backgroundColor:{red:.10,green:.16,blue:.25},textFormat:{bold:true,foregroundColor:{red:1,green:1,blue:1}}}},fields:'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat'}});
  formatRequests.push({updateDimensionProperties:{range:{sheetId:id,dimension:'ROWS',startIndex:0,endIndex:1},properties:{pixelSize:44},fields:'pixelSize'}});
  formatRequests.push({updateDimensionProperties:{range:{sheetId:id,dimension:'COLUMNS',startIndex:0,endIndex:columns},properties:{pixelSize:170},fields:'pixelSize'}});
  // Strict dropdowns apply only to status cells, never captions, dates or URLs.
  for(const column of templates[title].status_columns || []){
    // QC overview is a multi-account textual aggregate, not an enum.
    if(title==='Weekly Overview' && column==='QC')continue;
    const col=templates[title].headings.indexOf(column);
    const range={sheetId:id,startRowIndex:1,startColumnIndex:col,endColumnIndex:col+1};
    const statusValues=SCHEMA.status_colors.statuses.map(s=>s.label);
    const runtime=['PASS','FAIL','PENDING','IN_REVIEW','SKIP','draft','drafting','pending','queued','working','qc_pending','qc_review','approved','passed','rejected','scheduled','published','failed','blocked','needs_attention','skipped','complete','completed','cancelled'];
    const labels=[...new Set([...statusValues,...runtime])];
    formatRequests.push({setDataValidation:{range,rule:{condition:{type:'ONE_OF_LIST',values:labels.map(s=>({userEnteredValue:s}))},showCustomUi:true,strict:true}}});
    for(const label of labels){
      const st=SCHEMA.status_colors.statuses.find(s=>s.label.toLowerCase()===label.toLowerCase()) || SCHEMA.status_colors.statuses[2];
      const hex=st.color.slice(1);const color={red:parseInt(hex.slice(0,2),16)/255,green:parseInt(hex.slice(2,4),16)/255,blue:parseInt(hex.slice(4,6),16)/255};
      formatRequests.push({addConditionalFormatRule:{rule:{ranges:[range],booleanRule:{condition:{type:'TEXT_EQ',values:[{userEnteredValue:label}]},format:{backgroundColor:color}}},index:0}});
    }
  }
  const formulaCols=title==='Images'?[15]:title==='Videos'?[17,18]:title==='This Week'?[0,2,3,4,5,6,7]:[];
  for(const col of formulaCols){
    const description='skill35 trusted formula '+title+' '+col;
    if(!(existing?.protectedRanges||[]).some(r=>r.description===description))formatRequests.push({addProtectedRange:{protectedRange:{description,range:{sheetId:id,startRowIndex:1,startColumnIndex:col,endColumnIndex:col+1},warningOnly:false}}});
  }
  if(title==='Images' || title==='Videos'){
    const col=title==='Images'?15:17;
    formatRequests.push({updateDimensionProperties:{range:{sheetId:id,dimension:'COLUMNS',startIndex:col,endIndex:col+1},properties:{pixelSize:title==='Images'?220:240},fields:'pixelSize'}});
  }
}
for(const sheet of current){
  if(!order.includes(sheet.properties.title))formatRequests.push({deleteSheet:{sheetId:sheet.properties.sheetId}});
}
formatRequests.push({updateSpreadsheetProperties:{properties:{title:ctx.sheetName,timeZone:ctx.timezone},fields:'title,timeZone'}});
// Required for IMAGE previews; set only while false (true is read-only).
if(metadata.properties?.importFunctionsExternalUrlAccessAllowed!==true)formatRequests.push({updateSpreadsheetProperties:{properties:{importFunctionsExternalUrlAccessAllowed:true},fields:'importFunctionsExternalUrlAccessAllowed'}});
for(const [key,value] of Object.entries({skill35_company_id:ctx.company_id,skill35_planner_kind:ctx.planner_kind,skill35_template_schema:'1.2.0'})){
  const entries=(metadata.developerMetadata||[]).filter(m=>m.metadataKey===key);
  for(const entry of entries)formatRequests.push({deleteDeveloperMetadata:{dataFilter:{developerMetadataLookup:{metadataId:entry.metadataId}}}});
  formatRequests.push({createDeveloperMetadata:{developerMetadata:{metadataKey:key,metadataValue:value,location:{spreadsheet:true},visibility:'DOCUMENT'}}});
}
return [{json:{newSheetRequests,formatRequests,numeric,statuses:SCHEMA.status_colors.statuses.map(s=>s.label)}}];
