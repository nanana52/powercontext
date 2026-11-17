"""Public game entrypoint; Dify app keys remain in a private server config."""
from __future__ import annotations
import asyncio,json,os
from pathlib import Path
import httpx
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel,Field
ROOT=Path(__file__).resolve().parent
CONFIG=Path(os.environ.get("DREAM_DEMO_CONFIG",ROOT/".runtime/demo_private.json"))
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
gate=asyncio.Semaphore(1)
class Play(BaseModel):
    player_name:str=Field(min_length=1,max_length=32)
    lost_item:str=Field(min_length=1,max_length=250)
    action:str=Field(min_length=1,max_length=200)
@app.get("/",response_class=HTMLResponse)
async def home():return (ROOT/"index.html").read_text("utf-8")
@app.get("/health")
async def health():return {"status":"ok","workflow":"Dify","memory":"PowerContext","generation":"Qwen local"}
@app.post("/api/play")
async def play(body:Play,request:Request):
    origin=request.headers.get("origin")
    if origin and origin.rstrip("/")!=str(request.base_url).rstrip("/"):
        raise HTTPException(403,"Origin mismatch")
    if gate.locked():raise HTTPException(429,"The game is serving another turn. Please try again shortly.")
    async with gate:
        cfg=json.loads(CONFIG.read_text())
        async with httpx.AsyncClient(timeout=180) as client:
            result=await client.post(cfg["api_url"].rstrip("/")+"/v1/workflows/run",
                headers={"Authorization":"Bearer "+cfg["app_key"]},
                json={"inputs":body.model_dump(),"response_mode":"blocking","user":"dream-public-demo"})
        if result.status_code!=200:raise HTTPException(502,"Dify workflow request failed")
        document=result.json();data=document.get("data",{})
        if data.get("status")!="succeeded":raise HTTPException(502,"Dify workflow did not complete")
        out=data.get("outputs",{})
        return {k:out[k] for k in ["result","memory_saved","previous_memory_loaded"]}|{"workflow_run_id":document.get("workflow_run_id",data.get("id",""))}
