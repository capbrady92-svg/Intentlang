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
