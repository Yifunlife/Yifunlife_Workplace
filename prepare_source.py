"""Restore complete workflow source shipped alongside the core. No business data."""
from pathlib import Path
import hashlib, tarfile
ROOT = Path(__file__).resolve().parent
archive = ROOT/'workflow-source.tar.gz'
EXPECTED = '25a5d860c802df14462c9b1e759d730ffd5a832d387707ab6babb64338ece697'
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
