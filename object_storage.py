"""Private file storage; file bytes never enter new business database records."""
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote, urlparse
import database


def key_path(key):
    path = Path(key)
    if not key or path.is_absolute() or '..' in path.parts or '\\' in key:
        raise ValueError('Invalid object key')
    return path


def request(key, method='GET', body=None, mime='application/octet-stream'):
    key_path(key)
    endpoint = os.environ.get('YIFUN_OBJECT_ENDPOINT', '').rstrip('/')
    token = os.environ.get('YIFUN_OBJECT_TOKEN', '')
    private_binding = os.environ.get('YIFUN_CONTAINER_MODE') == '1' and endpoint == 'http://objects.yifun.internal'
    if not private_binding and (not endpoint or not token or urlparse(endpoint).scheme != 'https'):
        raise RuntimeError('Private HTTPS object endpoint and token are required')
    headers = {'Content-Type': mime}
    if not private_binding: headers['Authorization'] = 'Bearer '+token
    req = Request(endpoint + '/objects/' + quote(key, safe='/'), data=body, method=method,
                  headers=headers)
    with urlopen(req, timeout=30) as response:
        return response.read()


def backend():
    value = os.environ.get('YIFUN_OBJECT_BACKEND', 'local')
    if value not in ('local', 'r2'): raise RuntimeError('Unsupported object storage backend')
    return value


def put(key, content, mime):
    path = key_path(key)
    if backend() == 'r2':
        request(key, 'PUT', content, mime)
        return
    root = Path(os.environ.get('YIFUN_STORAGE_ROOT', database.DATA_ROOT/'objects')).resolve()
    target = root/path
    target.parent.mkdir(parents=True, exist_ok=True)
    # Random object keys, exclusive creation: existing files cannot be overwritten.
    with target.open('xb') as output: output.write(content)


def get(key):
    path = key_path(key)
    if backend() == 'r2': return request(key)
    root = Path(os.environ.get('YIFUN_STORAGE_ROOT', database.DATA_ROOT/'objects')).resolve()
    return (root/path).read_bytes()
