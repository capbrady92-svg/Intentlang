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
