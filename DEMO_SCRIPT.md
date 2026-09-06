# Demo recording script

Keep the browser on `http://localhost:8000`.

1. Introduce the flow in one sentence: plain English -> agent -> MCP -> SQLite -> chart -> pin.
2. Run: `Show monthly revenue trend for 2017`. Point out the line chart and date assumption.
3. Run: `Which product categories generate the most revenue?`. Point out the translated English category labels and horizontal ranking.
4. Run: `Which states have the worst delivery performance?`. Point out the delivery metric and the chart-selection justification.
5. Run: `What share of payments are credit card vs boleto?`. Point out the donut chart.
6. Run: `Do sellers with faster delivery get better reviews?`. Point out the scatter plot.
7. Pin the last result and refresh it. Show the change score and the “significant change” message.
8. Open the Tool trace details once to show that the model selected MCP tools rather than generating SQL directly.
