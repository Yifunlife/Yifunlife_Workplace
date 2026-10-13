"""Build and run the isolated local version; never deploy or migrate production."""
import os,sys,subprocess,socket,time,signal,shutil,json,webbrowser
from pathlib import Path
import workplace
ROOT=Path(__file__).resolve().parent
MODULES={'quote':8991,'procurement':8992,'aftersales':8993}
STORAGE_ROOT=Path(os.environ.get('YIFUN_STORAGE_ROOT', workplace.database.DATA_ROOT/'objects')).expanduser().resolve()
LOG_ROOT=Path(os.environ.get('YIFUN_LOG_ROOT', workplace.database.DATA_ROOT/'logs')).expanduser().resolve()

def prepare(build=True):
 LOG_ROOT.mkdir(parents=True,exist_ok=True);STORAGE_ROOT.mkdir(parents=True,exist_ok=True)
 workplace.init();bridge=workplace.BRIDGE_PATH.read_text()
 # Publish the same brand assets to each native center's existing local asset path.
 brand_files={
  'workplace-logo.png':['modules/quote/public/brand/yifun-life-logo.png','modules/procurement/public/yifun-logo.png','modules/aftersales/app/assets/yifun-life-logo-transparent.png','modules/aftersales/app/assets/yifun-life-logo-standard.png'],
  'workplace-favicon.png':['modules/quote/public/workplace-favicon.png','modules/procurement/public/yifun-mark.png','modules/aftersales/app/assets/workplace-favicon.png'],
  'workplace-theme.css':['modules/aftersales/app/workplace-theme.css'],
 }
 for source,targets in brand_files.items():
  for target in targets:shutil.copyfile(ROOT/source,ROOT/target)
 for name in MODULES:
  folder=ROOT/'modules'/name
  if not (folder/'node_modules').exists():
   raise RuntimeError(f'{name} 依赖不存在。请先按 README 恢复依赖。')
  variables='WORKSPACE_BRIDGE='+bridge+'\nWORKPLACE_URL=http://127.0.0.1:8975\n'
  if workplace.runtime_config.container_mode():
   variables+='PUBLIC_ORIGIN='+workplace.runtime_config.public_origin()+'\nYIFUN_R2_GATEWAY=http://files.yifun.internal\n'
  target=folder/'.dev.vars';target.write_text(variables);target.chmod(0o600)
  if build and name!='aftersales':
   command=['./node_modules/.bin/vinext','build'] if name=='quote' else ['./node_modules/.bin/vite','build']
   result=subprocess.run(command,cwd=folder,env={**os.environ,'WRANGLER_LOG_PATH':str(LOG_ROOT/f'{name}-build.log')})
   if result.returncode:raise RuntimeError(f'{name} 构建未通过，请查看日志')
  if name=='aftersales':continue
  configs=list((folder/'dist').rglob('wrangler.json'))
  if not configs:raise RuntimeError(f'{name} 尚未构建')
  for config in configs:
   target=config.parent/'.dev.vars';target.write_text(variables);target.chmod(0o600)

def available(port):
 with socket.socket() as sock:
  sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  try:sock.bind(('127.0.0.1',port));return True
  except OSError:return False

def main():
 if '--build-only' in sys.argv:prepare();return
 for port in (8975,*MODULES.values()):
  if not available(port):raise RuntimeError(f'端口 {port} 已在使用。如已启动，请打开 http://127.0.0.1:8975；否则先关闭旧启动窗口。')
 prepare('--no-build' not in sys.argv);processes=[];logs=[]
 try:
  log=open(LOG_ROOT/'workplace.log','a');logs.append(log);processes.append(subprocess.Popen([sys.executable,'workplace.py'],cwd=ROOT,stdout=log,stderr=log))
  for name,port in MODULES.items():
   folder=ROOT/'modules'/name
   configs=list((folder/'dist').rglob('wrangler.json')) if name!='aftersales' else []
   config=configs[0] if configs else folder/'wrangler.jsonc'
   log=open(LOG_ROOT/f'{name}.log','a');logs.append(log)
   command=[str(folder/'node_modules/.bin/wrangler'),'dev','--local','--ip','0.0.0.0' if workplace.runtime_config.container_mode() else '127.0.0.1','--port',str(port),'--inspector-port',str(port+100),'--config',str(config),'--persist-to',str(STORAGE_ROOT/f'{name}-storage')]
   processes.append(subprocess.Popen(command,cwd=folder,stdout=log,stderr=log,env={**os.environ,'WRANGLER_SEND_METRICS':'false'}))
  print('正在启动三个中心，请稍候…',flush=True)
  for _ in range(120):
   if any(p.poll() is not None for p in processes):raise RuntimeError('某个中心未启动，请检查 data 内运行日志')
   if all(not available(port) for port in (8975,*MODULES.values())):break
   time.sleep(.5)
  else:raise RuntimeError('启动超时，请检查日志')
  print('已启动：http://127.0.0.1:8975\n关闭此窗口可停止本地服务。',flush=True)
  if '--no-open' not in sys.argv:webbrowser.open('http://127.0.0.1:8975')
  while all(p.poll() is None for p in processes):time.sleep(1)
 finally:
  for p in reversed(processes):
   if p.poll() is None:p.terminate()
  for p in processes:
   try:p.wait(timeout=8)
   except subprocess.TimeoutExpired:p.kill()
  for f in logs:f.close()
if __name__=='__main__':
 def stop_service(signum,frame):raise KeyboardInterrupt()
 signal.signal(signal.SIGTERM,stop_service)
 signal.signal(signal.SIGHUP,stop_service)
 try:main()
 except KeyboardInterrupt:pass
 except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
