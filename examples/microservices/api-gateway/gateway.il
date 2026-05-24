// api-gateway/gateway.il — Gateway routing and middleware
//
// Shows: consuming @auth/UserIdentity from imported auth-service interface

domain gateway:
  description: "Request routing, auth middleware, rate limiting"

model RequestLog:
  id (uuid, pk)
  user: @auth/UserIdentity?
  method (str, required)
  path (str, required)
  status (int, required)
  duration_ms (int, required)
  ip (str, required)

feature Middleware:
  config AuthMiddleware:
    action: extract Bearer token, call auth-service GET /auth/validate
    on_valid: attach UserIdentity to request context
    on_invalid: return 401
    cache: cache valid tokens for 30s to reduce auth-service calls
    reason: every request hits this middleware — must be fast

  config RateLimiting:
    backend: redis sliding window
    key: user_id if authenticated, ip if not
    limit_default: 200/minute
    limit_search: 30/minute
    limit_write: 60/minute

  config RequestLogging:
    action: async log all requests to RequestLog table
    exclude: /health, /metrics
    reason: async so it never blocks request processing

  route GET /health:
    auth: public
    action: check db connection, redis connection, auth-service reachability
    returns: { status, services: { db, redis, auth } }

  route GET /metrics:
    auth: internal
    action: return prometheus metrics
    returns: prometheus text format
