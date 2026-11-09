"""Prepare the public Olist dataset at build time, never during a cold start."""
from mcp_server.db import DB_PATH, ensure_dataset
import sqlite3

if __name__ == '__main__':
    ensure_dataset()
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        connection.execute('PRAGMA journal_mode=DELETE')
    print(f'Olist database prepared: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB')
