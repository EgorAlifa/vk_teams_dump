"""
Lightweight stats dashboard server
Uses only Python stdlib - no extra dependencies
"""

import json
import os
import shutil
import threading
import time
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from stats import get_stats, save_metrics, get_metrics_history

PORT = int(os.environ.get("STATS_PORT", 8080))
METRICS_INTERVAL = 60  # Сохранять метрики каждые 60 секунд

EXPORTS_DIR = "/tmp/vkteams_exports"
FILES_TTL = 600  # 10 минут в секундах
MIN_FREE_DISK_GB = 5  # Не создавать новые файлы если свободно меньше 5 GB

os.makedirs(EXPORTS_DIR, exist_ok=True)


def metrics_collector():
    """Background thread to collect metrics periodically"""
    while True:
        try:
            save_metrics()
        except Exception as e:
            print(f"Metrics collector error: {e}")
        time.sleep(METRICS_INTERVAL)


def exports_cleanup():
    """Background thread: удаляет папки экспорта старше TTL"""
    while True:
        try:
            now = time.time()
            if os.path.isdir(EXPORTS_DIR):
                for entry in os.listdir(EXPORTS_DIR):
                    entry_path = os.path.join(EXPORTS_DIR, entry)
                    if os.path.isdir(entry_path):
                        mtime = os.path.getmtime(entry_path)
                        if now - mtime > FILES_TTL:
                            shutil.rmtree(entry_path, ignore_errors=True)
                            print(f"🗑️ Cleaned up expired export: {entry}")
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(30)  # Проверяем каждые 30 секунд


def get_free_disk_gb() -> float:
    """Свободное место на диске в GB"""
    try:
        st = os.statvfs("/tmp")
        return (st.f_bavail * st.f_frsize) / (1024 ** 3)
    except Exception:
        return 0.0


class StatsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            print(f"Request: {self.path}")
            if self.path == "/api/stats":
                self.send_json(get_stats())
            elif self.path == "/api/metrics/history":
                self.send_json(get_metrics_history(24))
            elif self.path == "/" or self.path == "/stats":
                self.send_html()
            elif self.path == "/health":
                self.send_json({"status": "ok"})
            elif self.path.startswith("/files/"):
                self.serve_export_file()
            else:
                self.send_error(404)
        except Exception as e:
            print(f"ERROR handling request {self.path}: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500)

    def send_json(self, data):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode())
        except Exception as e:
            print(f"ERROR sending JSON: {e}")
            raise

    def send_html(self):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        except Exception as e:
            print(f"ERROR sending HTML: {e}")
            raise

    def serve_export_file(self):
        """Раздача файлов экспорта: /files/{uuid}/{filename}"""
        # path = /files/{uuid}/{filename}
        parts = self.path.split("/")
        # parts: ['', 'files', uuid, filename...]
        if len(parts) < 4:
            self.send_error(404)
            return

        uuid = parts[2]
        filename = "/".join(parts[3:])  # filename может содержать подпапки

        # Защита от path traversal
        if ".." in uuid or ".." in filename or uuid.startswith("/") or filename.startswith("/"):
            self.send_error(403)
            return

        file_path = os.path.join(EXPORTS_DIR, uuid, filename)
        # Проверяем что path не выходит за EXPORTS_DIR
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(os.path.realpath(EXPORTS_DIR)):
            self.send_error(403)
            return

        if not os.path.isfile(real_path):
            print(f"404: real_path={real_path}, dir_exists={os.path.isdir(os.path.dirname(real_path))}, exports_dir_contents={os.listdir(EXPORTS_DIR) if os.path.isdir(EXPORTS_DIR) else 'NO DIR'}")
            self.send_error(404)
            return

        # Определяем content-type
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "application/octet-stream"

        try:
            file_size = os.path.getsize(real_path)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(filename)}"')
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            with open(real_path, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except Exception as e:
            print(f"ERROR serving file {real_path}: {e}")

    def log_message(self, format, *args):
        # Log important messages
        print(f"HTTP: {format % args}")


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VK Teams Export Bot</title>
    <style>
        :root {
            --bg: #0a0a0f;
            --bg2: #12121a;
            --card: #1a1a24;
            --card-hover: #22222e;
            --border: #2a2a3a;
            --text: #e4e4e7;
            --text2: #71717a;
            --accent: #6366f1;
            --accent2: #818cf8;
            --green: #22c55e;
            --green-bg: rgba(34,197,94,0.1);
            --yellow: #eab308;
            --yellow-bg: rgba(234,179,8,0.1);
            --red: #ef4444;
            --red-bg: rgba(239,68,68,0.1);
            --blue: #3b82f6;
            --blue-bg: rgba(59,130,246,0.1);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 24px; }

        /* Header */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 32px;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border);
        }
        .header h1 {
            font-size: 24px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .header h1::before {
            content: '';
            width: 8px;
            height: 8px;
            background: var(--green);
            border-radius: 50%;
            box-shadow: 0 0 12px var(--green);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .header-right {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .updated {
            font-size: 13px;
            color: var(--text2);
        }
        .refresh-btn {
            background: var(--card);
            color: var(--text);
            border: 1px solid var(--border);
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .refresh-btn:hover { background: var(--card-hover); border-color: var(--accent); }
        .refresh-btn.loading svg { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

        /* Section titles */
        .section-title {
            font-size: 14px;
            font-weight: 600;
            color: var(--text2);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .section-title .count {
            background: var(--card);
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 12px;
        }

        /* System metrics */
        .system-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            margin-bottom: 32px;
        }
        .metric-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }
        .metric-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        .metric-label {
            font-size: 13px;
            color: var(--text2);
            font-weight: 500;
        }
        .metric-value {
            font-size: 28px;
            font-weight: 700;
        }
        .metric-bar {
            height: 6px;
            background: var(--bg2);
            border-radius: 3px;
            overflow: hidden;
            margin-top: 12px;
        }
        .metric-bar-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.5s ease;
        }
        .metric-bar-fill.green { background: linear-gradient(90deg, #22c55e, #4ade80); }
        .metric-bar-fill.yellow { background: linear-gradient(90deg, #eab308, #facc15); }
        .metric-bar-fill.red { background: linear-gradient(90deg, #ef4444, #f87171); }
        .metric-detail {
            font-size: 12px;
            color: var(--text2);
            margin-top: 8px;
        }

        /* Stats grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 12px;
            margin-bottom: 32px;
        }
        .stat-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
            transition: all 0.2s;
        }
        .stat-card:hover {
            border-color: var(--accent);
            transform: translateY(-2px);
        }
        .stat-label {
            font-size: 11px;
            color: var(--text2);
            text-transform: uppercase;
            letter-spacing: 0.3px;
            margin-bottom: 8px;
        }
        .stat-value {
            font-size: 24px;
            font-weight: 700;
        }
        .stat-value.accent { color: var(--accent2); }
        .stat-value.green { color: var(--green); }

        /* Table */
        .table-wrapper {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
        }
        .table-scroll {
            max-height: 450px;
            overflow-y: auto;
        }
        .table-scroll::-webkit-scrollbar { width: 6px; }
        .table-scroll::-webkit-scrollbar-track { background: var(--bg2); }
        .table-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        table { width: 100%; border-collapse: collapse; }
        th {
            background: var(--bg2);
            padding: 12px 16px;
            text-align: left;
            font-size: 11px;
            font-weight: 600;
            color: var(--text2);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            position: sticky;
            top: 0;
            z-index: 1;
        }
        td {
            padding: 12px 16px;
            font-size: 13px;
            border-top: 1px solid var(--border);
        }
        tr:hover td { background: var(--bg2); }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 500;
        }
        .badge.ok { background: var(--green-bg); color: var(--green); }
        .badge.err { background: var(--red-bg); color: var(--red); }
        .badge.na { background: var(--card-hover); color: var(--text2); }
        .errors-cell {
            max-width: 400px;
            font-size: 11px;
            color: var(--yellow);
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.4;
        }
        .mono { font-family: 'SF Mono', Monaco, monospace; font-size: 12px; }

        /* Charts */
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
            margin-bottom: 32px;
        }
        .chart-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }
        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        .chart-title {
            font-size: 13px;
            color: var(--text2);
            font-weight: 500;
        }
        .chart-legend {
            display: flex;
            gap: 12px;
            font-size: 11px;
            color: var(--text2);
        }
        .chart-legend span::before {
            content: '';
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 2px;
            margin-right: 4px;
        }
        .legend-cpu::before { background: #6366f1; }
        .legend-mem::before { background: #22c55e; }
        .chart-container {
            position: relative;
            height: 150px;
        }
        .chart-container canvas {
            width: 100% !important;
            height: 100% !important;
        }
        .chart-time {
            display: flex;
            justify-content: space-between;
            font-size: 10px;
            color: var(--text2);
            margin-top: 8px;
        }
        .no-data {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 150px;
            color: var(--text2);
            font-size: 13px;
        }

        @media (max-width: 1200px) {
            .stats-grid { grid-template-columns: repeat(3, 1fr); }
            .charts-grid { grid-template-columns: 1fr; }
        }
        @media (max-width: 768px) {
            .system-grid { grid-template-columns: 1fr; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .header { flex-direction: column; gap: 16px; align-items: flex-start; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>VK Teams Export Bot</h1>
            <div class="header-right">
                <span class="updated" id="updated">Loading...</span>
                <button class="refresh-btn" onclick="loadStats()" id="refreshBtn">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 12a9 9 0 11-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>
                        <path d="M21 3v5h-5"/>
                    </svg>
                    Обновить
                </button>
            </div>
        </header>

        <div class="section-title">Система</div>
        <div class="system-grid">
            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-label">CPU</span>
                    <span class="metric-value" id="cpu-percent">0%</span>
                </div>
                <div class="metric-bar"><div class="metric-bar-fill green" id="cpu-bar" style="width:0%"></div></div>
                <div class="metric-detail" id="cpu-detail">Load: 0.0 / 0 cores</div>
            </div>
            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-label">Memory</span>
                    <span class="metric-value" id="mem-percent">0%</span>
                </div>
                <div class="metric-bar"><div class="metric-bar-fill green" id="mem-bar" style="width:0%"></div></div>
                <div class="metric-detail" id="mem-detail">0 / 0 GB</div>
            </div>
            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-label">Disk</span>
                    <span class="metric-value" id="disk-percent">0%</span>
                </div>
                <div class="metric-bar"><div class="metric-bar-fill green" id="disk-bar" style="width:0%"></div></div>
                <div class="metric-detail" id="disk-detail">0 / 0 GB</div>
            </div>
        </div>

        <div class="section-title">История (24ч)</div>
        <div class="charts-grid">
            <div class="chart-card">
                <div class="chart-header">
                    <span class="chart-title">CPU / Memory</span>
                    <div class="chart-legend">
                        <span class="legend-cpu">CPU</span>
                        <span class="legend-mem">Memory</span>
                    </div>
                </div>
                <div class="chart-container" id="chart-cpu-mem">
                    <canvas id="canvas-cpu-mem"></canvas>
                </div>
                <div class="chart-time">
                    <span id="chart-time-start">-</span>
                    <span id="chart-time-end">сейчас</span>
                </div>
            </div>
            <div class="chart-card">
                <div class="chart-header">
                    <span class="chart-title">Memory Usage (GB)</span>
                </div>
                <div class="chart-container" id="chart-mem-gb">
                    <canvas id="canvas-mem-gb"></canvas>
                </div>
                <div class="chart-time">
                    <span id="chart-time-start2">-</span>
                    <span id="chart-time-end2">сейчас</span>
                </div>
            </div>
        </div>

        <div class="section-title">Статистика</div>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Активных (1ч)</div>
                <div class="stat-value green" id="active-hour">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Активных (7д)</div>
                <div class="stat-value" id="active-week">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Активных (30д)</div>
                <div class="stat-value accent" id="active-month">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Экспортов сегодня</div>
                <div class="stat-value green" id="exports-today">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Всего экспортов</div>
                <div class="stat-value accent" id="total-exports">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Авторизаций</div>
                <div class="stat-value" id="auth-today">0</div>
            </div>
        </div>

        <div class="section-title">Пользователи <span class="count" id="user-count">0</span></div>
        <div class="table-wrapper">
            <div class="table-scroll">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Username</th>
                            <th>Email</th>
                            <th>Последняя активность</th>
                            <th>Статус</th>
                            <th>Ошибки</th>
                        </tr>
                    </thead>
                    <tbody id="users-table"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        function getBarColor(percent) {
            if (percent >= 90) return 'red';
            if (percent >= 70) return 'yellow';
            return 'green';
        }

        async function loadStats() {
            const btn = document.getElementById('refreshBtn');
            btn.classList.add('loading');

            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                // System metrics
                const sys = data.system || {};
                const cpuPct = sys.cpu_percent || 0;
                const memPct = sys.mem_percent || 0;
                const diskPct = sys.disk_percent || 0;

                document.getElementById('cpu-percent').textContent = cpuPct + '%';
                document.getElementById('cpu-bar').style.width = Math.min(cpuPct, 100) + '%';
                document.getElementById('cpu-bar').className = 'metric-bar-fill ' + getBarColor(cpuPct);
                document.getElementById('cpu-detail').textContent =
                    'Load: ' + (sys.cpu_load_1m || 0).toFixed(1) + ' / ' + (sys.cpu_cores || 0) + ' cores';

                document.getElementById('mem-percent').textContent = memPct + '%';
                document.getElementById('mem-bar').style.width = memPct + '%';
                document.getElementById('mem-bar').className = 'metric-bar-fill ' + getBarColor(memPct);
                document.getElementById('mem-detail').textContent =
                    (sys.mem_used_gb || 0) + ' / ' + (sys.mem_total_gb || 0) + ' GB';

                document.getElementById('disk-percent').textContent = diskPct + '%';
                document.getElementById('disk-bar').style.width = diskPct + '%';
                document.getElementById('disk-bar').className = 'metric-bar-fill ' + getBarColor(diskPct);
                document.getElementById('disk-detail').textContent =
                    (sys.disk_used_gb || 0) + ' / ' + (sys.disk_total_gb || 0) + ' GB';

                // Stats
                document.getElementById('active-hour').textContent = data.active_users_hour || 0;
                document.getElementById('active-week').textContent = data.active_users_week || 0;
                document.getElementById('active-month').textContent = data.active_users_month || 0;
                document.getElementById('exports-today').textContent = data.exports_today || 0;
                document.getElementById('total-exports').textContent = data.total_exports || 0;
                document.getElementById('auth-today').textContent = data.auth_today || 0;

                const now = new Date();
                document.getElementById('updated').textContent =
                    now.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit', second: '2-digit'});

                // Users table
                const users = data.recent_users || [];
                document.getElementById('user-count').textContent = users.length;

                const tbody = document.getElementById('users-table');
                tbody.innerHTML = users.map(u => {
                    let badge;
                    if (u.last_export_time === null) {
                        badge = '<span class="badge na">Нет данных</span>';
                    } else if (u.last_export_success === 1) {
                        badge = '<span class="badge ok">✓ OK</span>';
                    } else {
                        badge = '<span class="badge err">✗ Ошибка</span>';
                    }
                    const errors = u.last_export_errors || '-';
                    const lastSeen = new Date(u.last_seen);
                    const timeStr = lastSeen.toLocaleString('ru-RU', {
                        day: '2-digit', month: '2-digit',
                        hour: '2-digit', minute: '2-digit'
                    });
                    return `
                        <tr>
                            <td class="mono">${u.user_id}</td>
                            <td>${u.username || '-'}</td>
                            <td>${u.email || '-'}</td>
                            <td>${timeStr}</td>
                            <td>${badge}</td>
                            <td class="errors-cell">${errors}</td>
                        </tr>
                    `;
                }).join('');

            } catch (e) {
                console.error(e);
            } finally {
                btn.classList.remove('loading');
            }
        }

        loadStats();
        setInterval(loadStats, 10000);

        // Charts
        function drawChart(canvasId, data, keys, colors, maxVal = 100, unit = '%') {
            const canvas = document.getElementById(canvasId);
            if (!canvas || !data.length) return;

            const ctx = canvas.getContext('2d');
            const rect = canvas.parentElement.getBoundingClientRect();
            canvas.width = rect.width * 2;
            canvas.height = rect.height * 2;
            ctx.scale(2, 2);

            const w = rect.width;
            const h = rect.height;
            const padding = { top: 15, right: 15, bottom: 25, left: 45 };
            const chartW = w - padding.left - padding.right;
            const chartH = h - padding.top - padding.bottom;

            ctx.clearRect(0, 0, w, h);

            // Background gradient
            const bgGrad = ctx.createLinearGradient(0, padding.top, 0, h - padding.bottom);
            bgGrad.addColorStop(0, 'rgba(99, 102, 241, 0.03)');
            bgGrad.addColorStop(1, 'rgba(99, 102, 241, 0)');
            ctx.fillStyle = bgGrad;
            ctx.fillRect(padding.left, padding.top, chartW, chartH);

            // Grid lines with labels
            ctx.strokeStyle = 'rgba(255,255,255,0.06)';
            ctx.lineWidth = 1;
            ctx.fillStyle = '#71717a';
            ctx.font = '10px -apple-system, system-ui, sans-serif';
            ctx.textAlign = 'right';

            for (let i = 0; i <= 4; i++) {
                const y = padding.top + (chartH / 4) * i;
                ctx.beginPath();
                ctx.moveTo(padding.left, y);
                ctx.lineTo(w - padding.right, y);
                ctx.stroke();

                const val = Math.round(maxVal - (maxVal / 4) * i);
                ctx.fillText(val + unit, padding.left - 8, y + 4);
            }

            // Time labels on X axis
            if (data.length > 0) {
                ctx.textAlign = 'center';
                ctx.fillStyle = '#52525b';
                const timePoints = [0, Math.floor(data.length / 2), data.length - 1];
                timePoints.forEach(idx => {
                    if (data[idx]) {
                        const x = padding.left + (idx / (data.length - 1)) * chartW;
                        const d = new Date(data[idx].timestamp);
                        ctx.fillText(d.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'}), x, h - 8);
                    }
                });
            }

            // Draw smooth lines with glow effect
            keys.forEach((key, ki) => {
                const color = colors[ki];

                // Glow effect
                ctx.shadowColor = color;
                ctx.shadowBlur = 8;
                ctx.strokeStyle = color;
                ctx.lineWidth = 2;
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
                ctx.beginPath();

                let lastX, lastY;
                data.forEach((point, i) => {
                    const x = padding.left + (i / Math.max(data.length - 1, 1)) * chartW;
                    const val = Math.min(point[key] || 0, maxVal);
                    const y = padding.top + chartH - (val / maxVal) * chartH;

                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                    lastX = x; lastY = y;
                });
                ctx.stroke();
                ctx.shadowBlur = 0;

                // Fill area under line with gradient
                if (lastX !== undefined) {
                    const grad = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartH);
                    grad.addColorStop(0, color.replace(')', ', 0.25)').replace('rgb', 'rgba'));
                    grad.addColorStop(1, color.replace(')', ', 0)').replace('rgb', 'rgba'));

                    ctx.lineTo(lastX, padding.top + chartH);
                    ctx.lineTo(padding.left, padding.top + chartH);
                    ctx.closePath();
                    ctx.fillStyle = grad;
                    ctx.fill();
                }

                // Draw current value indicator (last point)
                if (data.length > 0) {
                    const lastPoint = data[data.length - 1];
                    const val = Math.min(lastPoint[key] || 0, maxVal);
                    const x = padding.left + chartW;
                    const y = padding.top + chartH - (val / maxVal) * chartH;

                    ctx.beginPath();
                    ctx.arc(x, y, 4, 0, Math.PI * 2);
                    ctx.fillStyle = color;
                    ctx.fill();
                    ctx.strokeStyle = '#1a1a24';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                }
            });
        }

        async function loadHistory() {
            try {
                const res = await fetch('/api/metrics/history');
                const data = await res.json();

                if (!data.length) {
                    document.getElementById('chart-cpu-mem').innerHTML = '<div class="no-data">Нет данных. Подождите несколько минут.</div>';
                    document.getElementById('chart-mem-gb').innerHTML = '<div class="no-data">Нет данных</div>';
                    return;
                }

                // CPU/Memory percent chart
                drawChart('canvas-cpu-mem', data, ['cpu_percent', 'mem_percent'], ['rgb(99, 102, 241)', 'rgb(34, 197, 94)'], 100, '%');

                // Memory GB chart
                const maxMem = Math.ceil(Math.max(...data.map(d => d.mem_used_gb || 0)) * 1.2) || 10;
                drawChart('canvas-mem-gb', data, ['mem_used_gb'], ['rgb(34, 197, 94)'], maxMem, 'GB');

                // Time labels
                if (data.length > 0) {
                    const first = new Date(data[0].timestamp);
                    const last = new Date(data[data.length - 1].timestamp);
                    const fmt = d => d.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'});
                    document.getElementById('chart-time-start').textContent = fmt(first);
                    document.getElementById('chart-time-start2').textContent = fmt(first);
                }
            } catch (e) {
                console.error('Failed to load history:', e);
            }
        }

        loadHistory();
        setInterval(loadHistory, 60000);

        // Handle resize
        window.addEventListener('resize', () => {
            loadHistory();
        });
    </script>
</body>
</html>"""


if __name__ == "__main__":
    try:
        # Запускаем сборщик метрик в фоне
        collector_thread = threading.Thread(target=metrics_collector, daemon=True)
        collector_thread.start()
        print(f"Metrics collector started (interval: {METRICS_INTERVAL}s)")

        # Запускаем очистку файлов экспорта в фоне
        cleanup_thread = threading.Thread(target=exports_cleanup, daemon=True)
        cleanup_thread.start()
        print(f"Exports cleanup started (TTL: {FILES_TTL}s, dir: {EXPORTS_DIR})")

        # Сохраняем первую точку сразу
        try:
            save_metrics()
            print("Initial metrics saved")
        except Exception as e:
            print(f"Failed to save initial metrics: {e}")

        # Создаём и запускаем сервер
        print(f"Creating HTTP server on port {PORT}...")
        server = HTTPServer(("0.0.0.0", PORT), StatsHandler)
        print(f"Stats server running on http://0.0.0.0:{PORT}")
        print("Waiting for connections...")
        server.serve_forever()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)
