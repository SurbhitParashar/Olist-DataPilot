from __future__ import annotations

from typing import Any


ALLOWED_TYPES = {'line', 'bar', 'doughnut', 'scatter'}


def _num(v: Any) -> float | None:
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _line(rows: list[dict], x: str, metrics: list[str], labels: list[str]) -> dict:
    datasets = []
    for idx, metric in enumerate(metrics):
        values = [_num(r.get(metric)) for r in rows]
        datasets.append({
            'label': metric.replace('_', ' ').title(),
            'data': values,
            'borderWidth': 2,
            'fill': False,
            'yAxisID': 'y' if idx == 0 else 'y1',
        })
    scales: dict[str, Any] = {'x': {'title': {'display': True, 'text': x.title()}}}
    if len(metrics) > 1:
        scales['y'] = {'type': 'linear', 'position': 'left'}
        scales['y1'] = {'type': 'linear', 'position': 'right', 'grid': {'drawOnChartArea': False}}
    return {
        'type': 'line',
        'data': {'labels': labels, 'datasets': datasets},
        'options': {'responsive': True, 'maintainAspectRatio': False, 'scales': scales},
    }


def build_chart(query: str, tool_results: list[dict]) -> tuple[str, str, dict]:
    q = query.lower()
    if not tool_results:
        return 'none', 'No successful data source returned rows.', {}

    successful = [r for r in tool_results if r.get('data', {}).get('ok') and r.get('data', {}).get('rows')]
    if not successful:
        return 'none', 'The query returned no data after filtering.', {}

    # Multi-source query: monthly orders + average review score.
    if 'monthly' in q and 'review score' in q and 'order' in q:
        orders = next((r for r in successful if 'order_trends' in r['name']), None)
        reviews = next((r for r in successful if 'review_analysis' in r['name']), None)
        if orders and reviews:
            rev = {row.get('month'): row for row in reviews['data']['rows'] if row.get('month')}
            joined = [row for row in orders['data']['rows'] if row.get('month') in rev]
            if joined:
                labels = [row['month'] for row in joined]
                config = _line(
                    [dict(row, avg_review_score=rev[row['month']].get('avg_review_score')) for row in joined],
                    'month', ['orders', 'avg_review_score'], labels,
                )
                return 'line', 'Two measures share the same monthly axis, so a dual-axis line chart compares order volume and review score without mixing scales.', config

    # Multi-source query: delivery delay + review score by state.
    if 'delivery' in q and 'review' in q and 'state' in q:
        delivery = next((r for r in successful if 'delivery_performance' in r['name']), None)
        review = next((r for r in successful if 'review_analysis' in r['name']), None)
        if delivery and review:
            d = {row.get('state'): row for row in delivery['data']['rows'] if row.get('state')}
            joined = []
            for row in review['data']['rows']:
                state = row.get('state')
                if state in d:
                    joined.append({**d[state], **{'avg_review_score': row.get('avg_review_score')}})
            if joined:
                labels = [r['state'] for r in joined]
                config = {
                    'type': 'bar',
                    'data': {'labels': labels, 'datasets': [
                        {'label': 'Average delay (days)', 'data': [_num(r.get('avg_delay_days')) for r in joined]},
                        {'label': 'Average review score', 'data': [_num(r.get('avg_review_score')) for r in joined]},
                    ]},
                    'options': {'responsive': True, 'maintainAspectRatio': False},
                }
                return 'bar', 'Side-by-side vertical bars compare two metrics across the same state categories.', config

    source = successful[0]
    rows = source['data']['rows']
    name = source['name']

    if 'order_trends' in name or 'monthly' in q and any('month' in r for r in rows):
        metrics = []
        if 'orders' in q and 'orders' in rows[0]: metrics.append('orders')
        if 'revenue' in q and 'revenue' in rows[0]: metrics.append('revenue')
        if 'on-time' in q or 'on time' in q:
            if 'on_time_rate' in rows[0]: metrics.append('on_time_rate')
        if not metrics:
            metrics = ['revenue'] if 'revenue' in rows[0] else ['orders']
        chart = _line(rows, 'month', metrics[:2], [r['month'] for r in rows])
        if len(metrics) == 1:
            return 'line', 'A single numeric measure changes over a monthly time axis, so a line chart preserves trend shape.', chart
        return 'line', 'Two measures share the same monthly axis, so a dual-axis line chart shows both trends without mixing scales.', chart

    if 'payment_breakdown' in name or 'share' in q or 'payment' in q:
        labels = [r['payment_type'] for r in rows]
        config = {'type': 'doughnut', 'data': {'labels': labels, 'datasets': [{'label': 'Payment share %', 'data': [_num(r.get('share_pct')) for r in rows]}]}, 'options': {'responsive': True, 'maintainAspectRatio': False}}
        return 'doughnut', 'Payment types form a part-to-whole composition, which is best represented by a donut chart.', config

    if 'review_analysis' in name and 'distribution' in q:
        labels = [f"{int(_num(r.get('score')) or 0)} stars" for r in rows]
        config = {'type': 'bar', 'data': {'labels': labels, 'datasets': [{'label': 'Reviews', 'data': [_num(r.get('reviews')) for r in rows]}]}, 'options': {'indexAxis': 'y', 'plugins': {'legend': {'display': False}}, 'scales': {'x': {'stacked': True}, 'y': {'stacked': True}}}}
        return 'bar', 'A 1–5 score distribution is discrete and ordinal, so a stacked horizontal bar keeps the rating order readable.', config

    if 'delivery_performance' in name:
        labels_key = 'route' if any('route' in r for r in rows) else 'state'
        labels = [r.get(labels_key) for r in rows]
        metric = 'avg_delay_days' if 'delay' in q or 'delivery' in q else 'on_time_rate'
        config = {'type': 'bar', 'data': {'labels': labels, 'datasets': [{'label': metric.replace('_', ' ').title(), 'data': [_num(r.get(metric)) for r in rows]}]}, 'options': {'responsive': True, 'maintainAspectRatio': False}}
        return 'bar', 'Delivery performance is a comparison across states or routes, so vertical bars make the ranking easy to scan.', config

    if 'seller_performance' in name and any(k in q for k in ('faster', 'correlation', 'better reviews', 'review')):
        config = {'type': 'scatter', 'data': {'datasets': [{'label': 'Seller: delivery speed vs review', 'data': [{'x': _num(r.get('avg_delivery_days')), 'y': _num(r.get('avg_review_score'))} for r in rows]}]}, 'options': {'responsive': True, 'maintainAspectRatio': False, 'scales': {'x': {'title': {'display': True, 'text': 'Average delivery days'}}, 'y': {'title': {'display': True, 'text': 'Average review score'}}}}}
        return 'scatter', 'Two continuous seller-level variables are being compared, so one dot per seller shows the relationship without implying a ranking.', config

    category_key = 'category' if 'category' in rows[0] else 'seller_id' if 'seller_id' in rows[0] else 'payment_type' if 'payment_type' in rows[0] else None
    if category_key:
        metric = 'revenue' if 'revenue' in rows[0] else 'order_volume' if 'order_volume' in rows[0] else 'orders' if 'orders' in rows[0] else 'avg_review_score'
        ordered = sorted(rows, key=lambda r: (_num(r.get(metric)) or 0), reverse=True)
        labels = [str(r.get(category_key)) for r in ordered]
        config = {'type': 'bar', 'data': {'labels': labels, 'datasets': [{'label': metric.replace('_', ' ').title(), 'data': [_num(r.get(metric)) for r in ordered]}]}, 'options': {'indexAxis': 'y', 'responsive': True, 'maintainAspectRatio': False, 'plugins': {'legend': {'display': False}}}}
        return 'bar', 'The result is a ranked entity list, so a sorted horizontal bar chart makes the ordering explicit.', config

    return 'bar', 'The data is categorical and the fallback visualization uses a bar chart for a clear comparison.', {
        'type': 'bar', 'data': {'labels': [str(i) for i in range(len(rows))], 'datasets': [{'label': 'Value', 'data': [1 for _ in rows]}]}, 'options': {'responsive': True, 'maintainAspectRatio': False}
    }
