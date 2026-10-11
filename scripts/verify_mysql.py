"""Run isolated MySQL tests using the portable verification database only."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
credentials = json.loads((root/'.runtime/mysql-credentials.json').read_text())
environment = dict(os.environ)
environment['TEST_DATABASE_URL'] = 'mysql+pymysql://health_verify:'+credentials['verify']+'@127.0.0.1:3307/health_copilot_verify'
raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q'],cwd=root,env=environment))
