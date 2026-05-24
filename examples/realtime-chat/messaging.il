// messaging.il — Messages and real-time delivery
domain messaging:

model Message:
  id (uuid, pk)
  content (str, required)
  room: @rooms/Room!
  sender: @identity/User!
  type (str, default "text")
  edited (bool, default false)
  edited_at (datetime, optional)
  deleted (bool, default false)

  @level: low
  reply_to (uuid, optional, indexed)

model Reaction:
  id (uuid, pk)
  message -> Message
  user: @identity/User!
  emoji (str, required)

feature Messaging:
  route GET /rooms/:id/messages:
    input: before? (cursor uuid), limit? (default 50)
    action: fetch Messages cursor-paginated, newest first, exclude deleted
    returns: { messages: Message[], has_more, next_cursor }

  event send_message:
    input: room_id, content, type?, reply_to?
    action: validate membership, persist Message, broadcast to room
    broadcast: new_message to room members
    error: if not member -> disconnect with 403
    error: if content too long -> emit error event

  event edit_message:
    input: message_id, content
    action: update Message if sender = current user, set edited=true
    broadcast: message_edited to room

  event delete_message:
    input: message_id
    action: soft delete if sender = current user or user is room admin
    broadcast: message_deleted to room

  event typing:
    input: room_id
    action: emit typing_start to room (exclude sender), auto-clear after 3s
    broadcast: typing_update to room

  event react:
    input: message_id, emoji
    action: toggle Reaction for current user on message
    broadcast: reaction_updated to room

  @level: mid
  config MessageDelivery:
    strategy: write-through — persist to postgres then emit socket event
    cache: last 100 messages per room in redis list
    reason: new joiners get instant history from redis before postgres query completes

  @level: low
  config CursorPagination:
    strategy: keyset pagination on (created_at, id)
    reason: offset pagination degrades on large message history
    index: composite (room_id, created_at DESC, id DESC)

rules:
  - users must be room members to send or read messages
  - deleted messages show as [deleted] to others, hidden to sender
  - reactions are toggled (add if absent, remove if present)
  - typing events are not persisted
  - message history loaded newest-first, paginated
