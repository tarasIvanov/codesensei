# Contract: `/api/reviews` endpoints — feature 012 additions

**Endpoints**: `GET /api/reviews?limit=N`, `GET /api/reviews/{id}`
**Source of truth**: `backend/src/codesensei/reviews_history/schema.py`

## `GET /api/reviews?limit=N` (list)

Response shape adds three optional fields to each summary row.

```json
{
  "runs": [
    {
      "id": "8c3c7b07-6102-4503-9802-38429381fc95",
      "created_at": "2026-05-21T15:42:11Z",
      "verdict": "request_changes",
      "provider": "openai",
      "finding_count": 5,
      "elapsed_ms": 1832,
      "input_kind": "pr_url",
      "pr_url": "https://github.com/.../pull/14",
      "has_temporal": true,
      "prompt_tokens": 1234,
      "completion_tokens": 567,
      "cost_usd": 0.000525
    }
  ]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `prompt_tokens` | integer / null | Mirrors the persisted column. |
| `completion_tokens` | integer / null | Mirrors the persisted column. |
| `cost_usd` | number / null | Mirrors the persisted column (NUMERIC(10, 6) coerced to JSON number). |

## `GET /api/reviews/{id}` (detail)

Response shape is byte-shape-identical to the live `POST /api/review` response (see `review_result.md`). The three new fields appear exactly as in the live response.

## `DELETE /api/reviews/{id}`

No change. Existing 204/404 semantics apply.

## Backward compatibility

- Pre-feature rows have `NULL` for all three columns; the API surfaces them as `null` in JSON.
- The frontend renders `tokens N/A` for such rows; the persisted run still loads, opens, deletes normally.
- No new error categories are introduced.
