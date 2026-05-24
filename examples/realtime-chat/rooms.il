// rooms.il — Room and membership management
domain rooms:

model Room:
  id (uuid, pk)
  name (str, required)
  description (str, optional)
  type (str, default "public")
  created_by: @identity/User!
  max_members (int, default 500)

model Membership:
  id (uuid, pk)
  room -> Room
  user: @identity/User!
  role (str, default "member")
  joined_at (datetime, default now)
  last_read_at (datetime, optional)

feature Rooms:
  route GET /rooms:
    action: fetch public Rooms + Rooms user is member of
    returns: Room[]

  route POST /rooms:
    input: name, description?, type?
    action: create Room, create Membership with role=owner
    returns: Room

  route GET /rooms/:id:
    action: fetch Room with member count and user's membership status
    returns: { room: Room, member_count, is_member, role }

  route DELETE /rooms/:id:
    action: delete Room if current user is owner
    error: if not owner -> 403

feature Members:
  route GET /rooms/:id/members:
    action: fetch Members with User details and presence status
    returns: { user: User, role, joined_at, status }[]

  route POST /rooms/:id/join:
    action: create Membership for current user
    error: if already member -> 409
    error: if room full -> 403 "Room is full"

  route POST /rooms/:id/leave:
    action: delete Membership for current user
    error: if owner -> 400 "Owner cannot leave — transfer ownership first"

rules:
  - private rooms require invite to join
  - owners cannot leave their own room
  - only owner or admin can delete room
  - member count cached in redis, updated on join/leave
