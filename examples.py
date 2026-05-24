#!/usr/bin/env python3
"""
IntentLang — Example Projects

Run this to generate example .il project folders you can load into intentlang.py

Usage:
    python examples.py                  # list available projects
    python examples.py <name>           # write a project to ./examples/<name>/
    python examples.py all              # write all projects

Then load into IntentLang:
    python intentlang.py
    il› load ./examples/<name>
"""

from pathlib import Path
import sys

# ─── EXAMPLE PROJECTS ─────────────────────────────────────────────────────────

PROJECTS = {}

# ══════════════════════════════════════════════════════════════════════════════
# 1. URL SHORTENER  —  small, clean, one domain
#    Stack: fastapi + postgres + redis
#    Good first project to transpile — tight scope, clear output
# ══════════════════════════════════════════════════════════════════════════════

PROJECTS["url-shortener"] = {

"core.il": """\
// core.il — URL Shortener
// Simple single-domain project. Good first IntentLang example.
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
    - rate limit all endpoints: 60/minute/ip
    - api_key required unless endpoint marked public
""",

"links.il": """\
// links.il — Core link shortening domain
domain links:
  description: "URL shortening, redirects, click tracking"

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

feature Shorten:
  route POST /links:
    input: original_url (str, required), slug?, title?, expires_at?
    action: validate url, generate slug if not provided (6 chars alphanumeric), create Link
    returns: { slug, short_url, original_url, expires_at }
    error: if slug taken -> 409 "Slug already in use"
    error: if invalid url -> 400 "Invalid URL"

  route GET /links:
    action: fetch all Links for api_key owner
    returns: Link[]

  route GET /links/:slug:
    action: fetch Link by slug
    returns: Link
    error: if not found -> 404

  route DELETE /links/:slug:
    action: deactivate Link
    returns: { ok: true }

feature Redirect:
  route GET /:slug:
    auth: public
    action: lookup slug in redis cache, fallback to postgres, record Click, redirect
    returns: 302 redirect to original_url
    error: if not found or inactive -> 404
    error: if expired -> 410 "Link expired"

feature Analytics:
  route GET /links/:slug/stats:
    action: fetch Link with click_count, recent Clicks
    returns: { link, total_clicks, clicks_by_day, top_countries }

  @level: mid
  config ClickAggregation:
    strategy: write to redis queue, batch flush to postgres every 60s
    reason: avoid write amplification on hot slugs

rules:
  - slugs are lowercase alphanumeric + hyphens only
  - max slug length: 50 chars
  - max original_url length: 2048 chars
  - expired links return 410 not 404
  - click tracking is async, never blocks redirect
""",

}

# ══════════════════════════════════════════════════════════════════════════════
# 2. EXPENSE TRACKER  —  multi-domain, auth, CSV export
#    Stack: react + express + sqlite
#    Shows: cross-domain refs, file export, user ownership patterns
# ══════════════════════════════════════════════════════════════════════════════

PROJECTS["expense-tracker"] = {

"core.il": """\
// core.il — Expense Tracker
project Ledger:
  version: 0.1.0
  stack: react + express + sqlite
  pattern: REST
  auth: jwt

  domains:
    - users
    - expenses
    - reports

  rules:
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message }
    - users can only access their own data
    - tokens expire after 30d
    - all monetary values stored as integers (cents)
""",

"users.il": """\
// users.il — Auth and user profiles
domain users:

model User:
  id (uuid, pk)
  email (str, required, unique)
  password (str, required, private)
  name (str, required)
  currency (str, default "USD")
  timezone (str, default "UTC")

feature Auth:
  route POST /auth/register:
    auth: public
    input: email, name, password
    action: create User, hash password
    returns: { token, user }
    error: if email exists -> 409

  route POST /auth/login:
    auth: public
    input: email, password
    action: verify password, issue jwt
    returns: { token, user }
    error: if invalid -> 401

  route GET /auth/me:
    action: return current User
    returns: User

  route PUT /auth/me:
    input: name?, currency?, timezone?
    action: update User profile
    returns: User
""",

"expenses.il": """\
// expenses.il — Expense tracking core
domain expenses:

model Category:
  id (uuid, pk)
  name (str, required)
  icon (str, optional)
  color (str, optional)
  owner: @users/User!

model Expense:
  id (uuid, pk)
  amount (int, required)
  description (str, required)
  date (date, required)
  category -> Category
  owner: @users/User!
  receipt_url (str, optional)
  notes (str, optional)
  tags (list, optional)

model Budget:
  id (uuid, pk)
  category -> Category
  owner: @users/User!
  amount (int, required)
  period (str, default "monthly")
  start_date (date, required)

feature Categories:
  route GET /categories:
    action: fetch Categories for current user
    returns: Category[]

  route POST /categories:
    input: name, icon?, color?
    action: create Category for current user
    returns: Category

  route DELETE /categories/:id:
    action: delete Category if no Expenses reference it
    error: if has expenses -> 409 "Category has expenses"

feature Expenses:
  route GET /expenses:
    input: from_date?, to_date?, category_id?, limit? (default 50), offset?
    action: fetch Expenses for current user, filter by params
    returns: { expenses: Expense[], total, has_more }

  route POST /expenses:
    input: amount (int, required), description, date, category_id, receipt_url?, notes?, tags?
    action: create Expense for current user
    returns: Expense

  route PUT /expenses/:id:
    input: amount?, description?, date?, category_id?, notes?, tags?
    action: update Expense owned by current user
    returns: Expense
    error: if not found or not owner -> 404

  route DELETE /expenses/:id:
    action: delete Expense
    error: if not found or not owner -> 404

feature Budgets:
  route GET /budgets:
    action: fetch Budgets with current spend for current user
    returns: { budget: Budget, spent: int, remaining: int, percent: float }[]

  route POST /budgets:
    input: category_id, amount, period?, start_date
    action: create Budget
    returns: Budget

rules:
  - amounts are always in cents (integer)
  - date filters are inclusive on both ends
  - deleting a category with expenses is forbidden
  - users can only read/write their own expenses and categories
""",

"reports.il": """\
// reports.il — Reporting and export
domain reports:

@level: mid
feature Summary:
  route GET /reports/summary:
    input: from_date, to_date, group_by? (day|week|month, default month)
    action: aggregate Expenses by period and category for current user
    returns: { period, total, by_category: { category, amount, count }[] }[]

  route GET /reports/trends:
    input: months? (default 6)
    action: compute month-over-month spend trend per category
    algorithm: simple moving average over rolling window
    returns: { category, trend: { month, amount }[], avg, change_pct }[]

feature Export:
  route GET /reports/export:
    input: from_date, to_date, format (csv|json, default csv)
    action: stream all Expenses in date range for current user
    returns: file download (Content-Disposition: attachment)

  @level: low
  config StreamExport:
    strategy: cursor-based pagination, stream rows directly to response
    chunk_size: 500
    reason: avoid loading all rows into memory for large exports
""",

}

# ══════════════════════════════════════════════════════════════════════════════
# 3. REALTIME CHAT  —  WebSocket, events, presence
#    Stack: react + node + socket.io + redis + postgres
#    Shows: WS events, @level:mid algorithms, cache strategy
# ══════════════════════════════════════════════════════════════════════════════

PROJECTS["realtime-chat"] = {

"core.il": """\
// core.il — Realtime Chat
project Relay:
  version: 0.1.0
  stack: react + node + socket.io + redis + postgres
  pattern: websocket + REST
  auth: jwt

  domains:
    - identity
    - rooms
    - messaging

  rules:
    - all models get id (uuid pk), created_at
    - all REST errors return { code, message }
    - jwt required for all connections
    - max message length: 4000 chars
    - all times in UTC ISO 8601
""",

"identity.il": """\
// identity.il — Users and presence
domain identity:

model User:
  id (uuid, pk)
  username (str, required, unique)
  display_name (str, required)
  avatar (str, optional)
  bio (str, optional)

  @level: low
  status (str, default "offline", indexed)
  last_seen (datetime, optional)

feature Auth:
  route POST /auth/register:
    auth: public
    input: username, display_name, password, avatar?
    action: create User
    returns: { token, user }
    error: if username taken -> 409

  route POST /auth/login:
    auth: public
    input: username, password
    action: verify, issue jwt
    returns: { token, user }

feature Presence:
  event connect:
    action: set User.status = online in redis, broadcast presence_update to rooms user is in

  event disconnect:
    action: set User.status = offline, update last_seen, broadcast presence_update

  @level: mid
  config PresenceStore:
    backend: redis hash per user
    ttl: 30s heartbeat
    reason: redis handles high-frequency presence updates without hitting postgres
""",

"rooms.il": """\
// rooms.il — Room and membership management
domain rooms:

model Room:
  id (uuid, pk)
  name (str, required)
  description (str, optional)
  type (str, default "public")
  created_by: @identity/User!
  max_members (int, default 500)

model Membership:
  id (uuid, pk)
  room -> Room
  user: @identity/User!
  role (str, default "member")
  joined_at (datetime, default now)
  last_read_at (datetime, optional)

feature Rooms:
  route GET /rooms:
    action: fetch public Rooms + Rooms user is member of
    returns: Room[]

  route POST /rooms:
    input: name, description?, type?
    action: create Room, create Membership with role=owner
    returns: Room

  route GET /rooms/:id:
    action: fetch Room with member count and user's membership status
    returns: { room: Room, member_count, is_member, role }

  route DELETE /rooms/:id:
    action: delete Room if current user is owner
    error: if not owner -> 403

feature Members:
  route GET /rooms/:id/members:
    action: fetch Members with User details and presence status
    returns: { user: User, role, joined_at, status }[]

  route POST /rooms/:id/join:
    action: create Membership for current user
    error: if already member -> 409
    error: if room full -> 403 "Room is full"

  route POST /rooms/:id/leave:
    action: delete Membership for current user
    error: if owner -> 400 "Owner cannot leave — transfer ownership first"

rules:
  - private rooms require invite to join
  - owners cannot leave their own room
  - only owner or admin can delete room
  - member count cached in redis, updated on join/leave
""",

"messaging.il": """\
// messaging.il — Messages and real-time delivery
domain messaging:

model Message:
  id (uuid, pk)
  content (str, required)
  room: @rooms/Room!
  sender: @identity/User!
  type (str, default "text")
  edited (bool, default false)
  edited_at (datetime, optional)
  deleted (bool, default false)

  @level: low
  reply_to (uuid, optional, indexed)

model Reaction:
  id (uuid, pk)
  message -> Message
  user: @identity/User!
  emoji (str, required)

feature Messaging:
  route GET /rooms/:id/messages:
    input: before? (cursor uuid), limit? (default 50)
    action: fetch Messages cursor-paginated, newest first, exclude deleted
    returns: { messages: Message[], has_more, next_cursor }

  event send_message:
    input: room_id, content, type?, reply_to?
    action: validate membership, persist Message, broadcast to room
    broadcast: new_message to room members
    error: if not member -> disconnect with 403
    error: if content too long -> emit error event

  event edit_message:
    input: message_id, content
    action: update Message if sender = current user, set edited=true
    broadcast: message_edited to room

  event delete_message:
    input: message_id
    action: soft delete if sender = current user or user is room admin
    broadcast: message_deleted to room

  event typing:
    input: room_id
    action: emit typing_start to room (exclude sender), auto-clear after 3s
    broadcast: typing_update to room

  event react:
    input: message_id, emoji
    action: toggle Reaction for current user on message
    broadcast: reaction_updated to room

  @level: mid
  config MessageDelivery:
    strategy: write-through — persist to postgres then emit socket event
    cache: last 100 messages per room in redis list
    reason: new joiners get instant history from redis before postgres query completes

  @level: low
  config CursorPagination:
    strategy: keyset pagination on (created_at, id)
    reason: offset pagination degrades on large message history
    index: composite (room_id, created_at DESC, id DESC)

rules:
  - users must be room members to send or read messages
  - deleted messages show as [deleted] to others, hidden to sender
  - reactions are toggled (add if absent, remove if present)
  - typing events are not persisted
  - message history loaded newest-first, paginated
""",

}

# ══════════════════════════════════════════════════════════════════════════════
# 4. CLI TOOL  —  low-level, no web, shows @level:low and @level:asm
#    Stack: rust
#    Shows: non-web target, low/asm levels, constraint directives
# ══════════════════════════════════════════════════════════════════════════════

PROJECTS["file-hasher-cli"] = {

"core.il": """\
// core.il — Fast File Hasher CLI tool
// Non-web project. Shows @level:low and @level:asm usage.
project Fhash:
  version: 0.1.0
  stack: rust
  pattern: CLI
  auth: none

  domains:
    - hasher
    - output

  rules:
    - all errors printed to stderr, exit code 1
    - all output is deterministic given same input
    - no heap allocation on the hot path
    - support stdin if no file argument given
""",

"hasher.il": """\
// hasher.il — Hashing engine
domain hasher:
  description: "Core hashing logic — performance critical"

model HashResult:
  algorithm (str, required)
  hex_digest (str, required)
  byte_count (int, required)
  duration_us (int, required)

@level: mid
feature Algorithms:
  config Supported:
    - sha256
    - sha512
    - blake3
    - md5
    - xxhash64

  config Selection:
    default: sha256
    flag: --algo (-a)
    error: if unknown algo -> print supported list, exit 1

@level: low
feature FileHashing:
  config BufferedRead:
    buffer_size: 65536
    strategy: read file in fixed chunks, update hasher incrementally
    constraint: single heap allocation for read buffer
    constraint: no mmap — portable across all targets

  config ParallelHashing:
    strategy: if multiple files given, hash concurrently using rayon thread pool
    threads: default to cpu count
    constraint: each thread gets its own hasher state — no locking on hot path

  @level: asm
  critical_path inner_hash_loop:
    @target: x86_64
    constraint: prefer AVX2 for blake3 and sha256
    constraint: align read buffer to 64 bytes for SIMD
    constraint: unroll 4x minimum

  @level: asm
  critical_path inner_hash_loop:
    @target: aarch64
    constraint: prefer NEON/SHA2 intrinsics
    constraint: align to 16 bytes

feature Verification:
  config CheckMode:
    flag: --check (-c)
    input: checksum file (sha256sum format)
    action: read expected digests, hash files, compare, report mismatches
    output: OK / FAILED per file, summary count
    exit_code: 0 if all pass, 1 if any fail
""",

"output.il": """\
// output.il — Output formatting
domain output:

@level: mid
feature Formatting:
  config Modes:
    default: "<hash>  <filename>"  // sha256sum compatible
    flag --json: structured JSON output
    flag --quiet (-q): hash only, no filename
    flag --progress (-p): show progress bar for large files (>10mb)

  config JSON:
    schema: { file, algorithm, digest, bytes, duration_ms }
    pretty: false by default, --pretty flag for indented

  config Progress:
    backend: indicatif crate
    update_rate: 20hz
    format: "[{bar:40}] {bytes}/{total_bytes} {bytes_per_sec} eta {eta}"

rules:
  - output format must be sha256sum-compatible by default
  - json output is always valid json even on error (error key set)
  - progress bar goes to stderr so stdout stays pipe-safe
  - zero exit code only if all operations succeeded
""",

}

# ══════════════════════════════════════════════════════════════════════════════
# 5. MULTI-TENANT SAAS  —  complex, billing, rbac, webhooks
#    Stack: next.js + fastapi + postgres + stripe
#    Shows: full multi-domain project, billing integration, complex rules
# ══════════════════════════════════════════════════════════════════════════════

PROJECTS["saas-starter"] = {

"core.il": """\
// core.il — Multi-tenant SaaS starter
project Launchpad:
  version: 0.1.0
  stack: next.js + fastapi + postgres + stripe + resend
  pattern: REST + webhooks
  auth: jwt + api_key

  domains:
    - identity
    - orgs
    - billing
    - api

  rules:
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message, request_id }
    - all mutations emit audit log entry
    - all endpoints require auth unless marked public
    - row-level security: users only access their org's data
    - api_key and jwt are interchangeable for authentication
    - request_id header echoed on every response
""",

"identity.il": """\
// identity.il — Users, auth, invites
domain identity:

model User:
  id (uuid, pk)
  email (str, required, unique)
  password (str, required, private)
  name (str, required)
  avatar (str, optional)
  email_verified (bool, default false)
  last_login (datetime, optional)

model Invite:
  id (uuid, pk)
  email (str, required)
  org: @orgs/Org!
  role (str, default "member")
  token (str, required, unique)
  invited_by: @identity/User!
  expires_at (datetime, required)
  accepted (bool, default false)

feature Auth:
  route POST /auth/register:
    auth: public
    input: email, password, name, invite_token?
    action: create User, send verification email, if invite_token accept Invite
    returns: { token, user }
    error: if email exists -> 409

  route POST /auth/login:
    auth: public
    input: email, password
    action: verify, update last_login, issue jwt
    returns: { token, user }
    error: if unverified -> 403 "Please verify your email"

  route POST /auth/verify-email:
    auth: public
    input: token
    action: verify email token, set email_verified = true
    returns: { ok: true }

  route POST /auth/forgot-password:
    auth: public
    input: email
    action: send reset email if user exists (always return 200 to prevent enumeration)
    returns: { ok: true }

  route POST /auth/reset-password:
    auth: public
    input: token, new_password
    action: verify reset token, update password, invalidate all sessions
    returns: { ok: true }

rules:
  - email verification required before org actions
  - password reset tokens expire after 1 hour
  - always return 200 on forgot-password (anti-enumeration)
  - bcrypt rounds: 12
""",

"orgs.il": """\
// orgs.il — Organizations, members, roles, invites
domain orgs:

model Org:
  id (uuid, pk)
  name (str, required)
  slug (str, required, unique)
  logo (str, optional)
  plan (str, default "free")
  owner: @identity/User!

model Member:
  id (uuid, pk)
  org -> Org
  user: @identity/User!
  role (str, default "member")
  joined_at (datetime, default now)

model AuditLog:
  id (uuid, pk)
  org -> Org
  actor: @identity/User?
  action (str, required)
  resource_type (str, optional)
  resource_id (uuid, optional)
  metadata (json, optional)
  ip (str, optional)

feature Orgs:
  route POST /orgs:
    input: name, slug?
    action: create Org, auto-generate slug from name if not provided, create Member with role=owner
    returns: Org
    error: if slug taken -> 409

  route GET /orgs/:slug:
    action: fetch Org with member count and current user's role
    returns: { org: Org, member_count, role }

  route PUT /orgs/:slug:
    input: name?, logo?
    guard: role = owner or admin
    action: update Org
    returns: Org

feature Members:
  route GET /orgs/:slug/members:
    action: fetch Members with User details
    returns: { user: User, role, joined_at }[]

  route POST /orgs/:slug/invites:
    guard: role = owner or admin
    input: email, role?
    action: create Invite, send invitation email
    returns: Invite
    error: if already member -> 409

  route DELETE /orgs/:slug/members/:user_id:
    guard: role = owner or admin
    action: remove Member
    error: if removing owner -> 400 "Cannot remove org owner"

  route PUT /orgs/:slug/members/:user_id:
    guard: role = owner
    input: role
    action: update Member role
    error: if demoting last owner -> 400

rules:
  - every org action is audit logged
  - only owners can delete the org
  - last owner cannot be removed or demoted
  - slugs are lowercase alphanumeric + hyphens
  - members can only see their own org's data
""",

"billing.il": """\
// billing.il — Stripe billing, subscriptions, usage
domain billing:

model Subscription:
  id (uuid, pk)
  org: @orgs/Org!
  stripe_customer_id (str, required, unique)
  stripe_subscription_id (str, optional, unique)
  plan (str, required)
  status (str, default "trialing")
  current_period_end (datetime, optional)
  cancel_at_period_end (bool, default false)

model Invoice:
  id (uuid, pk)
  org: @orgs/Org!
  stripe_invoice_id (str, required, unique)
  amount_cents (int, required)
  currency (str, default "usd")
  status (str, required)
  pdf_url (str, optional)
  paid_at (datetime, optional)

feature Plans:
  route GET /billing/plans:
    auth: public
    action: return plan definitions with features and pricing
    returns: { id, name, price_monthly, price_yearly, features, limits }[]

  route GET /orgs/:slug/billing:
    guard: role = owner or admin
    action: fetch Subscription with current Invoice list
    returns: { subscription: Subscription, invoices: Invoice[] }

feature Checkout:
  route POST /orgs/:slug/billing/checkout:
    guard: role = owner
    input: plan, interval (monthly|yearly)
    action: create or retrieve Stripe customer, create checkout session
    returns: { checkout_url }

  route POST /orgs/:slug/billing/portal:
    guard: role = owner
    action: create Stripe billing portal session
    returns: { portal_url }

  route POST /orgs/:slug/billing/cancel:
    guard: role = owner
    action: set cancel_at_period_end = true on Stripe subscription
    returns: { cancels_at }

feature Webhooks:
  route POST /webhooks/stripe:
    auth: stripe_signature
    action: handle Stripe events
    events:
      - checkout.session.completed -> activate subscription
      - customer.subscription.updated -> sync plan and status
      - customer.subscription.deleted -> downgrade to free
      - invoice.payment_succeeded -> record Invoice
      - invoice.payment_failed -> email owner, set status=past_due

  @level: mid
  config WebhookIdempotency:
    strategy: store processed stripe_event_ids in postgres
    on_duplicate: return 200 immediately
    reason: Stripe may deliver webhooks more than once

rules:
  - only org owners can manage billing
  - webhook endpoint verifies Stripe signature before processing
  - failed payments trigger email notification, not immediate suspension
  - all billing amounts in cents
  - free plan has no Stripe subscription record
""",

"api.il": """\
// api.il — Public API, API keys, rate limiting
domain api:

model ApiKey:
  id (uuid, pk)
  org: @orgs/Org!
  created_by: @identity/User!
  name (str, required)
  key_hash (str, required, private)
  key_prefix (str, required)
  last_used_at (datetime, optional)
  expires_at (datetime, optional)
  active (bool, default true)

model RateLimit:
  id (uuid, pk)
  org: @orgs/Org!
  endpoint (str, required)
  window_seconds (int, required)
  max_requests (int, required)

feature Keys:
  route GET /orgs/:slug/api-keys:
    guard: role = owner or admin
    action: fetch ApiKeys (never return raw key, only prefix + metadata)
    returns: { id, name, key_prefix, created_at, last_used_at, expires_at, active }[]

  route POST /orgs/:slug/api-keys:
    guard: role = owner or admin
    input: name, expires_at?
    action: generate key (prefix_randomsuffix), store bcrypt hash, return raw key ONCE
    returns: { id, name, key, key_prefix }
    note: raw key is shown only on creation — store it securely

  route DELETE /orgs/:slug/api-keys/:id:
    guard: role = owner or admin
    action: deactivate ApiKey
    returns: { ok: true }

  @level: mid
  config KeyFormat:
    format: "lp_<env>_<32 random chars>"
    example: "lp_live_a8f3k2m9..."
    prefix_stored: first 12 chars for identification
    hash_stored: bcrypt of full key

  @level: low
  config RateLimiting:
    backend: redis sliding window
    strategy: ZADD with score=timestamp, ZREMRANGEBYSCORE to prune, ZCARD to count
    granularity: per org + per endpoint
    constraint: all operations in single MULTI/EXEC block

rules:
  - raw API key shown only once at creation
  - only key hash stored in database
  - rate limits enforced in redis before hitting application
  - expired or inactive keys return 401
  - last_used_at updated asynchronously to avoid write on every request
""",

}

# ─── CLI ──────────────────────────────────────────────────────────────────────

DESCRIPTIONS = {
    "url-shortener":    "URL shortener with analytics         (fastapi + postgres + redis)",
    "expense-tracker":  "Personal expense tracker with export (react + express + sqlite)",
    "realtime-chat":    "Realtime chat with presence          (react + node + socket.io + redis)",
    "file-hasher-cli":  "Fast file hashing CLI tool           (rust, shows @level:asm)",
    "saas-starter":     "Multi-tenant SaaS with billing       (next.js + fastapi + stripe)",
}

def write_project(name: str, base_dir: str = "./examples"):
    if name not in PROJECTS:
        print(f"Unknown project: {name}")
        print(f"Available: {', '.join(PROJECTS)}")
        return

    project = PROJECTS[name]
    out = Path(base_dir) / name
    out.mkdir(parents=True, exist_ok=True)

    for filename, content in project.items():
        (out / filename).write_text(content, encoding="utf-8")

    print(f"✓  {name:20}  →  {out.resolve()}/")
    print(f"   {len(project)} files: {', '.join(project.keys())}")

def main():
    args = sys.argv[1:]

    if not args:
        print("\nIntentLang — Example Projects\n")
        print("Available projects:\n")
        for name, desc in DESCRIPTIONS.items():
            print(f"  {name:<22}  {desc}")
        print()
        print("Usage:")
        print("  python examples.py <name>        write one project")
        print("  python examples.py all           write all projects")
        print()
        print("Then load into IntentLang:")
        print("  python intentlang.py")
        print("  il› load ./examples/<name>")
        print()
        return

    if args[0] == "all":
        print()
        for name in PROJECTS:
            write_project(name)
        print(f"\nAll {len(PROJECTS)} projects written to ./examples/")
        print("\nLoad one into IntentLang:")
        print("  python intentlang.py")
        print("  il› load ./examples/url-shortener")
    else:
        name = args[0]
        print()
        write_project(name)
        print(f"\nLoad it into IntentLang:")
        print(f"  python intentlang.py")
        print(f"  il› load ./examples/{name}")

    print()

if __name__ == "__main__":
    main()
