import json, os, re, subprocess, tempfile, time
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='gramrail-smoke-') as tmp:
 logpath=Path(tmp)/'server.log'
 with logpath.open('w') as log:
  process=subprocess.Popen(['gramrail','dev','--port','8096'],cwd=tmp,stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(100):
   found=re.search(r'Temporary development key: (\S+)',logpath.read_text())
   try:
    if found and httpx.get('http://127.0.0.1:8096/health',timeout=1).is_success: break
   except httpx.HTTPError: pass
   time.sleep(.1)
  else: raise RuntimeError('Runtime did not start')
  key=found[1]
  with httpx.Client(base_url='http://127.0.0.1:8096',headers={'Authorization':'Bearer '+key}) as client:
   assert client.get('/health').json()['mode']=='simulation'
   for route in ['/console','/console/app.js','/console/style.css','/openapi.json']:
    assert client.get(route).is_success
   base='/api/v1/bots/demo'
   for idx,text in enumerate(['/submit','Example entry','https://example.com'],1):
    update={'update_id':idx,'message':{'message_id':idx,'from':{'id':1001,'is_bot':False},'chat':{'id':1001,'type':'private'},'text':text}}
    response=client.post(base+'/updates',json=update)
    assert response.status_code==200,response.text
   assert client.post(base+'/updates',json=update).json()['duplicate']
   jobs=client.get(base+'/jobs').json()
   review=next(j for j in jobs if j['payload'].get('params',{}).get('reply_markup'))
   button=review['payload']['params']['reply_markup']['inline_keyboard'][0][0]
   response=client.post(base+'/updates',json={'update_id':4,'callback_query':{'id':'4','from':{'id':1,'is_bot':False},'data':button['callback_data']}})
   assert response.is_success,response.text
   assert client.get(base+'/workflows').json()[0]['state']=='approved'
   env=os.environ.copy();env.update(GRAMRAIL_BOT_KEY=key,GRAMRAIL_URL='http://127.0.0.1:8096')
   worker=subprocess.run(['python',str(root/'examples/report-worker/worker.py')],env=env,capture_output=True,text=True,timeout=10)
   assert worker.returncode==0,worker.stderr
   jobs=client.get(base+'/jobs').json()
   assert any(j['kind']=='reports.generate' and j['state']=='succeeded' for j in jobs)
   assert client.get(base+'/events').json()
   print(json.dumps({'result':'passed','checks':['runtime starts','console assets and OpenAPI','form to approval','duplicate update','Python SDK worker','stored results and events'],'real_telegram_calls':0},indent=2))
 finally:
  process.terminate()
  try: process.wait(timeout=5)
  except subprocess.TimeoutExpired: process.kill();process.wait()
