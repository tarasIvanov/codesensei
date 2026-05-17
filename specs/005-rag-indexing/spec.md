# Feature Specification: Repo indexing + RAG-augmented review

**Feature Branch**: `005-rag-indexing`
**Created**: 2026-05-17
**Status**: Draft
**Input**: User description: "Extend `/api/review` from diff-only to retrieval-augmented — review sees relevant context from the whole repository, not just the diff. Sync indexing for small repos, async (queue-backed) for larger ones, a Vue `/repos` page to manage indexed repositories, and a context-repo selector on `/review`."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Index a small repository synchronously (Priority: P1)

A reviewer points the system at a small public repository (or a local mounted path). The system pulls the source, breaks it into searchable code chunks, computes semantic vectors for each chunk, persists everything, and immediately confirms the repository is ready for retrieval.

**Why this priority**: Without an indexed repository there is no retrieval — every later capability (RAG review, async indexing, the `/repos` UI) depends on this slice. Synchronous indexing for small inputs is the cheapest demoable path and proves the full embed-and-store pipeline end-to-end.

**Independent Test**: With the system freshly deployed and an empty database, the reviewer submits one small repository (≤200 source files); within roughly a minute they get back a repository identifier and a non-zero chunk count, and a follow-up listing call shows that repository with a recent indexed-at timestamp. No retrieval and no UI is required to validate this story — the index API alone proves the value.

**Acceptance Scenarios**:

1. **Given** the repository registry is empty, **When** the reviewer submits a public HTTPS URL pointing at a repository with 50 source files, **Then** the system responds with a success result containing a new repository identifier, a chunk count greater than zero, and an indexed-at timestamp, and a subsequent listing call returns exactly that one repository.
2. **Given** one repository has already been indexed, **When** the reviewer submits a second repository at a local mounted path, **Then** both repositories appear in the listing call, ordered with the most-recently-indexed first.
3. **Given** an indexed repository exists, **When** the reviewer issues a delete call for that repository, **Then** the repository disappears from the listing and all chunks associated with it are removed.
4. **Given** the reviewer submits a request that would exceed the repository size cap (more than 5,000 chunks would be produced), **When** the system performs its pre-scan, **Then** the request is rejected with a clear "too large" error before any embedding work is paid for, and no partial repository row remains in the registry.
5. **Given** the reviewer submits a URL that cannot be cloned (bad URL, network failure, private repo), **When** the system attempts to fetch it, **Then** the response carries a clear, distinct error category and no repository row remains.

---

### User Story 2 — Review a diff with repository context (Priority: P2)

A reviewer who has already indexed a repository submits a pull-request review request and asks the system to consult that repository while reviewing. The system finds chunks that are semantically related to the changes in the diff, includes them as additional context for the LLM, and returns findings that demonstrably reference the wider codebase rather than just the patch lines.

**Why this priority**: This is the actual end-user value of the feature — better, context-aware reviews. It depends on US1 (you need something to retrieve from) but does not require async indexing or the UI, so it is the second slice we ship.

**Independent Test**: With one repository already indexed (delivered by US1), the reviewer submits a review call that names that repository as the context source and supplies a diff that touches code present in the repository; the response is a structured review with at least one finding, the response also lists which repository files contributed retrieved context, and the same call without the repository identifier produces the unaugmented review (proving the new path does not regress the old one).

**Acceptance Scenarios**:

1. **Given** a repository has been indexed and contains a function `compute_total` in `billing.py`, **When** the reviewer submits a diff that modifies `compute_total` and asks for review using that repository as context, **Then** the response includes the file `billing.py` in the list of files that contributed retrieved context.
2. **Given** the reviewer submits a review request with no repository identifier, **When** the system processes the request, **Then** the response is structurally identical to the previous release's behaviour: findings, verdict, and severities — and no field about retrieved context is added.
3. **Given** the reviewer submits a review request naming a repository identifier that does not exist, **When** the system looks it up, **Then** the response is a clean validation error that names the unknown identifier and no language-model call is made.
4. **Given** retrieval would inject so much context that the language-model prompt would exceed safe size, **When** the system assembles the prompt, **Then** retrieved context is trimmed (down to the highest-scoring chunks) so that the prompt stays within the safe budget, and the trimming is logged for the operator to inspect.
5. **Given** an indexed repository where no chunks score above a low-similarity floor for the given diff, **When** the review runs, **Then** the response still completes, the list of files that contributed retrieved context may be empty, and the operator log records that retrieval produced no useful matches.

---

### User Story 3 — Index a larger repository asynchronously (Priority: P3)

A reviewer points the system at a repository big enough that indexing would block their browser tab. The system accepts the work, returns a tracking handle immediately, and the reviewer can poll status until indexing finishes. Re-indexing the same repository later replaces the stored chunks cleanly, without leaving stale vectors behind.

**Why this priority**: Without this slice the feature only works on small repositories. It is third because users can get demonstrable value (US1 + US2) on small inputs first, and the async path reuses the queue scaffold delivered in feature 004 rather than introducing new infrastructure.

**Independent Test**: With the system freshly deployed, the reviewer submits a repository whose pre-scan indicates more than 200 source files; the response immediately carries a tracking handle and a repository identifier whose indexed-at is empty; polling the tracking handle returns a status that progresses from pending to complete; after the job is done the repository listing shows the same identifier with a non-empty indexed-at and a non-zero chunk count. Re-submitting the same URL replaces the chunks without growing the count beyond what the second pass produced.

**Acceptance Scenarios**:

1. **Given** a repository registry is empty, **When** the reviewer submits a public URL whose pre-scan finds 800 source files, **Then** the response is accepted-for-processing, contains a tracking handle and a new repository identifier, and the registry shows the repository with an empty indexed-at and a zero chunk count.
2. **Given** an async indexing job is in flight, **When** the reviewer polls the tracking handle, **Then** the response status moves through pending and complete in finite time without errors visible to the reviewer.
3. **Given** an async job has completed for a repository, **When** the reviewer submits the same repository URL again, **Then** the second indexing pass replaces (not appends) the chunks of the first pass — the final chunk count equals only what the second pass produced.
4. **Given** an async job hits the repository size cap mid-flight, **When** the worker reaches the limit, **Then** the job ends with a clear "too large" status, the repository row is marked failed with the reason recorded, and no partial chunks are queryable from the retrieval path.
5. **Given** the worker is unreachable when the reviewer submits an async-eligible repository, **When** the system tries to enqueue, **Then** the response is a clean "queue unavailable" error and the registry holds no partial repository row.

---

### User Story 4 — Manage indexed repositories from the UI (Priority: P3)

A reviewer who prefers the web UI opens a new "Repositories" page, submits a URL through a form, watches progress for async jobs, sees the list of indexed repositories, and re-indexes or deletes any of them. On the review page they choose which repository (if any) should provide context for the next review.

**Why this priority**: The endpoints in US1–US3 are usable from the command line, but a thesis demo needs visible UI to be credible. It is third because the API path is already demoable; the UI layers convenience on top.

**Independent Test**: With the system freshly deployed, the reviewer opens the "Repositories" page in a browser, fills the URL field, clicks "Index now", sees the new repository appear in the on-page list with a chunk count and a timestamp (sync repos appear immediately; async repos show a progressing status bar), clicks "Delete" on a row and confirms it disappears, then opens the "Review" page, sees a "Use context from repository" selector populated with the remaining indexed repositories, picks one, runs a review, and the result page shows the list of repository files that contributed retrieved context.

**Acceptance Scenarios**:

1. **Given** the reviewer is on the "Repositories" page with no indexed repositories, **When** they submit a small public URL, **Then** within a few seconds the page shows the new repository with its URL, chunk count, and indexed-at timestamp.
2. **Given** the reviewer submits a URL that triggers async indexing, **When** the job is in flight, **Then** the page shows the repository row with a "indexing…" status that resolves to a chunk count and timestamp once the job is complete, without the reviewer having to refresh.
3. **Given** the reviewer has at least one indexed repository, **When** they open the "Review" page, **Then** a context-repository selector is visible and the previously-default "no context" option is preserved as the first choice; selecting a repository and submitting a review issues the review request against that repository.
4. **Given** the reviewer has no indexed repositories, **When** they open the "Review" page, **Then** the context-repository selector is hidden or shown disabled with a hint that no repositories are available, and the review flow still works exactly as it did before this feature.
5. **Given** the reviewer clicks "Delete" on a repository, **When** the confirmation is accepted, **Then** the row vanishes from the list and the same repository no longer appears in the "Review" page's selector.

---

### Edge Cases

- The reviewer submits a URL that points at a valid repository but every file is binary or unsupported; the index call should complete with zero chunks and a clear note in the registry, and the repository should not be offered for retrieval until it has at least one chunk.
- The reviewer submits two indexing requests for the same URL at almost the same moment; the second one must not corrupt the first — either it waits, returns the same handle, or is rejected with a clear "already indexing" message.
- The reviewer asks for context retrieval on a brand-new repository whose async job is still in flight; the review either fails with a clear "repository not ready" message or proceeds without context, but never reads partial data.
- The reviewer deletes a repository while a review using it as context is in flight; the in-flight review either completes with whatever context it already retrieved or fails with a clean error, but the system must never leave dangling chunk references.
- A retrieval query returns chunks whose source files have since been deleted from the repository (e.g., between two re-indexings, a file was renamed or removed); the response must either gracefully drop those chunks or surface their stale paths, but must never crash.
- The configured embedding provider is unreachable when indexing starts; sync indexing must fail cleanly and the registry must not hold a half-built repository row; async indexing must surface the failure on the tracking handle without leaving the worker queue jammed.
- The reviewer asks for a review with retrieval, but the configured embedding provider differs from the one used at index time; the system must detect the mismatch and refuse retrieval with a clear message rather than silently returning meaningless nearest-neighbour matches.

## Requirements *(mandatory)*

### Functional Requirements

**Registry & lifecycle (US1, US3)**

- **FR-001**: System MUST accept indexing requests that name a repository by either a public HTTPS URL or a path to a locally mounted directory.
- **FR-002**: System MUST persist, for every indexing attempt, a registry row that includes a stable identifier, the source URL or path, the default branch (when applicable), the indexed-at moment of the most recent successful pass, the chunk count produced, and the last error message (if any).
- **FR-003**: System MUST expose a listing endpoint that returns all known repositories ordered with the most-recently-indexed first.
- **FR-004**: System MUST expose a delete endpoint that removes a repository and all of its chunks together in a single operation, leaving no orphaned vectors.
- **FR-005**: System MUST reject any indexing request that would produce more than 5,000 chunks with a distinct "too large" error category, MUST not start embedding work for such a request, and MUST not leave a partial repository row behind.
- **FR-006**: System MUST classify each indexing request, before embedding any content, as either "small enough for synchronous processing" or "large enough for asynchronous processing"; the deciding rule MUST use a published, deterministic threshold (default: ≤200 source files → synchronous).

**Chunking & embedding (US1, US3)**

- **FR-007**: System MUST split a repository's source files into searchable chunks using language-aware boundaries where possible (function/class for Python, fixed-line sliding windows with overlap as the fallback for less-structured files, heading-based splits for Markdown).
- **FR-008**: System MUST record, for every chunk, the source file path, the language label, the start and end line numbers in the source file, the raw chunk text, and the embedding vector produced by the system's configured embedding provider.
- **FR-009**: System MUST batch embedding requests so that small repositories are not penalised by per-call latency, and MUST fail the whole indexing attempt cleanly if the embedding provider becomes unreachable mid-way (no partial repository, no orphan chunks).
- **FR-010**: System MUST persist, alongside each repository, the name of the embedding provider and the model identifier used when the chunks were generated, so that later retrieval requests can be rejected if a different embedding model is currently active.

**Asynchronous path (US3)**

- **FR-011**: For requests classified as asynchronous, System MUST immediately create the repository row with an empty indexed-at and a zero chunk count, MUST enqueue a background job, and MUST return both a repository identifier and a job tracking handle to the reviewer.
- **FR-012**: System MUST expose the background job's status through the same job-status surface used by other background work, so that reviewers can poll one tracking endpoint and see pending / in-progress / complete / failed states.
- **FR-013**: Re-indexing a repository (whether sync or async) MUST replace its stored chunks atomically: while the new pass is running the old chunks remain queryable, and only after the new pass succeeds do the old chunks disappear; on failure the old chunks remain intact.
- **FR-014**: If a background indexing job fails, System MUST record the cause on the repository row in a human-readable form and MUST NOT leave any chunks from the failed attempt queryable from retrieval.
- **FR-015**: If the worker queue is unreachable when an asynchronous-eligible request arrives, System MUST refuse the request with a "queue unavailable" error and MUST NOT leave a stub repository row.

**Retrieval-augmented review (US2)**

- **FR-016**: System MUST accept, on its review endpoint, an optional repository identifier; when absent, review behaviour MUST be byte-equivalent to the previous release.
- **FR-017**: When a repository identifier is supplied, System MUST, before invoking the language model, derive one or more semantic queries from the diff (using the new-file content around each hunk, including roughly ten lines of leading and trailing context), MUST request the top semantically-nearest chunks belonging to that repository, and MUST include those chunks in the language-model prompt under a clearly named "Relevant context from repository" section.
- **FR-018**: System MUST enforce an upper bound on the total size of retrieved context injected into the language-model prompt; when the natural top-N exceeds that bound, lower-scored chunks MUST be dropped in score order until the prompt fits, and the trimming MUST be observable to operators in logs.
- **FR-019**: Review responses MUST surface, per response (not per finding), the list of repository files that contributed retrieved context, so the reviewer can see why a particular finding was made.
- **FR-020**: System MUST reject a review request whose named repository does not exist with a validation error that names the offending identifier, and MUST NOT call the language model in that case.
- **FR-021**: System MUST reject retrieval (and clearly say so in the response) when the embedding provider that is currently configured differs from the one that produced the repository's chunks; the review may still proceed without retrieval if the reviewer omits the repository identifier.

**Operator visibility & observability**

- **FR-022**: Every indexing pass MUST emit a structured log entry that records, at minimum, the repository identifier, the number of files scanned, the number of chunks produced, the embedding provider and model, and the total embedding-call duration; this entry is the primary evidence used for cost evaluation in the thesis report.
- **FR-023**: Every retrieval pass attached to a review MUST emit a structured log entry that records the repository identifier, the number of distinct queries issued, the total number of chunks fetched, the number of chunks ultimately injected into the prompt after the size-budget trim, and whether retrieval found any matches at all.
- **FR-024**: Health checks MUST NOT consider the presence or absence of indexed repositories — having no repositories at all is a normal operating state, not a failure.

### Key Entities *(include if feature involves data)*

- **Indexed Repository**: A logical record of one source location the system has been asked to make searchable. Has an identifier, a URL or local path, an optional default branch, the moment of its most recent successful indexing (which may be empty for a freshly-enqueued repository), the current chunk count (zero until indexing completes), the name and model of the embedding provider used during indexing (so that retrieval can detect a mismatch later), and, if the most recent pass failed, a human-readable reason. Two distinct repositories never share an identifier; the same URL may be re-indexed and replaces its previous chunks atomically.
- **Code Chunk**: One contiguous slice of one source file inside one indexed repository, paired with the semantic vector that represents its meaning. Carries the file's path, the language label, the start and end line numbers inside that file, the chunk's text, and the vector. Chunks always belong to exactly one indexed repository; deleting the repository deletes its chunks.
- **Retrieval Result Set**: The transient bundle of chunks selected for a single review call: which repository they came from, which files they came from, their similarity scores, and whether the size-budget trim discarded any of them. This entity has no persisted form — it exists for the duration of one review request — but its summary appears in the response and in the operator log so the reviewer can audit the augmentation.
- **Indexing Job**: A tracked background unit of work that turns one indexed-repository row from "registered" into "fully indexed". Holds a handle that the reviewer can poll, a status that progresses through pending / in-progress / complete / failed, and a reference back to the repository it is filling. Only created for repositories classified as too large for synchronous indexing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can take the system from "freshly started" to "first indexed repository visible in the listing" in under five minutes, with no manual database editing, using nothing but the documented endpoints (or the new UI).
- **SC-002**: Indexing a 200-file repository completes within 90 seconds end-to-end on the cheapest documented embedding provider configuration, including clone-fetch, chunking, embedding, and the index write.
- **SC-003**: For a review request with a repository identifier set, the new code path adds no more than 25 % to the median latency of the existing diff-only review on the same diff, measured on a repository previously indexed against the same embedding provider.
- **SC-004**: For diffs that touch files present in the indexed repository, the response's list of files that contributed retrieved context is non-empty in at least 80 % of test cases drawn from the project's own commit history.
- **SC-005**: The retrieved-context bundle injected into the language-model prompt never exceeds the documented size budget, measured across at least 50 distinct review requests of varied diff sizes.
- **SC-006**: A reviewer cannot, by any combination of failed indexing, partial uploads, deletes, or worker crashes, leave the system in a state where the repository listing claims a non-zero chunk count for a repository whose chunks cannot in fact be retrieved.
- **SC-007**: When the configured embedding provider is changed after indexing, every subsequent retrieval-augmented review either succeeds (because the providers match) or fails fast with the mismatch error — none silently returns nearest-neighbour results computed across two different embedding spaces.

## Assumptions

- The thesis-scope deployment is single-tenant and self-hosted; there is no multi-user permission model and no per-repository access control beyond "if the repository row exists, any caller of the API can use it". Authentication is deferred to a later feature.
- Public HTTPS clones are the only remote source supported in this slice; SSH URLs and authenticated clones are deferred. Local mounted paths are supported because the docker-compose deployment commonly has a working tree mounted for demos.
- The synchronous-vs-asynchronous threshold is a deterministic published number rather than a real-time estimate; counting source files before any embedding work happens is a coarse but auditable proxy for "this won't take long".
- The chunk cap of 5,000 is a hard ceiling chosen to bound cost and latency for a thesis demo; a real-world deployment would expose it as configuration, but for v1 it is fixed.
- The embedding provider abstraction delivered in feature 002 is the source of truth for which provider/model is in use; this feature consumes that abstraction without changing it. Anthropic remains rejected for embedding because Anthropic has no embeddings surface.
- The background-job infrastructure delivered in feature 004 is the source of truth for async work; this feature adds one new job type (repository indexing) and reuses the existing tracking endpoint instead of introducing a parallel system.
- GitHub webhook auto-reindexing, incremental indexing (only-the-changed-files), multi-repository combined search, and authenticated repository sources are explicitly out of scope and deferred to feature 006 or later.
- Repository ignore patterns are limited to the standard `.git` directory and basic `.gitignore` honouring; richer per-language ignore patterns are deferred.
