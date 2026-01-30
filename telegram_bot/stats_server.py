"""
Lightweight stats dashboard server
Uses only Python stdlib - no extra dependencies
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from stats import get_stats

PORT = int(os.environ.get("STATS_PORT", 8080))


class StatsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/stats":
            self.send_json(get_stats())
        elif self.path == "/" or self.path == "/stats":
            self.send_html()
        elif self.path == "/health":
            self.send_json({"status": "ok"})
        else:
            self.send_error(404)

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode())

    def send_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(DASHBOARD_HTML.encode())

    def log_message(self, format, *args):
        pass  # Suppress logging


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VK Teams Export Bot - Stats</title>
    <style>
        :root { --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --accent: #3b82f6; --green: #22c55e; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); padding: 20px; }
        h1 { margin-bottom: 20px; font-size: 24px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .card { background: var(--card); padding: 20px; border-radius: 12px; }
        .card-title { font-size: 12px; color: #94a3b8; text-transform: uppercase; margin-bottom: 8px; }
        .card-value { font-size: 32px; font-weight: 600; color: var(--accent); }
        .card-value.green { color: var(--green); }
        table { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 12px; overflow: hidden; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #334155; }
        th { background: #334155; font-size: 12px; text-transform: uppercase; }
        .refresh-btn { background: var(--accent); color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; margin-bottom: 20px; }
        .refresh-btn:hover { opacity: 0.9; }
        .updated { font-size: 12px; color: #64748b; margin-bottom: 10px; }
    </style>
</head>
<body>
    <h1>VK Teams Export Bot</h1>
    <button class="refresh-btn" onclick="loadStats()">Refresh</button>
    <div class="updated" id="updated"></div>

    <div class="grid">
        <div class="card">
            <div class="card-title">Active users (1h)</div>
            <div class="card-value green" id="active-hour">-</div>
        </div>
        <div class="card">
            <div class="card-title">Active users (7d)</div>
            <div class="card-value" id="active-week">-</div>
        </div>
        <div class="card">
            <div class="card-title">Exports today</div>
            <div class="card-value green" id="exports-today">-</div>
        </div>
        <div class="card">
            <div class="card-title">Total exports</div>
            <div class="card-value" id="total-exports">-</div>
        </div>
        <div class="card">
            <div class="card-title">Auth today</div>
            <div class="card-value" id="auth-today">-</div>
        </div>
        <div class="card">
            <div class="card-title">Events today</div>
            <div class="card-value" id="events-today">-</div>
        </div>
    </div>

    <h2 style="margin: 20px 0 15px;">Recent Users</h2>
    <table>
        <thead>
            <tr><th>User ID</th><th>Username</th><th>Email</th><th>Last Seen</th></tr>
        </thead>
        <tbody id="users-table"></tbody>
    </table>

    <script>
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                document.getElementById('active-hour').textContent = data.active_users_hour || 0;
                document.getElementById('active-week').textContent = data.active_users_week || 0;
                document.getElementById('exports-today').textContent = data.exports_today || 0;
                document.getElementById('total-exports').textContent = data.total_exports || 0;
                document.getElementById('auth-today').textContent = data.auth_today || 0;
                document.getElementById('events-today').textContent = data.total_events_today || 0;
                document.getElementById('updated').textContent = 'Updated: ' + new Date().toLocaleString();

                const tbody = document.getElementById('users-table');
                tbody.innerHTML = (data.recent_users || []).map(u => `
                    <tr>
                        <td>${u.user_id}</td>
                        <td>${u.username || '-'}</td>
                        <td>${u.email || '-'}</td>
                        <td>${new Date(u.last_seen).toLocaleString()}</td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error(e);
            }
        }

        loadStats();
        setInterval(loadStats, 30000);
    </script>
</body>
</html>"""


if __name__ == "__main__":
    print(f"Stats server running on http://0.0.0.0:{PORT}")
    server = HTTPServer(("0.0.0.0", PORT), StatsHandler)
    server.serve_forever()
