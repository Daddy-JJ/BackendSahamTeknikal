// Execute the existing frontend dev probe with injected RPC errors; frontend is read-only.
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";

const source=readFileSync(new URL("../../../frontend/src/app/auth/check/actions.ts",import.meta.url),"utf8");
const body=source.slice(source.indexOf("export async function verifyDevOwnerAction()"))
  .replace("export async function","async function");
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
for(const code of ["PT412","23514"]) {
  test(`existing frontend signal probe handles ${code} as failure without retry or success`,async () => {
    const calls=[];
    const query={select(){return this;},eq(){return this;},order(){return this;},limit(){return this;},
      single:async()=>({data:{data_mode:"fixture"}}),
      maybeSingle:async()=>({data:{id:"a".repeat(64),role:"owner",enabled:true}})};
    const supabase={auth:{getUser:async()=>({data:{user:{id:"owner"}}})},from:()=>query,
      rpc:async(name,request)=>{calls.push({name,request});return {error:{code,message:"revision_conflict"},data:null};}};
    const run=new AsyncFunction("redirect","createClient","publicSupabaseConfig","DEV_PROJECT_URL",
      "DEV_FIXTURE_NAMESPACE","DEV_OWNER_ACTION_REQUEST_ID",body+"\nreturn verifyDevOwnerAction();");
    await assert.rejects(()=>run(url=>{throw new Error(url);},async()=>supabase,
      ()=>({url:"dev"}),"dev","fixture","request"),/\/auth\/check\?probe=failed/);
    assert.equal(calls.length,1);
    assert.equal(calls[0].name,"set_signal_action");
    assert.deepEqual(Object.keys(calls[0].request).sort(),
      ["p_action","p_expected_revision","p_request_id","p_signal_id"]);
  });
}
