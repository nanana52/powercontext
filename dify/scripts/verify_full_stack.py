"""Create a private local Dify app, import its DSL and verify real memory reuse."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
INNER = r'''
import hashlib,json,secrets,time,urllib.request,yaml
from pathlib import Path
from app import app
from extensions.ext_database import db
from extensions.ext_application_services import application_services
from services.account.contracts import SetupInput
config=json.loads(CONFIG)
report_dir=Path("/tmp/dream-full-validation")
report_dir.mkdir(exist_ok=True)
with app.app_context():
 services=application_services()
 if not services.setup.get_status().completed:
  services.setup.initialize(
   SetupInput(email="local-owner@dream.invalid",name="Local Dream Owner",
              password=config["owner_password"],ip_address="127.0.0.1",language="zh-Hans"),
   initialization_validated=True)
 from models.account import Account,Tenant
 from models.model import App,ApiToken
 from services.app_dsl_service import AppDslService
 from services.workflow_service import WorkflowService
 account=db.session.query(Account).first()
 tenant=db.session.query(Tenant).first()
 if account is None or tenant is None:raise RuntimeError("Dify owner initialization failed")
 account.set_current_tenant_with_session(tenant,session=db.session)
 document=yaml.safe_load(Path("/tmp/dream-input-dsl.yml").read_text())
 for variable in document["workflow"]["environment_variables"]:
  if variable["name"]=="POWERCONTEXT_BASE_URL":variable["value"]=config["backend_url"]
  if variable["name"]=="POWERCONTEXT_TOKEN":variable["value"]=config["backend_token"]
 imported=AppDslService(db.session).import_app(
  account=account,import_mode="yaml-content",
  yaml_content=yaml.safe_dump(document,allow_unicode=True),name="Dream local reproducible validation")
 if imported.status!="completed":raise RuntimeError("Dify DSL import failed: "+str(imported.model_dump()))
 model=db.session.get(App,imported.app_id)
 model.enable_api=True;model.enable_site=True
 published=WorkflowService().publish_workflow(
  session=db.session,app_model=model,account=account,marked_name="Local two-turn acceptance")
 model.workflow_id=published.id
 api_key=ApiToken.generate_api_key("app-",32,session=db.session)
 db.session.add(ApiToken(app_id=model.id,tenant_id=tenant.id,type="app",token=api_key))
 db.session.commit()
 app_id=model.id
player="verified-"+str(time.time_ns())
turns=[]
for turn,action in [(1,"\u7ed9\u96e8\u4f1e\u5199\u4e00\u5c01\u9053\u6b49\u4fe1"),(2,"\u8be2\u95ee\u67dc\u5458\u4e0a\u6b21\u767b\u8bb0\u4e86\u4ec0\u4e48")]:
 body={"inputs":{"player_name":player,"lost_item":"\u4f1a\u8bf4\u8bdd\u7684\u84dd\u96e8\u4f1e","action":action},
       "response_mode":"blocking","user":"reproducible-local-acceptance"}
 request=urllib.request.Request("http://127.0.0.1:5001/v1/workflows/run",
  data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"})
 result=json.load(urllib.request.urlopen(request,timeout=180))
 data=result.get("data",{})
 if data.get("status")!="succeeded":raise RuntimeError("Workflow failed: "+str(data.get("error")))
 outputs=data["outputs"]
 assert outputs["memory_saved"]=="\u662f",outputs
 assert outputs["previous_memory_loaded"]==("\u5426" if turn==1 else "\u662f"),outputs
 (report_dir/("turn"+str(turn)+".json")).write_text(json.dumps(result,ensure_ascii=False,indent=2))
 turns.append({"turn":turn,"status":data["status"],"memory_saved":True,"loaded_previous":turn==2})
def backend_call(path,payload):
 request=urllib.request.Request(config["backend_url"]+path,data=json.dumps(payload).encode(),
  headers={"Authorization":"Bearer "+config["backend_token"],"Content-Type":"application/json"})
 return json.load(urllib.request.urlopen(request,timeout=30))
scope=backend_call("/v1/scopes",{"title":"verification","idempotency_key":
 "lostfound-"+hashlib.sha256(("dream-lostfound-v1:"+player).encode()).hexdigest()})["scope_id"]
memory=backend_call("/v1/context/prepare",{"scope_id":scope})
assert memory["previous_memory_loaded"] and len(memory["memories"])==2,memory
report={"status":"PASS","app_id":app_id,"player":player,"turns":turns,
        "memory_count":len(memory["memories"]),"memory_ref":memory["memory_ref"],
        "scope_id":scope,"backend_url":config["backend_url"],"source":"real Dify workflow API, real local model and PowerContext"}
(report_dir/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
'''
def command(args, **kwargs):
    result = subprocess.run(args, check=False, **kwargs)
    if result.returncode:
        if result.stderr: print(result.stderr.decode('utf-8', errors='replace')[-7000:], file=sys.stderr)
        raise RuntimeError('Validation subprocess failed: '+str(result.returncode))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing-deployment",action="store_true",
                        help="Use this project's already prepared .runtime/dify deployment")
    args=parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    if not args.existing_deployment:
        command(["bash",str(ROOT/"start_backend.sh")],cwd=ROOT)
        command([sys.executable,str(ROOT/"scripts/setup_dify.py")],cwd=ROOT)
    compose=RUNTIME/"dify/compose.resolved.json"
    if not compose.exists():raise RuntimeError("Run scripts/setup_dify.py first")
    base=["docker","compose","-f",str(compose)]
    container=subprocess.check_output(base+["ps","-q","api"],text=True).strip()
    if not container:raise RuntimeError("Dify API is not running")
    private=RUNTIME/"owner.json"
    if private.exists():owner=json.loads(private.read_text())
    else:
        import secrets
        owner={"email":"local-owner@dream.invalid","password":secrets.token_urlsafe(24)+"aA1"}
        private.write_text(json.dumps(owner));private.chmod(0o600)
    command(["docker","cp",str(ROOT/"app.yml"),container+":/tmp/dream-input-dsl.yml"],
            stdout=subprocess.DEVNULL)
    config={"backend_url":os.environ.get("DREAM_DIFY_BACKEND_URL",
             "http://172.17.0.1:"+os.environ.get("DREAM_BACKEND_PORT","18090")),
            "backend_token":(RUNTIME/"access.token").read_text().strip(),"owner_password":owner["password"]}
    source=INNER.replace("CONFIG",repr(json.dumps(config)))
    # Secrets stay in memory and this process's stdin, never command arguments or output.
    result=command(["docker","exec","-i",container,"/app/api/.venv/bin/python","-"],
                   input=source.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    evidence=RUNTIME/"validation";evidence.mkdir(exist_ok=True)
    for name in ["turn1.json","turn2.json","report.json"]:
        command(["docker","cp",container+":/tmp/dream-full-validation/"+name,str(evidence/name)],
                stdout=subprocess.DEVNULL)
    report=json.loads((evidence/"report.json").read_text())
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print("DIFY_FULL_STACK_ACCEPTANCE_PASS")
    print("Private administrator credentials:",private)
    print("Workflow evidence:",evidence)
if __name__=="__main__":
    main()
