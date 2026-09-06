from app.charts import build_chart


def test_monthly_is_line():
    payload = [{'name': 'order_trends_tool', 'data': {'ok': True, 'rows': [
        {'month': '2017-01', 'revenue': 100.0, 'orders': 4},
        {'month': '2017-02', 'revenue': 120.0, 'orders': 5},
    ]}}]
    chart_type, _, config = build_chart('Show monthly revenue trend for 2017', payload)
    assert chart_type == 'line'
    assert config['type'] == 'line'


def test_payment_is_donut():
    payload = [{'name': 'payment_breakdown_tool', 'data': {'ok': True, 'rows': [
        {'payment_type': 'credit_card', 'share_pct': 80},
        {'payment_type': 'boleto', 'share_pct': 20},
    ]}}]
    chart_type, _, config = build_chart('What share of payments are credit card vs boleto?', payload)
    assert chart_type == 'doughnut'
    assert config['type'] == 'doughnut'


def test_ranked_list_is_horizontal_bar():
    payload = [{'name': 'category_performance_tool', 'data': {'ok': True, 'rows': [
        {'category': 'health', 'revenue': 20}, {'category': 'books', 'revenue': 10}
    ]}}]
    chart_type, _, config = build_chart('Which product categories generate the most revenue?', payload)
    assert chart_type == 'bar'
    assert config['options']['indexAxis'] == 'y'
