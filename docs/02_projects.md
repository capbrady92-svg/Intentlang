# Multi-File Projects

How to structure a real IntentLang project across multiple `.il` files.

---

## The Core Idea

In a regular codebase you organize files by technical layer — `models/`, `routes/`, `services/`. That's a convention driven by how code executes.

IntentLang files aren't executed. They express intent. So the right organizing unit is a **domain** — a coherent slice of your system that owns its own models, features, and rules.

```
intent/
  core.il        ← project root (required)
  identity.il    ← users, auth, sessions
  tasks.il       ← task management
  billing.il     ← billing, subscriptions
  platform.il    ← infra, deployment
```

Each file is independently readable and understandable. A new developer can read `billing.il` and fully understand the billing domain without reading anything else.

---

## core.il — The Root File

Every project needs exactly one `core.il`. It's the anchor for the entire IR graph.

```
project MyApp:
  version: 0.1.0
  stack: react + fastapi + postgres
  pattern: REST
  auth: jwt

  domains:
    - identity
    - tasks
    - billing
    - platform

  rules:
    - all endpoints require auth unless marked public
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message, trace_id }
    - audit log all mutations
    - tokens expire after 7d
    - bcrypt rounds: 12

  environment dev:
    database: localhost:5432/myapp_dev
    cache: localhost:6379
    debug: true

  environment prod:
    database: rds.prod/myapp + read_replica
    cache: elasticache.prod
    cdn: cloudfront
```

### What core.il does

**Global rules** — every rule declared in `core.il` is injected into every transpile call automatically. The LLM applies them everywhere without being told file by file. If you declare `all errors return { code, message, trace_id }` in `core.il`, every route in every domain gets that error format.

**Domain registry** — the `domains:` list tells the IR which files to expect and how to resolve cross-domain references.

**Stack declaration** — the `stack:` property tells the transpiler what to generate. `react + fastapi + postgres` produces TypeScript + Python + SQL. Change it and regenerate — the `.il` stays the same.

**Environment config** — dev, staging, prod differences declared once, applied everywhere.

---

## Domain Files

Each domain file declares one domain and owns everything inside it.

```
// identity.il
domain identity:
  description: "User identity and authentication"

model User:
  ...

model Session:
  ...

feature Auth:
  ...

rules:
  - bcrypt rounds: 12
  - session tokens expire after 7d
```

### Naming conventions

- File name = domain name = reference prefix
- `identity.il` → `domain identity:` → `@identity/`
- `tasks.il` → `domain tasks:` → `@tasks/`
- Keep names short, lowercase, hyphen-separated for multi-word: `user-events.il`

---

## Cross-File References

Reference a type from another domain with `@domain/TypeName`.

```
// tasks.il
model Task:
  owner: @identity/User!      // Task must have an owner — User must exist
  assignee: @identity/User?   // Assignee is optional — no User = graceful fallback
  reviewer: @identity/User    // Standard reference — resolves quietly
```

### Strictness levels

| Syntax | Behavior if unresolved |
|---|---|
| `@domain/Type!` | **Strict** — transpilation fails, error reported |
| `@domain/Type` | **Standard** — warning in IR, transpiler handles gracefully |
| `@domain/Type?` | **Optional** — transpiler emits fallback code |

Use `!` for required relationships (a Task must have an owner). Use `?` for optional ones (a Task may have an assignee). Use bare `@domain/Type` when you're prototyping and don't want hard failures yet.

### What references compile to

References are **semantic**, not syntactic. The transpiler decides what each reference means in the target stack:

| Target | `@identity/User!` compiles to |
|---|---|
| Postgres/SQL | `FOREIGN KEY (owner_id) REFERENCES users(id) NOT NULL` |
| SQLAlchemy | `owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))` |
| Mongoose | `owner: { type: Schema.Types.ObjectId, ref: 'User', required: true }` |
| GraphQL | `owner: User!` |
| Prisma | `owner User @relation(fields: [ownerId], references: [id])` |

You declare the relationship once. The mechanism is the transpiler's problem.

---

## Loading a Project

### From disk

```
il› load ./my-project
```

Loads all `.il` files from that directory. Always loads `core.il` first.

### From examples

```
python examples.py url-shortener    # writes to ./examples/url-shortener/
il› load ./examples/url-shortener
```

### Creating files

```
il› new billing          # creates billing.il, opens in editor prompt
il› edit billing.il      # open existing file in $EDITOR
il› save                 # write all loaded files to ./intent/
```

---

## Recommended Project Layouts

### Small project (1–2 domains)

```
intent/
  core.il
  app.il        // everything in one domain
```

### Medium project (3–5 domains)

```
intent/
  core.il
  identity.il
  <main-domain>.il
  notifications.il
  platform.il
```

### Large project (6+ domains)

```
intent/
  core.il
  identity.il
  billing.il
  <domain-a>.il
  <domain-b>.il
  <domain-c>.il
  integrations.il   // third-party services
  platform.il       // infra
```

### Non-web project (CLI, library, system tool)

```
intent/
  core.il           // stack: rust (or go, c, etc.), pattern: CLI
  <feature-a>.il
  <feature-b>.il
  platform.il       // @level:low and @level:asm concerns
```

---

## Workflow: Building a New Project

### Step 1 — Write core.il first

Decide your stack. Write global rules before writing anything else. Rules you write here you'll never have to repeat.

```
project Snip:
  stack: fastapi + postgres + redis
  pattern: REST
  auth: api_key
  
  domains:
    - links
  
  rules:
    - all errors return { code, message }
    - all models get id (uuid pk), created_at
    - rate limit: 60/minute/ip
```

### Step 2 — Write domain files top-down

Start with models (what are the data shapes?), then features (what can users do?), then rules (what are the constraints?).

```
// links.il
domain links:

model Link:
  slug (str, required, unique, indexed)
  original_url (str, required)
  active (bool, default true)
  click_count (int, default 0)

feature Shorten:
  route POST /links:
    input: original_url, slug?
    action: create Link with generated or provided slug
    returns: { slug, short_url }
    error: if slug taken -> 409

rules:
  - slugs are lowercase alphanumeric + hyphens only
  - max slug length: 50 chars
```

### Step 3 — Check the IR before transpiling

```
il› list                        # confirm files loaded
il› query show global rules     # confirm rules propagated from core.il
il› query list models           # confirm models parsed correctly
il› query show graph            # check cross-domain edges resolved
```

### Step 4 — Transpile

```
il› transpile core.il           # good first transpile — generates project scaffold
il› transpile links.il          # generates domain implementation
```

### Step 5 — Iterate in .il, never in generated code

Add a field → update `links.il` → transpile again. Change a rule → update `core.il` → transpile all affected files. Never touch the output.

---

## How the IR Sees Your Project

When you load a multi-file project, the IR builds a unified graph:

```
core.il
  └── rules (global)
  └── stack: fastapi + postgres + redis

identity.il
  └── model:User
  └── model:Session
  └── feature:Auth

tasks.il
  └── model:Task → @identity/User (resolved → identity:model:User)
  └── model:Project → @identity/User (resolved)
  └── feature:Tasks
```

Every node has a UID: `{domain}:{type}:{name}` — e.g. `identity:model:User`, `tasks:feature:Tasks`.

Cross-file references become edges in the graph. You can query this graph at any time to understand your project structure without reading any code.

---

## Common Mistakes

**Forgetting to declare a domain in core.il**

If `domains:` in `core.il` doesn't include your domain name, cross-refs to it won't resolve. Always keep the domains list current.

**Naming the file differently from the domain**

If the file is `users.il` but the domain inside is `identity`, cross-refs use `@identity/` not `@users/`. Keep them consistent.

**Putting everything in one file**

Works fine for small projects. But when a file gets long, split by domain. The IR handles it — there's no performance cost to more files.

**Adding global rules in domain files**

Rules in domain files apply only to that domain. Put rules that should apply everywhere in `core.il`.