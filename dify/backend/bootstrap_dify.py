"""Initialize the real local Dify installation and publish the delivered DSL."""
from pathlib import Path
import json,os,secrets,yaml
import sys
sys.path.insert(0,"/app/api")
from app import app
from extensions.ext_database import db
from extensions.ext_application_services import application_services
from services.account.contracts import SetupInput
from models.account import Account,Tenant
from models.model import App,ApiToken
from services.app_dsl_service import AppDslService
from services.workflow_service import WorkflowService
private=Path('/data/private');private.mkdir(parents=True,exist_ok=True)
with app.app_context():
 services=application_services()
 if not services.setup.get_status().completed:
  services.setup.initialize(SetupInput(email='local-owner@dream.invalid',name='Dream game owner',password=secrets.token_urlsafe(24)+'aA1',ip_address='127.0.0.1',language='zh-Hans'),initialization_validated=True)
 owner=db.session.query(Account).first();tenant=db.session.query(Tenant).first();owner.set_current_tenant_with_session(tenant,session=db.session)
 document=yaml.safe_load(Path('/opt/dream/app.yml').read_text())
 for variable in document['workflow']['environment_variables']:
  if variable['name']=='POWERCONTEXT_BASE_URL':variable['value']='http://127.0.0.1:'+os.environ.get('PORT','8080')
  if variable['name']=='POWERCONTEXT_TOKEN':variable['value']=os.environ['DREAM_ACCESS_TOKEN']
 imported=AppDslService(db.session).import_app(account=owner,import_mode='yaml-content',yaml_content=yaml.safe_dump(document,allow_unicode=True),name='Dream lost-and-found ready-to-play')
 if imported.status!='completed':raise RuntimeError('Actual Dify DSL import failed: '+str(imported.model_dump()))
 model=db.session.get(App,imported.app_id);model.enable_api=True;model.enable_site=True
 published=WorkflowService().publish_workflow(session=db.session,app_model=model,account=owner,marked_name='Verified local game workflow');model.workflow_id=published.id
 key=ApiToken.generate_api_key('app-',32,session=db.session);db.session.add(ApiToken(app_id=model.id,tenant_id=tenant.id,type='app',token=key));db.session.commit()
 state={'app_id':model.id,'workflow_id':published.id,'app_key':key};p=private/'dify_app.json';p.write_text(json.dumps(state));p.chmod(0o600)
 print('REAL_DIFY_WORKFLOW_PUBLISHED',model.id,flush=True)
