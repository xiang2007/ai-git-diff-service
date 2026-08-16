# AI Git Diff Service

## Authentication

Set the service's bearer token in the environment before starting it:

```bash
export API_BEARER_TOKEN="replace-with-a-long-random-token"
fastapi dev
```

Send that token on every `/v1/*` request in the `Authorization` header:

```bash
curl http://127.0.0.1:8000/v1/jobs \
  -H "Authorization: Bearer replace-with-a-long-random-token"
```

`/health` and `/spec` remain public. In `/docs`, click **Authorize** and enter
the token value without the `Bearer` prefix.

# Plan

Build a small authenticated HTTP service around an asynchronous review-job pipeline, using Python 3.12 and FastAPI. Keep the mock provider deterministic and independent from the optional LLM provider so the contract, ordering, streaming, caching, and failure handling are all testable locally before deployment; package it as a single container and deploy it to a managed container host.

## Scope

- In: The `/health`, `/spec`, and versioned review endpoints; auth; diff validation and chunking; mock and LLM providers; job lifecycle, caching, idempotency, SSE replay, rate limiting, tests, container infrastructure, deployment documentation, and submission notes.
- Out: Persistent multi-node job storage, a web UI, repository cloning, review rules beyond the specified mock rules, and high-availability infrastructure.

## Action Items

[ ] Establish Python 3.12, FastAPI, Uvicorn, pytest, and typed environment settings for the API bearer token and LLM credentials.

[ ] Scaffold the FastAPI application with semantic versioning, public `GET /health` and `GET /spec`, error-envelope handling, and bearer authentication for every `/v1/*` route.

[ ] Implement unified-diff parsing, 1-MiB payload validation, new-file line tracking, and file-boundary chunking at 64 KiB.

[ ] Implement the deterministic mock provider for all nine rules, including multiline empty catches and inert prompt injection; deduplicate, order, and truncate findings correctly.

[ ] Define the provider interface and add an LLM implementation with server-side credentials, structured-output validation, timeouts, and graceful failed jobs when unavailable.

[ ] Build the asynchronous job manager with four workers, lifecycle tracking, usage metrics, content-addressed caching, and idempotency-key replay/conflict handling.

[ ] Implement review submission, result polling, ordered/replayable SSE events, and POST-only rate limiting with compliant `429` responses.

[ ] Add a production Dockerfile, `.dockerignore`, pinned dependencies, non-root execution, health checks, and an environment example that never contains secrets.

[ ] Write and run contract/integration tests for rules, auth, errors, chunking, concurrency, caching, idempotency, SSE replay, rate limits, container operation, and unavailable-LLM behavior.

[ ] Deploy the tagged container to a managed container host with HTTPS and platform-managed secrets; verify the public and authenticated flows, then document architecture, verification, AI-tool use, and submission credentials in `SUBMISSION.md`.

## Open Questions

- Which managed container host will be used (for example, Google Cloud Run, Render, or Fly.io) and what plan will keep it reachable for the 48-hour scoring window?
- Which real LLM provider and credential source should back the optional `llm` path?
