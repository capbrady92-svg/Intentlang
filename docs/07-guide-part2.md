# The IntentLang Guide — Part 2: Building a Real SaaS Application

## What We're Building

In Part 1, you built a self-contained single-domain project. Everything lived in one `.il` file and nothing referenced anything else. That's fine for small tools.

Real software is more complex. A SaaS application has users, organizations, billing, notifications, and API access — all of which need to reference each other. A task's `owner` is a `User` from the identity domain. A `Subscription` belongs to an `Organization`. A notification's `recipient` is a `User`.

In this part, we'll build **Beacon** — a lightweight project management SaaS. It has:

- **Identity** — users, authentication, sessions
- **Organizations** — multi-tenant workspace management  
- **Projects** — project and task management (the core product)
- **Billing** — Stripe subscriptions and plan enforcement
- **Platform** — infrastructure, preserve rules, environments

Five domains, twelve cross-domain references, global rules that enforce consistency across everything. By the end, you'll understand how IntentLang handles complexity — and why it handles it better than any approach you've used before.

---

## Chapter 8: Designing Before Writing

Before writing any `.il`, spend five minutes on paper (or a whiteboard) answering three questions:

1. **What are my data shapes?** List every entity your system needs.
2. **What can users do?** List the actions, not the routes.
3. **What are my invariants?** What must always be true, regardless of what changes?

For Beacon:

**Data shapes:** User, Session, Organization, Membership, Project, Task, Comment, Subscription, Invoice, ApiKey, AuditLog

**Actions:** Register, login, create org, invite members, create project, manage tasks, subscribe, view invoices, generate API keys

**Invariants:**
- Users only see data from their own organization
- Free plan limited to 3 projects
- All mutations are audit-logged
- Passwords never exposed in API responses
- Billing actions require org-owner role

These invariants become your global rules in `core.il`. Write them before anything else. Rules written first shape everything; rules added later patch things.

---

## Chapter 9: core.il — The Root of Everything

Create a new directory for this project:

```bash
mkdir beacon
cd beacon
mkdir intent
```

Start IntentLang from this directory:

```bash
python /path/to/intentlang.py
il› load ./intent
```

Create `core.il`:

```
il› new core
il› edit core.il
```

```
// core.il — Beacon Project Management SaaS
project Beacon:
  version: 0.1.0
  stack: next.js + fastapi + postgres + redis + stripe + resend
  pattern: REST
  auth: jwt + api_key

  domains:
    - identity
    - orgs
    - projects
    - billing
    - platform

  rules:
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message, request_id }
    - all mutations emit an audit log entry
    - row-level security: users only access their own organization's data
    - jwt and api_key are interchangeable for authentication
    - all endpoints require auth unless explicitly marked public
    - request_id header echoed on every response for tracing
    - bcrypt rounds: 12
    - jwt expires after 24h
    - refresh tokens expire after 30d
```

Look at what these rules do. Every single route in every domain will:
- Return consistent error shapes
- Be protected by default
- Have audit logging
- Enforce organization-scoped data access

You wrote this once. The AI applies it everywhere. Forever.

Save and check:

```
il› query show global rules
1. all models get id (uuid pk), created_at, updated_at
2. all errors return { code, message, request_id }
3. all mutations emit an audit log entry
4. row-level security: users only access their own organization's data
...
```

---

## Chapter 10: The Identity Domain

The identity domain handles everything about who users are and how they prove it. It's also the domain that everything else references — every other domain needs to know who a `User` is.

```
il› new identity
il› edit identity.il
```

```
// identity.il — User identity and authentication
domain identity:
  description: "Users, authentication, sessions, and email verification"

// ── Models ────────────────────────────────────────────────────────────────────

model User:
  id (uuid, pk)
  email (str, required, unique, indexed)
  password_hash (str, required, private)
  name (str, required)
  avatar (str, optional)
  role (str, default "user")
  email_verified (bool, default false)
  last_login_at (datetime, optional)

model Session:
  id (uuid, pk)
  user -> User
  access_token_hash (str, required, private)
  refresh_token_hash (str, required, private)
  expires_at (datetime, required)
  ip (str, optional)
  user_agent (str, optional)

model EmailVerification:
  id (uuid, pk)
  user -> User
  token (str, required, unique, private)
  expires_at (datetime, required)
  used (bool, default false)

model PasswordReset:
  id (uuid, pk)
  user -> User
  token_hash (str, required, private)
  expires_at (datetime, required)
  used (bool, default false)

// ── Features ──────────────────────────────────────────────────────────────────

feature Auth:
  route POST /auth/register:
    auth: public
    input: email, password, name
    action: validate email format, check email not taken, hash password with bcrypt, create User, create EmailVerification token, send verification email via resend
    returns: { message: "Check your email to verify your account" }
    error: if email taken -> 409 "An account with this email already exists"

  route POST /auth/verify-email:
    auth: public
    input: token (str, required)
    action: find EmailVerification by token, check not expired or used, set User.email_verified = true, mark token used
    returns: { message: "Email verified", token, refresh_token, user }
    error: if token invalid -> 400 "Invalid verification token"
    error: if token expired -> 400 "Verification token expired — request a new one"

  route POST /auth/login:
    auth: public
    input: email, password
    action: find User by email, verify bcrypt password, check email_verified, create Session, update last_login_at
    returns: { token, refresh_token, user }
    error: if not found or wrong password -> 401 "Invalid email or password"
    error: if email not verified -> 403 "Please verify your email before logging in"

  route POST /auth/refresh:
    auth: public
    input: refresh_token
    action: find Session by refresh_token_hash, check not expired, issue new access token, rotate refresh token
    returns: { token, refresh_token }
    error: if invalid or expired -> 401 "Session expired"

  route POST /auth/logout:
    action: delete current Session
    returns: { ok: true }

  route POST /auth/forgot-password:
    auth: public
    input: email
    action: find User by email, create PasswordReset token, send reset email
    returns: { ok: true }
    note: always returns 200 regardless of whether email exists — prevents user enumeration

  route POST /auth/reset-password:
    auth: public
    input: token, new_password
    action: find PasswordReset by token_hash, check not expired or used, validate new password, update User.password_hash, mark token used, invalidate all active Sessions for user
    returns: { ok: true }
    error: if token invalid or expired -> 400

feature Profile:
  route GET /auth/me:
    action: return current User (never return password_hash)
    returns: User

  route PUT /auth/me:
    input: name?, avatar?
    action: update User profile fields
    returns: User

  route PUT /auth/me/password:
    input: current_password, new_password
    action: verify current_password, update password_hash, invalidate all other Sessions
    returns: { ok: true }
    error: if current_password wrong -> 400 "Current password is incorrect"

rules:
  - password_hash and all token fields are never returned in any API response
  - email verification required before login is permitted
  - password reset invalidates all active sessions for security
  - reset and verification tokens expire after 1 hour
  - always return 200 on forgot-password regardless of email existence
  - password minimum: 8 characters, at least one number
```

### Understanding the Identity Domain

A few things to notice:

**Privacy by default** — `password_hash`, `access_token_hash`, `refresh_token_hash`, `token` are all marked `private`. This means they'll never appear in any API response or serialization, even if a developer accidentally includes the whole model. The AI enforces this structurally.

**The `note:` field** — Used on `POST /auth/forgot-password`. This isn't formal syntax — it's a hint to the AI about intent. "Always returns 200 regardless of whether email exists" is a security practice (prevents user enumeration). Putting it in `note:` makes it visible and explicit.

**Specificity in actions** — Compare:
- Vague: `action: reset password`
- Specific: `action: find PasswordReset by token_hash, check not expired or used, validate new password, update User.password_hash, mark token used, invalidate all active Sessions for user`

The specific version tells the AI exactly what to do, in what order, with what side effects. The generated code will be correct the first time.

---

## Chapter 11: Cross-Domain References

Now we write the orgs domain, which references Users from identity. This is where IntentLang's cross-domain reference system becomes essential.

```
il› new orgs
il› edit orgs.il
```

```
// orgs.il — Organizations and membership
domain orgs:
  description: "Multi-tenant organizations, members, roles, invitations"

model Organization:
  id (uuid, pk)
  name (str, required)
  slug (str, required, unique, indexed)
  logo (str, optional)
  plan (str, default "free")
  owner: @identity/User!

model Membership:
  id (uuid, pk)
  org -> Organization
  user: @identity/User!
  role (str, default "member")
  joined_at (datetime, default now)

model Invitation:
  id (uuid, pk)
  org -> Organization
  email (str, required)
  role (str, default "member")
  token (str, required, unique, private)
  invited_by: @identity/User!
  expires_at (datetime, required)
  accepted (bool, default false)

model AuditLog:
  id (uuid, pk)
  org -> Organization
  actor: @identity/User?
  action (str, required)
  resource_type (str, optional)
  resource_id (uuid, optional)
  metadata (json, optional)
  ip (str, optional)

feature Orgs:
  route POST /orgs:
    input: name, slug?
    action: create Organization with slug auto-generated from name if not provided, create Membership for current user with role=owner
    returns: Organization
    error: if slug taken -> 409

  route GET /orgs:
    action: fetch all Organizations where current user is a Member
    returns: Organization[]

  route GET /orgs/:slug:
    action: fetch Organization with member count and current user's role
    returns: { org: Organization, member_count, role }
    error: if not member -> 404

  route PUT /orgs/:slug:
    guard: role = owner or admin
    input: name?, logo?
    action: update Organization
    returns: Organization

  route DELETE /orgs/:slug:
    guard: role = owner
    action: delete Organization and all associated data
    error: if has active subscription -> 400 "Cancel subscription before deleting organization"

feature Members:
  route GET /orgs/:slug/members:
    action: fetch all Memberships with User details and online status
    returns: { user: User, role, joined_at }[]

  route PUT /orgs/:slug/members/:user_id:
    guard: role = owner
    input: role
    action: update Membership role
    error: if changing own role as owner -> 400 "Cannot change your own role"
    error: if demoting last owner -> 400 "Organization must have at least one owner"

  route DELETE /orgs/:slug/members/:user_id:
    guard: role = owner or admin
    action: delete Membership
    error: if removing last owner -> 400

feature Invitations:
  route POST /orgs/:slug/invitations:
    guard: role = owner or admin
    input: email, role?
    action: check email not already a member, create Invitation with 7-day token, send invitation email
    returns: { id, email, role, expires_at }
    error: if already member -> 409

  route POST /invitations/:token/accept:
    auth: public
    action: find Invitation by token, check not expired or accepted, create Membership, mark accepted
    returns: { org: Organization, role }
    error: if invalid token -> 400
    error: if expired -> 400 "Invitation expired"

  route DELETE /orgs/:slug/invitations/:id:
    guard: role = owner or admin
    action: delete pending Invitation
    returns: { ok: true }

rules:
  - every org action is audit logged with actor, action, resource, and metadata
  - only owners can delete the organization
  - organization must always have at least one owner
  - owners cannot remove themselves or change their own role
  - slug: lowercase alphanumeric and hyphens, 3-50 chars
  - invitation tokens expire after 7 days
  - inviting an existing member returns 409
```

### Cross-Domain Reference Syntax

The new syntax here is `@identity/User`. Let's understand it:

**`@identity/User!`** — A reference to the `User` type in the `identity` domain. The `!` means *strict* — if this reference can't be resolved (because `identity.il` doesn't exist or doesn't declare a `User` model), transpilation fails with a clear error. Use `!` for required relationships.

**`@identity/User?`** — Optional reference. If `User` can't be found, the transpiler generates graceful fallback code instead of failing. Use `?` for relationships where the referenced entity might not exist.

**`@identity/User`** — Standard reference. Resolves quietly, handles gracefully.

### What the Reference Actually Means

When the transpiler sees `owner: @identity/User!`, it knows:
- This field stores a reference to a User entity
- The User entity is defined in the identity domain
- The relationship must exist (strict)

But it doesn't tell the transpiler *how* to represent that relationship. That depends on the stack. With FastAPI + Postgres, it generates a foreign key. With GraphQL, it generates a nested type. With MongoDB, it generates a document reference. The intent is separated from the mechanism.

### Checking References

After saving `orgs.il`:

```
il› query show graph
orgs:model:Organization →[xref:owner]→ identity:model:User
orgs:model:Membership →[xref:user]→ identity:model:User
orgs:model:Invitation →[xref:invited_by]→ identity:model:User
orgs:model:AuditLog →[xref:actor]→ identity:model:User
```

Four edges, all resolved. The IR knows exactly how these domains connect.

```
il› query used by User
orgs:model:Organization depends on identity:model:User via [xref]
orgs:model:Membership depends on identity:model:User via [xref]
orgs:model:Invitation depends on identity:model:User via [xref]
orgs:model:AuditLog depends on identity:model:User via [xref]
```

Flip it around: what depends on User? Everything in orgs. Now you know what needs to be regenerated if User changes.

---

## Chapter 12: The Projects Domain

The core product — project and task management. This domain references both identity and orgs.

```
il› new projects
il› edit projects.il
```

```
// projects.il — Project and task management
domain projects:
  description: "Projects, tasks, comments — the core product"

model Project:
  id (uuid, pk)
  name (str, required)
  description (str, optional)
  org: @orgs/Organization!
  created_by: @identity/User!
  status (str, default "active")
  color (str, optional)

model Task:
  id (uuid, pk)
  title (str, required)
  description (str, optional)
  project -> Project
  assignee: @identity/User?
  created_by: @identity/User!
  status (str, default "todo")
  priority (str, default "normal")
  due_date (date, optional)
  completed_at (datetime, optional)
  position (int, default 0)

  @level: low
  search_vector (tsvector, indexed)

model Comment:
  id (uuid, pk)
  task -> Task
  author: @identity/User!
  body (str, required)
  edited (bool, default false)
  edited_at (datetime, optional)

model TaskLabel:
  id (uuid, pk)
  org: @orgs/Organization!
  name (str, required)
  color (str, required)

model TaskLabelAssignment:
  id (uuid, pk)
  task -> Task
  label -> TaskLabel

feature Projects:
  route GET /orgs/:slug/projects:
    action: fetch all Projects for organization, current user must be a member
    returns: Project[]

  route POST /orgs/:slug/projects:
    guard: org member
    input: name, description?, color?
    action: check plan allows new project (free plan max 3), create Project
    returns: Project
    error: if plan limit reached -> 402 "Upgrade to create more projects"

  route GET /orgs/:slug/projects/:project_id:
    guard: org member
    action: fetch Project with task count and member list
    returns: { project: Project, task_count, members }

  route PUT /orgs/:slug/projects/:project_id:
    guard: org member
    input: name?, description?, color?, status?
    action: update Project
    returns: Project

  route DELETE /orgs/:slug/projects/:project_id:
    guard: role = owner or admin
    action: archive Project (set status = archived), do not hard delete
    returns: { ok: true }

feature Tasks:
  route GET /orgs/:slug/projects/:project_id/tasks:
    guard: org member
    input: status?, priority?, assignee_id?, label_id?, q? (search query), sort? (default position)
    action: fetch Tasks with optional filters, if q provided use full-text search on search_vector
    returns: Task[]

  route POST /orgs/:slug/projects/:project_id/tasks:
    guard: org member
    input: title, description?, assignee_id?, priority?, due_date?, label_ids?, position?
    action: create Task in project, assign labels if provided, set position
    returns: Task

  route GET /orgs/:slug/tasks/:task_id:
    guard: org member
    action: fetch Task with comments, labels, and assignee details
    returns: { task: Task, comments: Comment[], labels: TaskLabel[], assignee: User? }

  route PUT /orgs/:slug/tasks/:task_id:
    guard: org member
    input: title?, description?, assignee_id?, status?, priority?, due_date?, position?
    action: update Task, if status changes to "done" set completed_at = now
    returns: Task

  route DELETE /orgs/:slug/tasks/:task_id:
    guard: org member
    action: delete Task and all Comments
    returns: { ok: true }

  route POST /orgs/:slug/tasks/:task_id/labels:
    guard: org member
    input: label_id
    action: create TaskLabelAssignment
    returns: { ok: true }
    error: if already assigned -> 409

  route DELETE /orgs/:slug/tasks/:task_id/labels/:label_id:
    guard: org member
    action: delete TaskLabelAssignment
    returns: { ok: true }

feature Comments:
  route POST /orgs/:slug/tasks/:task_id/comments:
    guard: org member
    input: body (str, required)
    action: create Comment on Task
    returns: Comment

  route PUT /orgs/:slug/tasks/:task_id/comments/:comment_id:
    guard: comment author
    input: body
    action: update Comment body, set edited = true, edited_at = now
    returns: Comment

  route DELETE /orgs/:slug/tasks/:task_id/comments/:comment_id:
    guard: comment author or org admin
    action: delete Comment
    returns: { ok: true }

  @level: mid
  feature Search:
    route GET /orgs/:slug/search:
      guard: org member
      input: q (str, required), type? (tasks|projects|all, default all)
      action: full-text search Tasks using search_vector, rank by ts_rank_cd, include project name in results
      algorithm: postgres tsvector with tsquery, weight title > description
      returns: { tasks: Task[], projects: Project[], total }

rules:
  - users must be org members to access any project or task in that org
  - free plan organizations are limited to 3 active projects
  - archived projects do not count against the plan limit
  - task position is used for drag-and-drop ordering — gaps of 1000 allow reordering without update cascades
  - completing a task (status → done) automatically sets completed_at timestamp
  - deleting a task deletes all its comments (cascade)
  - search_vector is updated automatically via postgres trigger on title/description change
```

### What's New Here

**Multiple cross-domain references** — `Project` references both `@orgs/Organization!` and `@identity/User!`. `Task` references `@identity/User?` twice (assignee and created_by). The IR tracks all of these.

**The `guard:` field** — A shorthand for access control that's broader than `auth:`. `guard: org member` means the route checks that the current user is a member of the organization in the URL. `guard: comment author` means the route checks that the current user created the comment. These are application-level authorization rules, not just authentication.

**`@level: low` on a field** — The `search_vector (tsvector, indexed)` field is marked at `low` level because it's a PostgreSQL-specific type (`tsvector`) that only exists at the database level. The rest of Task stays at `high` level. This tells the transpiler to handle this field differently — generating the appropriate Postgres-specific migration, trigger, and GIN index.

**Plan enforcement in routes** — `error: if plan limit reached -> 402 "Upgrade to create more projects"` declares the business rule directly in the route. The AI will check this condition and return the appropriate response.

---

## Chapter 13: The Billing Domain

Billing is often the most complex and most copy-pasted domain in SaaS applications. In IntentLang, you express the intent once and the AI implements it correctly for your specific stack.

```
il› new billing
il› edit billing.il
```

```
// billing.il — Stripe billing and subscription management
domain billing:
  description: "Plans, subscriptions, invoices, and Stripe integration"

model Subscription:
  id (uuid, pk)
  org: @orgs/Organization!
  stripe_customer_id (str, required, unique)
  stripe_subscription_id (str, optional, unique)
  plan (str, required)
  status (str, default "trialing")
  trial_ends_at (datetime, optional)
  current_period_start (datetime, optional)
  current_period_end (datetime, optional)
  cancel_at_period_end (bool, default false)

model Invoice:
  id (uuid, pk)
  org: @orgs/Organization!
  stripe_invoice_id (str, required, unique)
  amount_cents (int, required)
  currency (str, default "usd")
  status (str, required)
  description (str, optional)
  invoice_pdf_url (str, optional)
  paid_at (datetime, optional)

model Plan:
  id (str, pk)
  name (str, required)
  price_monthly_cents (int, required)
  price_yearly_cents (int, required)
  max_projects (int, required)
  max_members (int, required)
  features (list, required)

feature Plans:
  route GET /plans:
    auth: public
    action: return all available Plans with pricing and features
    returns: Plan[]

feature Billing:
  route GET /orgs/:slug/billing:
    guard: role = owner or admin
    action: fetch Subscription with current period details and last 12 Invoices
    returns: { subscription: Subscription, invoices: Invoice[], plan: Plan }

  route POST /orgs/:slug/billing/checkout:
    guard: role = owner
    input: plan_id, interval (monthly|yearly)
    action: create or retrieve Stripe customer for org, create Stripe checkout session, return checkout URL
    returns: { checkout_url }

  route POST /orgs/:slug/billing/portal:
    guard: role = owner
    action: create Stripe billing portal session for managing payment method and invoices
    returns: { portal_url }

  route POST /orgs/:slug/billing/cancel:
    guard: role = owner
    action: set cancel_at_period_end = true on Stripe subscription, org retains access until period ends
    returns: { cancels_at, message: "Your subscription will cancel at the end of the billing period" }

feature Webhooks:
  route POST /webhooks/stripe:
    auth: stripe_signature
    action: verify Stripe webhook signature, handle events
    events:
      - checkout.session.completed: create or update Subscription, set status = active, update org.plan
      - customer.subscription.updated: sync plan, status, period dates, cancel_at_period_end
      - customer.subscription.deleted: set status = canceled, downgrade org.plan to free
      - invoice.payment_succeeded: create Invoice record, set paid_at
      - invoice.payment_failed: send payment failure email to org owner, set status = past_due

  @level: mid
  config WebhookIdempotency:
    strategy: store processed stripe_event_ids in postgres table
    on_duplicate_event_id: return 200 immediately without processing
    reason: Stripe guarantees at-least-once delivery — webhooks may arrive more than once

  @level: mid
  config PlanEnforcement:
    on_plan_downgrade: check current usage against new plan limits
    if_over_limit: do not delete data, set org status = over_limit, prompt upgrade
    reason: never delete user data on downgrade — always give users a chance to upgrade

rules:
  - only org owners can manage billing
  - billing amounts are always in cents to avoid floating point issues
  - webhooks must verify Stripe signature before processing any event
  - failed payments send email notification before suspension
  - org retains full access during trial and until period end on cancellation
  - free plan: max 3 projects, max 5 members
  - pro plan: unlimited projects, unlimited members
  - downgrading never deletes data — enforces limits on new actions only
```

### Webhook Design

The webhook route introduces a pattern worth examining:

```
route POST /webhooks/stripe:
  auth: stripe_signature
  action: verify Stripe webhook signature, handle events
  events:
    - checkout.session.completed: ...
    - invoice.payment_failed: ...
```

`auth: stripe_signature` — not JWT or api_key, but Stripe's HMAC signature verification. The AI understands this pattern and will generate the appropriate signature verification middleware.

The `events:` block is freeform — a list of event types with their handlers. This isn't formal syntax; it's structured prose that the AI reads as a dispatch table. The AI generates a webhook handler that routes each Stripe event to the appropriate internal action.

---

## Chapter 14: Platform — Infrastructure and Preservation

The final domain handles infrastructure configuration and, critically, the preserve rules that protect files you shouldn't regenerate.

```
il› new platform
il› edit platform.il
```

```
// platform.il — Infrastructure, environments, and preservation
domain platform:
  description: "Infrastructure configuration, environments, and generated file protection"

// ── Preserve Rules ────────────────────────────────────────────────────────────
// Files matching these patterns will NEVER be overwritten during transpilation.
// Remove a pattern here to allow regeneration.

preserve:
  - migrations/*
  - .env
  - .env.local
  - .env.production
  - backend/custom/*
  - scripts/seed.py
  - frontend/src/styles/custom.css

// ── Database ──────────────────────────────────────────────────────────────────

@level: low
config Database:
  engine: postgres 15
  pool_size: 20
  max_overflow: 10
  statement_timeout: 30s
  idle_timeout: 600s
  ssl: required in production

@level: mid
config DatabaseOptimization:
  connection_pooling: pgbouncer in transaction mode
  read_replicas: 1 in production for analytics queries
  reason: analytics queries from billing and projects are expensive — route to replica

// ── Cache ─────────────────────────────────────────────────────────────────────

@level: mid
config Cache:
  engine: redis 7
  strategy: lru
  max_memory: 512mb
  eviction: allkeys-lru
  key_namespacing: beacon:{environment}:{domain}:{key}
  reason: explicit namespacing prevents cross-environment cache collisions

config SessionCache:
  strategy: cache active Sessions in redis for 15 minutes
  key: session:{token_hash}
  reason: avoid postgres hit on every authenticated request

// ── Rate Limiting ─────────────────────────────────────────────────────────────

@level: mid
config RateLimit:
  backend: redis sliding window
  default: 200/minute/user
  auth_endpoints: 15/minute/ip
  webhook_endpoints: unlimited
  algorithm: ZADD with score=timestamp, ZREMRANGEBYSCORE to prune, ZCARD to count
  reason: sliding window is fairer than fixed window at period boundaries

// ── Environments ──────────────────────────────────────────────────────────────

environment dev:
  database: localhost:5432/beacon_dev
  redis: localhost:6379
  stripe: test keys
  email: log to console
  debug: true
  cors: allow all origins

environment staging:
  database: rds.staging.beacon/beacon
  redis: elasticache.staging
  stripe: test keys
  email: resend test mode
  cors: beacon-staging.vercel.app

environment production:
  database: rds.prod.beacon/beacon + read_replica
  redis: elasticache.prod (cluster mode)
  stripe: live keys
  email: resend production
  cdn: cloudfront
  cors: beacon.app
  error_tracking: sentry
  logging: structured JSON to cloudwatch
```

### The Preserve System

The `preserve:` block is critical to the "never edit generated code" discipline:

```
preserve:
  - migrations/*
  - .env
  - .env.local
```

Once a database migration is applied, you never regenerate it — regenerating would create a duplicate migration that breaks your database. The preserve pattern `migrations/*` protects all migration files after they're written.

Similarly, `.env` files contain secrets and environment-specific config that you set manually. They should never be overwritten.

`backend/custom/*` is a safety valve — anything you put in the `custom/` directory is intentionally hand-written code that supplements the generated code. It's never overwritten.

When you transpile now:

```
il› transpile platform.il
```

If a migration already exists in `~/intentlang/beacon/migrations/`, it won't be touched. You'll see:

```
✓  backend/config.py
✓  backend/middleware/rate_limit.py
⊘  migrations/001_initial.sql (preserved)
⊘  .env (preserved)
```

The `⊘` symbol means the file was skipped because it's protected.

---

## Chapter 15: The Full IR — Understanding Your System

With all five domains written, let's explore the full IR:

```
il› list

Loaded files:
  ├─ core.il       18 lines
  ├─ identity.il   98 lines
  ├─ orgs.il       102 lines
  ├─ projects.il   118 lines
  ├─ billing.il    95 lines
  └─ platform.il   72 lines

IR Summary
  Project      Beacon
  Stack        next.js + fastapi + postgres + redis + stripe + resend
  Files        core.il, identity.il, orgs.il, projects.il, billing.il, platform.il
  Nodes        312 (11 models, 8 features, 22 routes)
  Edges        14 (0 unresolved)
  Rules        10
  Preserve     migrations/*, .env, .env.local, .env.production, backend/custom/*, ...
```

312 nodes. 14 edges. 0 unresolved. All cross-domain references are wired correctly.

Now let's explore:

```
il› query used by Organization
orgs:model:Membership depends on orgs:model:Organization via [relation]
orgs:model:Invitation depends on orgs:model:Organization via [relation]
orgs:model:AuditLog depends on orgs:model:Organization via [relation]
projects:model:Project depends on orgs:model:Organization via [xref]
billing:model:Subscription depends on orgs:model:Organization via [xref]
billing:model:Invoice depends on orgs:model:Organization via [xref]
```

Before you change anything about Organization, you know exactly what's affected. In a normal codebase, discovering this would require reading multiple files and grep. Here it's one query.

```
il› query impact of User
Direct dependents:
  orgs:model:Organization [xref]
  orgs:model:Membership [xref]
  orgs:model:Invitation [xref]
  orgs:model:AuditLog [xref]
  projects:model:Task [xref]
  projects:model:Comment [xref]

Indirect (2nd-order):
  orgs:feature:Orgs
  orgs:feature:Members
  projects:feature:Tasks
  projects:feature:Comments
```

User is referenced by six models across two domains, and indirectly affects four features. This is architectural visibility you simply don't have in a normal codebase.

---

## Chapter 16: Transpiling the Full System

Now generate everything:

```
il› transpile core.il
```
*Project scaffold: docker-compose, Makefiles, CI config, README*

```
il› transpile identity.il
```
*User models, auth routes, JWT middleware, email templates, tests*

```
il› transpile orgs.il
```
*Organization models, membership routes, invitation flow, audit logging*

```
il› transpile projects.il
```
*Project and task models, all routes, full-text search, label system*

```
il› transpile billing.il
```
*Stripe integration, webhook handler, plan enforcement middleware*

```
il› transpile platform.il
```
*Config files, middleware, environment setup, rate limiting*

Each transpile call sends the AI the IR summary (which knows the full system) plus the target domain plus any referenced domains. The AI generates code that correctly integrates with everything else because it has structural knowledge of the entire system.

The output lands in `~/intentlang/beacon/`:

```
~/intentlang/beacon/
  backend/
    models/         — SQLAlchemy models for all domains
    routes/         — FastAPI route handlers
    schemas/        — Pydantic validation schemas
    middleware/     — Auth, rate limiting, audit logging
    services/       — Business logic layer
    workers/        — Background tasks (click aggregation, etc.)
  frontend/
    components/     — React components
    pages/          — Next.js pages
    lib/            — API client, auth utils
  migrations/       — Postgres migrations (preserved after first run)
  tests/            — pytest and jest tests
  docker-compose.yml
  Makefile
```

A complete SaaS application. Two commands per domain.

---

## Chapter 17: The Interface System

Beacon's identity domain is valuable. Other projects — a mobile app, an admin panel, a third-party integration — might want to consume its User and Auth surface without copying the implementation.

This is what the `interface:` block is for.

### Publishing an Interface

Add an interface declaration to `identity.il`:

```
// In identity.il, before the models:

interface:
  version: 1.0.0

  expose:
    - model User
    - feature Auth
    - feature Profile

  hide:
    - model Session
    - model EmailVerification
    - model PasswordReset
    - field User.password_hash
    - field User.email_verified

  deprecated:
    - route GET /auth/me (use GET /auth/me from Profile feature instead)
```

The `expose:` list declares what's public. The `hide:` list filters out internal models and private fields. `deprecated:` documents things that will be removed in future versions.

Now publish it:

```
il› publish identity
```

```
✓  ~/intentlang/beacon/interface/identity/identity.schema.json
✓  ~/intentlang/beacon/interface/identity/identity.client.ts
✓  ~/intentlang/beacon/interface/identity/identity_client.py
✓  ~/intentlang/beacon/interface/identity/identity.openapi.json
```

Four files:

**`identity.schema.json`** — Machine-readable interface definition. Other IntentLang projects import this.

**`identity.client.ts`** — TypeScript client with typed interfaces for User and AuthClient class with all exposed methods.

**`identity_client.py`** — Python client with User dataclass and IdentityClient class.

**`identity.openapi.json`** — OpenAPI 3.0 spec for the exposed API surface. Drop this into Swagger UI, Postman, or any OpenAPI tooling.

### Consuming an Interface from Another Project

Suppose you're building a mobile app backend that needs to authenticate with Beacon's identity service. In your mobile backend's `core.il`:

```
project BeaconMobile:
  stack: fastapi + postgres
  
  imports:
    identity: github.com/yourorg/beacon/intent@^1.0
    // or local path:
    // identity: ../beacon/intent

  domains:
    - mobile
```

Then in your mobile backend's domain files:

```
model DeviceToken:
  id (uuid, pk)
  user: @identity/User!
  device_id (str, required)
  platform (str, required)
  push_token (str, required)
```

When you load this project, IntentLang resolves `@identity/User` from the imported interface — no need to copy the User definition, no risk of it drifting out of sync. The transpiler generates code that calls Beacon's actual identity API.

### Checking Compatibility

After adding `deprecated:` or `breaking_changes:` entries:

```
il› query show compat
[identity v1.0.0] DEPRECATED: route GET /auth/me (use GET /auth/me from Profile feature instead)
```

Any project importing this interface can run the same query and see what's changing before upgrading.

---

## Chapter 18: Iteration at Scale

The real test of any abstraction is how it handles change. Let's walk through some realistic change scenarios.

### Scenario 1: Adding a Field to User

The product team wants to add user timezone preferences.

Edit `identity.il`, add to User model:

```
model User:
  ...
  timezone (str, default "UTC")
  date_format (str, default "YYYY-MM-DD")
```

Check impact:

```
il› query impact of User
Direct: Organization, Membership, Invitation, AuditLog, Task, Comment (6 models)
Indirect: Orgs feature, Members feature, Tasks feature, Comments feature
```

This is informational — adding fields doesn't break anything. Regenerate:

```
il› transpile identity.il
```

New migration, updated schema, updated serialization. Nothing in orgs or projects needs to change unless you want to expose the new field in cross-domain queries.

### Scenario 2: Adding a New Plan Tier

The business wants to add an "Enterprise" plan between Pro and free.

Edit `billing.il`, add to the rules:

```
rules:
  ...
  - enterprise plan: unlimited projects, unlimited members, SSO, audit log export, SLA
  - enterprise billing is annual only and requires sales contact
```

Add to the Plans feature:

```
route POST /orgs/:slug/billing/enterprise-inquiry:
  guard: role = owner
  input: contact_name, contact_email, company_size
  action: send enterprise inquiry to sales team via email, create lead in CRM
  returns: { message: "Our team will reach out within 24 hours" }
```

Regenerate billing:

```
il› transpile billing.il
```

### Scenario 3: Changing a Global Rule

The security team wants all API responses to include a `X-Request-ID` header in addition to the existing `request_id` field in error responses.

Edit `core.il`:

```
rules:
  - all models get id (uuid pk), created_at, updated_at
  - all errors return { code, message, request_id }
  - all responses include X-Request-ID response header   ← new
  - all mutations emit an audit log entry
  ...
```

This affects every domain. Regenerate everything:

```
il› transpile core.il
il› transpile identity.il
il› transpile orgs.il
il› transpile projects.il
il› transpile billing.il
il› transpile platform.il
```

The middleware that adds the header is generated once, in `core.il`. The rule propagates.

### Scenario 4: Renaming a Model

This is the scenario that breaks things in normal codebases. Let's rename `TaskLabelAssignment` to `TaskTag` in `projects.il`.

First, check impact:

```
il› query inspect TaskLabelAssignment
uid: projects:model:TaskLabelAssignment
type: model
name: TaskLabelAssignment
filename: projects.il
```

```
il› query used by TaskLabelAssignment
Nothing depends on "TaskLabelAssignment"
```

No other domain references this model — it's only used internally in projects.il. Make the change:

```
model TaskTag:          ← renamed from TaskLabelAssignment
  id (uuid, pk)
  task -> Task
  label -> TaskLabel
```

Update the routes that reference it, regenerate:

```
il› transpile projects.il
```

A new migration is generated: `ALTER TABLE task_label_assignments RENAME TO task_tags`. Because `migrations/*` is in the preserve list, the *old* migrations are preserved and a *new* one is added.

---

## Chapter 19: What Makes This Different

Looking back at what we've built, the architecture has some properties that are hard to achieve any other way.

### Your Codebase Is 500 Lines

The six `.il` files for Beacon total approximately 500 lines. The generated code is probably 8,000-12,000 lines across 60+ files. You maintain the 500 lines. The AI maintains the 60 files.

When a new developer joins your team, they read the `.il` files. They understand the entire system in an afternoon — not because the system is simple, but because the `.il` is dense with intent and free of implementation noise.

### The AI Always Has Complete Context

Every transpile call receives the IR summary — a structured description of the entire project. The AI knows Beacon's stack, all global rules, all domain relationships, and the preserve patterns before it reads the first line of your target file.

Compare this to a typical AI coding session where you paste in some code and hope the model infers the rest. There's no inference in IntentLang — every relevant fact is explicitly provided.

### Consistency Is Structural

Every route has consistent error shapes because it's a global rule. Every model has consistent timestamps because it's a global rule. Audit logging happens everywhere because it's a global rule.

These aren't coding standards that developers need to remember and reviewers need to check. They're facts about the system that the AI enforces automatically on every generation.

### Changes Are Scoped and Visible

Before any change, you query impact. After any change, you regenerate only what's affected. Nothing changes silently. Nothing drifts.

This is what software development looks like when the intent is the primary artifact and the code is a derived output.

---

## Where to Go From Here

You've now built two complete projects with IntentLang — a focused single-domain service and a complex multi-domain SaaS application. You understand:

- How to structure projects with `core.il` and domain files
- How to write precise, effective models and routes
- How cross-domain references work and what they compile to
- How to use abstraction levels for different kinds of code
- How to check impact before making changes
- How to publish and consume interfaces across projects
- How to preserve files that should never be regenerated

The next step is building something of your own. Start with `core.il`. Write the global rules first — they're the most important part. Then write your models. Then your features. Check the IR. Transpile.

The language will feel natural after your first project. By your second, you'll wonder why you ever built software any other way.

---

## Quick Reference

### File Structure
```
core.il          → project, stack, domains, global rules
<domain>.il      → domain, models, features, routes, rules
```

### Model Fields
```
name (type, modifiers...)
id (uuid, pk)
email (str, required, unique)
age (int, optional)
active (bool, default true)
```

### Cross-Domain References
```
owner: @identity/User!    # strict
assignee: @identity/User? # optional
org: @orgs/Organization   # standard
```

### Route Structure
```
route POST /path:
  auth: public | required | api_key
  guard: role = owner | org member | comment author
  input: field (type, required), other_field?
  action: plain English description of what this does
  returns: Model | Model[] | { field, field }
  error: if condition -> status_code "message"
  note: any additional context for the AI
```

### IR Queries
```
il› query list models
il› query list features
il› query show global rules
il› query show graph
il› query used by <name>
il› query impact of <name>
il› query inspect <name>
il› query show compat
il› query show preserve
```

### Transpile Commands
```
il› transpile <file>
il› transpile <file> --out ./custom/path
il› publish <domain>
```

### Config
```
il› config                              # show current config
il› config set INTENTLANG_API_KEY ...   # set API key
il› config set INTENTLANG_MODEL grok-3  # change model
il› config set INTENTLANG_API_BASE ...  # change endpoint
```
