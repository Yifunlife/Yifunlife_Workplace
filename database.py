"""The only business database used by Workplace and all three workflow adapters."""
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get('YIFUN_DATA_ROOT', ROOT / 'data')).expanduser().resolve()
DB_PATH = Path(os.environ.get('YIFUN_DB', DATA_ROOT / 'database/workplace.sqlite3')).expanduser().resolve()
# Keep existing desktop installations compatible without copying or moving their data.
if 'YIFUN_DB' not in os.environ and 'YIFUN_DATA_ROOT' not in os.environ and (ROOT / 'data/workplace.sqlite3').exists():
    DB_PATH = ROOT / 'data/workplace.sqlite3'


def connect():
    backend = os.environ.get('YIFUN_DATABASE_BACKEND', 'local')
    if backend == 'cloudflare':
        from cloud_database import Connection
        return Connection()
    if backend != 'local':
        raise RuntimeError('Unsupported YIFUN_DATABASE_BACKEND')
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS workplace_migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        for module in ('quote', 'procurement'):
            folder = ROOT / 'modules' / module / ('drizzle' if module == 'quote' else 'migrations')
            for file in sorted(folder.glob('*.sql')):
                key = f'{module}/{file.name}'
                if db.execute('SELECT 1 FROM workplace_migrations WHERE name=?', (key,)).fetchone():
                    continue
                try:
                    db.executescript('BEGIN;\n' + file.read_text() + "\nINSERT INTO workplace_migrations(name) VALUES('" + key + "');\nCOMMIT;")
                except Exception:
                    db.rollback()
                    raise
        if not db.execute("SELECT 1 FROM workplace_migrations WHERE name='workplace/001'").fetchone():
            # Upstream migrations contain old initial catalog rows. They are not a verified
            # migration of the user's live business data, so the new business library starts empty.
            protection = db.execute("SELECT sql FROM sqlite_master WHERE name='supplier_keep_identity'").fetchone()[0]
            db.execute('DROP TRIGGER supplier_keep_identity')
            for table in ('supplier_products', 'supplier_commercial_terms', 'suppliers'):
                db.execute('DELETE FROM ' + table)
            db.execute(protection)
            db.commit()
            db.executescript((ROOT / 'schema.sql').read_text())
        for file in sorted((ROOT/'migrations').glob('*.sql')):
            key='workplace/'+file.name
            if not db.execute('SELECT 1 FROM workplace_migrations WHERE name=?',(key,)).fetchone():
                db.executescript('BEGIN;\n'+file.read_text()+"\nINSERT INTO workplace_migrations(name) VALUES('"+key+"'); COMMIT;")


def d1_batch(statements):
    if not isinstance(statements, list) or not 1 <= len(statements) <= 1500:
        raise ValueError('数据库请求格式不正确')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        results = []
        for statement in statements:
            sql = statement.get('sql', '')
            if not isinstance(sql, str) or not sql.strip():
                raise ValueError('查询内容为空')
            cursor = db.execute(sql, statement.get('params', []))
            columns = [item[0] for item in cursor.description] if cursor.description else []
            rows = [list(row) for row in cursor.fetchall()] if columns else []
            changes = db.execute('SELECT changes()').fetchone()[0] if not sql.lstrip().upper().startswith(('SELECT', 'WITH', 'PRAGMA')) else 0
            results.append({'success': True, 'results': [dict(zip(columns, row)) for row in rows], 'rows': rows,
                            'columns': columns, 'meta': {'changes': changes, 'last_row_id': cursor.lastrowid or 0, 'duration': 0, 'rows_read': len(rows), 'rows_written': changes}})
        return results
