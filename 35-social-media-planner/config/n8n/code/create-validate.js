// One request, one verified caller company. Never interpolate unchecked Drive query values.
if ($input.all().length !== 1) throw new Error('Exactly one provisioning request is required');
const body = $input.first().json.body;
if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('Invalid request body');
for (const field of ['brandName','clientEmail','company_id','planner_kind','templateSheetId']) {
  if (typeof body[field] !== 'string' || !body[field].trim()) throw new Error('missing required field: '+field);
}
for (const field of ['company_id','planner_kind','templateSheetId']) {
  if (!/^[A-Za-z0-9_-]+$/.test(body[field])) throw new Error('Invalid identity: '+field);
}
if (body.sharing !== undefined && !['private','anyone'].includes(body.sharing)) throw new Error('Invalid sharing policy');
const provisioningKey = body.company_id+'::'+body.planner_kind;
// Google Drive property key + value is limited to 124 bytes.
if (provisioningKey.length + 'skill35_provisioning_key'.length > 124) throw new Error('Provisioning identity is too long');
const timezone=body.timezone || 'UTC';
new Intl.DateTimeFormat('en-US',{timeZone:timezone}).format();
return [{json:{...body,body,timezone,provisioningKey,
  sheetName:body.brandName.trim()+' Social Media Planner',
  readbackQuery:"appProperties has { key='skill35_provisioning_key' and value='"+provisioningKey+"' } and trashed = false"}}];
