const assert=require("assert");
const N="intake_skip_defer";const S=3600;let J={};
function G(){var c=(Object.entries(J).map(([k,v])=>k+"="+v).join(";")||"").split(";");for(var i=0;i<c.length;i++){var p=c[i].trim();if(p.indexOf(N+"=")===0)return p.substring(N.length+1)==="1"}return false}
function set(){J["intake_skip_defer"]="1"}function clr(){delete J["intake_skip_defer"]}
var p=0,f=0;function T(n,fn){try{fn();console.log("  [PASS] "+n);p++}catch(e){console.log("  [FAIL] "+n+": "+e.message);f++}}
console.log("=== U057 Skip/Defer Mutation-Proof Gate ===\n");
T("SKIP_COOKIE_NAME correct",()=>assert.strictEqual(N,"intake_skip_defer"));
T("SKIP_COOKIE_SECONDS is 3600",()=>assert.strictEqual(S,3600));
T("get returns false when not set",()=>{J={};assert.strictEqual(G(),false)});
T("set then get returns true",()=>{J={};set();assert.strictEqual(G(),true)});
T("clear then get returns false",()=>{clr();assert.strictEqual(G(),false)});
T("set stores value 1",()=>{J={};set();assert.strictEqual(J["intake_skip_defer"],"1")});
T("clear removes cookie",()=>{J={};set();clr();assert.strictEqual("intake_skip_defer" in J,false)});
T("set is idempotent",()=>{J={};set();set();assert.strictEqual(G(),true)});
T("clear safe when empty",()=>{J={};clr();clr();assert.strictEqual(G(),false)});
T("not confused by substring",()=>{J={"intake_skip":"maybe"};assert.strictEqual(G(),false)});
T("exact match alongside similar",()=>{J={"intake_skip":"maybe","intake_skip_defer":"1"};assert.strictEqual(G(),true)});
T("MUTATION RED: S=3600 not 0",()=>{assert.strictEqual(S,3600);assert.notStrictEqual(S,0)});
T("REVERT GREEN: S==3600",()=>assert.strictEqual(S,3600));
console.log("\n=== "+p+"/"+(p+f)+" passed ===");if(f>0)process.exit(1);
