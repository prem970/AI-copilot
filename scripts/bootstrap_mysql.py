"""Initialize a portable, loopback-only MySQL installation in the workspace."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request
import zipfile
import pymysql

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
TOOLS = ROOT / '.tools'
VERSION = '8.4.11'

def main():
    RUNTIME.mkdir(exist_ok=True)
    binary = TOOLS / ('mysql-'+VERSION+'-winx64') / 'bin' / 'mysqld.exe'
    if not binary.exists():
        TOOLS.mkdir(exist_ok=True)
        archive = TOOLS / 'mysql.zip'
        urllib.request.urlretrieve('https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-'+VERSION+'-winx64.zip', archive)
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(TOOLS)
    credentials = RUNTIME / 'mysql-credentials.json'
    first = not credentials.exists()
    if first:
        credentials.write_text(json.dumps({'root':secrets.token_hex(24),'health':secrets.token_hex(24),'verify':secrets.token_hex(24)}))
    secrets_data = json.loads(credentials.read_text())
    data = RUNTIME / 'mysql-data'
    base = binary.parents[1].as_posix()
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    if not data.exists():
        subprocess.run([str(binary), '--initialize-insecure', '--basedir='+base, '--datadir='+data.as_posix()], check=True, creationflags=flags)
    arguments = [str(binary), '--basedir='+base, '--datadir='+data.as_posix(), '--port=3307', '--bind-address=127.0.0.1',
        '--mysqlx=OFF', '--innodb-buffer-pool-size=128M', '--log-error='+(RUNTIME/'mysql.log').as_posix()]
    init = RUNTIME/'mysql-init.sql'
    if first:
        init.write_text("ALTER USER 'root'@'localhost' IDENTIFIED BY '"+secrets_data['root']+"';\n"
            "CREATE DATABASE health_copilot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
            "CREATE DATABASE health_copilot_verify CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
            "CREATE USER 'health'@'127.0.0.1' IDENTIFIED BY '"+secrets_data['health']+"';\n"
            "CREATE USER 'health_verify'@'127.0.0.1' IDENTIFIED BY '"+secrets_data['verify']+"';\n"
            "GRANT ALL ON health_copilot.* TO 'health'@'127.0.0.1';\n"
            "GRANT ALL ON health_copilot_verify.* TO 'health_verify'@'127.0.0.1';\n")
        arguments.append('--init-file='+init.as_posix())
    try:
        connection = pymysql.connect(host='127.0.0.1',port=3307,user='root',password=secrets_data['root'])
        connection.close()
        print('MySQL is already running on 127.0.0.1:3307')
    except pymysql.MySQLError:
        process = subprocess.Popen(arguments, cwd=ROOT, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (RUNTIME/'mysql.pid').write_text(str(process.pid))
        for _ in range(60):
            try:
                connection = pymysql.connect(host='127.0.0.1',port=3307,user='root',password=secrets_data['root'])
                connection.close()
                break
            except pymysql.MySQLError:
                if process.poll() is not None:
                    raise RuntimeError('MySQL failed to start; inspect .runtime/mysql.log')
                time.sleep(1)
        else:
            raise RuntimeError('MySQL startup timed out')
    init.unlink(missing_ok=True)
    env = ROOT/'.env'
    if not env.exists():
        env.write_text('DATABASE_URL=mysql+pymysql://health:'+secrets_data['health']+'@127.0.0.1:3307/health_copilot\n'
            'QDRANT_API_KEY='+secrets.token_hex(32)+'\nSARVAM_API_KEY=\nLAYA_API_KEY=\nGEMINI_API_KEY=\nCOOKIE_SECURE=false\n', encoding='utf-8')
    print('MySQL ready. Credentials are stored privately in .runtime. No patient accounts were created.')

if __name__ == '__main__':
    main()
