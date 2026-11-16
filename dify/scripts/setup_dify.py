"""Create an isolated Dify 1.18.0 deployment using the delivered upstream configuration."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "deployment/upstream_docker"
RUNTIME = ROOT / ".runtime/dify"
DEPLOYMENT = RUNTIME / "deployment"
PROJECT = os.environ.get("DREAM_DIFY_PROJECT", "dream-lostfound")
API_PORT = os.environ.get("DREAM_DIFY_API_PORT", "15001")
WEB_PORT = os.environ.get("DREAM_DIFY_WEB_PORT", "13000")
HTTP_PORT = os.environ.get("DREAM_DIFY_HTTP_PORT", "18080")
SELECTED = {"init_permissions", "api", "worker", "worker_beat", "redis", "db_postgres", "sandbox",
            "ssrf_proxy", "plugin_daemon", "qdrant", "web", "nginx"}
RUNTIME.mkdir(parents=True, exist_ok=True)
# Service env_file paths are relative to the Compose YAML. Keep its private
# environment beside a runtime copy, never in delivered source files.
shutil.copytree(SOURCE, DEPLOYMENT, dirs_exist_ok=True)
environment_path = DEPLOYMENT / ".env"
if not environment_path.exists():
    values = {
        "DB_TYPE":"postgresql", "VECTOR_STORE":"qdrant",
        "COMPOSE_PROFILES":"qdrant,postgresql",
        "SECRET_KEY":secrets.token_urlsafe(48), "DB_PASSWORD":secrets.token_urlsafe(24),
        "REDIS_PASSWORD":secrets.token_urlsafe(24), "SANDBOX_API_KEY":secrets.token_urlsafe(32),
        "PLUGIN_DAEMON_KEY":secrets.token_urlsafe(32),
        "PLUGIN_DIFY_INNER_API_KEY":secrets.token_urlsafe(32),
        "EXPOSE_NGINX_PORT":"18080", "EXPOSE_NGINX_SSL_PORT":"18443",
        "SSRF_PROXY_ALLOW_PRIVATE_IPS":"172.17.0.1/32",
    }
    base = (SOURCE / ".env.example").read_text(encoding="utf-8")
    lines = []
    used = set()
    for line in base.splitlines():
        key = line.split("=",1)[0] if "=" in line and not line.lstrip().startswith("#") else ""
        if key in values:
            lines.append(key+"="+values[key])
            used.add(key)
        else:
            lines.append(line)
    lines.extend(key+"="+value for key,value in values.items() if key not in used)
    environment_path.write_text("\n".join(lines)+"\n",encoding="utf-8")
    environment_path.chmod(0o600)
# The API client and sandbox must authenticate with the same generated key.
env_lines = environment_path.read_text(encoding="utf-8").splitlines()
sandbox_key = next(line.split("=", 1)[1] for line in env_lines if line.startswith("SANDBOX_API_KEY="))
redis_key = next(line.split("=", 1)[1] for line in env_lines if line.startswith("REDIS_PASSWORD="))
coordinated = {
    "CODE_EXECUTION_API_KEY": sandbox_key,
    "CELERY_BROKER_URL": "redis://:"+redis_key+"@redis:6379/1",
    "COMPOSE_WORKER_HEALTHCHECK_DISABLED": "false",
}
env_lines = [line for line in env_lines if line.split("=", 1)[0] not in coordinated]
env_lines.extend(key+"="+value for key, value in coordinated.items())
environment_path.write_text("\n".join(env_lines)+"\n", encoding="utf-8")
sandbox_conf = RUNTIME / "volumes/sandbox/conf"
sandbox_conf.mkdir(parents=True, exist_ok=True)
sandbox_template = (ROOT / "deployment/sandbox/config.yaml").read_text(encoding="utf-8")
sandbox_path = sandbox_conf / "config.yaml"
sandbox_path.write_text(sandbox_template.replace("key: dify-sandbox", "key: "+sandbox_key), encoding="utf-8")
sandbox_path.chmod(0o600)
base = ["docker","compose","--project-name",PROJECT,
        "--env-file",str(environment_path),"-f",str(DEPLOYMENT/"docker-compose.yaml")]
configuration = json.loads(subprocess.check_output(base+["config","--format","json"],cwd=DEPLOYMENT))
services = {}
for name in SELECTED:
    service = configuration["services"][name]
    service.pop("profiles",None)
    service["depends_on"] = {key:value for key,value in service.get("depends_on",{}).items()
                             if key in SELECTED}
    if not service["depends_on"]:
        service.pop("depends_on")
    for volume in service.get("volumes",[]):
        if volume.get("type")=="bind" and "/volumes/" in volume.get("source",""):
            suffix=volume["source"].split("/volumes/",1)[1]
            destination=RUNTIME/"volumes"/suffix
            destination.mkdir(parents=True,exist_ok=True)
            volume["source"]=str(destination)
    if name in {"api","worker","ssrf_proxy"}:
        service.setdefault("environment",{})["SSRF_PROXY_ALLOW_PRIVATE_IPS"]="172.17.0.1/32"
    if name=="api":
        service["ports"]=[{"target":5001,"published":API_PORT,"host_ip":"127.0.0.1","protocol":"tcp"}]
    elif name=="web":
        service["ports"]=[{"target":3000,"published":WEB_PORT,"host_ip":"127.0.0.1","protocol":"tcp"}]
    elif name=="nginx":
        service["ports"]=[{"target":80,"published":HTTP_PORT,"host_ip":"127.0.0.1","protocol":"tcp"}]
    else:
        service.pop("ports",None)
    services[name]=service
configuration["services"]=services
configuration["name"]=PROJECT
resolved=RUNTIME/"compose.resolved.json"
resolved.write_text(json.dumps(configuration),encoding="utf-8")
resolved.chmod(0o600)
subprocess.run(["docker","compose","-f",str(resolved),"up","-d","--wait","--wait-timeout","180"],check=True)
print("Dify: http://127.0.0.1:"+HTTP_PORT+"/install")
print("Initialize your own administrator account, then import dsl/dream-lostfound.yml.")
