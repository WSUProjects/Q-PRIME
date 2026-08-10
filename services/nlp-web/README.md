# Q-PRIME query application

Next.js UI for querying and visualising IoT data through an external read-only
query endpoint. It provides sensor cards, charts, SQL access, and a natural-
language chat interface backed by `services/nlp`.

The application does not contain database or device connectors.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `QUERY_API_URL` | core API in Compose | Server-side Q-PRIME query endpoint used by cards and charts |
| `LLM_API` | `http://qprime-nlp:5500` | NLP API used by chat requests |
| `NEXT_PUBLIC_SQL_TABLE_NAME` | `qprime.continuum` | Logical table used in generated chart SQL |
| `NEXT_PUBLIC_BASE_PATH` | empty | Optional deployment base path |

When `QUERY_API_URL` is unset, data requests return HTTP 503 with a
configuration message.

## Development

```bash
npm install
QUERY_API_URL=http://your-query-service/api/query \
LLM_API=http://localhost:5500 \
npm run dev
```

Open <http://localhost:3000>.
