"""Actual live acceptance run: seekdb + PowerContext + MiniMax + unchanged tests."""
from __future__ import annotations
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from sdd.seekdb_store import SeekDBStore
from sdd.powercontext import PowerContext
from sdd.minimax_client import make_prompt,call_real_minimax,parse_patch,apply_generated_patch

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"evidence"
STATE=ROOT/".local"
CODE=ROOT/"app/shipping.py"
TASK="shipping inclusive free shipping boundary 100"
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def save(name,obj):
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    (EVIDENCE/name).write_text(
        json.dumps(obj,indent=2,ensure_ascii=False,default=str)+"\n",
        encoding="utf-8")
def sha(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()
def command(cmd,stage):
    p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
    data={"command":" ".join(cmd),"exit_code":p.returncode,
          "code_sha256":sha(CODE.read_text(encoding="utf-8")),
          "stdout":p.stdout,"stderr":p.stderr,"timestamp_utc":now()}
    save(stage+".json",data)
    return p

def main():
    if not os.getenv("MINIMAX_API_KEY"):
        raise RuntimeError("Provide actual MINIMAX_API_KEY. Never commit or share the token.")
    STATE.mkdir(exist_ok=True)
    EVIDENCE.mkdir(exist_ok=True)
    CODE.write_text((ROOT/"snapshots/before/shipping.py").read_text(encoding="utf-8"),
                    encoding="utf-8")
    before=CODE.read_text(encoding="utf-8")
    pre_target=command([sys.executable,"-m","unittest","tests.test_target","-v"],"01_before_target")
    pre_reg=command([sys.executable,"-m","unittest","tests.test_regression","-v"],"02_before_regression")
    if pre_target.returncode==0 or "FAIL:" not in pre_target.stderr or "ERROR" in pre_target.stderr:
        raise RuntimeError("Before target failure must be functional assertion failure")
    if pre_reg.returncode!=0:
        raise RuntimeError("Before regression tests must pass")
    scope_id=None
    power=PowerContext(STATE/"powercontext")
    try:
        power.start()
        scope=power.new_scope()
        scope_id=scope["scope_id"]
        initial=power.remember(scope_id,
            "BOUNDARY2026 task opened. Before MiniMax edit: inclusive boundary tests "
            "fail on incorrect quote, regression tests pass.")
        save("03_powercontext_initial_write.json",{"scope":scope,"memory_result":initial,
                                                   "timestamp_utc":now()})
        initial_memory = power.recall(scope_id)
        save("03b_powercontext_initial_recall.json",initial_memory)
        if "BOUNDARY2026" not in json.dumps(initial_memory,ensure_ascii=False):
            raise RuntimeError("PowerContext initial saved state was not readable")
        with SeekDBStore(STATE/"seekdb") as db:
            db.import_project(ROOT)
            context=db.context(TASK)
            save("04_seekdb_context.json",context)
            save("05_seekdb_sql_trace.json",db.sql_log)
            prompt=make_prompt(context, json.dumps(initial_memory,ensure_ascii=False))
            save("06_minimax_prompt.json",{
                "provider":"MiniMax","task":TASK,"source":"seekdb SQL result",
                "prompt":prompt,"timestamp_utc":now()})
            result=call_real_minimax(prompt)
            save("07_minimax_real_response.json",result)
            old,new=parse_patch(result["content"])
            after=apply_generated_patch(before,old,new)
            CODE.write_text(after,encoding="utf-8")
            (ROOT/"snapshots/after").mkdir(parents=True,exist_ok=True)
            (ROOT/"snapshots/after/shipping.py").write_text(after,encoding="utf-8")
            diff="".join(difflib.unified_diff(before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile="snapshots/before/shipping.py",tofile="app/shipping.py"))
            (EVIDENCE/"08_real_minimax_code_diff.patch").write_text(diff,encoding="utf-8")
            post=command([sys.executable,"-m","unittest","discover","-s","tests",
                          "-p","test_*.py","-v"],"09_after_all_tests")
            if post.returncode!=0:
                raise RuntimeError("Generated patch failed unchanged target/regression tests")
            # Verify importing revised spec causes a new live DB query to return it.
            original_spec=(ROOT/"specs/shipping.md").read_text(encoding="utf-8")
            changed=original_spec+"\nSPEC-SHIP-006: Demo spec update evidence tag SDD-UPDATE-2026.\n"
            db.import_doc("spec-current","spec","specs/shipping.md",changed)
            fresh=db.context(TASK)
            spec=next(x["body"] for x in fresh["sources"] if x["path"]=="specs/shipping.md")
            if "SDD-UPDATE-2026" not in spec: raise RuntimeError("Spec reimport ineffective")
            save("10_spec_reimport_query.json",{
                "updated_spec_from_seekdb":spec,
                "has_new_revision":True,"context_source_hashes":[
                  {"path":x["path"],"sha256":x["sha256"]} for x in fresh["sources"]]})
            db.import_doc("spec-current","spec","specs/shipping.md",original_spec)
            db.import_doc("app-shipping","code","app/shipping.py",after)
            save("11_seekdb_final_sql_trace.json",db.sql_log)
        completed=power.remember(scope_id,
            "BOUNDARY2026 completed. MiniMax-M2.5 returned source patch and it was applied. "
            "Target and regression tests are green; current source SHA256 "+sha(after)+".")
        save("12_powercontext_final_write.json",{
            "memory_result":completed,"timestamp_utc":now()})
        power.restart()
        # A distinct Python process reopens the seekdb context module and
        # retrieves actual PowerContext Memory after the Server restart.
        fresh=subprocess.run(
            [sys.executable,"-m","sdd.resume",scope_id],
            cwd=ROOT,capture_output=True,text=True)
        if fresh.returncode!=0:
            raise RuntimeError("Fresh context-module process failed: "+fresh.stderr[-900:])
        resumed=json.loads(fresh.stdout.strip().splitlines()[-1])
        if not resumed.get("state_retrieved_after_server_restart"):
            raise RuntimeError("No persisted task state in fresh module process")
        save("13_powercontext_after_restart.json",resumed)
        save("14_context_reused_after_restart.json",{
            "task":TASK,"separate_context_process_id":resumed["fresh_process_pid"],
            "context_sources":resumed["seekdb_sources_reopened_in_fresh_process"],
            "powercontext_reused_memory":resumed["reused_task_state_preview"],
            "timestamp_utc":now()})
        save("ACCEPTANCE_SUMMARY.json",{
            "timestamp_utc":now(),"before_target_failed_by_assertion":True,
            "before_regression_passed":True,"minimax_real_api_response_recorded":True,
            "actual_seekdb_import_and_sql_used":True,
            "powercontext_memory_read_after_server_restart":True,
            "updated_spec_reimported_and_queried":True,
            "after_all_tests_passed":True,
            "before_sha256":sha(before),"after_sha256":sha(after),
            "scope_id":scope_id,"status":"PASS"})
        print("\nPASS: MiniMax changed code, seekdb queried documents, "
              "PowerContext remembered across restart, target + regressions passed.")
        print("Check minimax/evidence/ then git commit the actual files.")
    finally:
        power.stop()

if __name__=="__main__":
    try: main()
    except Exception as e:
        save("ERROR.json",{"timestamp_utc":now(),"error_type":type(e).__name__,
                          "message":str(e)})
        print("STOP: ",e,file=sys.stderr)
        sys.exit(1)
