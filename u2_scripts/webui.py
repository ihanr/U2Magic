import base64
import hmac
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import qbittorrentapi


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get('U2_WEBUI_CONFIG_PATH', ROOT / 'webui_config.json'))
LOG_DIR = Path(os.environ.get('U2_WEBUI_LOG_DIR', ROOT / 'webui_logs'))
AUTO_MAGIC_DATA_PATH = Path(os.environ.get(
    'AUTO_MAGIC_DATA_PATH', ROOT / 'auto_magic_seeds.data.txt'
))
AUTO_MAGIC_LOG_PATH = Path(os.environ.get(
    'AUTO_MAGIC_LOG_PATH', ROOT / 'auto_magic_seeds.log'
))
PYTHON = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

DEFAULT_CONFIG = {
    'U2_COOKIE': '',
    'U2_UID': '',
    'U2_API_TOKEN': '',
    'QB_TARGETS': json.dumps([
        {
            'name': 'qB 1',
            'host': 'http://127.0.0.1',
            'port': 8080,
            'username': '',
            'password': ''
        }
    ], ensure_ascii=False, indent=2),
    'MAGIC_SELF_ENABLE': '1',
    'MAGIC_SELF_INTERVAL': '60',
    'MAGIC_DOWNLOADING': '1',
    'MAGIC_UPLOAD_RATIO': '2.33',
    'MAGIC_EXISTING_SKIP_RATIO': '2.0',
    'MAGIC_MIN_RATE': '1024',
    'MAGIC_MIN_SIZE': '5',
    'MAGIC_MIN_DAYS': '180',
    'UC_MAX': '30000',
    'TOTAL_UC_MAX': '200000',
    'MAGIC_ALL_ENABLE': '0',
    'MAGIC_ALL_INTERVAL': '86400',
    'MAGIC_ALL_TORRENT_NUM': '5',
    'MAGIC_ALL_MAX_SEEDER_NUM': '5',
    'MAGIC_ALL_233_ALL': '1',
    'MAGIC_ALL_HOURS': '24',
    'MAGIC_ALL_MIN_RM_HR': '0',
}

PROCESS = None
LOCK = threading.Lock()
AUTH_REALM = 'Auto Magic Seeds'

HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auto Magic Seeds</title>
  <style>
    :root {
      --bg: #f6f7fb;
      --panel: #fff;
      --line: #d8dee8;
      --text: #1d2433;
      --muted: #667085;
      --accent: #0f766e;
      --danger: #b42318;
      --ok: #067647;
      --warn: #b54708;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 "Segoe UI", Arial, sans-serif;
    }
    header {
      height: 60px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      background: #172033;
      color: white;
    }
    h1 { margin: 0; font-size: 19px; letter-spacing: 0; }
    h2 { margin: 0; font-size: 15px; letter-spacing: 0; }
    main {
      width: min(1560px, calc(100vw - 32px));
      margin: 18px auto 36px;
      display: grid;
      grid-template-columns: minmax(620px, 1fr) minmax(620px, 1fr);
      gap: 16px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .head {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    form {
      padding: 15px 16px 18px;
      display: grid;
      gap: 11px;
    }
    label { display: grid; gap: 6px; color: #344054; font-size: 13px; }
    input, textarea, select {
      width: 100%;
      border: 1px solid #c8d0dc;
      border-radius: 6px;
      padding: 7px 9px;
      font: inherit;
      color: var(--text);
      background: white;
    }
    input, select { height: 36px; }
    textarea {
      min-height: 150px;
      resize: vertical;
      font: 12px/1.45 Consolas, "Cascadia Mono", monospace;
    }
    input:focus, textarea:focus, select:focus {
      outline: 2px solid rgba(15, 118, 110, .18);
      border-color: var(--accent);
    }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; }
    button {
      height: 36px;
      border: 1px solid transparent;
      border-radius: 6px;
      padding: 0 12px;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
      background: #eef2f7;
      color: #1f2937;
    }
    button.primary { background: var(--accent); color: white; }
    button.danger { background: #fff1f0; color: var(--danger); border-color: #fecdca; }
    .right { display: grid; gap: 16px; align-content: start; }
    .status {
      padding: 16px;
      display: grid;
      gap: 12px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 76px;
      height: 24px;
      padding: 0 9px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 750;
      background: #fff4ed;
      color: var(--warn);
    }
    .pill.running { background: #dcfae6; color: var(--ok); }
    .notice {
      min-height: 38px;
      padding: 10px 12px;
      border: 1px solid #bfd7d4;
      border-radius: 6px;
      background: #f0fdfa;
      color: #134e4a;
    }
    .muted { color: var(--muted); }
    pre {
      margin: 0;
      min-height: 430px;
      max-height: 560px;
      overflow: auto;
      padding: 14px;
      background: #111827;
      color: #e5e7eb;
      border-radius: 8px;
      font: 12px/1.55 Consolas, "Cascadia Mono", monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .log-wrap { padding: 0 16px 16px; }
    .records {
      padding: 0 16px 16px;
      max-height: 300px;
      overflow: auto;
    }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td {
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th { color: #344054; font-weight: 700; background: #f8fafc; }
    .qb-table { table-layout: fixed; }
    .qb-table th:nth-child(1), .qb-table td:nth-child(1) { width: 14%; }
    .qb-table th:nth-child(2), .qb-table td:nth-child(2) { width: 32%; }
    .qb-table th:nth-child(3), .qb-table td:nth-child(3) { width: 11%; }
    .qb-table th:nth-child(4), .qb-table td:nth-child(4) { width: 17%; }
    .qb-table th:nth-child(5), .qb-table td:nth-child(5) { width: 17%; }
    .qb-table th:nth-child(6), .qb-table td:nth-child(6) { width: 9%; }
    .qb-table th, .qb-table td { padding: 6px; }
    .qb-table input { min-width: 0; padding-left: 7px; padding-right: 7px; }
    .qb-table button { width: 100%; padding: 0 6px; }
    td.hash {
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 12px;
      word-break: break-all;
    }
    @media (max-width: 960px) {
      main { grid-template-columns: 1fr; }
      .grid3 { grid-template-columns: 1fr; }
      .qb-table { min-width: 0; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Auto Magic Seeds</h1>
    <span id="clock" class="muted"></span>
  </header>
  <main>
    <section>
      <div class="head">
        <h2>配置</h2>
        <span class="muted">本地保存</span>
      </div>
      <form id="configForm">
        <label>U2 Cookie
          <input name="U2_COOKIE" type="password" autocomplete="off">
        </label>
        <div class="grid2">
          <label>U2 UID
            <input name="U2_UID" inputmode="numeric">
          </label>
          <label>U2 API Token
            <input name="U2_API_TOKEN" type="password" autocomplete="off">
          </label>
        </div>
        <div class="head" style="padding:0;border:0;">
          <h2>qB 列表</h2>
          <button type="button" id="addQb">添加 qB</button>
        </div>
        <div class="records">
          <table class="qb-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>地址</th>
                <th>端口</th>
                <th>用户名</th>
                <th>密码</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="qbBody"></tbody>
          </table>
        </div>
        <div class="grid3">
          <label>上传倍率
            <input name="MAGIC_UPLOAD_RATIO" inputmode="decimal">
          </label>
          <label>已有上传≥跳过
            <input name="MAGIC_EXISTING_SKIP_RATIO" inputmode="decimal">
          </label>
          <label>最小上传 KiB/s
            <input name="MAGIC_MIN_RATE" inputmode="numeric">
          </label>
        </div>
        <div class="grid3">
          <label>最小体积 GiB
            <input name="MAGIC_MIN_SIZE" inputmode="decimal">
          </label>
          <label>最小天数
            <input name="MAGIC_MIN_DAYS" inputmode="decimal">
          </label>
          <label>检查间隔 秒
            <input name="MAGIC_SELF_INTERVAL" inputmode="numeric">
          </label>
          <label>单次 UC 上限
            <input name="UC_MAX" inputmode="numeric">
          </label>
          <label>24h UC 上限
            <input name="TOTAL_UC_MAX" inputmode="numeric">
          </label>
        </div>
        <div class="grid2">
          <label>下载中也放
            <select name="MAGIC_DOWNLOADING">
              <option value="1">是</option>
              <option value="0">否</option>
            </select>
          </label>
          <label>地图炮
            <select name="MAGIC_ALL_ENABLE">
              <option value="0">关闭</option>
              <option value="1">开启</option>
            </select>
          </label>
        </div>
        <div class="actions">
          <button class="primary" type="submit">保存配置</button>
          <button type="button" id="testQb">测试 qB</button>
        </div>
        <div id="message" class="notice">就绪</div>
      </form>
    </section>

    <div class="right">
      <section>
        <div class="head">
          <h2>任务</h2>
          <button type="button" id="refresh">刷新</button>
        </div>
        <div class="status">
          <div>
            状态：<span id="state" class="pill">未知</span>
            <span id="pid" class="muted"></span>
          </div>
          <div class="actions">
            <button class="primary" type="button" id="start">启动自动放魔法</button>
            <button class="danger" type="button" id="stop">停止</button>
          </div>
        </div>
      </section>
      <section>
        <div class="head">
          <h2>放魔记录</h2>
          <button type="button" id="refreshRecords">刷新记录</button>
        </div>
        <div class="records">
          <table>
            <thead>
              <tr>
                <th>状态</th>
                <th>时间</th>
                <th>TID</th>
                <th>Hash</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody id="recordsBody"></tbody>
          </table>
        </div>
      </section>
      <section>
        <div class="head">
          <h2>日志</h2>
          <button type="button" id="refreshLogs">刷新日志</button>
        </div>
        <div class="log-wrap">
          <pre id="logs"></pre>
        </div>
      </section>
    </div>
  </main>
  <script>
    const form = document.getElementById('configForm');
    const message = document.getElementById('message');
    const logs = document.getElementById('logs');
    const recordsBody = document.getElementById('recordsBody');
    const qbBody = document.getElementById('qbBody');
    let qbTargets = [];

    function setMessage(text) { message.textContent = text; }

    async function api(path, options = {}) {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.error || '请求失败');
      return data;
    }

    function fillConfig(config) {
      for (const [key, value] of Object.entries(config)) {
        const el = form.elements[key];
        if (el) el.value = value ?? '';
      }
      fillQbTargets(config.QB_TARGETS);
    }

    function fillQbTargets(rawTargets) {
      let targets = [];
      try {
        targets = JSON.parse(rawTargets || '[]');
        if (!Array.isArray(targets)) targets = [targets];
      } catch {
        targets = [];
      }
      qbTargets = targets.length ? targets : [{ name: 'qB 1', host: 'http://127.0.0.1', port: 8080, username: '', password: '' }];
      renderQbTargets();
    }

    function escapeAttr(value) {
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('"', '&quot;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
    }

    function renderQbTargets() {
      qbBody.innerHTML = '';
      qbTargets.forEach((target, index) => {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td><input data-qb-field="name" value="${escapeAttr(target.name || `qB ${index + 1}`)}"></td>
          <td><input data-qb-field="host" placeholder="http://127.0.0.1" value="${escapeAttr(target.host || '')}"></td>
          <td><input data-qb-field="port" inputmode="numeric" value="${escapeAttr(target.port || 8080)}"></td>
          <td><input data-qb-field="username" value="${escapeAttr(target.username || '')}"></td>
          <td><input data-qb-field="password" type="password" autocomplete="off" value="${escapeAttr(target.password || '')}"></td>
          <td><button type="button" data-qb-remove="${index}">删除</button></td>
        `;
        qbBody.appendChild(row);
      });
    }

    function collectQbTargets() {
      const targets = [];
      qbBody.querySelectorAll('tr').forEach((row, index) => {
        const field = name => row.querySelector(`[data-qb-field="${name}"]`).value;
        const host = field('host').trim();
        if (!host) return;
        targets.push({
          name: field('name').trim() || `qB ${index + 1}`,
          host,
          port: Number(field('port') || 8080),
          username: field('username'),
          password: field('password')
        });
      });
      return targets;
    }

    function readConfig() {
      const config = {};
      for (const el of form.elements) {
        if (el.name && !el.name.startsWith('QB_')) config[el.name] = el.value;
      }
      config.QB_TARGETS = JSON.stringify(collectQbTargets(), null, 2);
      config.MAGIC_SELF_ENABLE = '1';
      return config;
    }

    function renderStatus(process) {
      const state = document.getElementById('state');
      const pid = document.getElementById('pid');
      state.textContent = process.running ? '运行中' : '已停止';
      state.className = 'pill' + (process.running ? ' running' : '');
      pid.textContent = process.running ? `PID ${process.pid}` : '';
    }

    async function saveConfig() {
      return api('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(readConfig())
      });
    }

    async function refresh() {
      const data = await api('/api/status');
      fillConfig(data.config);
      renderStatus(data.process);
      await refreshRecords();
      await refreshLogs();
    }

    async function refreshLogs() {
      const data = await api('/api/logs');
      logs.textContent = data.logs || '';
      logs.scrollTop = logs.scrollHeight;
    }

    function renderRecords(records) {
      recordsBody.innerHTML = '';
      if (!records.length) {
        const row = document.createElement('tr');
        row.innerHTML = '<td colspan="5" class="muted">暂无记录</td>';
        recordsBody.appendChild(row);
        return;
      }
      for (const item of records) {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td>${item.status}</td>
          <td>${item.time || ''}</td>
          <td>${item.tid || ''}</td>
          <td class="hash">${item.hash || ''}</td>
          <td>${item.note || ''}</td>
        `;
        recordsBody.appendChild(row);
      }
    }

    async function refreshRecords() {
      const data = await api('/api/records');
      renderRecords(data.records || []);
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await saveConfig();
        setMessage('配置已保存');
      } catch (error) {
        setMessage(error.message);
      }
    });

    document.getElementById('testQb').addEventListener('click', async () => {
      try {
        await saveConfig();
        const data = await api('/api/test-qb', { method: 'POST' });
        setMessage('qB 测试成功：' + data.targets.map(t => `${t.name}: ${t.version}, ${t.torrent_count} 个种子`).join('；'));
      } catch (error) {
        setMessage(error.message);
      }
    });

    document.getElementById('start').addEventListener('click', async () => {
      try {
        await saveConfig();
        const data = await api('/api/start', { method: 'POST' });
        setMessage(data.message);
        await refresh();
      } catch (error) {
        setMessage(error.message);
      }
    });

    document.getElementById('stop').addEventListener('click', async () => {
      try {
        const data = await api('/api/stop', { method: 'POST' });
        setMessage(data.message);
        await refresh();
      } catch (error) {
        setMessage(error.message);
      }
    });

    document.getElementById('refresh').addEventListener('click', refresh);
    document.getElementById('refreshLogs').addEventListener('click', refreshLogs);
    document.getElementById('refreshRecords').addEventListener('click', refreshRecords);
    document.getElementById('addQb').addEventListener('click', () => {
      qbTargets = collectQbTargets();
      qbTargets.push({ name: `qB ${qbTargets.length + 1}`, host: '', port: 8080, username: '', password: '' });
      renderQbTargets();
    });
    qbBody.addEventListener('click', (event) => {
      const remove = event.target.dataset.qbRemove;
      if (remove === undefined) return;
      qbTargets = collectQbTargets();
      qbTargets.splice(Number(remove), 1);
      if (!qbTargets.length) qbTargets.push({ name: 'qB 1', host: 'http://127.0.0.1', port: 8080, username: '', password: '' });
      renderQbTargets();
    });
    setInterval(refreshLogs, 4000);
    setInterval(refreshRecords, 10000);
    setInterval(() => document.getElementById('clock').textContent = new Date().toLocaleString(), 1000);
    refresh().catch(error => setMessage(error.message));
  </script>
</body>
</html>'''


def load_config():
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            config.update(json.loads(CONFIG_PATH.read_text(encoding='utf-8')))
        except json.JSONDecodeError:
            pass
    return config


def save_config(config):
    cleaned = DEFAULT_CONFIG.copy()
    for key in cleaned:
        cleaned[key] = str(config.get(key, cleaned[key]))
    json.loads(cleaned['QB_TARGETS'])
    ratio = float(cleaned['MAGIC_UPLOAD_RATIO'])
    if ratio < 1.3 or ratio > 2.33:
        raise ValueError('上传倍率必须在 1.3 到 2.33 之间')
    cleaned['MAGIC_UPLOAD_RATIO'] = str(ratio)
    existing_skip_ratio = float(cleaned['MAGIC_EXISTING_SKIP_RATIO'])
    if existing_skip_ratio < 1.3 or existing_skip_ratio > 2.33:
        raise ValueError('已有上传跳过倍率必须在 1.3 到 2.33 之间')
    cleaned['MAGIC_EXISTING_SKIP_RATIO'] = str(existing_skip_ratio)
    if CONFIG_PATH.exists():
        (ROOT / 'webui_config.json.bak').write_text(CONFIG_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    CONFIG_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding='utf-8')
    return cleaned


def parse_qb_targets(config):
    targets = json.loads(str(config.get('QB_TARGETS') or '').strip())
    if isinstance(targets, dict):
        targets = [targets]
    normalized = []
    for index, target in enumerate(targets, start=1):
        host = str(target.get('host') or '').strip()
        if not host:
            continue
        normalized.append({
            'name': str(target.get('name') or f'qB {index}'),
            'host': host,
            'port': int(target.get('port') or 8080),
            'username': str(target.get('username') or ''),
            'password': str(target.get('password') or ''),
        })
    if not normalized:
        raise ValueError('No qBittorrent targets configured')
    return normalized


def env_from_config():
    env = os.environ.copy()
    env.update(load_config())
    env['PYTHONUTF8'] = '1'
    return env


def process_status():
    if PROCESS is None:
        return {'running': False, 'pid': None}
    code = PROCESS.poll()
    return {'running': code is None, 'pid': PROCESS.pid, 'returncode': code}


def test_qb():
    results = []
    for target in parse_qb_targets(load_config()):
        client = qbittorrentapi.Client(
            host=target['host'],
            port=target['port'],
            username=target['username'],
            password=target['password'],
        )
        client.auth_log_in()
        torrents = client.torrents_info()
        results.append({
            'name': target['name'],
            'version': client.app.version,
            'api_version': client.app.web_api_version,
            'torrent_count': len(torrents),
        })
    return {'targets': results}


def stop_external_auto_magic():
    current_pid = str(PROCESS.pid) if PROCESS and PROCESS.poll() is None else ''
    if os.name != 'nt':
        pattern = str(ROOT / 'auto_magic_seeds.py')
        try:
            output = subprocess.check_output(['pgrep', '-f', pattern], text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return
        for pid in output.split():
            if pid and pid != current_pid:
                subprocess.run(['kill', '-TERM', pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return

    script = (
        "$current = '" + current_pid + "'; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*auto_magic_seeds.py*' "
        "-and ($current -eq '' -or $_.ProcessId -ne [int]$current) } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def start_auto_magic():
    global PROCESS
    with LOCK:
        if PROCESS and PROCESS.poll() is None:
            return '自动放魔法已经在运行'
        if not load_config().get('U2_COOKIE'):
            raise RuntimeError('请先填写 U2 Cookie')
        if not PYTHON.exists():
            raise RuntimeError(f'Python venv not found: {PYTHON}')
        stop_external_auto_magic()
        LOG_DIR.mkdir(exist_ok=True)
        log = (LOG_DIR / 'auto_magic.out.log').open('ab', buffering=0)
        PROCESS = subprocess.Popen(
            [str(PYTHON), str(ROOT / 'auto_magic_seeds.py')],
            cwd=str(ROOT),
            env=env_from_config(),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
    return '自动放魔法已启动'


def stop_auto_magic():
    global PROCESS
    with LOCK:
        if not PROCESS or PROCESS.poll() is not None:
            return '自动放魔法没有运行'
        PROCESS.terminate()
        try:
            PROCESS.wait(timeout=8)
        except subprocess.TimeoutExpired:
            PROCESS.kill()
    return '自动放魔法已停止'


def read_logs():
    chunks = []
    for path in [LOG_DIR / 'auto_magic.out.log', AUTO_MAGIC_LOG_PATH]:
        if path.exists():
            chunks.append(f'===== {path.name} =====\n')
            chunks.append(path.read_bytes()[-50000:].decode('utf-8', errors='replace'))
    return '\n'.join(chunks)


def format_ts(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ''


def read_magic_records():
    records = []
    data_path = AUTO_MAGIC_DATA_PATH
    if data_path.exists():
        try:
            data = json.loads(data_path.read_text(encoding='utf-8') or '{}')
        except json.JSONDecodeError:
            data = {}
        for torrent_hash, info in data.items():
            if 'uc' in info:
                records.append({
                    'status': '待确认',
                    'time': '',
                    'tid': str(info.get('tid') or ''),
                    'hash': torrent_hash,
                    'note': f"估算 UC {info['uc']}",
                    'sort': 0,
                })

    log_pattern = re.compile(
        r'^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ .*? - (?P<msg>.*)$'
    )
    sent_pattern = re.compile(
        r"Sent a .*? magic to torrent (?P<hash>[0-9a-f]{40}), tid: (?P<tid>\d+).*?uc usage (?P<uc>-?\d+), 24h total (?P<total>-?\d+)"
    )
    existed_pattern = re.compile(
        r"Torrent (?P<hash>[0-9a-f]{40}), id: (?P<tid>\d+): (?P<ratio>[\d.]+)x upload magic existed!"
    )
    failed_pattern = re.compile(
        r"Failed to send magic to torrent (?P<hash>[0-9a-f]{40}), id: (?P<tid>\d+)"
    )

    for path in [AUTO_MAGIC_LOG_PATH, LOG_DIR / 'auto_magic.out.log']:
        if not path.exists():
            continue
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()[-300:]
        for line in lines:
            match = log_pattern.match(line)
            if not match:
                continue
            msg = match.group('msg')
            item = None
            sent = sent_pattern.search(msg)
            existed = existed_pattern.search(msg)
            failed = failed_pattern.search(msg)
            if sent:
                item = {
                    'status': '已发送',
                    'tid': sent.group('tid'),
                    'hash': sent.group('hash'),
                    'note': f"消耗 UC {sent.group('uc')}，24h 合计 {sent.group('total')}",
                }
            elif existed:
                item = {
                    'status': '已存在',
                    'tid': existed.group('tid'),
                    'hash': existed.group('hash'),
                    'note': f"检测到 {existed.group('ratio')}x 上传魔法已存在，未重复放",
                }
            elif failed:
                item = {
                    'status': '失败',
                    'tid': failed.group('tid'),
                    'hash': failed.group('hash'),
                    'note': '发送魔法失败，查看日志详情',
                }
            if item:
                item['time'] = match.group('time')
                try:
                    item['sort'] = int(datetime.strptime(item['time'], '%Y-%m-%d %H:%M:%S').timestamp())
                except ValueError:
                    item['sort'] = 0
                records.append(item)

    records.sort(key=lambda item: item.get('sort', 0), reverse=True)
    merged = {}
    for item in records:
        tid = item.get('tid') or ''
        note = item.get('note') or ''
        if not item.get('time'):
            rank = 0
        elif '24h' in note:
            rank = 3
        elif 'x ' in note:
            rank = 1
        elif note:
            rank = 2
        else:
            rank = 0
        key = f"tid:{tid}" if tid else f"raw:{item.get('status')}:{item.get('time')}:{item.get('hash')}:{note}"
        existing = merged.get(key)
        if not existing or rank > existing.get('_rank', 0):
            item['_rank'] = rank
            merged[key] = item

    unique = sorted(merged.values(), key=lambda item: item.get('sort', 0), reverse=True)
    for item in unique:
        item.pop('sort', None)
        item.pop('_rank', None)
    return unique[:100]

    unique = []
    seen = set()
    for item in records:
        if item['status'] == '已存在':
            key = (item['status'], item.get('tid'), item.get('hash'), item.get('note'))
        else:
            key = (item['status'], item.get('time'), item.get('tid'), item.get('hash'), item.get('note'))
        if key in seen:
            continue
        seen.add(key)
        item.pop('sort', None)
        unique.append(item)
    return unique[:100]


def send_json(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def auth_credentials():
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        LOG_DIR.mkdir(exist_ok=True)
        with (LOG_DIR / 'webui.out.log').open('a', encoding='utf-8') as fp:
            fp.write('%s - %s\n' % (self.address_string(), fmt % args))

    def read_json(self):
        length = int(self.headers.get('Content-Length', '0') or '0')
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def is_authorized(self):
        credentials = auth_credentials()
        if not credentials:
            return True
        expected_username, expected_password = credentials
        header = self.headers.get('Authorization', '')
        if not header.startswith('Basic '):
            return False
        try:
            decoded = base64.b64decode(header[6:], validate=True).decode('utf-8')
            username, password = decoded.split(':', 1)
        except Exception:
            return False
        return (
            hmac.compare_digest(username, expected_username)
            and hmac.compare_digest(password, expected_password)
        )

    def require_auth(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', f'Basic realm="{AUTH_REALM}", charset="UTF-8"')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        if not self.is_authorized():
            self.require_auth()
            return
        parsed = urlparse(self.path)
        if parsed.path == '/':
            body = HTML.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == '/api/status':
            send_json(self, {'ok': True, 'config': load_config(), 'process': process_status()})
            return
        if parsed.path == '/api/logs':
            send_json(self, {'ok': True, 'logs': read_logs()})
            return
        if parsed.path == '/api/records':
            send_json(self, {'ok': True, 'records': read_magic_records()})
            return
        send_json(self, {'ok': False, 'error': 'Not found'}, 404)

    def do_POST(self):
        if not self.is_authorized():
            self.require_auth()
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == '/api/config':
                send_json(self, {'ok': True, 'config': save_config(self.read_json())})
                return
            if parsed.path == '/api/test-qb':
                send_json(self, {'ok': True, **test_qb()})
                return
            if parsed.path == '/api/start':
                send_json(self, {'ok': True, 'message': start_auto_magic()})
                return
            if parsed.path == '/api/stop':
                send_json(self, {'ok': True, 'message': stop_auto_magic()})
                return
            send_json(self, {'ok': False, 'error': 'Not found'}, 404)
        except Exception as exc:
            send_json(self, {'ok': False, 'error': f'{exc.__class__.__name__}: {exc}'}, 500)


def main():
    host = os.environ.get('U2_WEBUI_HOST', '127.0.0.1')
    port = int(os.environ.get('U2_WEBUI_PORT', '18765'))
    LOG_DIR.mkdir(exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f'Auto Magic Seeds WebUI: http://{host}:{port}')
    if auth_credentials():
        print('WebUI basic auth: enabled')
    else:
        print('WebUI basic auth: disabled')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_auto_magic()
        server.server_close()


if __name__ == '__main__':
    sys.exit(main())
