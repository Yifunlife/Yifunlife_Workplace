"""Restore complete workflow source shipped alongside the core. No business data."""
from pathlib import Path
import hashlib, tarfile
ROOT = Path(__file__).resolve().parent
archive = ROOT/'workflow-source.tar.gz'
EXPECTED = '5932acf4fc1ca87bda8491d25ba94b2edad00a476e7878a03d9f184de83112c2'
if hashlib.sha256(archive.read_bytes()).hexdigest() != EXPECTED:
    raise SystemExit('Source archive checksum mismatch')
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        path = Path(member.name)
        if path.is_absolute() or '..' in path.parts or not member.isfile():
            raise SystemExit('Invalid source archive member')
        if path.parts[0] not in {'modules','migrations','cloudflare','scripts'}:
            raise SystemExit('Unexpected source path')
    tar.extractall(ROOT)
print('Full workflow source restored: quote, procurement, aftersales and migrations')
