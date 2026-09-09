const src=$('Validate + Build Provisioning Key').first().json;
const response=$input.first().json;
if (!Array.isArray(response.files)) throw new Error('Malformed Drive readback');
if (response.nextPageToken || response.files.length>1) throw new Error('Ambiguous provisioning identity; reconcile registry before retry');
const existingFile=response.files[0] || null;
if (existingFile) {
  const p=existingFile.appProperties || {};
  if (!existingFile.id || p.skill35_company_id!==src.company_id || p.skill35_provisioning_key!==src.provisioningKey)
    throw new Error('Existing planner ownership is unverified; migrate from verified registry before retry');
  if (!['initializing','formatted','ready'].includes(p.skill35_provisioning_state)) throw new Error('Existing planner state requires verified migration');
  if (p.skill35_template_schema!=='1.2.0') throw new Error('Existing planner schema requires a preserving migration');
}
return [{json:{...src,existing:!!existingFile,existingFile}}];
