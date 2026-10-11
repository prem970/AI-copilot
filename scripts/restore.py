"""Restore into an empty MySQL database and empty storage directory only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
from sqlalchemy import create_engine, inspect
from backup import credentials, binary

def restore(archive_path, url, storage):
    engine = create_engine(url)
    try:
        if inspect(engine).get_table_names():
            raise RuntimeError('Restore target must have no tables. Existing data will never be overwritten.')
    finally:
        engine.dispose()
    if storage.exists() and any(storage.iterdir()):
        raise RuntimeError('Restore storage target must be empty')
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        expected = set(manifest['sha256'])
        if set(archive.namelist()) != expected | {'manifest.json'} or 'database.sql' not in expected:
            raise RuntimeError('Invalid backup manifest')
        for name, digest in manifest['sha256'].items():
            if name != 'database.sql' and (not name.startswith('storage/') or Path(name).name != name[8:] or not name.endswith('.bin')):
                raise RuntimeError('Invalid backup path')
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise RuntimeError('Backup checksum failed')
        with credentials(url) as (config, database):
            subprocess.run([binary('mysql'), '--defaults-extra-file='+config, '--binary-mode', database],
                input=archive.read('database.sql'), capture_output=True, check=True)
        storage.mkdir(parents=True, exist_ok=True)
        for name in expected - {'database.sql'}:
            (storage/Path(name).name).write_bytes(archive.read(name))
    print('Restore completed into the empty target. Reindex approved documents before using narrative search.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--storage', type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get('RESTORE_DATABASE_URL')
    if not url:
        raise SystemExit('Set RESTORE_DATABASE_URL to an empty MySQL database')
    restore(args.backup, url, args.storage.resolve())
