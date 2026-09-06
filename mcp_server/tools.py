from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from mcp_server.db import execute

VALID_STATES = {
    'acre': 'AC', 'alagoas': 'AL', 'amapa': 'AP', 'amazonas': 'AM', 'bahia': 'BA',
    'ceara': 'CE', 'distrito federal': 'DF', 'espirito santo': 'ES', 'goias': 'GO',
    'maranhao': 'MA', 'mato grosso': 'MT', 'mato grosso do sul': 'MS', 'minas gerais': 'MG',
    'para': 'PA', 'paraiba': 'PB', 'parana': 'PR', 'pernambuco': 'PE', 'piaui': 'PI',
    'rio de janeiro': 'RJ', 'rio grande do norte': 'RN', 'rio grande do sul': 'RS',
    'rondonia': 'RO', 'roraima': 'RR', 'santa catarina': 'SC', 'sao paulo': 'SP',
    'sergipe': 'SE', 'tocantins': 'TO',
}


def _error(message: str, code: str = 'INVALID_INPUT', details: Any = None) -> dict:
    return {'ok': False, 'error': {'code': code, 'message': message, 'details': details}}


def _success(rows: list[dict], source: str, metric: str | None = None, metadata: dict | None = None) -> dict:
    return {
        'ok': True,
        'source': source,
        'metric': metric,
        'metadata': metadata or {},
        'rows': rows,
    }


def _validate_range(date_from: str | None, date_to: str | None) -> tuple[str | None, str | None, dict | None]:
    try:
        if date_from:
            date.fromisoformat(date_from)
        if date_to:
            date.fromisoformat(date_to)
        if date_from and date_to and date_from > date_to:
            return date_from, date_to, _error('date_from must be on or before date_to')
        return date_from, date_to, None
    except ValueError:
        return date_from, date_to, _error('Dates must use YYYY-MM-DD format')


def _date_predicate(column: str, date_from: str | None, date_to: str | None) -> tuple[str, list[str]]:
    clauses, params = [], []
    if date_from:
        clauses.append(f"date({column}) >= date(?)")
        params.append(date_from)
    if date_to:
        clauses.append(f"date({column}) <= date(?)")
        params.append(date_to)
    return (' AND '.join(clauses) if clauses else '1=1'), params


def resolve_category(category: str | None) -> str | None:
    if not category:
        return None
    rows = execute(
        "SELECT product_category_name_english FROM product_category_name_translation "
        "WHERE lower(product_category_name_english)=lower(?) OR lower(product_category_name)=lower(?) LIMIT 1",
        (category, category),
    )
    return rows[0]['product_category_name_english'] if rows else category


def normalize_state(state: str | None) -> str | None:
    if not state:
        return None
    raw = state.strip().lower()
    return raw.upper() if len(raw) == 2 and raw.upper() in set(VALID_STATES.values()) else VALID_STATES.get(raw, state.upper())


def order_trends(date_from: str | None = None, date_to: str | None = None, metric: str = 'revenue') -> dict:
    """Return monthly order volume, revenue, and delivery performance for the order fact table."""
    date_from, date_to, err = _validate_range(date_from, date_to)
    if err:
        return err
    allowed = {'revenue', 'orders', 'late_rate', 'avg_delivery_days'}
    if metric not in allowed:
        return _error(f'metric must be one of {sorted(allowed)}')
    pred, params = _date_predicate('o.order_purchase_timestamp', date_from, date_to)
    sql = f"""
      SELECT substr(o.order_purchase_timestamp, 1, 7) AS month,
             COUNT(DISTINCT o.order_id) AS orders,
             ROUND(SUM(i.price + i.freight_value), 2) AS revenue,
             ROUND(AVG(CASE WHEN o.order_delivered_customer_date IS NOT NULL
                              THEN julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp) END), 2) AS avg_delivery_days,
             ROUND(100.0 * AVG(CASE WHEN o.order_delivered_customer_date IS NOT NULL
                                       AND date(o.order_delivered_customer_date) <= date(o.order_estimated_delivery_date) THEN 1.0 ELSE 0.0 END), 2) AS on_time_rate
      FROM olist_orders_dataset o
      LEFT JOIN olist_order_items_dataset i ON i.order_id = o.order_id
      WHERE {pred}
      GROUP BY 1 ORDER BY 1
    """
    rows = execute(sql, tuple(params))
    if not rows:
        return _error('No rows matched the requested date range', 'EMPTY_RESULT')
    return _success(rows, 'orders + order_items', metric, {'date_range': {'from': date_from, 'to': date_to}})


def category_performance(date_from: str | None = None, date_to: str | None = None, limit: int = 20, sort: str = 'desc', category: str | None = None) -> dict:
    """Return product-category revenue, order volume, review score, and freight, joining the English translation table."""
    date_from, date_to, err = _validate_range(date_from, date_to)
    if err:
        return err
    if not 1 <= limit <= 100:
        return _error('limit must be between 1 and 100')
    if sort not in {'asc', 'desc'}:
        return _error('sort must be asc or desc')
    category_en = resolve_category(category)
    pred, params = _date_predicate('o.order_purchase_timestamp', date_from, date_to)
    extra = ''
    if category_en:
        extra = ' AND lower(t.product_category_name_english) = lower(?)'
        params.append(category_en)
    order_by = 'revenue DESC' if sort == 'desc' else 'avg_review_score ASC'
    sql = f"""
      SELECT COALESCE(t.product_category_name_english, 'unknown') AS category,
             ROUND(SUM(i.price), 2) AS revenue,
             COUNT(DISTINCT o.order_id) AS order_volume,
             ROUND(AVG(r.review_score), 2) AS avg_review_score,
             ROUND(SUM(i.freight_value), 2) AS freight
      FROM olist_order_items_dataset i
      JOIN olist_orders_dataset o ON o.order_id=i.order_id
      JOIN olist_products_dataset p ON p.product_id=i.product_id
      LEFT JOIN product_category_name_translation t ON t.product_category_name=p.product_category_name
      LEFT JOIN (SELECT order_id, AVG(review_score) AS review_score FROM olist_order_reviews_dataset GROUP BY order_id) r ON r.order_id=o.order_id
      WHERE {pred}{extra}
      GROUP BY 1 ORDER BY {order_by} LIMIT ?
    """
    params.append(limit)
    rows = execute(sql, tuple(params))
    if not rows:
        return _error('No rows matched the requested filters', 'EMPTY_RESULT')
    return _success(rows, 'orders + items + products + category translation + reviews', metadata={'resolved_category': category_en})


def seller_performance(date_from: str | None = None, date_to: str | None = None, state: str | None = None, limit: int = 20, sort: str = 'desc') -> dict:
    """Return seller revenue, average review score, delivery speed, and seller state."""
    date_from, date_to, err = _validate_range(date_from, date_to)
    if err:
        return err
    if not 1 <= limit <= 100:
        return _error('limit must be between 1 and 100')
    if sort not in {'asc', 'desc'}:
        return _error('sort must be asc or desc')
    state_code = normalize_state(state)
    pred, params = _date_predicate('o.order_purchase_timestamp', date_from, date_to)
    extra = ''
    if state_code:
        extra = ' AND s.seller_state = ?'
        params.append(state_code)
    order_by = 'revenue DESC' if sort == 'desc' else 'avg_review_score ASC'
    sql = f"""
      SELECT i.seller_id,
             s.seller_state,
             ROUND(SUM(i.price), 2) AS revenue,
             COUNT(DISTINCT o.order_id) AS orders,
             ROUND(AVG(r.review_score), 2) AS avg_review_score,
             ROUND(AVG(CASE WHEN o.order_delivered_customer_date IS NOT NULL
                            THEN julianday(o.order_delivered_customer_date)-julianday(o.order_purchase_timestamp) END), 2) AS avg_delivery_days
      FROM olist_order_items_dataset i
      JOIN olist_orders_dataset o ON o.order_id=i.order_id
      JOIN olist_sellers_dataset s ON s.seller_id=i.seller_id
      LEFT JOIN (SELECT order_id, AVG(review_score) AS review_score FROM olist_order_reviews_dataset GROUP BY order_id) r ON r.order_id=o.order_id
      WHERE {pred}{extra}
      GROUP BY i.seller_id, s.seller_state
      ORDER BY {order_by} LIMIT ?
    """
    params.append(limit)
    rows = execute(sql, tuple(params))
    if not rows:
        return _error('No seller rows matched the requested filters', 'EMPTY_RESULT')
    return _success(rows, 'orders + items + sellers + reviews', metadata={'state': state_code})


def review_analysis(date_from: str | None = None, date_to: str | None = None, category: str | None = None, state: str | None = None, group_by: str = 'score') -> dict:
    """Return review score distribution and review response-time statistics, optionally for an English product category."""
    date_from, date_to, err = _validate_range(date_from, date_to)
    if err:
        return err
    category_en = resolve_category(category)
    state_code = normalize_state(state)
    pred, params = _date_predicate('o.order_purchase_timestamp', date_from, date_to)
    extra = ''
    if category_en:
        extra += ' AND lower(t.product_category_name_english)=lower(?)'
        params.append(category_en)
    if state_code:
        extra += ' AND c.customer_state = ?'
        params.append(state_code)
    if group_by not in {'score', 'state', 'month'}:
        return _error("group_by must be 'score', 'state', or 'month'")
    if group_by == 'month':
        select_group = "substr(o.order_purchase_timestamp,1,7) AS month"
        select_values = ', ROUND(AVG(r.review_score),2) AS avg_review_score, COUNT(*) AS reviews'
        group_clause = 'substr(o.order_purchase_timestamp,1,7)'
        order_clause = 'month'
    elif group_by == 'state':
        select_group = 'c.customer_state AS state'
        select_values = ', ROUND(AVG(r.review_score),2) AS avg_review_score, COUNT(*) AS reviews'
        group_clause = 'c.customer_state'
        order_clause = 'avg_review_score DESC'
    else:
        select_group = 'r.review_score AS score'
        select_values = ', COUNT(*) AS reviews, ROUND(AVG(CASE WHEN r.review_answer_timestamp IS NOT NULL AND r.review_creation_date IS NOT NULL THEN julianday(r.review_answer_timestamp)-julianday(r.review_creation_date) END), 2) AS avg_response_days'
        group_clause = 'r.review_score'
        order_clause = 'r.review_score'
    sql = f"""
      SELECT {select_group}{select_values}
      FROM olist_order_reviews_dataset r
      JOIN olist_orders_dataset o ON o.order_id=r.order_id
      LEFT JOIN olist_customers_dataset c ON c.customer_id=o.customer_id
      LEFT JOIN olist_order_items_dataset i ON i.order_id=o.order_id
      LEFT JOIN olist_products_dataset p ON p.product_id=i.product_id
      LEFT JOIN product_category_name_translation t ON t.product_category_name=p.product_category_name
      WHERE {pred}{extra}
      GROUP BY {group_clause} ORDER BY {order_clause}
    """
    rows = execute(sql, tuple(params))
    if not rows:
        return _error('No review rows matched the requested filters', 'EMPTY_RESULT')
    return _success(rows, 'reviews + orders + customer + items + products + category translation', metadata={'group_by': group_by, 'state': state_code, 'resolved_category': category_en})


def payment_breakdown(date_from: str | None = None, date_to: str | None = None, payment_types: list[str] | None = None) -> dict:
    """Return payment type share and total value by payment type for the selected period."""
    date_from, date_to, err = _validate_range(date_from, date_to)
    if err:
        return err
    pred, params = _date_predicate('o.order_purchase_timestamp', date_from, date_to)
    extra = ''
    if payment_types:
        clean = [x.lower().strip() for x in payment_types if x.lower().strip() in {'credit_card','boleto','voucher','debit_card','not_defined'}]
        if not clean:
            return _error('payment_types contains no supported values')
        extra = ' AND lower(op.payment_type) IN (' + ','.join('?' for _ in clean) + ')'
        params.extend(clean)
    sql = f"""
      WITH p AS (
        SELECT op.payment_type, SUM(op.payment_value) AS value, COUNT(DISTINCT op.order_id) AS orders
        FROM olist_order_payments_dataset op
        JOIN olist_orders_dataset o ON o.order_id=op.order_id
        WHERE {pred}{extra}
        GROUP BY op.payment_type
      )
      SELECT payment_type, ROUND(value,2) AS value, orders,
             ROUND(100.0*value/SUM(value) OVER (),2) AS share_pct
      FROM p ORDER BY value DESC
    """
    rows = execute(sql, tuple(params))
    if not rows:
        return _error('No payment rows matched the requested period', 'EMPTY_RESULT')
    return _success(rows, 'order_payments + orders', metadata={'payment_types': payment_types or 'all'})


def delivery_performance(date_from: str | None = None, date_to: str | None = None, state: str | None = None, route: bool = False) -> dict:
    """Return estimated-vs-actual delivery performance by state or customer-seller route."""
    date_from, date_to, err = _validate_range(date_from, date_to)
    if err:
        return err
    state_code = normalize_state(state)
    pred, params = _date_predicate('o.order_purchase_timestamp', date_from, date_to)
    extra = ''
    route_select = "c.customer_state || ' -> ' || s.seller_state AS route,"
    group = 'c.customer_state, s.seller_state'
    if not route:
        route_select = 'c.customer_state AS state,'
        group = 'c.customer_state'
    if state_code:
        extra = ' AND c.customer_state = ?'
        params.append(state_code)
    sql = f"""
      SELECT {route_select}
             COUNT(DISTINCT o.order_id) AS orders,
             ROUND(AVG(CASE WHEN o.order_delivered_customer_date IS NOT NULL
                            THEN julianday(o.order_delivered_customer_date)-julianday(o.order_estimated_delivery_date) END), 2) AS avg_delay_days,
             ROUND(100.0*AVG(CASE WHEN o.order_delivered_customer_date IS NOT NULL
                                   AND date(o.order_delivered_customer_date) <= date(o.order_estimated_delivery_date) THEN 1.0 ELSE 0.0 END),2) AS on_time_rate
      FROM olist_orders_dataset o
      JOIN olist_customers_dataset c ON c.customer_id=o.customer_id
      LEFT JOIN olist_order_items_dataset i ON i.order_id=o.order_id
      LEFT JOIN olist_sellers_dataset s ON s.seller_id=i.seller_id
      WHERE {pred}{extra}
      GROUP BY {group}
      HAVING orders > 0
      ORDER BY avg_delay_days DESC
      LIMIT 100
    """
    rows = execute(sql, tuple(params))
    if not rows:
        return _error('No delivery rows matched the requested filters', 'EMPTY_RESULT')
    return _success(rows, 'orders + customers + items + sellers', metadata={'route': route})


def tool_call(name: str, args: dict) -> dict:
    """Dispatcher used by tests and the MCP registration layer."""
    functions = {
        'order_trends': order_trends,
        'category_performance': category_performance,
        'seller_performance': seller_performance,
        'review_analysis': review_analysis,
        'payment_breakdown': payment_breakdown,
        'delivery_performance': delivery_performance,
    }
    fn = functions.get(name)
    if fn is None:
        return _error(f'Unknown tool: {name}', 'UNKNOWN_TOOL')
    try:
        result = fn(**args)
        return result
    except Exception as exc:
        return _error('Tool execution failed safely', 'TOOL_ERROR', {'type': type(exc).__name__, 'message': str(exc)[:300]})
