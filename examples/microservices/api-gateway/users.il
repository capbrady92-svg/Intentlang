// api-gateway/users.il — User profiles (wraps auth-service identity)
//
// Shows: extending an imported interface with local data

domain users:
  description: "User profiles and preferences, built on top of auth-service identity"

model UserProfile:
  id (uuid, pk)
  auth_user_id: @auth/UserIdentity!
  display_name (str, required)
  avatar (str, optional)
  bio (str, optional)
  location (str, optional)
  website (str, optional)

model UserPreferences:
  id (uuid, pk)
  user -> UserProfile
  theme (str, default "system")
  email_notifications (bool, default true)
  timezone (str, default "UTC")

feature Profiles:
  route GET /users/me:
    action: fetch UserProfile for current auth user, merge with @auth/UserIdentity
    returns: { identity: UserIdentity, profile: UserProfile, preferences: UserPreferences }

  route PUT /users/me:
    input: display_name?, avatar?, bio?, location?, website?
    action: update UserProfile
    returns: UserProfile

  route GET /users/:handle:
    auth: public
    action: fetch public UserProfile by handle (handle resolved via auth-service)
    returns: { handle, display_name, avatar, bio }
    error: if not found -> 404

feature Preferences:
  route GET /users/me/preferences:
    action: fetch UserPreferences
    returns: UserPreferences

  route PUT /users/me/preferences:
    input: theme?, email_notifications?, timezone?
    action: update UserPreferences
    returns: UserPreferences
