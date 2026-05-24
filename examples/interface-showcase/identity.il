// identity.il — Identity domain with a published interface
//
// This domain publishes a typed interface so other projects can:
//   1. Import the schema:  imports: identity: ../this-project/intent
//   2. Use the TypeScript client:  intentlang_output/interface/identity/identity.client.ts
//   3. Use the Python client:      intentlang_output/interface/identity/identity_client.py
//   4. Browse the OpenAPI spec:    intentlang_output/interface/identity/identity.openapi.json
//
// Run: il› publish identity

domain identity:
  description: "User identity, auth, and profile management"

interface:
  version: 2.1.0

  expose:
    - model User
    - model Profile
    - feature Auth
    - feature Users

  hide:
    - model PasswordReset
    - model AuditEntry
    - field User.password_hash
    - field User.mfa_secret

  breaking_changes:
    - User.username field renamed to User.handle (v1.x -> v2.0)
    - POST /auth/login now returns { token, user } instead of just token (v2.0 -> v2.1)

  deprecated:
    - route GET /auth/profile (use GET /users/me instead, removed in v3.0)
    - field User.legacy_id (will be removed in v3.0)

// ── Models ────────────────────────────────────────────────────────────────────

model User:
  id (uuid, pk)
  handle (str, required, unique, indexed)
  email (str, required, unique)
  password_hash (str, required, private)
  mfa_secret (str, optional, private)
  role (str, default "user")
  verified (bool, default false)
  legacy_id (str, optional)

model Profile:
  id (uuid, pk)
  user -> User
  display_name (str, required)
  avatar (str, optional)
  bio (str, optional)
  location (str, optional)
  website (str, optional)

model PasswordReset:
  id (uuid, pk)
  user -> User
  token (str, required, unique, private)
  expires_at (datetime, required)
  used (bool, default false)

model AuditEntry:
  id (uuid, pk)
  user -> User
  action (str, required)
  ip (str, optional)
  user_agent (str, optional)

// ── Features ──────────────────────────────────────────────────────────────────

feature Auth:
  route POST /auth/register:
    auth: public
    input: handle, email, password, display_name?
    action: validate handle unique, hash password, create User and Profile, send verification email
    returns: { token, user }
    error: if handle taken -> 409 "Handle already in use"
    error: if email taken -> 409 "Email already registered"

  route POST /auth/login:
    auth: public
    input: email, password
    action: verify credentials, record audit entry, issue jwt
    returns: { token, user }
    error: if invalid -> 401 "Invalid credentials"
    error: if unverified -> 403 "Please verify your email first"

  route POST /auth/verify-email:
    auth: public
    input: token (str, required)
    action: verify token, set User.verified = true
    returns: { ok: true }

  route POST /auth/forgot-password:
    auth: public
    input: email
    action: create PasswordReset token, send reset email
    returns: { ok: true }
    note: always returns 200 regardless of whether email exists (prevents enumeration)

  route POST /auth/reset-password:
    auth: public
    input: token, new_password
    action: verify PasswordReset token not used/expired, update password hash, mark token used
    returns: { ok: true }
    error: if expired -> 400 "Reset token expired"
    error: if already used -> 400 "Reset token already used"

  route POST /auth/logout:
    action: invalidate current session token
    returns: { ok: true }

feature Users:
  route GET /users/me:
    action: return current User with Profile
    returns: { user: User, profile: Profile }

  route PUT /users/me:
    input: display_name?, bio?, location?, website?, avatar?
    action: update Profile for current user
    returns: Profile

  route GET /users/:handle:
    auth: public
    action: fetch User and Profile by handle
    returns: { user: User, profile: Profile }
    error: if not found -> 404

  route PUT /users/me/handle:
    input: handle (str, required)
    action: update User.handle, validate uniqueness
    returns: User
    error: if taken -> 409

rules:
  - password minimum 8 characters
  - handles are lowercase alphanumeric + underscores only, 3-30 chars
  - audit log all auth events (login, logout, password change)
  - mfa_secret and password_hash never appear in any API response
