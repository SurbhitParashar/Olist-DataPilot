# Olist Sales Analytics Chatbot

I built this as a small analytics product rather than a single LLM prompt wrapped around a database.
The main idea is simple: an analyst asks a question in normal English, the agent decides which analytics capabilities it needs, MCP owns the data access, and the API turns the returned rows into a predictable Chart.js response. Pins are stored separately so a dashboard survives restarts.

The assignment specifically asks for the Olist Brazilian E-Commerce dataset, an MCP tool layer, an LLM agent with a rule-based fallback, chart selection based on data shape, and a refreshable pinned dashboard. This repo implements those pieces end-to-end. The assignment also calls out the category translation join as mandatory, so product/category tools never expose the raw Portuguese category as the primary category field.

## 1. High-level architecture

```text
                       +----------------------+
                       |      Browser UI      |
                       |  plain English query |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       |       FastAPI API     |
                       |  /api/ask /api/pins   |
                       +----------+-----------+
                                  |
                       +----------v-----------+
                       |   Agent abstraction   |
                       |      ILLMAgent        |
                       +------+-----------+----+
                              |           |
                         LLM mode      Fallback
                              |           |
                              +-----+-----+
                                    |
                                    v
                           +-------------------+
                           |    MCP client     |
                           +---------+---------+
                                     |
                                     v
                           +-------------------+
                           |   MCP analytics    |
                           |   official Python  |
                           |   SDK / HTTP       |
                           +---------+----------+
                                     |
                                     v
                           +-------------------+
                           | SQLite Olist DB    |
                           | loaded at startup  |
                           +-------------------+

Dashboard pins -> FastAPI SQLite state DB -> survive container restarts via named volume
```

The important boundary is MCP. The LLM never gets database credentials and it never writes SQL. It only selects typed tools and arguments. The MCP server is responsible for validating inputs, performing the joins, and returning structured results.

The LLM is also not trusted with visualization correctness. The agent can suggest a chart type, but the backend checks the returned data shape and builds the final Chart.js config deterministically. That is deliberate: it keeps a language model from randomly choosing a chart that does not fit the data.

## 2. Services

### `mcp`

Loads all Olist CSV files into SQLite on first startup, creates the useful indexes, and exposes six analytics tools:

- order trends
- category/product performance
- seller performance
- review analysis
- payment breakdown
- delivery performance

The MCP server uses Streamable HTTP, so the API service can act as a normal MCP client over the Docker network.

### `app`

FastAPI application containing the agent abstraction, chart builder, guardrails, persistent pin store, and the small web UI.

The LLM implementation talks to OpenRouter through the OpenAI-compatible API. The configured model is intentionally:

```env
OPENROUTER_MODEL=openrouter/free
```

`openrouter/free` is a router over free models and can select a tool-capable model when the request requires tools.

OpenRouter's API is OpenAI-compatible, so the official OpenAI Python SDK is used with the OpenRouter base URL. Native tool calling is implemented with the normal `tools` / `tool_calls` loop.

The MCP side uses the official Python SDK. The current SDK supports a URL-based `Client("http://.../mcp")`, `list_tools()`, and `call_tool()`, which is what the agent uses here.

## 3. Project structure

```text
olist-sales-chatbot/
├── app/
│   ├── charts.py             # deterministic chart selection + Chart.js config
│   ├── config.py             # environment configuration
│   ├── guardrails.py         # unsupported / unsafe analytics queries
│   ├── main.py               # FastAPI routes
│   ├── observability.py      # structured-ish timing/logging hooks
│   ├── pipeline.py           # agent -> chart -> response orchestration
│   ├── schemas.py            # API contracts
│   └── storage.py            # persistent pinned-dashboard state
├── agent/
│   ├── fallback_agent.py     # deterministic rule-based fallback
│   ├── interfaces.py         # ILLMAgent + internal result models
│   ├── llm_agent.py          # OpenRouter native tool-calling agent
│   ├── mcp_client.py         # MCP client adapter
│   └── prompts.py            # planner instructions
├── mcp_server/
│   ├── db.py                 # dataset download, SQLite loading, indexes
│   ├── server.py              # official MCP server registration
│   └── tools.py               # analytics tools + error handling
├── frontend/
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── main.js
│       └── style.css
├── scripts/
│   └── healthcheck_mcp.py
├── tests/
│   └── test_chart_rules.py
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## 4. Setup

There is no manual database import step. The MCP container downloads the public Olist archive on first boot, extracts all CSVs, creates the SQLite database and indexes, then becomes healthy. The assignment's requested dataset is the Brazilian E-Commerce Public Dataset by Olist.

Create `.env` from `.env.example` and set only the API key you need for LLM mode:

```env
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=openrouter/free
AGENT_MODE=llm
```

Then run:

```bash
docker compose up --build
```

Open `http://localhost:8000`.

For a zero-key demo, set `AGENT_MODE=fallback`. The same command starts the whole stack, and the fallback agent does not call an LLM.

## 5. What happens when a question is submitted

1. FastAPI validates the request.
2. A small guardrail layer checks whether the topic is inside the Olist dataset's scope.
3. The selected agent receives the plain-English question.
4. In LLM mode, OpenRouter chooses the MCP tool(s) and supplies structured arguments.
5. MCP runs the query against SQLite and returns JSON-like structured content.
6. The backend keeps the tool trace for observability and debugging.
7. The chart builder inspects the returned data shape and chooses the visualization.
8. The LLM produces the one-sentence insight, but it is not allowed to invent values outside tool results.
9. The API returns one stable JSON response containing assumptions, chart type, justification, insight, rows, tool trace, and the Chart.js config.

## 6. MCP tool layer

The assignment requires the tools to cover time trends, product/category performance, sellers, reviews, payments and delivery, and to handle invalid inputs without crashing the agent.

The server exposes:

| Tool | Main coverage |
|---|---|
| `order_trends_tool` | monthly orders, revenue, delivery speed, on-time rate |
| `category_performance_tool` | category revenue, order volume, reviews, freight |
| `seller_performance_tool` | seller revenue, orders, rating, delivery speed, state |
| `review_analysis_tool` | 1–5 score distribution, response time, state/category grouping |
| `payment_breakdown_tool` | payment type, value, share, orders |
| `delivery_performance_tool` | delay, on-time rate, by state or route |

Every public tool wrapper returns a structured result with `ok`, `rows`, `metadata`, or an `error` object. Exceptions are contained by the dispatcher instead of being allowed to crash the overall agent flow.

The category query explicitly joins `product_category_name_translation` so the returned category field is English. This matches the assignment's warning that returning product data without this translation join is incomplete.

## 7. Natural-language parameter handling

The planner prompt and fallback parser cover the assignment's specified resolutions:

- `last year` -> 2017-01-01 to 2017-12-31
- `first half of 2017` -> 2017-01-01 to 2017-06-30
- `São Paulo` -> `SP`
- `top 10` -> `limit=10` with descending ranking
- `worst rated` -> ascending average review score
- English category names -> resolved through the translation table
- no date range -> full dataset assumption is stated in the response

Those mappings are part of the assignment itself.

## 8. Agent design

`ILLMAgent` is the interface boundary. The rest of the backend only consumes `AgentResult`, so it does not care which agent implementation is active.

### LLM agent

- OpenRouter via the OpenAI-compatible SDK
- model controlled by `OPENROUTER_MODEL`
- native tool calling
- configurable `LLM_TIMEOUT_SECONDS`
- up to three tool-call rounds
- safe handling of malformed tool arguments
- final summary step constrained to a small JSON object

OpenRouter's current tool-calling flow is request -> `tool_calls` -> application executes the tool -> tool result is appended -> next model request. The implementation follows that pattern rather than pretending the model executes the database operation itself.

### Fallback agent

The fallback is intentionally boring, which is useful during an outage. It uses keyword routing, extracts obvious parameters with deterministic regexes, calls one MCP capability, and always chooses a bar chart downstream. That matches the requirement that the fallback use no LLM and always produce a bar chart.

## 9. Chart selection logic

The assignment gives explicit minimum rules. The backend implements them as deterministic logic rather than relying on a free-form model decision.

| Returned shape | Result |
|---|---|
| one metric over month | line |
| two metrics over same time axis | dual-axis line |
| ranked top-N list | horizontal bar, descending |
| category comparison | vertical bar |
| part-to-whole payment mix | donut |
| two continuous entity variables | scatter |
| 1–5 score distribution | stacked horizontal bar |

For genuinely ambiguous shapes, the design leaves room for the API layer to return alternative options later. The current sample queries have deterministic shapes, so a single chart is returned.

## 10. Dashboard and refresh diff

Pins are stored in a small application SQLite database on the named Docker volume, so they survive a restart.

A pin stores the original natural-language query and the last generated payload. Refreshing a pin re-runs the original query, then compares the numeric chart series against the saved snapshot.

The current significance rule is a relative mean absolute difference of at least 5% across the overlapping numeric series:

```text
change_score = mean(abs(new - old)) / mean(abs(old))
changed = change_score >= 0.05
```

This threshold is deliberately simple and explainable. It avoids pretending there is statistical significance where there is only a product-level “something changed enough to look at this again” signal. The refresh response surfaces both the boolean and the score.

## 11. Failure handling

The assignment calls for no chart when the dataset cannot answer a question or a filter returns no rows, and for partial results when one tool times out.

The implementation handles those cases in three places:

- Guardrails reject clearly out-of-scope topics before any chart is built.
- MCP returns structured error payloads for validation and empty-result cases.
- The LLM agent records per-tool failures and keeps successful tool results, so a partial response can still be visualized with a warning naming the failed source.

## 12. API surface

```text
GET    /health
POST   /api/ask
GET    /api/pins
POST   /api/pins
DELETE /api/pins/{id}
POST   /api/pins/{id}/refresh
```

`POST /api/ask` is the main integration point. A request looks like:

```json
{
  "query": "Show monthly revenue trend for 2017"
}
```

A successful response contains:

```json
{
  "query": "...",
  "assumptions": [],
  "chart_type": "line",
  "chart_justification": "...",
  "insight": "...",
  "chart_config": { "type": "line", "data": {}, "options": {} },
  "rows": [],
  "tool_trace": [],
  "agent_mode": "llm",
  "warnings": []
}
```

## 13. Demo walkthrough

Use these five queries in this order. They map directly to the assignment's sample-query section.

```text
1. Show monthly revenue trend for 2017
2. Which product categories generate the most revenue?
3. Which states have the worst delivery performance?
4. What share of payments are credit card vs boleto?
5. Do sellers with faster delivery get better reviews?
```

For a demo recording, show the browser, run each query, point briefly at the tool trace, and pin one result. Then refresh the pin so the change indicator is visible.

## 14. Production-minded choices

This is still internship-assignment sized, but the architecture leaves useful seams for production work:

- typed API contracts with Pydantic
- isolated agent interface
- isolated MCP boundary
- timeout controls for model and tool calls
- structured tool errors
- SQLite indexes on join keys
- persistent state in a Docker volume
- deterministic visualization policy
- healthcheck-gated service startup
- logs and timing hooks around application spans
- no secrets committed to source
- frontend bundled into the image, so the browser does not depend on a CDN at runtime

For a larger production deployment I would move the Olist warehouse and dashboard state to Postgres, put the MCP server behind service auth, add OpenTelemetry traces, add a model/evaluator dataset for regression testing, and track query latency / tool accuracy / fallback rate as explicit service metrics.

## 15. Dataset note

The source dataset is the Brazilian E-Commerce Public Dataset by Olist, licensed CC BY-NC-SA 4.0 as stated in the assignment.
