const src=$('Interpret Readback').first().json;
const file=src.existing ? src.existingFile : $input.first().json;
const p=file.appProperties || {};
if (typeof file.id!=='string' || !/^[A-Za-z0-9_-]+$/.test(file.id) || p.skill35_company_id!==src.company_id || p.skill35_provisioning_key!==src.provisioningKey)
  throw new Error('Drive copy/readback did not prove this company owns the planner');
return [{json:{...src,sheetId:file.id,sheetName:file.name || src.sheetName,deduped:src.existing,
  ready:p.skill35_provisioning_state==='ready',formatted:['formatted','ready'].includes(p.skill35_provisioning_state)}}];
