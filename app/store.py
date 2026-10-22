"""Tiny SQLite store: message de-duplication and pending issue drafts."""
import json
import os
import sqlite3
from contextlib import closing


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(os.getenv('DB_PATH', 'bot.db'))
    c.execute('create table if not exists seen(id text primary key)')
    c.execute('create table if not exists pending(who text primary key, draft text)')
    return c


def seen(message_id: str) -> bool:
    """Return True if this message id was already processed (webhook retry)."""
    with closing(_conn()) as c:
        try:
            c.execute('insert into seen values (?)', (message_id,))
            c.commit()
            return False
        except sqlite3.IntegrityError:
            return True


def set_pending(who: str, draft: dict) -> None:
    with closing(_conn()) as c:
        c.execute('insert or replace into pending values (?, ?)', (who, json.dumps(draft)))
        c.commit()


def pop_pending(who: str):
    with closing(_conn()) as c:
        row = c.execute('select draft from pending where who=?', (who,)).fetchone()
        c.execute('delete from pending where who=?', (who,))
        c.commit()
    return json.loads(row[0]) if row else None
