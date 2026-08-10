# Q-PRIME NLP API

This Flask service converts natural-language questions to read-only SQL,
sends that SQL to an externally configured query API, and summarises the
returned rows.

It does not connect to databases or retain queried data.

## API

```text
GET  /api/health
POST /api/query
```

Example request:

```json
{
  "query": "how many door events today",
  "type": "natural",
  "scope": "continuum"
}
```

The `scope` may be `continuum`, `edge`, or `cloud`. Responses include the
generated SQL, raw external rows, a natural-language summary, and any tier
counts supplied by the external endpoint.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `QUERY_API_URL` | unset | Required external read-only query endpoint |
| `CONTINUUM_DB` | `qprime` | SQL catalog/database name |
| `CONTINUUM_TABLE` | `continuum` | SQL table name |
| `EPOCH_SCALE` | `s` | Timestamp unit: `s`, `ms`, or `ns` |
| `LOCAL_TZ_NAME` | `Australia/Sydney` | Timezone for relative dates |
| `USE_LLM_SQL` | off | Give an optional local model the first attempt at unmatched questions |
| `USE_LLM_SUMMARY` | off | Use the optional local model for summaries |

Without `QUERY_API_URL`, actionable queries return HTTP 503 with setup
instructions. Greetings and help prompts still work locally.

```bash
pip install -r requirements.txt
QUERY_API_URL=http://your-query-service/api/query python app.py
```
