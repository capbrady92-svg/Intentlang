# IntentLang (.il)

> A structured, multi-level intent language that gives AI coding agents the context, memory, and constraints they need to generate reliable code — at any abstraction level, across any stack.

---

## The Problem

AI coding tools today accept natural language prompts. Natural language is the most ambiguous communication format humans have. Every underspecified prompt is a micro-decision silently outsourced to a model with no memory of what it decided last time, no stake in the outcome, and no structured understanding of your system.

The result: code that looks right, runs in dev, and silently accumulates architectural decisions nobody made consciously.

IntentLang fixes the input side of AI code generation.

---

## What IntentLang Is

IntentLang is an **intermediate intent language** — not a programming language, not prose specs, not pseudocode. It sits between human intent and generated code.

```
You write .il  →  Parser builds IR  →  AI transpiles to any target
```

The `.il` file is your **only source of truth**. Never edit generated code. If something needs to change, change the `.il` and regenerate.

---

## Core Concepts

### 1. Abstraction Levels

IntentLang spans the full stack from architecture to assembly. Use `@level:` to declare which layer you're operating at within any block:

```
@level: high   # default — features, APIs, data models, architecture
@level: mid    # algorithms, business logic, specific data structures
@level: low    # memory layout, performance constraints, system calls
@level: asm    # register hints, instruction preferences, platform targets
```

Levels can nest — a high-level feature can contain a low-level critical path:

```
feature ImageProcessor:
  @level: high
  input: raw_bytes
  output: compressed_image

  @level: low
  critical_path encode_block:
    @target: x86_64-linux
    constraint: no heap allocation
    constraint: SIMD preferred
    max_cycles: 200
```

The transpiler sees the level context and matches its output accordingly — clean idiomatic code at `@level:high`, low-level C or inline asm at `@level:asm`.

### 2. Multi-File Project Structure

Organize your `.il` files by **domain** (concern), not technical layer:

```
intent/
  core.il        # project root — stack, global rules, domain registry
  identity.il    # users, auth, sessions
  tasks.il       # task management domain
  billing.il     # billing and subscriptions
  platform.il    # infrastructure, deployment, low-level config
```

Every project needs a `core.il` that declares the stack and global rules:

```
project MyApp:
  version: 0.1.0
  stack: react + fastapi + postgres
  pattern: REST
  auth: jwt

  domains:
    - identity
    - tasks
    - platform

  rules:
    - all endpoints require auth unless marked public
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message, trace_id }
    - audit log all mutations
```

Global rules propagate to **every file** in the project. The transpiler applies them everywhere without being told.

### 3. Cross-File References

Reference types from other domains with `@domain/Type`:

```
# tasks.il
model Task:
  owner: @identity/User!      # strict — fail if User doesn't exist in identity domain
  assignee: @identity/User?   # optional — emit graceful fallback if missing
  reviewer: @identity/User    # normal — resolve quietly
```

Reference semantics:
- `@domain/Type` — standard reference, resolved at IR build time
- `@domain/Type!` — strict: transpilation fails with a clear error if unresolved
- `@domain/Type?` — optional: generates graceful fallback code if target is missing

References are **semantic**, not syntactic. The transpiler decides what the reference means in the target stack — a foreign key in SQL, a populated object in GraphQL, a Mongoose ref in MongoDB. You express the relationship; the AI handles the mechanism.

### 4. The IntentIR

When all `.il` files are parsed, the system builds a **flat, queryable IR** (Intermediate Representation). This is the real source of truth the transpiler operates on.

The IR contains:
- Every node from every file, indexed by UID and type
- A dependency graph of all cross-file references
- Global rules propagated from `core.il`
- Domain membership for every node
- Abstraction level annotations

The transpiler receives a compact IR summary (not the full source) plus only the adjacent nodes it needs. This is why IntentLang works reliably at scale — the AI always has surgical context, never a firehose.

### 5. Transpilation is a Graph Traversal

When you transpile a file, the system:

1. Parses all `.il` files → builds complete IR
2. Resolves all cross-file references → flags unresolved
3. Propagates global rules from `core.il` down through the graph
4. Identifies which nodes changed since last transpile (diff)
5. Provides the AI with: the target node, its resolved dependencies, applicable global rules, and the diff

Only changed nodes need regeneration. Change a field on `User` in `identity.il` — only User's model file, its migration, and the routes that directly reference it are regenerated. Everything else stays.

---

## Language Reference

### Block Declarations

```
project MyApp:       # root — one per codebase, in core.il
domain identity:     # domain boundary — one per file
model User:          # data model
feature Auth:        # feature grouping routes and logic
route GET /users:    # HTTP endpoint (method + path)
route WS /chat:      # WebSocket endpoint
event user_joined:   # event (WebSocket, message queue, etc.)
config Database:     # infrastructure config block
platform infra:      # platform/deployment concerns
critical_path foo:   # performance-critical code path
inline raw_code:     # escape hatch for dropping in literal code
```

### Field Definitions

```
model User:
  id (uuid, pk)
  email (str, required, unique)
  name (str, required)
  role (str, default "member")
  avatar (str, optional)
  score (int, default 0)
  active (bool, default true)
  data (json, nullable)
  tags (list, optional)
```

Available types: `str`, `int`, `float`, `bool`, `uuid`, `date`, `datetime`, `json`, `list`, `map`, `bytes`

Available modifiers: `required`, `optional`, `pk`, `fk`, `unique`, `indexed`, `default`, `nullable`, `readonly`, `private`, `public`, `async`, `sync`

### Relations

```
# Local (within same file)
model Task:
  project -> Project

# Cross-domain
model Task:
  owner: @identity/User!
  assignee: @identity/User?
```

### Route Blocks

```
feature Tasks:
  route POST /tasks:
    auth: required
    input: title (str, required), priority?, due_date?
    action: create Task, assign owner = current_user
    returns: Task
    error: if title empty -> 400 "Title required"
    error: if not member -> 403 "Not a project member"

  route PATCH /tasks/:id:
    auth: required
    input: title?, status?, priority?
    action: update Task where id = :id, owner = current_user
    returns: Task
    error: if not found -> 404
```

### Rules Blocks

```
rules:
  - all endpoints require auth unless marked public
  - passwords must be hashed with bcrypt
  - rate limit: 100 req/min/ip
  - max file upload: 10mb
```

Rules in `core.il` apply globally. Rules inside a `feature:` block apply only to that feature.

### Level Directives

```
@level: high        # applies to all children below until overridden
@level: mid

model Task:
  title (str, required)

  @level: low
  search_vector (tsvector, indexed)    # this field gets low-level treatment

@level: asm
critical_path hot_loop:
  @target: x86_64-linux
  constraint: no heap allocation
  constraint: prefer AVX2 intrinsics
  max_cycles: 50
```

### Environment Blocks

```
environment dev:
  database: localhost:5432/myapp_dev
  cache: localhost:6379
  email: console
  debug: true

environment staging:
  database: rds.staging/myapp
  email: ses

environment prod:
  database: rds.prod/myapp + read_replica
  cache: elasticache.prod
  cdn: cloudfront
```

---

## The IR Query Engine

The IDE includes a live query interface over the compiled IR. Use it to explore your project structure, debug cross-references, and understand impact before making changes.

### Query Syntax

```
list models                   # all model nodes across all files
list features                 # all feature nodes
list routes                   # all route nodes
show global rules             # rules from core.il
show stack                    # stack, project name, files
show graph                    # all dependency edges
show domains                  # domain → node count

deps of <name>                # what does <name> depend on?
used by <name>                # what depends on <name>?
impact of <name>              # direct + indirect dependents (before you change something)
inspect <name>                # full IR node JSON for <name>
```

### Example Workflow

Before changing the `User` model:
```
> impact of User
Direct dependents:
  tasks:model:Task (xref)
  tasks:feature:Tasks (xref)
  identity:feature:Auth (relation)

Indirect (2nd-order):
  tasks:route:GET_/projects/:id/tasks
  tasks:route:POST_/projects/:id/tasks
```

Now you know exactly what gets regenerated before touching anything.

---

## Multi-File Dependency Resolution

### How References Resolve

Given:
```
# tasks.il
model Task:
  owner: @identity/User!
```

1. Parser sees `@identity/User!` → creates an `xref_property` node
2. IR builder scans `ir.domains["identity"]` for a node with `name === "User"`
3. If found: edge `tasks:model:Task → identity:model:User` added to graph, `resolved: true`
4. If not found and strictness is `!`: transpilation blocked with clear error
5. If not found and strictness is `?`: edge added as unresolved, transpiler emits fallback

### Transpilation Order

The transpiler topologically sorts changed nodes by their dependency edges. A model must be transpiled before the features that reference it. `core.il` global rules are always applied first.

---

## IDE Panels

### Editor
Write `.il` files with live syntax highlighting. Supports multiple files via file tabs. Tab key inserts 2-space indentation. `⌘↵` triggers transpilation.

### IR Explorer
Visual overview of the compiled IR: node type distribution, dependency edges, global rules, domain membership, abstraction level distribution, and parse errors.

### Query
Live query interface against the IR graph. Type any query and press Enter, or click suggested queries. Query history is preserved in session.

### Output
Generated code, split into file tabs. Select which `.il` file to transpile from the dropdown in the header. The AI receives the IR summary + target file + any referenced domain files as context.

---

## Design Principles

**1. Never edit generated code.**
The `.il` file is the source of truth. If you edit generated code, you have two sources of truth and you've lost the whole value. Change the `.il` and regenerate.

**2. Structure is not overhead — it's the product.**
Every `rule:`, every `@level:`, every `constraint:` is load-bearing. The richer the `.il`, the better and more reliable the generated code.

**3. The IR is the memory.**
The compiled IR is what gives the AI access to your full project context without flooding it with source. Keep the IR current (it rebuilds on every edit in the IDE).

**4. Levels are instructions, not labels.**
`@level:asm` isn't a comment — it's an instruction to the transpiler to match the code to that level of abstraction. Use it intentionally.

**5. Cross-file references are semantic contracts.**
`@identity/User!` is a declaration that this thing *must exist* in the identity domain. It will fail loudly if it doesn't. That's intentional.

---

## Roadmap

- [ ] CLI transpiler (`npx intentlang transpile`)
- [ ] `.intentir/` persistent IR cache (incremental rebuilds)
- [ ] IR diff viewer (what changed between versions)
- [ ] Watch mode (auto-regenerate on `.il` save)
- [ ] Multi-target transpilation (same `.il` → React + Vue simultaneously)
- [ ] `inline:` block support (escape hatch for literal code injection)
- [ ] Language server protocol (LSP) for editor integrations
- [ ] `intentlang check` — validate all cross-refs without transpiling
- [ ] Constitutional constraints (security rules that block unsafe patterns)

---

*IntentLang v0.2.0 — the source of truth is the intent, not the code.*
