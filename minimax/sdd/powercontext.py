"""PowerContext local Server, explicit memory, cross-process continuity."""
import json, os, subprocess, time
from urllib.request import urlopen, Request
from urllib.error import HTTPError

class PowerContext:
    def __init__(self, home, port=18761):
        self.home=home
        self.url="http://127.0.0.1:"+str(port)
        self.port=port
        self.proc=None
        self.log=None
    def start(self):
        self.home.mkdir(parents=True,exist_ok=True)
        env=dict(os.environ)
        env.update(POWERCONTEXT_HOME=str(self.home.resolve()),
                   POWERCONTEXT_SERVER_HTTP_HOST="127.0.0.1",
                   POWERCONTEXT_SERVER_HTTP_PORT=str(self.port),
                   POWERCONTEXT_SERVER_DATABASE_KIND="sqlite",
                   POWERCONTEXT_SERVER_ACCESS_MODE="disabled")
        self.log=(self.home/"server.log").open("ab")
        self.proc=subprocess.Popen(["powercontext","server","run","--no-env-file"],
                                   env=env, stdout=self.log,stderr=subprocess.STDOUT)
        for _ in range(90):
            if self.proc.poll() is not None:
                raise RuntimeError("PowerContext server stopped; see .local/powercontext/server.log")
            try:
                with urlopen(self.url+"/health/ready",timeout=2) as response:
                    if response.status==200: return
            except Exception: pass
            time.sleep(1)
        raise TimeoutError("PowerContext could not become healthy")
    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=12)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if self.log: self.log.close()
        self.proc=None
        self.log=None
    def restart(self):
        self.stop()
        self.start()
    def post(self,path,data):
        req=Request(self.url+path,data=json.dumps(data,ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type":"application/json"},method="POST")
        try:
            with urlopen(req,timeout=45) as response: return json.load(response)
        except HTTPError as e:
            raise RuntimeError(f"PowerContext {path} HTTP {e.code}: "+e.read().decode("utf-8","replace")[:600])
    def new_scope(self):
        result=self.post("/v1/scopes",{
            "title":"MiniMax SDD shipping task",
            "summary":"Task continuity for code change acceptance",
            "idempotency_key":"minimax-shipping-sdd-2026"})
        assert result.get("scope_id"),"No scope_id from PowerContext"
        return result
    def remember(self,sid,detail):
        result=self.post("/v1/memory/remember",{
            "scope_id":sid,"kind":"decision","text":detail,
            "reason":"Actual verification result and task progress"})
        assert result.get("records"),"Memory write did not return records"
        return result
    def recall(self,sid):
        return self.post("/v1/memory/search",{
            "scope_id":sid,"query":"BOUNDARY2026","limit":15})
    def prepare(self,sid):
        return self.post("/v1/context/prepare",{
            "scope_id":sid,"query":"BOUNDARY2026","max_bytes":4000})
