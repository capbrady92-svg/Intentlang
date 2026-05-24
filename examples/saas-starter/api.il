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
