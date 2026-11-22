import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.errors import TideError

from .manifest import canonical


class Journal:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS journals (
                id TEXT PRIMARY KEY, created TEXT NOT NULL, receipt TEXT NOT NULL,
                inputs TEXT NOT NULL, reports TEXT NOT NULL)''')
            connection.execute('''CREATE TABLE IF NOT EXISTS intakes (
                run_id TEXT NOT NULL REFERENCES journals(id), id TEXT NOT NULL, received TEXT NOT NULL,
                receipt TEXT NOT NULL, inputs TEXT NOT NULL, reports TEXT NOT NULL,
                PRIMARY KEY (run_id, id))''')

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            yield connection

    def publish(self, receipt, sources, reports):
        with self.connection() as connection:
            connection.execute('INSERT INTO journals VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING', (
                receipt['run_id'], receipt['started_at'], canonical(receipt), canonical(sources), canonical(reports)))
            cursor = connection.execute('INSERT INTO intakes VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING', (
                receipt['run_id'], receipt['intake_id'], receipt['started_at'],
                canonical(receipt), canonical(sources), canonical(reports)))
            return cursor.rowcount == 1

    def get(self, key, intake=None):
        with self.connection() as connection:
            if intake is None:
                row = connection.execute(
                    'SELECT receipt, inputs, reports FROM journals WHERE id=?', (key,)).fetchone()
            else:
                row = connection.execute(
                    'SELECT receipt, inputs, reports FROM intakes WHERE run_id=? AND id=?', (key, intake)).fetchone()
        if row is None:
            if intake is None:
                raise TideError('NO_RUN', '未找到这份运行簿', 404)
            raise TideError('NO_INTAKE', '这份原件不在该簿实收中', 404)
        return tuple(json.loads(value) for value in row)

    def intakes(self, key):
        with self.connection() as connection:
            if connection.execute('SELECT 1 FROM journals WHERE id=?', (key,)).fetchone() is None:
                raise TideError('NO_RUN', '未找到这份运行簿', 404)
            rows = connection.execute(
                'SELECT receipt FROM intakes WHERE run_id=? ORDER BY received, id', (key,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def list(self):
        with self.connection() as connection:
            rows = connection.execute('''SELECT j.receipt, COUNT(i.id) FROM journals j
                LEFT JOIN intakes i ON i.run_id=j.id GROUP BY j.id
                ORDER BY j.created DESC, j.id LIMIT 40''').fetchall()
        return [dict(json.loads(receipt), filings=count) for receipt, count in rows]
