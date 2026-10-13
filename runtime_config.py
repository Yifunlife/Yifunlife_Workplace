"""Explicit origin configuration shared by desktop and cloud deployments."""
import os
from urllib.parse import urlsplit


def public_origin():
    value = os.environ.get('YIFUN_PUBLIC_ORIGIN', '').rstrip('/')
    if not value:
        return None
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise RuntimeError('YIFUN_PUBLIC_ORIGIN must be a single HTTPS origin')
    return value


def allowed_hosts(port):
    origin = public_origin()
    # Internal service traffic retains the original loopback addresses.
    return {f'127.0.0.1:{port}', f'localhost:{port}'} | ({urlsplit(origin).netloc} if origin else set())


def allowed_origins(port):
    origin = public_origin()
    return {origin} if origin else {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}


def module_urls():
    origin = public_origin()
    return {name: f'{origin}/modules/{name}/' if origin else f'http://127.0.0.1:{port}/'
            for name, port in [('quote', 8991), ('procurement', 8992), ('aftersales', 8993)]}


def session_cookie(token, max_age=28800):
    secure = '; Secure' if public_origin() else ''
    return f'workplace_complete_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}{secure}'


def container_mode():
    return os.environ.get('YIFUN_CONTAINER_MODE') == '1'


def password_login():
    return container_mode() and os.environ.get('YIFUN_AUTH_MODE') == 'password'


def owner_email():
    return os.environ.get('YIFUN_OWNER_EMAIL', '').strip().lower()


def allowed_emails():
    return {owner_email()} | {value.strip().lower() for value in os.environ.get('YIFUN_VIEWER_EMAILS', '').split(',') if value.strip()}


def verified_email(headers):
    if not container_mode(): return None
    value = headers.get('X-Yifun-Verified-Email', '').strip().lower()
    return value if value and value in allowed_emails() else None


def read_only(user):
    return container_mode() and user['email'].lower() != owner_email()
