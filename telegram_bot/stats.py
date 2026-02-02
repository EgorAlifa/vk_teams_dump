"""
Simple statistics tracking with SQLite
Lightweight monitoring for VK Teams Export Bot
"""

import sqlite3
import os
import subprocess
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = os.environ.get("STATS_DB_PATH", "data/stats.db")


def get_system_metrics() -> dict:
    """Get system metrics (CPU, memory, disk)"""
    metrics = {}

    try:
        # CPU usage (from /proc/stat)
        with open('/proc/stat', 'r') as f:
            line = f.readline()
            fields = line.split()[1:5]
            idle = int(fields[3])
            total = sum(int(x) for x in fields)

        # Store for delta calculation (simple approach - instant load)
        with open('/proc/loadavg', 'r') as f:
            load = f.read().split()
            metrics['cpu_load_1m'] = float(load[0])
            metrics['cpu_load_5m'] = float(load[1])
            metrics['cpu_load_15m'] = float(load[2])

        # CPU cores
        cpu_count = os.cpu_count() or 1
        metrics['cpu_cores'] = cpu_count
        metrics['cpu_percent'] = round(metrics['cpu_load_1m'] / cpu_count * 100, 1)

    except Exception:
        metrics['cpu_percent'] = 0
        metrics['cpu_load_1m'] = 0

    try:
        # Memory (from /proc/meminfo)
        mem = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(':')] = int(parts[1])

        total_kb = mem.get('MemTotal', 0)
        available_kb = mem.get('MemAvailable', mem.get('MemFree', 0))
        used_kb = total_kb - available_kb

        metrics['mem_total_gb'] = round(total_kb / 1024 / 1024, 1)
        metrics['mem_used_gb'] = round(used_kb / 1024 / 1024, 1)
        metrics['mem_percent'] = round(used_kb / total_kb * 100, 1) if total_kb else 0

    except Exception:
        metrics['mem_percent'] = 0
        metrics['mem_total_gb'] = 0
        metrics['mem_used_gb'] = 0

    try:
        # Disk usage
        stat = os.statvfs('/')
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free

        metrics['disk_total_gb'] = round(total / 1024 / 1024 / 1024, 1)
        metrics['disk_used_gb'] = round(used / 1024 / 1024 / 1024, 1)
        metrics['disk_percent'] = round(used / total * 100, 1) if total else 0

    except Exception:
        metrics['disk_percent'] = 0
        metrics['disk_total_gb'] = 0
        metrics['disk_used_gb'] = 0

    return metrics


def init_db():
    """Initialize SQLite database"""
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)

    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                data TEXT
            );

            CREATE TABLE IF NOT EXISTS active_users (
                user_id INTEGER PRIMARY KEY,
                last_seen TEXT NOT NULL,
                username TEXT,
                email TEXT,
                last_export_time TEXT,
                last_export_success INTEGER,
                last_export_errors TEXT
            );

            CREATE TABLE IF NOT EXISTS metrics_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cpu_percent REAL,
                cpu_load REAL,
                mem_percent REAL,
                mem_used_gb REAL,
                disk_percent REAL
            );

            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics_history(timestamp);
        """)
        # Добавляем новые колонки если их нет (для совместимости)
        try:
            conn.execute("ALTER TABLE active_users ADD COLUMN last_export_time TEXT")
        except:
            pass
        try:
            conn.execute("ALTER TABLE active_users ADD COLUMN last_export_success INTEGER")
        except:
            pass
        try:
            conn.execute("ALTER TABLE active_users ADD COLUMN last_export_errors TEXT")
        except:
            pass


@contextmanager
def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_event(event_type: str, user_id: int = None, data: str = None):
    """Log an event"""
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO events (timestamp, event_type, user_id, data) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), event_type, user_id, data)
            )
    except Exception as e:
        print(f"Stats error: {e}")


def update_active_user(user_id: int, username: str = None, email: str = None):
    """Update active user"""
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO active_users (user_id, last_seen, username, email,
                    last_export_time, last_export_success, last_export_errors)
                VALUES (?, ?,
                    COALESCE(?, (SELECT username FROM active_users WHERE user_id = ?)),
                    COALESCE(?, (SELECT email FROM active_users WHERE user_id = ?)),
                    (SELECT last_export_time FROM active_users WHERE user_id = ?),
                    (SELECT last_export_success FROM active_users WHERE user_id = ?),
                    (SELECT last_export_errors FROM active_users WHERE user_id = ?)
                )
            """, (user_id, datetime.now().isoformat(), username, user_id, email, user_id,
                  user_id, user_id, user_id))
    except Exception as e:
        print(f"Stats error: {e}")


def update_user_export(user_id: int, success: bool, errors: list = None):
    """Update user's last export status"""
    try:
        with get_db() as conn:
            errors_text = "; ".join(errors[:5]) if errors else None  # Max 5 errors
            conn.execute("""
                UPDATE active_users
                SET last_export_time = ?,
                    last_export_success = ?,
                    last_export_errors = ?
                WHERE user_id = ?
            """, (datetime.now().isoformat(), 1 if success else 0, errors_text, user_id))
    except Exception as e:
        print(f"Stats error: {e}")


def save_metrics():
    """Save current system metrics to history (call periodically)"""
    try:
        metrics = get_system_metrics()
        with get_db() as conn:
            conn.execute("""
                INSERT INTO metrics_history (timestamp, cpu_percent, cpu_load, mem_percent, mem_used_gb, disk_percent)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                metrics.get('cpu_percent', 0),
                metrics.get('cpu_load_1m', 0),
                metrics.get('mem_percent', 0),
                metrics.get('mem_used_gb', 0),
                metrics.get('disk_percent', 0)
            ))
            # Удаляем старые записи (старше 24 часов)
            day_ago = (datetime.now() - timedelta(hours=24)).isoformat()
            conn.execute("DELETE FROM metrics_history WHERE timestamp < ?", (day_ago,))
    except Exception as e:
        print(f"Stats error saving metrics: {e}")


def get_metrics_history(hours: int = 24) -> list:
    """Get metrics history for the last N hours"""
    try:
        with get_db() as conn:
            since = (datetime.now() - timedelta(hours=hours)).isoformat()
            rows = conn.execute("""
                SELECT timestamp, cpu_percent, cpu_load, mem_percent, mem_used_gb, disk_percent
                FROM metrics_history
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            """, (since,)).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"Stats error getting metrics history: {e}")
        return []


def get_stats() -> dict:
    """Get statistics summary"""
    try:
        with get_db() as conn:
            now = datetime.now()
            today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            week_ago = (now - timedelta(days=7)).isoformat()
            month_ago = (now - timedelta(days=30)).isoformat()
            hour_ago = (now - timedelta(hours=1)).isoformat()

            # Total events today
            total_today = conn.execute(
                "SELECT COUNT(*) FROM events WHERE timestamp >= ?", (today,)
            ).fetchone()[0]

            # Events by type today
            events_by_type = dict(conn.execute("""
                SELECT event_type, COUNT(*)
                FROM events
                WHERE timestamp >= ?
                GROUP BY event_type
            """, (today,)).fetchall())

            # Active users (last hour)
            active_hour = conn.execute(
                "SELECT COUNT(*) FROM active_users WHERE last_seen >= ?", (hour_ago,)
            ).fetchone()[0]

            # Active users (last week)
            active_week = conn.execute(
                "SELECT COUNT(*) FROM active_users WHERE last_seen >= ?", (week_ago,)
            ).fetchone()[0]

            # Active users (last month)
            active_month = conn.execute(
                "SELECT COUNT(*) FROM active_users WHERE last_seen >= ?", (month_ago,)
            ).fetchone()[0]

            # Total exports
            total_exports = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'export_complete'"
            ).fetchone()[0]

            # Exports today
            exports_today = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'export_complete' AND timestamp >= ?",
                (today,)
            ).fetchone()[0]

            # Auth today
            auth_today = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'auth_success' AND timestamp >= ?",
                (today,)
            ).fetchone()[0]

            # Recent active users list (all users, sorted by last_seen)
            recent_users = conn.execute("""
                SELECT user_id, username, email, last_seen,
                       last_export_time, last_export_success, last_export_errors
                FROM active_users
                ORDER BY last_seen DESC
            """).fetchall()

            return {
                "timestamp": now.isoformat(),
                "total_events_today": total_today,
                "events_by_type": events_by_type,
                "active_users_hour": active_hour,
                "active_users_week": active_week,
                "active_users_month": active_month,
                "total_exports": total_exports,
                "exports_today": exports_today,
                "auth_today": auth_today,
                "recent_users": [dict(u) for u in recent_users],
                "system": get_system_metrics()
            }
    except Exception as e:
        return {"error": str(e)}


def get_active_user_ids(days: int = 30) -> list[int]:
    """Get list of recently active user IDs (for broadcast/notification)

    Args:
        days: Number of days to look back (default 30)
    """
    try:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with get_db() as conn:
            rows = conn.execute(
                "SELECT user_id FROM active_users WHERE last_seen >= ?", (cutoff,)
            ).fetchall()
            return [row[0] for row in rows]
    except Exception:
        return []


# Initialize on import
try:
    init_db()
except Exception as e:
    print(f"Failed to init stats DB: {e}")
