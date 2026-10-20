"""Bundle the uploaded source scripts in their preserved execution order."""
from pathlib import Path
import json,sys
root=Path(__file__).resolve().parents[1]
names=json.loads((root/'aftercare/bundle-sources.json').read_text())
assert all('/' not in n and n.endswith('.js') for n in names)
content='\n;\n'.join((root/'aftercare/public'/n).read_text() for n in names)
out=root/'aftercare/public/workflow-bundle.js'
if '--check' in sys.argv:
    assert out.read_text()==content,'Aftercare bundle is stale; run scripts/build_aftercare_bundle.py'
else:out.write_text(content)
print('PASS: aftercare bundle matches its source scripts')
