"""Rehearse a real dump/restore into an isolated, empty verification database."""
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
import pymysql
from sqlalchemy import create_engine, inspect, text
from app.core.config import ROOT, settings
from backup import backup
from restore import restore

def main():
    credentials = json.loads((ROOT/'.runtime/mysql-credentials.json').read_text())
    target = 'health_copilot_restore_verify'
    with pymysql.connect(host='127.0.0.1', port=3307, user='root', password=credentials['root']) as db:
        with db.cursor() as cursor:
            cursor.execute('CREATE DATABASE IF NOT EXISTS '+target+' CHARACTER SET utf8mb4')
            cursor.execute("GRANT ALL ON "+target+".* TO 'health_verify'@'127.0.0.1'")
    destination = ROOT/'.runtime/rehearsal'/secrets.token_hex(8)
    destination.mkdir(parents=True)
    archive = destination/'backup.zip'
    backup(archive)
    url = 'mysql+pymysql://health_verify:'+credentials['verify']+'@127.0.0.1:3307/'+target
    restore(archive, url, destination/'storage')
    original, restored = create_engine(settings.database_url), create_engine(url)
    try:
        tables = inspect(original).get_table_names()
        assert tables == inspect(restored).get_table_names()
        with original.connect() as left, restored.connect() as right:
            for table in tables:
                query = text('SELECT COUNT(*) FROM `'+table+'`')
                assert left.scalar(query) == right.scalar(query), table
        print('MySQL backup/restore verified across '+str(len(tables))+' tables and source-file checksums.')
    finally:
        original.dispose(); restored.dispose()
    # Keep the isolated restored database for review; a repeated rehearsal requires a new empty target.

if __name__ == '__main__':
    main()
