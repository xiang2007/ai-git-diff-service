# SUBMISSION

## Service details

- Base URL: https://your-service.example.com
- Bearer token: <redacted-long-random-token>
- Repository: https://github.com/your-org/ai-git-diff-service

## Architecture

FastAPI service with a single authenticated API surface and an in-memory
async job pipeline.

- `/health` and `/spec` are public; every `/v1/*` route requires a bearer token
  via a router-level dependency.
- `POST /v1/reviews` validates the body, parses the diff with `unidiff`, chunks
  files on 64 KiB boundaries, and enqueues the job.
- Four asyncio workers process jobs concurrently; a fifth job queues without
  failing.
- Mock findings are deterministic; Gemini findings are validated against the
  actual added lines before being stored.
- Jobs expose polling and an ordered, replayable SSE stream backed by an
  in-memory event log.
- Caching is keyed by the SHA-256 of the raw request body; idempotency keys map
  to a body hash and existing job id.
- Deployment is a non-root, healthchecked container built with `uv`.

## Provider design

The provider boundary is one function per provider that receives parsed diff
chunks and returns a normalized list of finding objects.

- `mock`: implements the nine contract rules exactly, scans added lines only,
  reports new-file line numbers, dedupes by id, and sorts by path, line, then
  rule id. Prompt-injection text is treated as inert content and reported.
- `llm`: uses Gemini with server-side credentials. Responses are parsed through
  a constrained schema, then validated against the actual added lines so the
  model cannot invent paths or line numbers. Timeouts, unreachable APIs, and
  invalid responses degrade to a `failed` job with a clear error — never a
  crash.

## Cross-cutting behaviors verified

- Authentication: missing/wrong/non-Bearer tokens return 401 with the error
  envelope on every `/v1` route; health and spec stay public.
- Error taxonomy: malformed JSON returns 400 `invalid_json`; missing, empty, or
  unparseable diffs return 422 `invalid_diff`; oversized payloads return 413.
- Mock rules: each rule tested against a crafted diff, including multiline
  empty catches and case-insensitive injection phrases.
- Chunking: multi-file diffs over 64 KiB split only at file boundaries; scan
  output matches an unchunked run.
- Ordering and dedup: results sorted by path, line, rule id, deduped by id.
- Caching and idempotency: byte-identical submissions return `cacheHit: true`;
  identical idempotency keys return the same job id; mismatched bodies return
  409.
- SSE: status/finding/done events are ordered, and reconnecting to a finished
  job replays the same sequence.
- Rate limiting and concurrency: 30 submissions per minute pass; excess gets
  429 with `Retry-After`; four jobs run concurrently and a fifth queues.
- LLM degradation: missing credentials or an unreachable Gemini API produce a
  failed job, not an unhandled exception.

## AI tools used

Codex was used to scaffold and review the FastAPI routes, auth dependency,
error handling, chunking, mock rules, Gemini provider, job lifecycle, and
Docker setup. Generated code was tested against the contract with local
scripts and adjusted where behavior diverged from the spec.

## AI suggestion rejected

Codex initially suggested a middleware-based payload-size check. I rejected it
in favor of reading the already-cached request body inside the single POST
route: there is only one endpoint subject to the 1 MiB limit, and a route-level
check avoids middleware lifecycle complexity without weakening the behavior.

## Next steps with more time

- Add a full pytest suite and CI so contract probes run on every commit.
- Move job/cache state to Redis or a database for multi-instance deployments.
- Add TTL/LRU eviction for caches and job state.
- Add request IDs and structured logs for observability.
- Generalize the LLM boundary behind a common provider interface for additional
  vendors.
- Harden startup configuration validation and pin container image digests.