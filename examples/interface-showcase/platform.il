// platform.il — Infrastructure with preserve rules
//
// Shows: preserve: block protecting migrations and env files

domain platform:

// ── Preserve Rules ────────────────────────────────────────────────────────────
// These files will NEVER be overwritten by transpilation, even if regenerated.
// Remove a pattern here to allow regeneration.

preserve:
  - migrations/*
  - .env
  - .env.local
  - .env.production
  - backend/custom/*
  - scripts/seed_data.py

@level: low
config Database:
  engine: postgres 15
  pool_size: 20
  max_overflow: 10
  statement_timeout: 30s
  idle_timeout: 600s

@level: mid
config Cache:
  engine: redis 7
  strategy: lru
  max_memory: 256mb
  eviction: allkeys-lru
  key_prefix: showcase:

config RateLimit:
  default: 120/minute/ip
  auth_endpoints: 15/minute/ip
  search: 30/minute/user
  reason: tighter limits on auth to prevent brute force

environment dev:
  database: localhost:5432/showcase_dev
  cache: localhost:6379
  email: console
  debug: true

environment staging:
  database: rds.staging/showcase
  cache: elasticache.staging
  email: ses

environment prod:
  database: rds.prod/showcase + read_replica
  cache: elasticache.prod
  email: ses
  cdn: cloudfront
