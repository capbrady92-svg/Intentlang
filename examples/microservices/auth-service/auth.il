// auth-service/auth.il — Auth microservice domain + published interface
//
// Publishes a typed interface consumed by api-gateway and any other service.
// Run: il› publish auth

domain auth:
  description: "Token issuance, validation, and user identity"

interface:
  version: 1.0.0

  expose:
    - model TokenPair
    - model UserIdentity
    - feature TokenAPI

  hide:
    - model RefreshToken
    - model BlacklistedToken
    - field UserIdentity.internal_flags

model UserIdentity:
  id (uuid, pk)
  email (str, required, unique)
  handle (str, required, unique)
  role (str, default "user")
  verified (bool, default false)
  internal_flags (int, default 0, private)

model TokenPair:
  access_token (str, required)
  refresh_token (str, required)
  expires_in (int, required)
  token_type (str, default "Bearer")

model RefreshToken:
  id (uuid, pk)
  user -> UserIdentity
  token_hash (str, required, private)
  expires_at (datetime, required)
  rotated (bool, default false)

model BlacklistedToken:
  id (uuid, pk)
  jti (str, required, unique, indexed)
  expires_at (datetime, required)

feature TokenAPI:
  route POST /auth/token:
    auth: public
    input: email, password
    action: verify credentials, issue TokenPair, store RefreshToken hash
    returns: TokenPair
    error: if invalid -> 401

  route POST /auth/token/refresh:
    auth: public
    input: refresh_token
    action: validate refresh token, rotate it, issue new TokenPair
    returns: TokenPair
    error: if expired -> 401 "Refresh token expired"
    error: if rotated -> 401 "Refresh token already used"

  route POST /auth/token/revoke:
    input: token
    action: blacklist the token JTI
    returns: { ok: true }

  route GET /auth/validate:
    input: token (header: Authorization)
    action: validate JWT signature and expiry, check not blacklisted
    returns: { valid: bool, user: UserIdentity }
    note: this route is called by api-gateway on every request — keep it fast

  @level: low
  config TokenValidation:
    strategy: check blacklist in redis before postgres
    cache_ttl: match token expiry
    reason: /auth/validate is on the hot path — must be sub-millisecond

rules:
  - refresh tokens are rotated on every use (one-time use)
  - blacklisted JTIs cached in redis for duration of token lifetime
  - access tokens expire in 15 minutes
  - refresh tokens expire in 7 days
  - internal_flags never exposed outside this service
