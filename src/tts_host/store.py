"""Small single-node durable catalog. Separate API/worker processes share SQLite WAL."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS records (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, owner TEXT NOT NULL,
              payload TEXT NOT NULL, created REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS records_owner ON records(owner, kind);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / "catalog.sqlite3", timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def create(self, kind, owner, payload, record_id=None):
        rid = record_id or uuid.uuid4().hex
        obj = {**payload, "id": rid, "created_at": time.time()}
        with self.db() as db:
            db.execute("INSERT INTO records VALUES (?,?,?,?,?)",
                       (rid, kind, owner, json.dumps(obj), obj["created_at"]))
        return obj

    def get(self, kind, owner, rid):
        with self.db() as db:
            row = db.execute("SELECT payload FROM records WHERE id=? AND kind=? AND owner=?",
                             (rid, kind, owner)).fetchone()
        if row is None:
            raise KeyError(rid)
        return json.loads(row[0])

    def list(self, kind, owner):
        with self.db() as db:
            rows = db.execute("SELECT payload FROM records WHERE kind=? AND owner=? ORDER BY created",
                              (kind, owner)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def update(self, kind, owner, rid, **updates):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM records WHERE id=? AND kind=? AND owner=?",
                             (rid, kind, owner)).fetchone()
            if row is None:
                raise KeyError(rid)
            obj = {**json.loads(row[0]), **updates}
            db.execute("UPDATE records SET payload=? WHERE id=?", (json.dumps(obj), rid))
        return obj

    def claim_job(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute("SELECT * FROM records WHERE kind='job' ORDER BY created"):
                obj = json.loads(row["payload"])
                if obj["status"] == "queued":
                    obj.update(status="running", stage="preparing", started_at=time.time())
                    db.execute("UPDATE records SET payload=? WHERE id=?", (json.dumps(obj), row["id"]))
                    return row["owner"], obj
        return None

    def asset(self, rid: str) -> Path:
        if len(rid) != 32 or any(c not in "0123456789abcdef" for c in rid):
            raise ValueError("Invalid asset ID")
        return self.root / "audio" / f"{rid}.wav"
