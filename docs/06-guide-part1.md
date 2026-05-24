# The IntentLang Guide — Part 1: Learning the Language

## A Different Way to Build Software

Before we write a single line of IntentLang, it's worth understanding what we're doing and why it works.

When you use a typical AI coding tool, you describe what you want in natural language and the AI generates code. This works surprisingly well — until it doesn't. The AI forgets what it decided in the last session. It makes a naming convention in one file that contradicts another. It implements auth differently than it did last week. The code accumulates silent decisions nobody made consciously.

IntentLang takes a different approach. Instead of describing what you want in prose and hoping the AI interprets it correctly, you write it in a structured language that the AI can parse unambiguously. The `.il` file becomes the single source of truth for your entire system. The code is generated from it — and you never touch the generated code directly.

This might sound constraining. It's actually the opposite. When you stop worrying about *how* the code is structured and focus entirely on *what* you're building, you think more clearly and build faster. The constraint is the feature.

### The Mental Model

Think of IntentLang like an architect's blueprint. An architect doesn't build walls — they draw plans. The plans are the source of truth. The construction team reads the plans and builds from them. If something needs to change, the architect updates the plan and the team rebuilds that section.

You are the architect. The `.il` files are your plans. The AI is the construction team.

```
You write .il  →  IntentLang parses it into an IR graph  →  AI generates complete code
```

The IR (Intermediate Representation) is the compiled form of your intent — a queryable graph of every model, feature, route, rule, and relationship in your system. The AI receives this IR as context for every code generation call, so it always has a complete, structured picture of what you're building.

---

## Chapter 1: Your First .il File

Let's start simple. We're going to build a URL shortener — a service that takes long URLs and gives you short ones. It's small enough to understand completely, complex enough to show you everything IntentLang can do.

### Setting Up

First, make sure IntentLang is running:

```bash
pip install httpx rich prompt_toolkit
python intentlang.py
```

On first run, it will ask for your API key. Enter it and press Y to save it to `.env` — you won't need to enter it again.

You should see the IntentLang prompt:

```
il›
```

### The Structure of a .il File

Every `.il` file follows the same pattern: indentation-based blocks, with properties nested inside them. If you've used Python or YAML, the indentation will feel familiar.

```
block_type Name:
  property: value
  property: value

  nested_block NestedName:
    property: value
```

Two spaces per indent level. Block types are keywords like `project`, `model`, `feature`, `route`. Everything indented beneath a block belongs to it.

### Writing core.il

Every IntentLang project starts with `core.il`. This file is the root of your entire system — it declares the project name, the technology stack, which domains exist, and rules that apply everywhere.

Create a new file at `intent/core.il`:

```
il› new core
```

This creates a blank `core.il` in the `./intent/` directory. Now edit it:

```
il› edit core.il
```

Your editor will open. Type this exactly:

```
// core.il — URL Shortener
// Comments start with //

project Snip:
  version: 0.1.0
  stack: fastapi + postgres + redis
  pattern: REST
  auth: api_key

  domains:
    - links

  rules:
    - all errors return { code, message }
    - all models get id (uuid pk), created_at
    - rate limit all endpoints: 60 requests per minute per ip
    - api_key required on all endpoints unless marked public
```

Save and close. IntentLang reloads automatically. You'll see:

```
Reloaded: core.il

IR Summary
  Project    Snip
  Stack      fastapi + postgres + redis
  Files      core.il
  Nodes      12 (0 models, 0 features, 0 routes)
  Rules      4
```

Let's break down what you just wrote.

**`project Snip:`** — This declares the project. The name `Snip` will be used as the output directory name (`~/intentlang/snip/`). Always one per project, always in `core.il`.

**`stack:`** — The technology stack. IntentLang is stack-agnostic — write `go + grpc + postgres` and it generates Go. Write `rust` and it generates Rust. The AI reads this and generates appropriate code for every domain.

**`pattern: REST`** — The architectural pattern. Could be `REST`, `GraphQL`, `gRPC`, `websocket`, or combinations.

**`domains:`** — A list of domain files that belong to this project. We'll create `links.il` shortly.

**`rules:`** — These are global constraints that apply to every file, every feature, every route in the entire project. The AI receives them for every code generation call. If you write it here, the AI will never forget it.

Notice how the rules are plain English. IntentLang doesn't try to parse them into formal logic — it passes them directly to the AI as structured intent. The AI understands "all errors return { code, message }" perfectly well. Write rules the way you'd explain them to a developer.

### Querying the IR

Even with just `core.il`, you can start querying the IR graph:

```
il› query show stack
Stack: fastapi + postgres + redis
Project: Snip
Files: core.il

il› query show global rules
1. all errors return { code, message }
2. all models get id (uuid pk), created_at
3. rate limit all endpoints: 60 requests per minute per ip
4. api_key required on all endpoints unless marked public
```

The IR is live — it rebuilds every time you save a file.

---

## Chapter 2: Models

Models are the data shapes in your system — they map to database tables, API response bodies, and validation schemas. In IntentLang, you define them once and the AI figures out what to generate for your target stack.

### Writing the Links Domain

```
il› new links
il› edit links.il
```

Start with the models:

```
// links.il — Core link shortening domain
domain links:
  description: "URL shortening, redirects, and click analytics"

model Link:
  id (uuid, pk)
  slug (str, required, unique, indexed)
  original_url (str, required)
  title (str, optional)
  expires_at (datetime, optional)
  active (bool, default true)
  click_count (int, default 0)

model Click:
  id (uuid, pk)
  link -> Link
  ip (str, optional)
  user_agent (str, optional)
  referer (str, optional)
  country (str, optional)
```

**`domain links:`** — Every non-core `.il` file declares a domain. The domain name matches the filename.

**`model Link:`** — A data model. The AI will generate a database table, an ORM model, a Pydantic schema, and TypeScript types from this single declaration.

**Fields** use the syntax `name (type, modifier, modifier...)`:

- `id (uuid, pk)` — a UUID primary key, auto-generated
- `slug (str, required, unique, indexed)` — a string, must be provided, must be unique, has a database index for fast lookups
- `original_url (str, required)` — required string
- `title (str, optional)` — can be null
- `expires_at (datetime, optional)` — nullable datetime
- `active (bool, default true)` — boolean with a default value
- `click_count (int, default 0)` — integer starting at zero

**`link -> Link`** — A local relation. The `->` syntax means "Click belongs to Link" in the same domain. The AI generates the appropriate foreign key relationship.

Notice that we declared `id` on both models even though `core.il` says "all models get id (uuid pk), created_at". That's fine — the rule is additive. The AI will apply it whether or not you repeat it. But being explicit in your models is also fine and sometimes clearer.

### Field Types Reference

| Type | Description | Example |
|------|-------------|---------|
| `str` | String/text | `title (str, required)` |
| `int` | Integer | `click_count (int, default 0)` |
| `float` | Floating point | `price (float, required)` |
| `bool` | Boolean | `active (bool, default true)` |
| `uuid` | UUID | `id (uuid, pk)` |
| `date` | Date only | `due_date (date, optional)` |
| `datetime` | Date + time | `expires_at (datetime, optional)` |
| `json` | Arbitrary JSON | `metadata (json, optional)` |
| `list` | Array | `tags (list, optional)` |
| `map` | Key-value pairs | `headers (map, optional)` |

### Field Modifiers Reference

| Modifier | Meaning |
|----------|---------|
| `required` | Cannot be null, must be provided |
| `optional` | Can be null or absent |
| `pk` | Primary key |
| `unique` | Unique constraint |
| `indexed` | Database index |
| `default <value>` | Default value |
| `private` | Never exposed in API responses |
| `readonly` | Cannot be updated after creation |

---

## Chapter 3: Features and Routes

Models define what data looks like. Features define what users can *do* with that data. A feature is a grouping of related routes.

### Adding Features to links.il

Continue editing `links.il`, adding features after the models:

```
feature Shorten:
  route POST /links:
    auth: public
    input: original_url (str, required), slug?, title?, expires_at?
    action: validate url format, generate slug if not provided (6 chars alphanumeric), create Link
    returns: { slug, short_url, original_url, expires_at }
    error: if slug taken -> 409 "Slug already in use"
    error: if invalid url -> 400 "Invalid URL format"

  route GET /links:
    action: fetch all Links for current api_key owner
    returns: Link[]

  route GET /links/:slug:
    action: fetch Link by slug
    returns: Link
    error: if not found -> 404

  route DELETE /links/:slug:
    action: deactivate Link by setting active = false
    returns: { ok: true }
    error: if not found -> 404

feature Redirect:
  route GET /:slug:
    auth: public
    action: lookup slug in redis cache, fallback to postgres if cache miss, record Click asynchronously, redirect to original_url
    returns: 302 redirect to original_url
    error: if not found or inactive -> 404
    error: if expired -> 410 "Link expired"

feature Analytics:
  route GET /links/:slug/stats:
    action: fetch Link with aggregated click data
    returns: { link, total_clicks, clicks_by_day, top_countries, top_referrers }
```

### Understanding Route Syntax

**`route METHOD /path:`** — HTTP method followed by the path. Supported: `GET POST PUT PATCH DELETE WS`

**`auth:`** — Who can access this route. `public` means no authentication required. If omitted, the global rule applies — in our case, api_key authentication.

**`input:`** — Parameters accepted by the route. A `?` suffix means optional. You can add type annotations: `original_url (str, required)`. For GET routes, these become query parameters. For POST/PUT/PATCH, they become the request body.

**`action:`** — What the route does. This is the most important property and the most freeform. Write it in plain English — the more specific and clear, the better the generated code. Notice these details:
- "generate slug if not provided (6 chars alphanumeric)" — the AI will implement this exactly
- "lookup slug in redis cache, fallback to postgres if cache miss" — the AI implements the caching strategy
- "record Click asynchronously" — the AI knows not to await this

**`returns:`** — The response shape. Can be a model name (`Link`), an array (`Link[]`), a JSON shape (`{ slug, short_url }`), or a status code description.

**`error:`** — Error conditions. The format `if <condition> -> <status_code> "<message>"` is convention — write it however makes sense to you. The AI reads the English.

### The Power of the `action:` Field

The `action:` field is where IntentLang shines. You're not writing pseudocode — you're writing *intent*. Compare:

**Vague:**
```
action: create link
```

**Specific:**
```
action: validate url format, generate slug if not provided (6 chars alphanumeric, lowercase), check slug uniqueness, create Link, cache slug→url mapping in redis with TTL = expires_at or 30 days, return link with short_url = base_url + slug
```

The second version produces dramatically better generated code because the AI doesn't have to guess. Every detail you add removes one potential hallucination.

### Adding Domain Rules

At the bottom of `links.il`, add rules specific to this domain:

```
rules:
  - slugs are lowercase alphanumeric and hyphens only
  - max slug length: 50 characters
  - max original_url length: 2048 characters
  - expired links return 410 Gone, not 404 Not Found
  - click tracking is async and never blocks redirect response
  - click_count on Link is a cached counter, updated in batches every 60 seconds
```

These rules apply only to the `links` domain. Global rules in `core.il` apply everywhere.

---

## Chapter 4: Checking Your Work Before Generating

One of IntentLang's most useful features is being able to inspect and validate your project structure before writing a single line of code.

### Listing What You've Built

```
il› list
```

You'll see all loaded files and the IR summary:

```
Loaded files:
  ├─ core.il    12 lines
  └─ links.il   68 lines

IR Summary
  Project    Snip
  Stack      fastapi + postgres + redis
  Files      core.il, links.il
  Nodes      89 (2 models, 3 features, 7 routes)
  Edges      1 (0 unresolved)
  Rules      4
```

### Querying the IR

The IR query engine lets you explore your project structure:

```
il› query list models
[@high] model "Link" (links.il) uid:links:model:Link
[@high] model "Click" (links.il) uid:links:model:Click

il› query list routes
[@high] route "POST_/links" (links.il)
[@high] route "GET_/links" (links.il)
[@high] route "GET_/links/:slug" (links.il)
[@high] route "DELETE_/links/:slug" (links.il)
[@high] route "GET_/:slug" (links.il)
[@high] route "GET_/links/:slug/stats" (links.il)

il› query show graph
links:model:Click →[relation]→ Link
```

The graph shows one edge: Click relates to Link. No unresolved references.

### Previewing a File

```
il› view links.il
```

This shows your `.il` file with syntax highlighting so you can verify what was parsed.

---

## Chapter 5: Transpiling — Generating Real Code

Now for the moment everything has been building toward. Let's generate the actual implementation.

```
il› transpile core.il
```

Start with `core.il` — this typically generates the project scaffold: directory structure, configuration files, docker-compose, requirements, README.

You'll see code streaming into your terminal. The AI is generating files separated by `// FILE: path/to/file.ext` markers. When it finishes, IntentLang parses the output into individual files and writes them to `~/intentlang/snip/`.

```
✓  ~/intentlang/snip/requirements.txt
✓  ~/intentlang/snip/docker-compose.yml
✓  ~/intentlang/snip/backend/config.py
✓  ~/intentlang/snip/.env.example

4 generated

Output: ~/intentlang/snip/
```

Now transpile the links domain:

```
il› transpile links.il
```

```
✓  ~/intentlang/snip/backend/models/link.py
✓  ~/intentlang/snip/backend/models/click.py
✓  ~/intentlang/snip/backend/routes/links.py
✓  ~/intentlang/snip/backend/routes/redirect.py
✓  ~/intentlang/snip/backend/schemas/link.py
✓  ~/intentlang/snip/migrations/001_create_links.sql
✓  ~/intentlang/snip/migrations/002_create_clicks.sql
✓  ~/intentlang/snip/tests/test_links.py

8 generated
```

That's a complete FastAPI backend — models, routes, schemas, migrations, tests — from two `.il` files.

### What Just Happened

The transpiler sent the AI three things:

1. **IR Summary** — a compact description of your whole project: stack, rules, relationships, node counts. This is what gives the AI "memory" of your system.

2. **The target file** — the full `links.il` source.

3. **Referenced domains** — any domains that `links.il` references. (In this case, none — it's self-contained.)

The AI receives this structured context and generates complete, production-ready code. It knows to use FastAPI because of `stack: fastapi`. It knows every endpoint needs api_key auth because of the global rule. It knows click tracking should be async because you said so in the action.

### The Golden Rule

**Never edit the files in `~/intentlang/snip/`.**

This is the most important discipline in IntentLang. The moment you edit generated code, you have two sources of truth. The `.il` says one thing; the code says another. The next transpile will overwrite your edit.

If something is wrong with the generated code:

1. **Wrong intent** — fix the `.il` and regenerate
2. **Underspecified** — add more detail to `action:`, `constraint:`, or `reason:` and regenerate  
3. **Something the language can't express** — use an `inline:` block

If you find yourself wanting to edit generated code, that's the signal that your `.il` is incomplete. Add the detail there.

---

## Chapter 6: Iteration

IntentLang is designed for rapid iteration. Changing a model field, adding a route, updating a rule — these are all one-step operations: edit the `.il`, regenerate.

### Adding a Feature

Let's say you want to add API key management — users need to create and revoke their API keys.

Add to `links.il`:

```
model ApiKey:
  id (uuid, pk)
  key_hash (str, required, private)
  key_prefix (str, required, readonly)
  name (str, required)
  last_used_at (datetime, optional)
  active (bool, default true)

feature Keys:
  route POST /keys:
    input: name (str, required)
    action: generate 32-char random key with prefix "snip_", hash it with sha256, store hash, return raw key once
    returns: { id, name, key, key_prefix }
    note: raw key is shown only on creation — it cannot be retrieved again

  route GET /keys:
    action: fetch all ApiKeys for current owner, never return key_hash
    returns: { id, name, key_prefix, last_used_at, active }[]

  route DELETE /keys/:id:
    action: deactivate ApiKey
    returns: { ok: true }

rules:
  - raw api key shown only once at creation, never stored, only hash stored
  - key format: snip_<32 random alphanumeric chars>
  - key_prefix is first 8 chars of key for identification
```

Now check impact before regenerating:

```
il› query impact of ApiKey
No dependents for "ApiKey"
```

Good — ApiKey is standalone, nothing else references it. Regenerate:

```
il› transpile links.il
```

The new model and routes are generated alongside the existing ones.

### Changing a Model Field

Suppose you want to add a `description` field to Link:

Edit `links.il`, add to the model:

```
model Link:
  id (uuid, pk)
  slug (str, required, unique, indexed)
  original_url (str, required)
  title (str, optional)
  description (str, optional)    ← new
  expires_at (datetime, optional)
  active (bool, default true)
  click_count (int, default 0)
```

Before regenerating, check impact:

```
il› query impact of Link
Direct dependents:
  links:model:Click [relation]
  links:feature:Analytics [implied]
```

This tells you that Click and Analytics will also be affected. Regenerate:

```
il› transpile links.il
```

The new field propagates through models, schemas, routes, and the migration.

### Changing a Global Rule

Suppose you want to change the rate limit. Edit `core.il`:

```
rules:
  - all errors return { code, message }
  - all models get id (uuid pk), created_at
  - rate limit all endpoints: 100 requests per minute per ip   ← changed
  - api_key required on all endpoints unless marked public
```

Now every route that implements rate limiting needs to be regenerated. Transpile both files:

```
il› transpile core.il
il› transpile links.il
```

The rule change propagates everywhere.

---

## Chapter 7: Abstraction Levels

So far we've been working at `@level: high` — the default. IntentLang supports four levels, and you can mix them within a single file.

### The Four Levels

```
@level: high   # default — architecture, APIs, data models
@level: mid    # algorithms, business logic, specific logic
@level: low    # memory layout, performance, system calls
@level: asm    # registers, SIMD, platform-specific
```

Levels are inherited downward. A block at `@level: low` produces low-level code for everything inside it.

### Using @level:mid for Specific Logic

The redirect route needs to be fast. Let's specify the caching strategy more precisely:

```
feature Redirect:
  route GET /:slug:
    auth: public
    action: lookup slug in redis cache, fallback to postgres if cache miss, record Click asynchronously, redirect
    returns: 302 redirect
    error: if not found or inactive -> 404
    error: if expired -> 410

  @level: mid
  config RedirectCache:
    strategy: redis GET on key "slug:{slug}", cache hit = immediate redirect
    on_miss: fetch from postgres, SET in redis with TTL = min(expires_at, 30 days)
    on_click: LPUSH to "clicks:queue" list, background worker batch-inserts every 30s
    reason: redirect latency is critical — must be sub-10ms p99
```

The `@level: mid` directive tells the transpiler to generate more implementation-specific code for the `RedirectCache` config block — actual Redis commands, specific TTL logic, the queue-based click recording pattern.

### Using @level:low for Performance

For the click aggregation worker:

```
@level: low
config ClickAggregator:
  strategy: background asyncio task, wakes every 30s
  action: LRANGE clicks:queue 0 -1, LTRIM to clear, batch INSERT into clicks table
  constraint: single transaction per batch
  constraint: if batch insert fails, push items back to queue
  max_batch_size: 1000
  reason: avoid write amplification on hot slugs
```

### Mixing Levels

Levels nest naturally. A high-level feature can contain a mid-level config:

```
feature Analytics:
  @level: high
  route GET /links/:slug/stats:
    action: return aggregated analytics
    returns: { total_clicks, clicks_by_day, top_countries }

  @level: mid
  config Aggregation:
    clicks_by_day: SELECT date_trunc('day', created_at), COUNT(*) GROUP BY 1 ORDER BY 1 DESC LIMIT 30
    top_countries: SELECT country, COUNT(*) GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    cache: results cached 5 minutes per slug
    reason: these queries are expensive — never run on every request
```

The route stays at `high` (clean FastAPI handler), while the aggregation config drops to `mid` (actual SQL, specific cache TTL).

---

## The Complete URL Shortener

Here's the full `links.il` we've built through this chapter:

```
// links.il — URL Shortener domain
domain links:
  description: "URL shortening, redirects, and click analytics"

// ── Models ────────────────────────────────────────────────────────────────────

model Link:
  id (uuid, pk)
  slug (str, required, unique, indexed)
  original_url (str, required)
  title (str, optional)
  description (str, optional)
  expires_at (datetime, optional)
  active (bool, default true)
  click_count (int, default 0)

model Click:
  id (uuid, pk)
  link -> Link
  ip (str, optional)
  user_agent (str, optional)
  referer (str, optional)
  country (str, optional)

model ApiKey:
  id (uuid, pk)
  key_hash (str, required, private)
  key_prefix (str, required, readonly)
  name (str, required)
  last_used_at (datetime, optional)
  active (bool, default true)

// ── Features ──────────────────────────────────────────────────────────────────

feature Shorten:
  route POST /links:
    auth: public
    input: original_url (str, required), slug?, title?, description?, expires_at?
    action: validate url format, generate slug if not provided (6 chars alphanumeric lowercase), check uniqueness, create Link, cache slug→url in redis
    returns: { slug, short_url, original_url, expires_at }
    error: if slug taken -> 409 "Slug already in use"
    error: if invalid url -> 400 "Invalid URL format"

  route GET /links:
    action: fetch all active Links for current api_key owner, newest first
    returns: Link[]

  route GET /links/:slug:
    action: fetch Link by slug
    returns: Link
    error: if not found -> 404

  route DELETE /links/:slug:
    action: set Link.active = false
    returns: { ok: true }
    error: if not found -> 404

feature Redirect:
  route GET /:slug:
    auth: public
    action: lookup slug in redis cache, fallback to postgres, record Click async, redirect
    returns: 302 redirect to original_url
    error: if not found or inactive -> 404
    error: if expired -> 410 "Link expired"

  @level: mid
  config RedirectCache:
    strategy: redis GET "slug:{slug}", on miss fetch postgres and SET with TTL
    ttl: min(expires_at - now, 30 days)
    click_queue: LPUSH "clicks:queue" JSON payload, worker batch-inserts every 30s
    reason: redirect must be sub-10ms p99 — cache miss is acceptable, blocking is not

feature Analytics:
  route GET /links/:slug/stats:
    action: return aggregated analytics for Link
    returns: { link, total_clicks, clicks_by_day, top_countries, top_referrers }

  @level: mid
  config Aggregation:
    clicks_by_day: GROUP BY date_trunc('day', created_at) LIMIT 30 days
    top_countries: GROUP BY country ORDER BY count DESC LIMIT 10
    cache_ttl: 5 minutes per slug
    reason: expensive aggregation queries — never run on every request

feature Keys:
  route POST /keys:
    input: name (str, required)
    action: generate key "snip_<32 random alphanumeric>", hash with sha256, store hash + prefix
    returns: { id, name, key, key_prefix }
    note: raw key shown only once — cannot be retrieved again

  route GET /keys:
    action: fetch ApiKeys for current owner
    returns: { id, name, key_prefix, last_used_at, active }[]

  route DELETE /keys/:id:
    action: set ApiKey.active = false
    returns: { ok: true }

// ── Rules ─────────────────────────────────────────────────────────────────────

rules:
  - slugs are lowercase alphanumeric and hyphens only, max 50 chars
  - max original_url length: 2048 chars
  - expired links return 410 Gone, not 404
  - click tracking never blocks redirect — always async
  - raw api key shown only once at creation, never stored or retrievable
  - key format: snip_<32 random alphanumeric chars>
```

To generate the complete implementation:

```
il› transpile core.il
il› transpile links.il
```

Two commands. A complete, production-grade FastAPI + Postgres + Redis URL shortener — with models, routes, schemas, migrations, caching strategy, async click tracking, API key management, and tests.

---

## What You've Learned

In this first part, you've learned:

- The philosophy behind IntentLang — intent as the source of truth
- How to write `core.il` — the project root with global rules
- How to define models with typed fields and modifiers
- How to write features and routes with precise action descriptions
- How to use domain-level rules alongside global rules
- How to check your work with the IR query engine before generating
- How to transpile and why you never edit generated code
- How to iterate — adding fields, features, and changing rules
- How to use abstraction levels to control code sophistication

In Part 2, we'll build a more complex project — a multi-domain SaaS application — that introduces cross-file references, the interface system, and real multi-project architecture.
