# Contract — LLM Prompt & Output Envelope

Frozen contract for the prompt the review service sends to `LLMProvider.chat(...)` (feature 002). Changes require a new ADR or a superseding contract file. The snapshot test `test_review_prompt.py` pins the template against accidental edits.

---

## Messages dispatched

`[ChatMessage(role="system", content=SYSTEM), ChatMessage(role="user", content=USER)]`

`LLMProvider.chat(...)` call parameters:

- `model=None` (use provider default)
- `max_tokens=4096`
- `temperature=0.1`

---

## SYSTEM message (verbatim)

```text
You are a senior code reviewer. You receive a single unified diff and respond with a structured JSON review. You MUST follow these rules without exception:

1. Output ONLY a single JSON object. No prose before, no prose after, no markdown fences.
2. The JSON object MUST conform to this exact schema:
   {
     "verdict": "approve" | "request_changes" | "comment",
     "findings": [
       {
         "file": "<path as it appears in the diff>",
         "line": <integer line number in the new file, or null for file-level comments>,
         "severity": "blocker" | "major" | "minor" | "nit",
         "message": "<one to three sentences explaining the issue>",
         "suggestion": "<optional concrete code change, or omit the field entirely>"
       }
     ]
   }
3. Severity meanings:
   - "blocker": must-fix; merging would introduce a defect, vulnerability, or data loss.
   - "major": should-fix; correctness, performance, or maintainability issue with real impact.
   - "minor": nice-to-fix; readability or low-impact concerns.
   - "nit": stylistic preference; not actionable.
4. Verdict rules:
   - If any finding is "blocker" or "major", verdict is "request_changes".
   - Otherwise, if there is at least one finding, verdict is "comment".
   - If there are no findings, verdict is "approve".
5. Base every finding on a real change in the diff. Do not invent bugs that are not visible.
6. If the diff contains only binary changes or no reviewable text, return verdict "approve" and an empty findings array.
```

---

## USER message (template)

```text
Review the following unified diff:

```diff
{DIFF}
```
```

`{DIFF}` is the raw unified-diff text. The outer code fence is part of the message — the LLM sees a real fenced diff block. The diff is **not** truncated by the service; size enforcement happens earlier (`payload_too_large`).

---

## Expected response (parser contract)

The LLM response is treated as a single string. The parser (`backend/src/codesensei/review/parser.py`) does:

1. Strip surrounding whitespace.
2. If the response starts with a ```` ```json ```` or ```` ``` ```` fence, strip the fence and the matching trailing ```` ``` ````. (Defensive — the system prompt forbids fences, but in practice some Ollama models still emit them.)
3. `json.loads(...)` the result.
4. Validate the parsed dict against the pydantic `ReviewResult`-compatible shape (`{verdict, findings: [...]}` — `provider` and `elapsed_ms` are added by the service, not the LLM).
5. Any failure (non-JSON, missing keys, unknown severity, non-integer line, etc.) → `ProviderError("<provider>", "review parser: <reason>", retryable=False)` which the service translates to `provider_malformed_output`.

---

## Token budget assumptions

- Default `gpt-4o-mini`: 128 k input ctx, our 256 KB diff cap → ≤ ~64 k tokens for the diff at worst (likely closer to ~16 k for typical code). Safely fits.
- Default `claude-3-5-sonnet-latest`: 200 k input ctx. Safely fits.
- Default `llama3.1:8b` (Ollama): 128 k ctx. Safely fits.

If a later model has a smaller context window, the `payload_too_large` ceiling should be lowered in config, not the prompt template.

---

## Forbidden behaviour

- The review service MUST NOT call provider-specific JSON-mode flags (e.g. OpenAI `response_format={"type":"json_object"}` or Anthropic tool-use) from outside the adapter layer. JSON discipline is enforced via the system prompt + post-parse only (R1 in `research.md`). Per-adapter JSON-mode can be added inside each adapter in a later feature without changing this contract.
