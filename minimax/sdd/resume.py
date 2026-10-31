"""Independent fresh process: reopen seekdb and query persisted PowerContext task memory."""
import json, os, sys
from pathlib import Path
from sdd.seekdb_store import SeekDBStore
from sdd.powercontext import PowerContext

ROOT=Path(__file__).resolve().parents[1]
def main():
    if len(sys.argv)!=2: raise SystemExit("Usage: python -m sdd.resume <real-scope-id>")
    scope_id=sys.argv[1]
    pc=PowerContext(ROOT/".local/powercontext")
    memory=pc.recall(scope_id)
    raw=json.dumps(memory,ensure_ascii=False)
    if "BOUNDARY2026" not in raw:
        raise RuntimeError("Restarted module did not find PowerContext task state")
    prepared=pc.prepare(scope_id)
    with SeekDBStore(ROOT/".local/seekdb") as db:
        context=db.context("shipping inclusive free shipping boundary 100")
        paths=[x["path"] for x in context["sources"]]
    result={"fresh_process_pid":os.getpid(),"scope_id":scope_id,
            "state_retrieved_after_server_restart":True,
            "seekdb_sources_reopened_in_fresh_process":paths,
            "recalled_memory_result":memory,
            "prepared_context":prepared,
            "reused_task_state_preview":raw[:2000]}
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__": main()
