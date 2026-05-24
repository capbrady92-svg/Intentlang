# IntentLang Language Reference

Complete syntax reference for `.il` files.

---

## File Structure

Every `.il` file is indentation-based. Two spaces per level. Blocks are declared with a keyword, a name, and a colon. Everything indented beneath a block belongs to it.

```
// This is a comment

project MyApp:          ← block declaration
  stack: react + fastapi  ← property (key: value)
  
  model User:           ← nested block
    id (uuid, pk)       ← field definition
    email (str, required, unique)
```

Rules:
- Indent with **2 spaces** (tabs work but spaces are recommended)
- Comments start with `//`
- Blank lines are ignored
- A block owns everything indented beneath it until the next block at the same level

---

## Block Types

### `project`
Root declaration. One per codebase, always in `core.il`.

```
project MyApp:
  version: 0.1.0
  stack: react + fastapi + postgres
  pattern: REST
  auth: jwt
```

### `domain`
Declares a domain boundary. One per `.il` file (except `core.il`).

```
domain identity:
  description: "User identity and authentication"
```

### `model`
A data model — maps to a database table, document, or struct.

```
model User:
  id (uuid, pk)
  email (str, required, unique)
  name (str, required)
  role (str, default "member")
  active (bool, default true)
```

### `feature`
A grouping of routes and logic that belong together.

```
feature Auth:
  route POST /auth/login:
    ...
  route POST /auth/register:
    ...
```

### `route`
An HTTP endpoint. Two forms:

```
// Shorthand (inside a feature)
route GET /users:
  action: fetch all Users
  returns: User[]

// With method explicit
route POST /auth/login:
  auth: public
  input: email, password
  action: verify credentials
  returns: { token, user }
  error: if invalid -> 401 "Invalid credentials"
```

Supported methods: `GET` `POST` `PUT` `PATCH` `DELETE` `WS`

### `event`
A WebSocket or message queue event.

```
event send_message:
  input: room_id, content
  action: persist Message, broadcast to room
  broadcast: new_message to room members
```

### `config`
Infrastructure or system configuration block.

```
config Database:
  engine: postgres 15
  pool_size: 20
  statement_timeout: 30s
```

### `environment`
Environment-specific overrides.

```
environment dev:
  database: localhost:5432/myapp_dev
  debug: true

environment prod:
  database: rds.prod/myapp
  cdn: cloudfront
```

### `critical_path`
A performance-critical section. Usually paired with `@level:low` or `@level:asm`.

```
@level: asm
critical_path inner_loop:
  @target: x86_64-linux
  constraint: no heap allocation
  constraint: prefer AVX2
  max_cycles: 50
```

### `platform`
Infrastructure and deployment concerns.

```
platform infra:
  provider: aws
  region: us-east-1
```

### `api`
Public API surface definition.

```
api PublicAPI:
  version: v1
  base_path: /api/v1
```

### `inline`
Escape hatch for raw literal content passed directly to the transpiler.

```
inline setup_script:
  content: |
    #!/bin/bash
    echo "custom setup"
```

---

## Field Definitions

Fields live inside `model` blocks. Syntax: `name (type, modifier, modifier...)`

```
model Product:
  id (uuid, pk)
  name (str, required)
  price (int, required)           // store as cents
  description (str, optional)
  active (bool, default true)
  tags (list, optional)
  metadata (json, nullable)
  created_at (datetime, default now)
```

### Types

| Type | Description |
|---|---|
| `str` | String / text |
| `int` | Integer |
| `float` | Floating point |
| `bool` | Boolean |
| `uuid` | UUID (auto-generated if pk) |
| `date` | Date only (no time) |
| `datetime` | Date + time |
| `json` | Arbitrary JSON object |
| `list` | Array / list |
| `map` | Key-value map / dict |
| `bytes` | Raw binary data |

### Modifiers

| Modifier | Description |
|---|---|
| `required` | Cannot be null, must be provided |
| `optional` | May be null or absent |
| `pk` | Primary key |
| `fk` | Foreign key |
| `unique` | Unique constraint |
| `indexed` | Database index |
| `default <val>` | Default value |
| `nullable` | Explicitly nullable |
| `readonly` | Cannot be updated after creation |
| `private` | Never exposed in API responses |
| `public` | Always exposed |

---

## Relations

### Local relation (same file)

```
model Task:
  project -> Project      // Task belongs to Project (same domain)
  created_by -> User
```

### Cross-domain reference

```
model Task:
  owner: @identity/User!     // strict — fail if User missing
  assignee: @identity/User?  // optional — graceful fallback
  reviewer: @identity/User   // standard reference
```

Reference strictness:
- `@domain/Type` — standard, resolves quietly
- `@domain/Type!` — strict, transpilation fails if unresolved
- `@domain/Type?` — optional, transpiler emits fallback code if missing

---

## Properties (Key-Value)

Any key-value pair inside a block. Values can be strings, numbers, booleans, or lists.

```
feature Search:
  route GET /search:
    auth: required
    input: q (str, required), limit? (default 20)
    action: full-text search Posts using search_vector
    algorithm: postgres tsvector + tsquery ranking
    returns: { results: Post[], total, took_ms }
    cache: 60s per unique query string
    rate_limit: 30/minute/user
```

Common property keys:
- `action:` — what the route or event does (prose is fine)
- `input:` — parameters accepted
- `returns:` — response shape
- `error:` — error conditions and codes
- `auth:` — auth requirement (`required`, `public`, `api_key`, etc.)
- `algorithm:` — implementation hint
- `strategy:` — architectural approach
- `reason:` — why a decision was made (helps the LLM)
- `constraint:` — hard requirement
- `note:` — free-form annotation

---

## Rules Blocks

Rules are constraints that apply to everything in their parent scope.

```
// In core.il — apply globally
rules:
  - all endpoints require auth unless marked public
  - all models get id (uuid pk), created_at, updated_at
  - all errors return { code, message, trace_id }
  - passwords hashed with bcrypt rounds 12
  - tokens expire after 7d

// Inside a feature — apply to that feature only
feature Tasks:
  rules:
    - only project members can create tasks
    - only assignee or owner can close tasks
```

Rules are plain English — write them the way you'd describe them to a developer. The LLM reads them directly.

---

## Abstraction Level Directives

`@level:` declares the abstraction level for everything beneath it until overridden.

```
@level: high   // default — architecture, APIs, models
@level: mid    // algorithms, business logic
@level: low    // memory, performance, system calls
@level: asm    // registers, SIMD, platform-specific
```

Levels nest and override:

```
feature DataPipeline:
  @level: high
  input: raw_csv
  output: normalized_records

  @level: mid
  config Transform:
    algorithm: streaming parser, columnar normalization
    
  @level: low
  critical_path parse_row:
    constraint: no allocation per row
    constraint: SIMD for numeric parsing
    
    @level: asm
    critical_path simd_parse_float:
      @target: x86_64
      constraint: use _mm256_cvtepi32_ps
```

### `@target:` directive

Used with `@level:asm` to specify the platform:

```
@target: x86_64-linux
@target: aarch64
@target: wasm32
@target: arm-cortex-m4
```

### `constraint:` directive

Hard requirements the transpiler must satisfy:

```
constraint: no heap allocation on hot path
constraint: prefer SO_REUSEPORT
constraint: thread-safe without locks
constraint: O(1) lookup
```

---

## Anonymous Blocks

Some blocks don't need a name:

```
model User:
  schema:
    ...

feature Auth:
  actions:
    ...
  guards:
    ...

project MyApp:
  domains:
    - identity
    - tasks
  dependencies:
    - stripe
    - sendgrid
```

---

## Freeform Values

IntentLang is intentionally permissive about values. The parser extracts structure; the LLM reads intent. You don't need to be formal in value fields.

These are all valid:

```
action: validate the email format, check it isn't already registered, hash the password with bcrypt, create the user record, send a welcome email asynchronously, return a JWT
algorithm: sliding window rate limit using redis sorted sets — ZADD score=timestamp, ZREMRANGEBYSCORE to prune, ZCARD to count
strategy: write-through cache — update redis and postgres in the same transaction, use redis as read-through for hot data
reason: we use integer cents to avoid floating point rounding issues in financial calculations
```

The `reason:` key is particularly useful — it gives the LLM the *why* behind a decision, which dramatically improves how it implements the *what*.

---

## Complete Example

```
// billing.il — Billing and subscription management
domain billing:
  description: "Stripe billing, plans, and subscription lifecycle"

model Subscription:
  id (uuid, pk)
  org: @orgs/Org!
  stripe_customer_id (str, required, unique)
  stripe_subscription_id (str, optional)
  plan (str, required)
  status (str, default "trialing")
  current_period_end (datetime, optional)
  cancel_at_period_end (bool, default false)

model Invoice:
  id (uuid, pk)
  org: @orgs/Org!
  stripe_invoice_id (str, required, unique)
  amount_cents (int, required)
  status (str, required)
  paid_at (datetime, optional)

feature Checkout:
  route POST /orgs/:slug/billing/checkout:
    guard: role = owner
    input: plan, interval (monthly|yearly)
    action: create Stripe checkout session
    returns: { checkout_url }

  route POST /webhooks/stripe:
    auth: stripe_signature
    action: handle Stripe events
    events:
      - checkout.session.completed -> activate subscription
      - invoice.payment_succeeded -> record Invoice
      - invoice.payment_failed -> notify owner, set past_due

  @level: mid
  config WebhookIdempotency:
    strategy: store processed stripe_event_ids, return 200 on duplicate
    reason: Stripe delivers webhooks at least once, may duplicate

rules:
  - only org owners can manage billing
  - webhook signature verified before any processing
  - all amounts in cents
  - failed payments notify by email before suspension
```
