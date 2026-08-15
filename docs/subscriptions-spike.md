# GraphQL Subscriptions — Feasibility Spike

**Status:** investigation only (no production code). **Question:** can we add
GraphQL subscriptions (server-push, real-time) to NPH, what would it take, and
is it worth it?

**TL;DR:** Feasible. Redis is already in the stack (Celery), which removes one
of the bigger costs. But subscriptions require moving the app to **ASGI in
production** and adding **Channels + WebSocket auth + client plumbing** — a
non-trivial infra change. **Recommendation: defer** until a concrete real-time
need is prioritized; when it is, ship **one** high-value subscription (critical
vitals alerts) as a vertical slice. For merely "fresher" data, Apollo polling
is far cheaper and needs zero infra change.

---

## 1. Current state (as-is)

| Piece | Today |
|---|---|
| GraphQL server | Strawberry `0.316.0` + strawberry-graphql-django `0.86.0`, a single **sync** `JWTGraphQLView` over HTTP |
| Server model | **WSGI** (`config/wsgi.py`, dev `runserver`). `config/asgi.py` is the stock Django ASGI app with **no WebSocket routing** |
| Schema | `Query` + `Mutation` only — **no `Subscription` type** |
| Auth | JWT **bearer in the HTTP `Authorization` header** (`api/auth.get_user_from_request`) |
| Realtime infra | **None.** No Channels, no ASGI/WebSocket server (`uvicorn`/`daphne`), no channel layer wired for app use |
| Redis | **Present** — added for Celery (`CELERY_BROKER_URL`) |
| Frontend | Apollo Client with `HttpLink` + `authLink` only; **no `graphql-ws`** client |

So subscriptions are a green-field addition, not a config flip.

## 2. What subscriptions require (the gap)

1. **Transport = WebSocket.** Strawberry speaks the modern `graphql-ws`
   protocol, but only over **ASGI** — the sync WSGI view cannot serve
   subscriptions.
2. **Run under ASGI in production.** Queries/mutations keep working over HTTP,
   but the process must be served by an ASGI server (**uvicorn** or **daphne**)
   instead of a sync WSGI server (gunicorn-sync). This is a **deployment
   change**. (Celery worker/beat are unaffected.)
3. **Integration path — Django Channels** (the documented strawberry-django
   route): add `channels`, wire `GraphQLProtocolTypeRouter` in `asgi.py`, and
   use a **channel layer** for pub/sub. The channel layer can be
   **`channels_redis` pointed at the Redis we already run for Celery** — nice
   reuse. (A standalone Strawberry ASGI app mounted beside Django is the more
   DIY alternative; Channels is more batteries-included.)
4. **WebSocket auth.** Browsers can't set an `Authorization` header on the WS
   handshake, so the current bearer scheme doesn't carry over. Standard fix:
   send the JWT in the `graphql-ws` **`connection_init` payload**
   (`connectionParams`), validate it in an `on_ws_connect` hook using the
   existing `auth.decode_token`, put the user on the connection context, and
   reject on failure. Also handle **access-token expiry** on long-lived sockets
   (short 15-min access tokens today) — re-auth or refresh over the socket.
5. **A `Subscription` type + an event source.** Async-generator resolvers that
   yield when something happens; producers (mutations, Celery tasks) **publish**
   events to the channel layer, subscribers receive them.
6. **Frontend plumbing.** Add `graphql-ws` + a `GraphQLWsLink`, and a **split
   link** so subscriptions go over WS while queries/mutations stay on
   `HttpLink`; pass the token via `connectionParams`; handle reconnects.

## 3. Effort & risks

- **Infra (biggest):** production must move WSGI → ASGI (uvicorn/daphne) and add
  Channels. New moving parts to deploy and monitor.
- **Auth over WS:** token-in-connectionParams + expiry/refresh handling is
  fiddly and easy to get subtly wrong (security-sensitive).
- **Testing:** subscription tests need an async test client; more involved than
  the current sync GraphQL tests.
- **Redis dependency deepens:** Redis becomes required for *live features*, not
  just background billing — factor into HA/uptime expectations.
- **Low-ish payoff for most current screens:** dashboards/lists are fine with
  refetch/polling; only a few flows genuinely benefit from push.

## 4. Candidate use cases (value ranked)

1. **Critical vitals alerts** → push a flagged/critical reading to the
   NURSE/ADMIN dashboard the moment it's recorded. *Highest clinical value; the
   one case where seconds matter.*
2. New-payment / new-admission toasts for Finance/Admin. *Nice-to-have.*
3. Live dashboard KPIs / bed availability. *Convenience; polling covers it.*

## 5. Cheaper alternatives (no infra change)

- **Apollo polling** (`pollInterval`) on the dashboard / fees-due / vitals feed —
  trivial, already possible today, good enough for "fresh within N seconds."
- **Refetch on mutation** (already used across the app) for immediate local
  consistency.
- **Server-Sent Events (SSE)** — one-way server→client, simpler than full WS,
  but still needs ASGI; only worth it if we want push without the `graphql-ws`
  machinery.

## 6. Recommendation

**Defer full subscriptions** until a real-time requirement is actually
prioritized. The infra cost (ASGI in prod + Channels + WS auth) outweighs the
benefit for today's mostly request/response screens, and **Apollo polling**
closes the "freshness" gap now at ~zero cost.

**When we do proceed**, do it as a **single vertical slice** rather than a broad
enablement:

1. Add `channels` + `channels_redis` (reuse the Celery Redis); wire
   `GraphQLProtocolTypeRouter` in `config/asgi.py`; run prod under uvicorn/daphne.
2. Implement `on_ws_connect` JWT auth (token via `connectionParams`, validated
   with `auth.decode_token`), with an expiry/refresh story.
3. Add one `Subscription` — `criticalVitalFlagged` — publishing from the
   `create_vital_reading` mutation to the channel layer.
4. Frontend: `graphql-ws` + split link; a live "critical vitals" banner on the
   dashboard.
5. Prove it end-to-end, then decide whether to extend to other events.

Estimated size for that slice: a **medium PR on the backend** (Channels wiring,
auth hook, one subscription) plus a **small frontend PR** — best done only once
the clinical push requirement is confirmed.

## 7. Decision needed

- **Build now** (accept the ASGI/Channels infra change) — I'll start with the
  critical-vitals vertical slice above; or
- **Defer** and, if you want fresher data in the meantime, I can add **Apollo
  polling** to the dashboard / vitals feed in a tiny PR (no infra change).
