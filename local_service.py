"""Run Workplace independently of the startup window and supervise its centers."""
import fcntl
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / 'data/background-service.pid'
URL = 'http://127.0.0.1:8975/'


def ready():
    for port in (8975, 8991, 8992, 8993):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2) as response:
                if response.status != 200:
                    return False
        except urllib.error.HTTPError as error:
            if error.code != 401:
                return False
        except (OSError, urllib.error.URLError):
            return False
    return True


def service_pid():
    if not PID_FILE.exists():
        return None
    value = PID_FILE.read_text().strip()
    if not value.isdigit():
        return None
    result = subprocess.run(['/bin/ps', '-p', value, '-o', 'command='], capture_output=True, text=True)
    if str(ROOT / 'local_service.py') + ' --supervise' in result.stdout:
        return int(value)
    return None


def supervise():
    with PID_FILE.open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()
        child = None
        def stop(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, stop)
        try:
            while True:
                child = subprocess.Popen([sys.executable, str(ROOT / 'run_workplace.py'), '--no-build', '--no-open'], cwd=ROOT)
                child.wait()
                print('服务已退出，10 秒后重新启动。', flush=True)
                time.sleep(10)
        except KeyboardInterrupt:
            pass
        finally:
            if child and child.poll() is None:
                child.terminate()
                child.wait()
            lock.seek(0)
            lock.truncate()


def main():
    (ROOT / 'data').mkdir(exist_ok=True)
    if '--supervise' in sys.argv:
        supervise()
        return
    if '--stop' in sys.argv:
        pid = service_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
            for _ in range(60):
                if service_pid() is None:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('服务仍在退出，请稍后查看运行日志。')
        print('后台服务已停止。')
        return
    if service_pid() is None and not ready():
        env = {**os.environ, 'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
               'YIFUN_DB': str(ROOT / 'data/workplace.sqlite3'), 'YIFUN_PORT': '8975'}
        with (ROOT / 'data/background-service.log').open('a') as log:
            subprocess.Popen([sys.executable, str(ROOT / 'local_service.py'), '--supervise'], cwd=ROOT,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True, env=env)
    for _ in range(60):
        if ready():
            print(f'Workplace 已在后台运行：{URL}\n关闭此窗口不会停止服务；重启 Mac 后请再次双击启动器。')
            if '--no-open' not in sys.argv:
                webbrowser.open(URL)
            return
        time.sleep(1)
    raise RuntimeError('启动未完成，请查看 data/background-service.log 和各中心日志。')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
