"""Supplemental fixture-only real HTTPS interruption/recovery acceptance.
Runs original Git.Fetch and Vcs.UpdateProject actions; never touches global proxy/NIC.
"""
from pathlib import Path
import argparse,subprocess,json,hashlib,time,os,sys,datetime,shutil,socket
p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--matrix',type=Path,required=True);args=p.parse_args()
r=Path.cwd().resolve();assert (r/'upstream.lock.json').exists();matrix=args.matrix.resolve();assert matrix.is_relative_to(r/'out/remote-matrix')
read=lambda x:json.loads(Path(x).read_text(encoding='utf-8-sig'))
m=read(matrix);assert m['status']=='passed';assert hashlib.sha256(args.archive.read_bytes()).hexdigest()==m['archiveSha256']
case=matrix.parent/'https-sync.json';assert hashlib.sha256(case.read_bytes()).hexdigest()==m['cases']['https-sync']['resultSha256'];sync=read(case);assert sync['status']=='passed' and sync['transport']=='https'
source_repo=Path(sync['fixture']).resolve();assert source_repo.is_relative_to(r/'out/fixtures') and (source_repo/'.git').is_dir();base_branch=sync['branch'];assert base_branch.startswith('alhena-ui-') and base_branch.endswith('-https')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S');branch='alhena-network-'+stamp;e=r/'out/network-recovery'/stamp;e.mkdir(parents=True,exist_ok=False);peer=r/'out/fixtures'/('workflow-network-peer-'+stamp);checks=[];launch=None;relay=None;repo=r/'out/fixtures'/('workflow-network-target-'+stamp);report={'status':'failed','evidence':str(e),'archiveSha256':m['archiveSha256'],'transport':'real HTTPS to authorized GitHub repository through opaque loopback tunnel'}
sources=e/'probe-sources';sources.mkdir()
source_hashes={}
for name in ['run.py','relay.py','NetworkNotificationProbe.java']:
 source=r/'out/diagnostics/network-recovery'/name;shutil.copyfile(source,sources/name);source_hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
report['externalProbeSha256']=source_hashes
env=os.environ.copy();env.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never');old_proxy=None

def execute(argv,timeout=90,check=True):
 result=subprocess.run([str(x) for x in argv],cwd=r,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8-sig',errors='replace',timeout=timeout)
 if check and result.returncode:raise RuntimeError(Path(str(argv[0])).name+' failed: '+result.stderr[:1800])
 return result

def git(directory,*argv,check=True):return execute(['git','-c','safe.directory='+directory.as_posix(),'-C',directory,*argv],check=check).stdout.strip()
def ps(script,*argv):return execute(['pwsh','-NoProfile','-File',r/script,*argv]).stdout

def probe(stage,step):return ps('tools/workflow-probe.ps1','-Stage',stage,'-Evidence',str((e/step).relative_to(r)))
def notifications(step):
 path=e/step;path.mkdir(exist_ok=True)
 result=execute([jdk/'java.exe','--add-modules','jdk.attach','-cp',r/'out/diagnostics/network-recovery','Attach',str(launch['pid']),agent,str(r)+'|'+str(repo)+'|'+str(path)])
 value=(path/'notifications.txt').read_text(encoding='utf-8');assert 'snapshotPassed=true' in value;return value

def wait(test,label,seconds=90):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  value=test()
  if value:checks.append(label);return value
  time.sleep(.3)
 raise RuntimeError('Timed out: '+label)

def events():
 file=e/'relay-events.jsonl'
 if not file.exists():return []
 rows=[]
 for line in file.read_text(encoding='utf-8').splitlines():
  try:rows.append(json.loads(line))
  except json.JSONDecodeError:pass
 return rows

jdk=next((r/'.cache/bootstrap').rglob('javac.exe')).parent;agent=r/'out/diagnostics/network-recovery/network-probe.jar'
assert git(source_repo,'remote','get-url','origin')=='https://github.com/loevc/Alhena-test.git'
git(r/'out/fixtures','clone','--shared','--branch',base_branch,str(source_repo),str(repo));git(repo,'remote','set-url','origin','https://github.com/loevc/Alhena-test.git');git(repo,'checkout','-b',branch);git(repo,'push','--set-upstream','origin',branch)
assert not git(repo,'status','--porcelain');assert git(repo,'branch','--show-current')==branch
initial=git(repo,'rev-parse','HEAD');tracking='refs/remotes/origin/'+branch;assert git(repo,'rev-parse',tracking)==initial
old=execute(['git','-c','safe.directory='+repo.as_posix(),'-C',repo,'config','--local','--get','http.proxy'],check=False)
if old.returncode==0:old_proxy=old.stdout.strip()
try:
 # No proxy credential values are written to diagnostic configuration.
 (e/'relay-config.json').write_text(json.dumps({'root':str(r),'evidence':str(e),'cutAfterBytes':65536}),encoding='utf-8');(e/'restore.flag').write_text('pass through during startup',encoding='utf-8')
 creation=getattr(subprocess,'CREATE_NO_WINDOW',0)
 relay=subprocess.Popen([sys.executable,str(r/'out/diagnostics/network-recovery/relay.py'),str(e/'relay-config.json')],cwd=r,env=env,stdout=(e/'relay-stdout.log').open('wb'),stderr=(e/'relay-stderr.log').open('wb'),creationflags=creation)
 ready=wait(lambda:read(e/'relay-ready.json') if (e/'relay-ready.json').exists() else None,'owned loopback relay listening')
 git(repo,'config','--local','http.proxy','http://127.0.0.1:'+str(ready['port']))
 launch=json.loads(ps('run.ps1','-Archive',str(args.archive.resolve()),'-Repository',str(repo),'-Smoke','-Hidden','-SandboxDirectory',str(e/'sandbox')))
 (e/'launch.json').write_text(json.dumps(launch,indent=2),encoding='utf-8');assert launch['archiveSha256']==m['archiveSha256']
 wait(lambda:'selectedEditor=com.intellij.vcs.log.ui.editor.VcsLogEditor' in probe('ui-inspect','ready'),'original central editor ready')
 before=notifications('notifications-before');known={line.split('|')[1] for line in before.splitlines() if line.startswith('notification=')}
 git(r/'out/fixtures','clone','--shared',str(repo),str(peer));git(peer,'remote','set-url','origin','https://github.com/loevc/Alhena-test.git')
 name='network-recovery-'+stamp+'.bin';payload=hashlib.shake_256(('Alhena network fixture '+stamp).encode()).digest(512*1024);(peer/name).write_bytes(payload)
 git(peer,'add',name);git(peer,'-c','user.name=Alhena Network Fixture','-c','user.email=fixture@example.invalid','commit','-m','Real transport interruption and recovery fixture '+stamp);git(peer,'push','origin','HEAD:refs/heads/'+branch);incoming=git(peer,'rev-parse','HEAD')
 assert git(repo,'rev-parse',tracking)==initial,'Unexpected fetch occurred before fault was armed'
 flag=e/'restore.flag';assert flag.resolve().is_relative_to(e);flag.unlink()
 probe('ui-fetch','fetch-interrupted')
 def cut_ready():
  snapshot=probe('ui-inspect','fetch-progress')
  if 'title=Log In to GitHub' in snapshot or 'title=Log In to github.com' in snapshot or __import__('re').search('button=.*[Cc]redential helper',snapshot):probe('ui-auth-helper','credential-helper')
  return next((x for x in events() if x['event']=='transfer_cut'),None)
 cut=wait(cut_ready,'HTTPS connection cut after transfer bytes')
 assert cut['upstreamBytes']>=65536
 def fetch_error():
  value=notifications('notifications-after-cut')
  lines=[line for line in value.splitlines() if line.startswith('notification=ERROR|') and line.split('|')[1] not in known and 'fetch' in line.lower()]
  return lines[0] if lines else None
 error=wait(fetch_error,'original fetch error notification visible')
 assert git(repo,'rev-parse','HEAD')==initial and git(repo,'rev-parse',tracking)==initial,'Failed fetch advanced refs'
 assert not git(repo,'status','--porcelain'),'Failed fetch changed worktree/index'
 checks+=['failed transfer leaves branch/tracking ref and worktree/index unchanged']
 flag.write_text('restore transport',encoding='utf-8')
 probe('ui-fetch','fetch-recovered');wait(lambda:git(repo,'rev-parse',tracking)==incoming,'original Fetch succeeds after transport restore')
 probe('ui-update-open','update-open');wait(lambda:'title=Update Project' in probe('ui-inspect','update-dialog'),'original Update dialog')
 probe('ui-update','update-confirm');wait(lambda:git(repo,'rev-parse','HEAD')==incoming,'original Update integrates recovered commit')
 assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==hashlib.sha256(payload).hexdigest();assert not git(repo,'status','--porcelain')
 checks+=['recovered binary content matches exact source hash','final real repository index and worktree clean']
 report.update(status='passed',branch=branch,fixture=str(repo),peer=str(peer),initialHead=initial,incomingHead=incoming,receivedFile=name,receivedFileBytes=len(payload),receivedFileSha256=hashlib.sha256(payload).hexdigest(),cutAfterUpstreamBytes=cut['upstreamBytes'],originalErrorNotification=error,checks=checks,limits=['Opaque per-repository HTTPS transport interruption; no global proxy or physical NIC change','Physical link removal and SSH in-flight interruption are not covered'])
except BaseException as error:
 report['error']=str(error);raise
finally:
 try:
  (e/'restore.flag').write_text('restore on exit',encoding='utf-8')
  if old_proxy is None:git(repo,'config','--local','--unset-all','http.proxy',check=False)
  else:git(repo,'config','--local','http.proxy',old_proxy)
  report['localProxyRestored']=True
  if launch:
   probe('ui-exit','exit')
   wait(lambda:execute(['powershell','-NoProfile','-Command','if(Get-Process -Id '+str(launch['pid'])+' -ErrorAction SilentlyContinue){exit 1}'],check=False).returncode==0,'normal platform shutdown',30)
   log=(Path(launch['sandbox'])/'log/idea.log').read_text(encoding='utf-8');assert not __import__('re').search(r'\] (?:SEVERE|\s*ERROR) - ',log);report['normalExit']=True
 except BaseException as cleanup_error:
  report['status']='failed';report['cleanupError']=str(cleanup_error);raise
 finally:
  if launch:
   command="$p=Get-CimInstance Win32_Process -Filter 'ProcessId="+str(launch['pid'])+"'; if($p -and $p.ExecutablePath -eq '"+str(Path(launch['productRoot'])/'bin/alhena64.exe').replace("'","''")+"'){Stop-Process -Id "+str(launch['pid'])+" -ErrorAction SilentlyContinue}"
   execute(['powershell','-NoProfile','-Command',command],check=False)
  if relay:
   relay.terminate()
   try:relay.wait(timeout=10)
   except subprocess.TimeoutExpired:relay.kill();relay.wait(timeout=10)
  report['relayStopped']=relay is None or relay.poll() is not None
  (e/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(str(e/'result.json'))
