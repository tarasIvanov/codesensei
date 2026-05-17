# Contract — LLM Prompt v2 (SYSTEM delta vs 003)

Supersedes the SYSTEM section of `specs/003-pr-review-mvp/contracts/llm_prompt.md`. The USER template and the parser contract from 003 are **unchanged**.

The new SYSTEM message is exactly the 003 SYSTEM message with two new rules inserted into the rule list and one new "Example" block appended at the end.

---

## SYSTEM message (verbatim, after this feature)

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
3a. Blocker tier (mandatory). Findings that describe any of the following MUST use severity "blocker": hardcoded credentials or API keys; SQL injection (any user input concatenated into a SQL string); eval()/exec()/compile() of user-controlled input; deserialisation of untrusted data; remote-code-execution vectors; arbitrary-shell-command execution. Do not downgrade these to "major".
4. Verdict rules:
   - If any finding is "blocker" or "major", verdict is "request_changes".
   - Otherwise, if there is at least one finding, verdict is "comment".
   - If there are no findings, verdict is "approve".
5. Base every finding on a real change in the diff. Do not invent bugs that are not visible.
5a. Line-number anchor. The "line" field in every finding MUST refer to the new-file line number visible in the diff's `@@ -A,B +C,D @@` hunk headers, not to a position inside the diff text. If a hunk header reads `@@ -0,0 +1,71 @@`, then the first added line in that hunk is line 1 of the new file.
6. If the diff contains only binary changes or no reviewable text, return verdict "approve" and an empty findings array.

Example finding for a hardcoded credential:
{"verdict": "request_changes", "findings": [{"file": "samples/login_service.py", "line": 14, "severity": "blocker", "message": "ADMIN_API_KEY is hardcoded at module level. Anyone with read access to the source can extract it.", "suggestion": "ADMIN_API_KEY = os.environ['ADMIN_API_KEY']"}]}
```

---

## What is pinned by the snapshot test (test_review_prompt.py)

The full SYSTEM string is **not** SHA-pinned (overly brittle for prompt iteration). Instead, the snapshot test asserts the presence of each of the following substrings — every one of them is a load-bearing fragment whose absence is a regression:

| Pin | Substring                                                                |
|-----|--------------------------------------------------------------------------|
| P1  | `"You are a senior code reviewer."`                                      |
| P2  | `'"verdict": "approve" \| "request_changes" \| "comment"'`               |
| P3  | `'"severity": "blocker" \| "major" \| "minor" \| "nit"'`                 |
| P4  | `"Output ONLY a single JSON object"`                                     |
| P5  | `'Blocker tier'`                                                          |
| P6  | `'hardcoded credentials'`                                                 |
| P7  | `'SQL injection'`                                                         |
| P8  | `'eval()/exec()/compile()'`                                              |
| P9  | `'Line-number anchor.'`                                                   |
| P10 | `'@@ -A,B +C,D @@'`                                                       |
| P11 | `'Example finding for a hardcoded credential:'`                          |

P1–P4 carry over from 003's pins (verbatim); P5–P11 are new pins from this feature's additions. The USER template and parser contract pins from 003 are unchanged and still apply.

---

## Token-budget impact

The additions total roughly **350 input tokens** (rough count). The defaults from 003's quickstart still hold: every supported model has hundreds of thousands of input-context tokens available; the 256 KB diff cap stays untouched.

---

## Forbidden behaviour (unchanged from 003)

The review service still MUST NOT call provider-specific JSON-mode flags from outside the adapter layer. JSON discipline is enforced via system prompt + post-parse only. R1 from 003's research stands.
