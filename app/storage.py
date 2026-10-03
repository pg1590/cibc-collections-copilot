"""Local persistent sessions, human decisions and append-only audit records."""
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime,timezone,timedelta
from app.settings import STATE


def now():return datetime.now(timezone.utc).isoformat()


def connect():
    STATE.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(STATE,timeout=20);c.row_factory=sqlite3.Row
    c.executescript('''
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,username TEXT NOT NULL,role TEXT NOT NULL,expires_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS briefs(brief_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,actor TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL,decision TEXT,reason TEXT,reviewer TEXT);
    CREATE TABLE IF NOT EXISTS audit(event_id INTEGER PRIMARY KEY AUTOINCREMENT,at TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,resource TEXT NOT NULL,details TEXT NOT NULL,previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'Audit is append only'); END;
    CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'Audit is append only'); END;
    ''');c.commit();return c


def audit(c,actor,action,resource,details):
    at=now();data=json.dumps(details,sort_keys=True,default=str)
    row=c.execute('SELECT event_hash FROM audit ORDER BY event_id DESC LIMIT 1').fetchone()
    previous=row[0] if row else ''
    digest=hashlib.sha256(json.dumps([at,actor,action,resource,data,previous],ensure_ascii=False).encode()).hexdigest()
    c.execute('INSERT INTO audit(at,actor,action,resource,details,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?)',(at,actor,action,resource,data,previous,digest))


def create_session(username,role):
    token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
    with connect() as c:
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(digest,username,role,(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()))
        audit(c,username,'login',role,{})
    return token


def session(token):
    with connect() as c:
        row=c.execute('SELECT username,role FROM sessions WHERE token_hash=? AND expires_at>?',(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone()
    return dict(row) if row else None
