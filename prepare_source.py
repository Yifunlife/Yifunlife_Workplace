"""Restore complete workflow source shipped alongside the core. No business data."""
from pathlib import Path
import hashlib, tarfile
ROOT = Path(__file__).resolve().parent
archive = ROOT/'workflow-source.tar.gz'
EXPECTED = '1d114d4f652c46a5c91a8194755d7f3bbf7f56dc261fae44d7159e97eb0c7aa1'
if hashlib.sha256(archive.read_bytes()).hexdigest() != EXPECTED:
    raise SystemExit('Source archive checksum mismatch')
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        path = Path(member.name)
        if path.is_absolute() or '..' in path.parts or not member.isfile():
            raise SystemExit('Invalid source archive member')
        if path.parts[0] not in {'modules','migrations','cloudflare','scripts'}:
            raise SystemExit('Unexpected source path')
    # The versioned Worker may be newer than the bundled module sources.
    # Keep its private service bindings and scheduled handlers on rebuilds.
    members=[m for m in tar.getmembers() if not (m.name=='cloudflare/container-worker.js' and (ROOT/m.name).is_file())]
    tar.extractall(ROOT,members=members)
print('Full workflow source restored: quote, procurement, aftersales and migrations')
