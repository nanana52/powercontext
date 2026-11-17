from pathlib import Path
import json,os,secrets,subprocess
ROOT=Path(__file__).resolve().parents[1];RUNTIME=ROOT/'.runtime/dify';RUNTIME.mkdir(parents=True,exist_ok=True)
p=RUNTIME/'private.json'
if p.exists():values=json.loads(p.read_text())
else:
 values={k:secrets.token_urlsafe(32) for k in ['SECRET_KEY','DB_PASSWORD','REDIS_PASSWORD','SANDBOX_API_KEY','PLUGIN_DAEMON_KEY','PLUGIN_DIFY_INNER_API_KEY','DIFY_AGENT_SERVER_SECRET_KEY','QDRANT_API_KEY','WEAVIATE_API_KEY']};p.write_text(json.dumps(values));p.chmod(0o600)
# The API's sandbox key is coordinated with sandbox configuration.
values['CODE_EXECUTION_API_KEY']=values['SANDBOX_API_KEY']
s=(ROOT/'deployment/compose.template.json').read_text()
for k,v in values.items():s=s.replace('__SECRET_'+k+'__',v)
for k,v in {'ROOT':str(ROOT),'RUNTIME':str(RUNTIME),'PROJECT':os.environ.get('DREAM_DIFY_PROJECT','dream-mini'),'API_PORT':os.environ.get('DREAM_DIFY_API_PORT','15001'),'WEB_PORT':os.environ.get('DREAM_DIFY_WEB_PORT','13000'),'HTTP_PORT':os.environ.get('DREAM_DIFY_HTTP_PORT','18080')}.items():s=s.replace('__'+k+'__',v)
assert '__SECRET_' not in s,'Unresolved private config'
doc=json.loads(s);common=doc.pop('x-dream-shared-environment')
for n in ['api','worker','worker_beat','plugin_daemon','web','sandbox']:doc['services'][n]['environment']=common|doc['services'][n].get('environment',{})
for service in doc['services'].values():
 for vol in service.get('volumes',[]):
  if vol.get('type')=='bind' and vol.get('source','').startswith(str(RUNTIME)):Path(vol['source']).mkdir(parents=True,exist_ok=True)
conf=RUNTIME/'volumes/sandbox/conf/config.yaml';conf.write_text((ROOT/'deployment/sandbox/config.yaml').read_text().replace('key: dify-sandbox','key: '+values['SANDBOX_API_KEY']));conf.chmod(0o600)
p=RUNTIME/'compose.resolved.json';p.write_text(json.dumps(doc));p.chmod(0o600)
subprocess.run(['docker','compose','-f',str(p),'up','-d','--wait','--wait-timeout','180'],check=True)
print('DIFY_SERVICES_READY')
