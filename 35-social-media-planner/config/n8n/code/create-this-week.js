const numeric=$('Build Formatting Requests (F25)').first().json.numeric;
const ctx=$('Sheet Context').first().json;
const id=numeric['This Week'];
const identityStamps=[];
[110,190,300,130,130,130,130,160].forEach((pixelSize,i)=>identityStamps.push({updateDimensionProperties:{range:{sheetId:id,dimension:'COLUMNS',startIndex:i,endIndex:i+1},properties:{pixelSize},fields:'pixelSize'}}));
// Summary is restricted to the current local week; no invented completion counts.
const week='=TODAY()-WEEKDAY(TODAY(),2)+1';
const count=(field,state)=>`SUMPRODUCT((LOWER(Posts!${field}:${field})="${state.toLowerCase()}")*(LEFT(Posts!I:I,10)>=TEXT(A2,"yyyy-mm-dd"))*(LEFT(Posts!I:I,10)<TEXT(A2+7,"yyyy-mm-dd")))`;

const values=[{formulaValue:week},{stringValue:ctx.brandName},{formulaValue:'=IF(H2>0,"Review items needing attention",IF(SUM(D2:G2)=0,"Choose this week’s theme","Review progress and approvals"))'},
 {formulaValue:'='+count('K','draft')+'+'+count('K','drafting')},
 {formulaValue:'='+count('L','qc_pending')+'+'+count('L','qc_review')+'+'+count('L','QC Review')},
 {formulaValue:'='+count('K','scheduled')},{formulaValue:'='+count('K','published')},
 {formulaValue:'='+count('K','failed')+'+'+count('K','blocked')+'+'+count('K','needs_attention')}];
identityStamps.push({updateCells:{start:{sheetId:id,rowIndex:1,columnIndex:0},rows:[{values:values.map(userEnteredValue=>({userEnteredValue}))}],fields:'userEnteredValue'}});
identityStamps.push({repeatCell:{range:{sheetId:id,startRowIndex:1,endRowIndex:2,startColumnIndex:0,endColumnIndex:1},cell:{userEnteredFormat:{numberFormat:{type:'DATE',pattern:'mmm d, yyyy'}}},fields:'userEnteredFormat.numberFormat'}});
return [{json:{identityStamps,thisWeekCreated:true}}];
