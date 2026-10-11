"""Back up MySQL and private source files. Stop app/worker writes first."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from app.core.config import ROOT, settings
from sqlalchemy.engine import make_url

def binary(name):
    portable = ROOT/'.tools/mysql-8.4.11-winx64/bin'/(name+'.exe')
    found = str(portable) if portable.exists() else shutil.which(name)
    if not found:
        raise RuntimeError('Install MySQL client tools before backup/restore')
    return found

@contextmanager
def credentials(url):
    url = make_url(url)
    if url.get_backend_name() != 'mysql':
        raise RuntimeError('Backup and restore require MySQL')
    def quoted(value):
        return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r')+'"'
    fd, path = tempfile.mkstemp(prefix='health-mysql-', suffix='.cnf')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write('[client]\nhost='+quoted(url.host or '127.0.0.1')+'\nport='+str(url.port or 3306)+'\nuser='+quoted(url.username)+'\npassword='+quoted(url.password or '')+'\n')
        yield path, url.database
    finally:
        Path(path).unlink(missing_ok=True)

def backup(output):
    with credentials(settings.database_url) as (config, database):
        dump = subprocess.run([binary('mysqldump'), '--defaults-extra-file='+config, '--single-transaction',
            '--no-tablespaces', '--set-gtid-purged=OFF', '--skip-add-drop-table', '--hex-blob', database],
            capture_output=True, check=True).stdout
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {'created_at':datetime.now(timezone.utc).isoformat(), 'database':database, 'sha256':{}}
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('database.sql', dump)
        manifest['sha256']['database.sql'] = hashlib.sha256(dump).hexdigest()
        for path in sorted(settings.storage_dir.glob('*.bin')):
            name = 'storage/'+path.name
            data = path.read_bytes()
            archive.writestr(name, data)
            manifest['sha256'][name] = hashlib.sha256(data).hexdigest()
        archive.writestr('manifest.json', json.dumps(manifest, indent=2))
    print('Backup created: '+str(output))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'.runtime/backups'/('health-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip'))
    args = parser.parse_args()
    backup(args.output.resolve())
