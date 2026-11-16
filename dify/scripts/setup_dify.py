"""Create an isolated Dify 1.18.0 deployment using the delivered upstream configuration."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "deployment/upstream_docker"
RUNTIME = ROOT / ".runtime/dify"
SELECTED = {"api", "worker", "worker_beat", "redis", "db_postgres", "sandbox",
            "ssrf_proxy", "plugin_daemon", "qdrant", "web", "nginx"}
RUNTIME.mkdir(parents=True, exist_ok=True)
environment_path = RUNTIME / ".env"
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
base = ["docker","compose","--project-name","dream-lostfound",
        "--env-file",str(environment_path),"-f",str(SOURCE/"docker-compose.yaml")]
configuration = json.loads(subprocess.check_output(base+["config","--format","json"],cwd=SOURCE))
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
        service["ports"]=[{"target":5001,"published":"15001","host_ip":"127.0.0.1","protocol":"tcp"}]
    elif name=="web":
        service["ports"]=[{"target":3000,"published":"13000","host_ip":"127.0.0.1","protocol":"tcp"}]
    elif name=="nginx":
        service["ports"]=[{"target":80,"published":"18080","host_ip":"127.0.0.1","protocol":"tcp"}]
    else:
        service.pop("ports",None)
    services[name]=service
configuration["services"]=services
configuration["name"]="dream-lostfound"
resolved=RUNTIME/"compose.resolved.json"
resolved.write_text(json.dumps(configuration),encoding="utf-8")
resolved.chmod(0o600)
subprocess.run(["docker","compose","-f",str(resolved),"up","-d"],check=True)
print("Dify: http://127.0.0.1:18080/install")
print("Initialize your own administrator account, then import dsl/dream-lostfound.yml.")
