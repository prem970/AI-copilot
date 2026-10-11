import { defineConfig } from '@playwright/test'
import path from 'node:path'
const python = path.resolve('..', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const server = path.resolve('..', 'scripts/e2e_server.py')
export default defineConfig({
  testDir: './tests', fullyParallel: false, workers: 1, timeout: 60000,
  use: { baseURL: 'http://127.0.0.1:5174', trace: 'retain-on-failure' },
  webServer: [
    { command: `"${python}" "${server}"`, env: { PYTHONPATH: path.resolve('..', 'backend') }, port: 8010, reuseExistingServer: false, timeout: 60000 },
    { command: 'node node_modules/vite/bin/vite.js --port 5174 --host 127.0.0.1', env: { BACKEND_URL: 'http://127.0.0.1:8010' }, port: 5174, reuseExistingServer: false },
  ],
})
