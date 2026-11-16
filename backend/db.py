import json
import sqlite3
import time
from contextlib import contextmanager

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS platforms (
 id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 adapter TEXT NOT NULL, base_url TEXT NOT NULL, proxy TEXT DEFAULT '', enabled INTEGER DEFAULT 1,
 builtin INTEGER DEFAULT 0, meta TEXT DEFAULT '{}', created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, platform_id INTEGER NOT NULL REFERENCES platforms(id) ON DELETE CASCADE,
 name TEXT NOT NULL, credential TEXT NOT NULL, credential_type TEXT DEFAULT 'cookie', status TEXT DEFAULT 'unknown',
 status_msg TEXT DEFAULT '', member_level TEXT DEFAULT '', quota_pct REAL, quota_json TEXT DEFAULT '{}',
 user_info TEXT DEFAULT '{}', check_at TEXT, last_used_at TEXT, request_count INTEGER DEFAULT 0,
 enabled INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS request_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, platform_key TEXT, model TEXT, ok INTEGER,
 latency_ms INTEGER, err TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_reqlog_time ON request_log(created_at);
CREATE TABLE IF NOT EXISTS rate_limit (
 scope TEXT NOT NULL, rkey TEXT NOT NULL, at REAL NOT NULL,
 PRIMARY KEY(scope, rkey)
);
CREATE TABLE IF NOT EXISTS tokens (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 token TEXT UNIQUE NOT NULL,
 platform_key TEXT DEFAULT '',
 enabled INTEGER DEFAULT 1,
 note TEXT DEFAULT '',
 created_at TEXT DEFAULT (datetime('now','localtime')),
 last_used_at TEXT,
 request_count INTEGER DEFAULT 0
);
"""

@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()

def init_db():
    with connect() as db:
        db.executescript(SCHEMA)
        seeds = [
            ("tabbit-domestic", "Tabbit 国内版", "tabbit", "https://web.tabbit.com", "", 1, 1, '{}'),
            ("tabbit-intl", "Tabbit 国际版", "tabbit", "https://web.tabbit.ai", "socks5h://127.0.0.1:1080", 1, 1, '{}'),
            ("loomy", "Loomy 讯飞", "loomy", "https://loomyad.xunfei.cn/api/v1", "", 1, 1, '{}'),
            ("trae", "Trae", "openai_compat", "", "", 1, 1, '{"upstream":"trae2api-cn 社区网关，base_url 填上游 /v1"}'),
            ("workbuddy", "WorkBuddy", "openai_compat", "", "", 1, 1, '{"upstream":"workbuddy2api 社区网关，base_url 填上游 /v1"}'),
        ]
        db.executemany("INSERT OR IGNORE INTO platforms(key,name,adapter,base_url,proxy,enabled,builtin,meta) VALUES(?,?,?,?,?,?,?,?)", seeds)
        # 老库迁移：trae/workbuddy 平台改用 openai_compat 适配器
        db.execute("UPDATE platforms SET adapter='openai_compat' WHERE key IN ('trae','workbuddy') AND adapter IN ('trae','workbuddy')")
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('gateway_key','aam-local-key')")

def rowdict(row):
    return dict(row) if row else None

def get_platform(platform_id):
    with connect() as db:
        return rowdict(db.execute("SELECT * FROM platforms WHERE id=?", (platform_id,)).fetchone())

def get_account(account_id):
    with connect() as db:
        return rowdict(db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone())

def get_setting(key, default=None):
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

def set_setting(key, value):
    with connect() as db:
        db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

def update_account(account_id, fields):
    if not fields:
        return get_account(account_id)
    with connect() as db:
        db.execute("UPDATE accounts SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), account_id))
        return rowdict(db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone())

def pick_account(platform_id):
    """原子领取最久未用账号（BEGIN IMMEDIATE 双进程安全，杜绝热点账号）。"""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM accounts WHERE platform_id=? AND enabled=1 AND status='active' "
            "ORDER BY COALESCE(last_used_at,'') ASC, id ASC LIMIT 1",
            (platform_id,),
        ).fetchone()
        if not row:
            return None
        db.execute("UPDATE accounts SET last_used_at=? WHERE id=?",
                   (time.strftime("%Y-%m-%d %H:%M:%S"), row["id"]))
        return dict(row)

def bump_account_usage(account_id):
    """原子累加 request_count 并刷新 last_used_at（并发不丢计数）。"""
    with connect() as db:
        db.execute("UPDATE accounts SET request_count=request_count+1, last_used_at=? WHERE id=?",
                   (time.strftime("%Y-%m-%d %H:%M:%S"), account_id))

def rate_limit(scope, rkey, min_interval):
    """分布式（双进程 SQLite）限频：距上次放行不足 min_interval 秒返回 False。"""
    now = time.time()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT at FROM rate_limit WHERE scope=? AND rkey=?",
                         (scope, rkey)).fetchone()
        if row is not None and now - row["at"] < min_interval:
            return False
        db.execute(
            "INSERT INTO rate_limit(scope,rkey,at) VALUES(?,?,?) "
            "ON CONFLICT(scope,rkey) DO UPDATE SET at=excluded.at",
            (scope, rkey, now),
        )
        return True

def log_request(account_id, platform_key, model, ok, latency_ms, err=''):
    with connect() as db:
        db.execute("INSERT INTO request_log(account_id,platform_key,model,ok,latency_ms,err) VALUES(?,?,?,?,?,?)", (account_id,platform_key,model,int(ok),latency_ms,err[:1000]))

def parse_json(value, fallback=None):
    try:
        return json.loads(value or '{}')
    except (TypeError, json.JSONDecodeError):
        return fallback if fallback is not None else {}
