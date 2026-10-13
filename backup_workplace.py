"""Offline backup/restore into a new directory; never overwrite existing data."""
import argparse,hashlib,json,shutil,socket,sqlite3,tempfile,zipfile
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parent

def ensure_stopped():
 with socket.socket() as sock:
  if sock.connect_ex(('127.0.0.1',8975))==0:raise ValueError('请先关闭 Workplace 启动窗口，再制作完整备份')

def create_backup(source,destination):
 source=Path(source);destination=Path(destination)
 if destination.exists():raise ValueError('备份文件已存在，请使用新的文件名')
 if not (source/'workplace.sqlite3').exists():raise ValueError('未找到工作数据库')
 destination.parent.mkdir(parents=True,exist_ok=True)
 manifest={}
 with tempfile.TemporaryDirectory() as temp:
  snapshot=Path(temp)/'workplace.sqlite3'
  with sqlite3.connect(source/'workplace.sqlite3') as origin,sqlite3.connect(snapshot) as target:origin.backup(target)
  with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as archive:
   for path in [snapshot,*sorted(source.rglob('*'))]:
    if not path.is_file() or (path!=snapshot and (path.name.startswith('workplace.sqlite3') or path.suffix in ('.log','.pid'))):continue
    relative='data/'+('workplace.sqlite3' if path==snapshot else path.relative_to(source).as_posix())
    raw=path.read_bytes();archive.writestr(relative,raw);manifest[relative]=hashlib.sha256(raw).hexdigest()
   archive.writestr('manifest.json',json.dumps({'format':1,'created_at':datetime.now().isoformat(),'files':manifest},indent=2))
 return destination

def restore_backup(archive,destination):
 destination=Path(destination)
 if destination.exists():raise ValueError('恢复位置必须是一个尚不存在的新目录')
 with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
  stage=Path(temp)
  with zipfile.ZipFile(archive) as source:
   manifest=json.loads(source.read('manifest.json'))
   if manifest.get('format')!=1:raise ValueError('不支持的备份格式')
   for name,digest in manifest['files'].items():
    path=Path(name)
    if path.is_absolute() or '..' in path.parts or path.parts[0]!='data':raise ValueError('备份路径不正确')
    raw=source.read(name)
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('备份校验失败：'+name)
    output=stage/path;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(raw)
  with sqlite3.connect(stage/'data/workplace.sqlite3') as db:
   if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('数据库完整性检查未通过')
  shutil.copytree(stage/'data',destination)
 return destination
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--restore');parser.add_argument('--to');args=parser.parse_args()
 try:
  if args.restore:
   if not args.to:parser.error('恢复时必须指定 --to 新目录')
   print(restore_backup(args.restore,args.to))
  else:
   ensure_stopped();print(create_backup(ROOT/'data',ROOT/'backups'/('workplace-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip')))
 except (ValueError,sqlite3.Error,zipfile.BadZipFile) as e:parser.exit(1,str(e)+'\n')
