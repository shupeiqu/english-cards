"""Concurrent local collection and study storage; no desktop dependency."""
import json
import os
import sqlite3
import time
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get('ENGLISH_CARDS_HOME', str(Path.home() / 'Library/Application Support/EnglishCards')))
MAX_TEXT = 1200

def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split()).strip()

def validate(text):
    text = normalize(text)
    if not text:
        raise ValueError('请先选中一段英文，再使用“收藏到英语卡片”。')
    if len(text) > MAX_TEXT:
        raise ValueError('一次最多收藏 1200 个字符，请选中单词、短语或较短的句子。')
    return text

class Store:
    def __init__(self, directory=DATA_DIR):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'cards.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS words (
                    id TEXT PRIMARY KEY, en TEXT NOT NULL, normalized TEXT NOT NULL UNIQUE,
                    zh TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT NOT NULL DEFAULT '', token TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO meta VALUES ('session', '{"queue":[],"total":0,"done":0}');
            ''')
        self.migrate()
        self.reload()
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    def migrate(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM meta WHERE key='imported_v1'").fetchone(): return
            old = self.directory / 'data.json'
            data = json.loads(old.read_text(encoding='utf-8')) if old.exists() else {}
            now = time.time()
            for w in data.get('words', []):
                en = normalize(w['en'])
                if en:
                    db.execute('INSERT OR IGNORE INTO words (id,en,normalized,zh,status,created,updated) VALUES (?,?,?,?,?,?,?)',
                        (w['id'],en,en.casefold(),w['zh'],'ready' if w['zh'].strip() else 'pending',now,now))
            if data:
                ids = {r[0] for r in db.execute("SELECT id FROM words WHERE status='ready'")}
                queue = [i for i in data.get('queue', []) if i in ids]
                done = data.get('done',0)
                state = dict(queue=queue, total=done+len(queue), done=done)
                db.execute("UPDATE meta SET value=? WHERE key='session'", (json.dumps(state),))
            db.execute("INSERT INTO meta VALUES ('imported_v1','1')")
    def reload(self):
        with self.connect() as db:
            db.execute('BEGIN')
            self.words = [dict(r) for r in db.execute('SELECT * FROM words ORDER BY created DESC, rowid DESC')]
            state = json.loads(db.execute("SELECT value FROM meta WHERE key='session'").fetchone()[0])
        valid = {w['id'] for w in self.words if w['status']=='ready'}
        self.queue = [i for i in state['queue'] if i in valid]
        self.done, self.total = state['done'], state['done'] + len(self.queue)
    def add(self, en, zh=''):
        en, zh = validate(en), zh.strip()
        if len(zh)>MAX_TEXT: raise ValueError('中文释义请控制在 1200 字以内。')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM words WHERE normalized=?',(en.casefold(),)).fetchone()
            if row: return row['id'], False
            word_id, now = uuid.uuid4().hex, time.time()
            db.execute('INSERT INTO words (id,en,normalized,zh,status,created,updated) VALUES (?,?,?,?,?,?,?)',
                (word_id,en,en.casefold(),zh,'ready' if zh else 'pending',now,now))
        return word_id, True
    def edit(self, word_id, en, zh):
        en, zh = validate(en), zh.strip()
        if not zh: raise ValueError('编辑时请填写中文释义，或取消编辑后点击“重试翻译”。')
        with self.connect() as db:
            try:
                db.execute("UPDATE words SET en=?,normalized=?,zh=?,status='ready',error='',token='',updated=? WHERE id=?",
                    (en,en.casefold(),zh,time.time(),word_id))
            except sqlite3.IntegrityError: raise ValueError('这条英文已经收藏，请编辑已有词条。')
    def delete(self, ids):
        ids = set(ids)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.executemany('DELETE FROM words WHERE id=?',[(i,) for i in ids])
            state=json.loads(db.execute("SELECT value FROM meta WHERE key='session'").fetchone()[0])
            state['queue']=[i for i in state['queue'] if i not in ids]
            state['total']=state['done']+len(state['queue'])
            db.execute("UPDATE meta SET value=? WHERE key='session'",(json.dumps(state),))
    def start(self, ids):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            valid={r[0] for r in db.execute("SELECT id FROM words WHERE status='ready'")}
            queue=list(dict.fromkeys(i for i in ids if i in valid))
            state=dict(queue=queue,total=len(queue),done=0)
            db.execute("UPDATE meta SET value=? WHERE key='session'",(json.dumps(state),))
        self.reload()
    def answer(self, known, expected=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state=json.loads(db.execute("SELECT value FROM meta WHERE key='session'").fetchone()[0])
            if not state['queue'] or (expected and state['queue'][0]!=expected): return
            current=state['queue'].pop(0)
            if known: state['done']+=1
            else: state['queue'].append(current)
            db.execute("UPDATE meta SET value=? WHERE key='session'",(json.dumps(state),))
        self.reload()
    def retry(self, ids):
        with self.connect() as db:
            db.executemany("UPDATE words SET status='pending',error='',token='',updated=? WHERE id=? AND status='error'",
                [(time.time(),i) for i in ids])
    def recover_interrupted(self):
        # Called only while holding the exclusive translation-worker lock.
        with self.connect() as db:
            db.execute("UPDATE words SET status='pending',token='' WHERE status='translating'")
    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM words WHERE status='pending' ORDER BY created LIMIT 1").fetchone()
            if not row:return None
            token=uuid.uuid4().hex
            db.execute("UPDATE words SET status='translating',token=?,updated=? WHERE id=?",(token,time.time(),row['id']))
            return dict(row) | {'token':token}
    def finish(self, job, zh='', error=''):
        with self.connect() as db:
            db.execute("UPDATE words SET zh=?,status=?,error=?,token='',updated=? WHERE id=? AND token=? AND status='translating'",
                (zh,'error' if error else 'ready',error,time.time(),job['id'],job['token']))
