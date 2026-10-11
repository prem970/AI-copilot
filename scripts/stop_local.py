import json
import argparse
from pathlib import Path
import psutil

root = Path(__file__).resolve().parents[1]
registry=root/'.runtime/services.json'
services=json.loads(registry.read_text()) if registry.exists() else {}
parser=argparse.ArgumentParser()
parser.add_argument('--services', nargs='+', choices=['api','worker','vectors','frontend'])
args=parser.parse_args()
for name, entry in list(services.items()):
    if args.services and name not in args.services:
        continue
    try:
        process=psutil.Process(entry['pid'])
        if str(root).lower() in process.cwd().lower() and entry['command']==process.cmdline():
            process.terminate()
            process.wait(timeout=15)
            print(name+' stopped')
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    services.pop(name, None)
if services:
    registry.write_text(json.dumps(services,indent=2))
else:
    registry.unlink(missing_ok=True)
