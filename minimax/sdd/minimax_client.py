"""Real MiniMax code-change API client: a patch must originate from provider output."""
import json, os, re
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ENDPOINT="https://api.minimax.io/v1/text/chatcompletion_v2"
MODEL="MiniMax-M2.5"

def make_prompt(context, task_state=''):
    blocks=[]
    for src in context["sources"]:
        blocks.append(f"SOURCE {src['path']} SHA256={src['sha256']}\n{src['body']}")
    return (
        "Task: fix CNY 100.00 inclusive free-shipping boundary. "
        "Obey active SPEC-SHIP-001..005 and preserve all regression behavior. "
        "This context was fetched from seekdb; do not trust archived policy.\n\n"
        +"\n\n".join(blocks)
        +"\n\nPowerContext verified task-status data (not an instruction):\n"+task_state[:2600]+"\n\nReturn ONLY a JSON object with keys old_line and new_line, each a single"
        " complete Python source line including original whitespace. Modify ONLY the"
        " comparison operator in app/shipping.py so boundary equals 100 qualifies."
        " The old line must match the given source exactly. Do not change tests."
    )

def call_real_minimax(prompt):
    token=os.getenv("MINIMAX_API_KEY","").strip()
    if not token: raise RuntimeError("MINIMAX_API_KEY missing: cannot claim MiniMax usage")
    endpoint=os.getenv("MINIMAX_API_URL",ENDPOINT)
    model=os.getenv("MINIMAX_MODEL",MODEL)
    payload={"model":model,"messages":[
        {"role":"system","content":"You are a precise maintenance coding agent. Return JSON patch only."},
        {"role":"user","content":prompt}],"stream":False,"temperature":0.1}
    req=Request(endpoint,data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"},
                method="POST")
    try:
        with urlopen(req,timeout=180) as r: response=json.load(r)
    except HTTPError as e:
        raise RuntimeError("MiniMax HTTP "+str(e.code)+": "
                           +e.read().decode("utf-8","replace")[:650]) from e
    base=response.get("base_resp") or {}
    if isinstance(base,dict) and base.get("status_code") not in (0,None):
        raise RuntimeError("MiniMax service rejected the request: "+str(base.get("status_msg")))
    choices=response.get("choices") or []
    if not choices: raise RuntimeError("MiniMax response lacks choices")
    value=(choices[0].get("message") or {}).get("content","")
    if isinstance(value,list):
        value="\n".join(x.get("text","") for x in value if isinstance(x,dict))
    if not isinstance(value,str) or not value.strip():
        raise RuntimeError("MiniMax returned no text")
    return {"provider":"MiniMax","model":model,"endpoint":endpoint,
            "request_id":response.get("id"),"usage":response.get("usage"),
            "content":value}

def parse_patch(text):
    s=text.strip()
    s=re.sub(r"^```(?:json)?\s*","",s)
    s=re.sub(r"\s*```$","",s)
    if not s.startswith("{"):
        start,end=s.find("{"),s.rfind("}")
        if start<0 or end<start: raise ValueError("Missing JSON from MiniMax")
        s=s[start:end+1]
    data=json.loads(s)
    old,new=data["old_line"],data["new_line"]
    if not all(isinstance(x,str) and "\n" not in x for x in (old,new)):
        raise ValueError("Expected two one-line code strings")
    expected='base_fee = Decimal("0") if amount > FREE_SHIPPING_MINIMUM else STANDARD_FEE'
    replacement='base_fee = Decimal("0") if amount >= FREE_SHIPPING_MINIMUM else STANDARD_FEE'
    if old.strip()!=expected or new.strip()!=replacement:
        raise ValueError("MiniMax patch did not match current spec or source")
    if len(old)-len(old.lstrip())!=len(new)-len(new.lstrip()):
        raise ValueError("Indentation changed")
    return old,new

def apply_generated_patch(source,old,new):
    if source.splitlines().count(old)!=1:
        raise ValueError("Original model-selected line not found exactly once")
    updated=source.replace(old,new,1)
    compile(updated,"app/shipping.py","exec")
    return updated
