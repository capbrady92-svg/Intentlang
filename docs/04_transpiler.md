# The Transpiler

How IntentLang turns `.il` files into real code.

---

## What Happens When You Transpile

```
il› transpile tasks.il
```

1. All `.il` files are parsed → IR graph built
2. Unresolved cross-refs checked — strict refs (`!`) block if missing
3. Global rules read from `core.il`
4. Referenced domain files identified from IR edges
5. Context package assembled (IR summary + target + referenced domains)
6. Sent to the configured LLM with streaming enabled
7. Output streamed to terminal and parsed into files
8. Files written to `./intentlang_output/`

---

## The Context Package

The LLM receives three things, in this order:

### 1. System prompt

Explains what IntentLang is, the level system, the multi-file reference system, and the output format. The LLM knows it's an IntentLang transpiler before it sees any of your code.

### 2. IR Summary

A compact snapshot of your whole project:

```
PROJECT: TaskFlow
STACK: react + fastapi + postgres
FILES: core.il, identity.il, tasks.il, platform.il
NODES: 112 total (4 models, 3 features, 8 routes)
EDGES: 7 (0 unresolved)
GLOBAL RULES:
  - all endpoints require auth unless marked public
  - all models get id (uuid pk), created_at, updated_at
  - all errors return { code, message, trace_id }
  - audit log all mutations
  - tokens expire after 7d
```

This is what gives the LLM memory across files. It doesn't need to re-read your whole codebase — the IR summary is the codebase, compressed to the things that matter.

### 3. Target file + referenced domains

The full source of `tasks.il`, followed by any domain files it references (pulled automatically from the IR edge graph):

```
TARGET: tasks.il
domain tasks:
  ...

REFERENCED: identity.il
domain identity:
  ...
```

The LLM sees exactly what it needs — no more, no less.

---

## Output Format

The LLM is instructed to separate files with:

```
// FILE: path/to/file.ext
```

Example output stream:

```
// FILE: backend/models/task.py
from sqlalchemy import ...
...

// FILE: backend/routes/tasks.py
from fastapi import ...
...

// FILE: backend/migrations/001_create_tasks.sql
CREATE TABLE tasks ...
...

// FILE: backend/tests/test_tasks.py
import pytest
...
```

IntentLang parses these markers and writes each file to the correct path under `./intentlang_output/`.

---

## What the LLM Generates

Given a well-written `.il` file and a clear stack declaration, the transpiler generates:

**For a web backend domain:**
- Data models / ORM definitions
- Database migration SQL
- Route handlers / controllers
- Input validation schemas
- Service layer (if the stack uses one)
- Unit tests for routes
- Type definitions / interfaces

**For a frontend domain:**
- React components
- API client functions
- TypeScript types
- State management (if declared)
- Form validation

**For a CLI domain:**
- Main entry point
- Command handlers
- Configuration parsing
- Error handling

**For a low-level domain (`@level:low` / `@level:asm`):**
- C with platform intrinsics
- Rust unsafe blocks
- Inline assembly
- Memory management code

The LLM decides what files to generate based on the stack and the content of the `.il`. You don't need to specify — it figures out what a complete implementation requires.

---

## Transpiling Multiple Files

Transpile files one at a time, in dependency order — leaf domains first, then domains that reference them:

```
il› transpile core.il           # generates project scaffold, config, docker-compose, etc.
il› transpile identity.il       # generates User model, auth routes, session handling
il› transpile tasks.il          # generates Task/Project models, task routes (refs identity)
il› transpile billing.il        # generates billing (refs identity + orgs)
```

Or transpile all at once — the IR handles ordering:

```
il› transpile core.il
il› transpile identity.il
il› transpile tasks.il
```

Output files accumulate in `./intentlang_output/`. Re-transpiling overwrites previous output for that file.

---

## The Golden Rule

**Never edit files in `./intentlang_output/`.**

The moment you edit generated code, you have two sources of truth. The `.il` says one thing; the generated code says another. The next transpile will overwrite your changes.

If something is wrong with the generated code:

1. **Is the intent wrong?** Fix the `.il` and regenerate.
2. **Is the LLM making a bad choice?** Add a `constraint:`, `note:`, or `reason:` to the `.il` to guide it. Regenerate.
3. **Is it something the language can't express?** Use an `inline:` block to pass raw code through.

If you find yourself wanting to edit generated code, that's a signal that your `.il` is underspecified.

---

## Getting Better Output

### Add `reason:` fields

The LLM makes much better decisions when it knows *why*, not just *what*:

```
// Without reason — LLM picks an implementation
config ClickTracking:
  strategy: async queue

// With reason — LLM makes the right tradeoff
config ClickTracking:
  strategy: write clicks to redis queue, batch flush to postgres every 60s
  reason: redirect latency is critical — click tracking must never block the 302 response
```

### Be explicit about constraints

```
route POST /tasks:
  action: create Task
  
// Better:
route POST /tasks:
  input: title (str, required, max 200 chars), priority? (low|normal|high), due_date?
  action: validate input, create Task owned by current_user, invalidate list cache
  constraint: title cannot be blank after trimming whitespace
  constraint: due_date must be in the future
  returns: Task
  error: if title blank -> 400 "Title required"
  error: if due_date in past -> 400 "Due date must be in the future"
```

### Use `algorithm:` for non-obvious implementations

```
feature Search:
  route GET /search:
    input: q
    action: search Posts
    algorithm: postgres full-text search using tsvector + tsquery, ranked by ts_rank
    reason: built-in postgres FTS is sufficient at this scale — no Elasticsearch needed
```

### Layer your rules

Global rules in `core.il` for system-wide concerns. Feature-level rules for domain-specific constraints.

```
// core.il — applies everywhere
rules:
  - all endpoints require auth unless marked public
  - all errors return { code, message }

// tasks.il — applies to this domain only
feature Tasks:
  rules:
    - only project members can create tasks
    - task status can only move forward (todo→in_progress→done)
    - completed tasks cannot be edited
```

### Use `@level:` intentionally

If you don't declare a level, everything is `@level:high` — clean, idiomatic, high-level code. Only drop to lower levels when you mean to:

```
model Task:
  title (str, required)
  description (str, optional)
  
  @level: low
  search_vector (tsvector, indexed)    // this field gets DB-level treatment
  fts_updated_at (datetime, indexed)
```

---

## Configuring the Transpiler

In `intentlang.py` config block:

```python
MAX_TOKENS  = 8000      # increase for larger files, decrease for speed/cost
TEMPERATURE = 0.2       # lower = more consistent output, higher = more creative
```

Lower temperature (0.1–0.2) produces more consistent, predictable code — recommended for production use. Higher temperature (0.5–0.7) produces more varied output — useful when you want the LLM to explore implementation options.

---

## Understanding Streaming Output

The terminal streams output as the LLM generates it. You'll see files appear one by one. This is normal — the LLM generates sequentially, file by file.

If the stream cuts off mid-file, it usually means:
- `MAX_TOKENS` is too low for the complexity of the domain
- The LLM hit its context limit (reduce referenced domains or split the `.il` file)

Increase `MAX_TOKENS` in the config if you're regularly hitting truncation on large domains.