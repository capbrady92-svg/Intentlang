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
