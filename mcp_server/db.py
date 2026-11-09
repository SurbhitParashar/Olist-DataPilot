from __future__ import annotations

import csv
import json
import os
import sqlite3
import time
import urllib.request
import zipfile
from pathlib import Path

DATA_DIR = Path(os.getenv('DATA_DIR', str(Path(__file__).resolve().parents[1] / 'data')))
DB_PATH = DATA_DIR / 'olist.db'
DATASET_URL = os.getenv(
    'DATASET_URL',
    'https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce',
)
LOCK_PATH = Path(os.getenv('INGEST_LOCK', str(DATA_DIR / '.ingest.lock')))

CSV_TABLES = {
    'olist_customers_dataset.csv': 'olist_customers_dataset',
    'olist_geolocation_dataset.csv': 'olist_geolocation_dataset',
    'olist_order_items_dataset.csv': 'olist_order_items_dataset',
    'olist_order_payments_dataset.csv': 'olist_order_payments_dataset',
    'olist_order_reviews_dataset.csv': 'olist_order_reviews_dataset',
    'olist_orders_dataset.csv': 'olist_orders_dataset',
    'olist_products_dataset.csv': 'olist_products_dataset',
    'olist_sellers_dataset.csv': 'olist_sellers_dataset',
    'product_category_name_translation.csv': 'product_category_name_translation',
}


def _ident(name: str) -> str:
    if not name.replace('_', '').isalnum():
        raise ValueError(f'unsafe identifier: {name}')
    return '"' + name + '"'


def _clean_col(name: str) -> str:
    name = name.strip().lower().replace(' ', '_').replace('-', '_')
    if not name:
        return 'column'
    if name[0].isdigit():
        name = '_' + name
    return ''.join(c if c.isalnum() or c == '_' else '_' for c in name)


def ensure_dataset() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    marker = DATA_DIR / '.ready'
    if marker.exists() and DB_PATH.exists():
        return

    # Simple cross-container lock. The MCP service is the owner of the data volume,
    # while waiting app instances can safely keep retrying the healthcheck.
    deadline = time.time() + 600
    while True:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if marker.exists() and DB_PATH.exists():
                return
            if time.time() > deadline:
                raise TimeoutError('timed out waiting for dataset ingestion lock')
            time.sleep(2)

    try:
        if marker.exists() and DB_PATH.exists():
            return
        archive = DATA_DIR / 'brazilian-ecommerce.zip'
        if not archive.exists():
            tmp = archive.with_suffix('.download')
            urllib.request.urlretrieve(DATASET_URL, tmp)
            tmp.replace(archive)

        extract_dir = DATA_DIR / 'csv'
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)

        _ingest(extract_dir)
        marker.write_text('ready\n', encoding='utf-8')
    finally:
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def _find_csv(root: Path, filename: str) -> Path:
    hits = list(root.rglob(filename))
    if not hits:
        raise FileNotFoundError(f'missing dataset file: {filename}')
    return hits[0]


def _ingest(root: Path) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH, timeout=60)
    try:
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        for filename, table in CSV_TABLES.items():
            path = _find_csv(root, filename)
            with path.open('r', encoding='utf-8-sig', newline='') as fh:
                reader = csv.reader(fh)
                raw_header = next(reader)
                columns = [_clean_col(x) for x in raw_header]
                col_sql = ', '.join(f'{_ident(c)} TEXT' for c in columns)
                conn.execute(f'DROP TABLE IF EXISTS {_ident(table)}')
                conn.execute(f'CREATE TABLE {_ident(table)} ({col_sql})')
                placeholders = ','.join('?' for _ in columns)
                sql = f'INSERT INTO {_ident(table)} VALUES ({placeholders})'
                batch = []
                for row in reader:
                    if len(row) < len(columns):
                        row = row + [''] * (len(columns) - len(row))
                    elif len(row) > len(columns):
                        row = row[:len(columns)]
                    batch.append(row)
                    if len(batch) >= 5000:
                        conn.executemany(sql, batch)
                        batch.clear()
                if batch:
                    conn.executemany(sql, batch)
            conn.commit()

        indexes = [
            ('idx_orders_order_id', 'olist_orders_dataset', 'order_id'),
            ('idx_orders_customer_id', 'olist_orders_dataset', 'customer_id'),
            ('idx_items_order_id', 'olist_order_items_dataset', 'order_id'),
            ('idx_items_product_id', 'olist_order_items_dataset', 'product_id'),
            ('idx_items_seller_id', 'olist_order_items_dataset', 'seller_id'),
            ('idx_payments_order_id', 'olist_order_payments_dataset', 'order_id'),
            ('idx_reviews_order_id', 'olist_order_reviews_dataset', 'order_id'),
            ('idx_customers_customer_id', 'olist_customers_dataset', 'customer_id'),
            ('idx_products_product_id', 'olist_products_dataset', 'product_id'),
            ('idx_sellers_seller_id', 'olist_sellers_dataset', 'seller_id'),
        ]
        for index_name, table, column in indexes:
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS {_ident(index_name)} '
                f'ON {_ident(table)}({_ident(column)})'
            )
        conn.commit()
    finally:
        conn.close()


def execute(query: str, params: tuple = (), timeout_seconds: float = 15.0) -> list[dict]:
    ensure_dataset()
    # The bundled analytics database is immutable on Vercel.
    conn = sqlite3.connect(f'{DB_PATH.as_uri()}?mode=ro&immutable=1' if os.getenv('VERCEL') == '1' else DB_PATH,
                           timeout=timeout_seconds, uri=os.getenv('VERCEL') == '1')
    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + timeout_seconds
    try:
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
