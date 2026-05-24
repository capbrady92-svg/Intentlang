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
