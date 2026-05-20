# Contract: `ReviewResult` wire shape — feature 012 additions

**Endpoints**: `POST /api/review`, `GET /api/reviews/{id}`
**Source of truth**: `backend/src/codesensei/review/schema.py:ReviewResult`

## Existing fields (unchanged)

```json
{
  "verdict": "approve" | "request_changes" | "comment",
  "findings": [ /* Finding[] */ ],
  "provider": "openai",
  "elapsed_ms": 1832,
  "context_files": ["src/x.py"]
}
```

## New fields (added by feature 012)

```json
{
  "prompt_tokens": 1234,
  "completion_tokens": 567,
  "cost_usd": 0.002340
}
```

| Field | Type | Nullability | Notes |
|-------|------|-------------|-------|
| `prompt_tokens` | integer | nullable | Provider-reported input tokens. `null` when the provider does not surface usage (Ollama in some modes) OR when the call short-circuited before reaching the provider. |
| `completion_tokens` | integer | nullable | Provider-reported output tokens. Same null semantics. |
| `cost_usd` | number | nullable | USD cost rounded to 6 dp. `null` when either token field is `null` OR when `(provider, model)` is not present in the pricing table. |

## Combined examples

**Happy path (OpenAI, known pricing)**:

```json
{
  "verdict": "request_changes",
  "findings": [ /* ... */ ],
  "provider": "openai",
  "elapsed_ms": 1832,
  "context_files": null,
  "prompt_tokens": 1234,
  "completion_tokens": 567,
  "cost_usd": 0.000525
}
```

**Anthropic provider, unknown model in pricing table**:

```json
{
  "verdict": "approve",
  "findings": [],
  "provider": "anthropic",
  "elapsed_ms": 2150,
  "context_files": null,
  "prompt_tokens": 980,
  "completion_tokens": 12,
  "cost_usd": null
}
```

**Ollama provider, no usage surfaced**:

```json
{
  "verdict": "comment",
  "findings": [ /* ... */ ],
  "provider": "ollama",
  "elapsed_ms": 5300,
  "context_files": null,
  "prompt_tokens": null,
  "completion_tokens": null,
  "cost_usd": null
}
```

**Historical row pre-dating feature 012** (via `GET /api/reviews/{id}`):

```json
{
  "verdict": "comment",
  "findings": [ /* ... */ ],
  "provider": "openai",
  "elapsed_ms": 1200,
  "context_files": null,
  "prompt_tokens": null,
  "completion_tokens": null,
  "cost_usd": null
}
```

## Backward compatibility

All three new fields default to `null` (not absent). Pre-feature clients that consume the response either:

1. Ignore unrecognised JSON keys (the only stance the existing CodeSensei frontend takes), in which case nothing breaks.
2. Strictly validate the shape, in which case they would have already broken at every prior feature that extended `ReviewResult`. The pattern is unchanged.
