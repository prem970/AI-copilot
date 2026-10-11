"""Start private loopback-only services. Run after installation and migrations."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT/'.runtime'

def cleanup_retired_runtime():
    # Only the known uninstall residue from this project's former Torch runtime.
    retired = (RUNTIME/'removed-torch-runtime').resolve()
    if retired.parent != RUNTIME.resolve():
        raise RuntimeError('Retired runtime cleanup escaped the workspace runtime directory')
    library = retired/'lib'/'torch_cpu.dll'
    if library.is_symlink() or library.resolve() != library:
        raise RuntimeError('Refusing cleanup of a redirected runtime file')
    if library.exists():
        try:
            library.unlink()
        except OSError:
            print('Windows denied cleanup of an unused Torch DLL. Startup will retry; AI uses APIs only.')
            return
    for directory in (retired/'lib', retired):
        if directory.exists():
            try:
                directory.rmdir()
            except OSError:
                pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--services', nargs='+', choices=['api', 'worker', 'vectors', 'frontend'])
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    cleanup_retired_runtime()
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ROOT/'backend')
    python = sys.executable
    services = {
        'api':[python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],
        'worker':[python,'-m','app.worker'],
        'vectors':[python,'-m','uvicorn','app.vector_server:app','--host','127.0.0.1','--port','6333'],
        'frontend':['node',str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5173'],
    }
    registry = RUNTIME/'services.json'
    previous = json.loads(registry.read_text()) if registry.exists() else {}
    pids = dict(previous)
    if args.services:
        services = {name: command for name, command in services.items() if name in args.services}
    for name, command in services.items():
        if name in previous:
            # Use psutil to verify a stored PID actually belongs to this workspace.
            import psutil
            try:
                existing=psutil.Process(previous[name]['pid'])
                if existing.is_running() and str(ROOT).lower() in existing.cwd().lower() and previous[name]['command'] == existing.cmdline():
                    pids[name]=previous[name]; print(name+' already running'); continue
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        output = open(RUNTIME/(name+'.stdout.log'),'ab')
        errors = open(RUNTIME/(name+'.stderr.log'),'ab')
        process = subprocess.Popen(command, cwd=ROOT/'frontend' if name=='frontend' else ROOT, env=env,
            stdout=output,stderr=errors,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        output.close(); errors.close()
        pids[name]={'pid':process.pid,'command':command}
        print(name+' started')
    registry.write_text(json.dumps(pids,indent=2))
    print('Portal: http://127.0.0.1:5173 · API readiness: http://127.0.0.1:8000/ready')

if __name__=='__main__':
    main()
