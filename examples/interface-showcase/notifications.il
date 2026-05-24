// notifications.il — Notifications domain with versioned interface
//
// Shows: interface with events exposed, deprecation notices
// Run: il› publish notifications

domain notifications:
  description: "In-app and email notification delivery"

interface:
  version: 1.3.0

  expose:
    - model Notification
    - feature Notifications
    - event notification_sent

  hide:
    - model NotificationTemplate
    - model DeliveryLog

  deprecated:
    - field Notification.read (use Notification.status instead, removed in v2.0)
    - route POST /notifications/mark-read (use PATCH /notifications/:id instead)

model Notification:
  id (uuid, pk)
  recipient -> User
  type (str, required)
  title (str, required)
  body (str, required)
  status (str, default "unread")
  read (bool, default false)
  action_url (str, optional)
  metadata (json, optional)
  sent_at (datetime, optional)

model NotificationTemplate:
  id (uuid, pk)
  type (str, required, unique)
  subject (str, required)
  body_template (str, required, private)
  channel (str, default "in_app")

model DeliveryLog:
  id (uuid, pk)
  notification -> Notification
  channel (str, required)
  status (str, required)
  error (str, optional)
  attempted_at (datetime, required)

feature Notifications:
  route GET /notifications:
    input: status? (unread|read|all, default unread), limit? (default 20), cursor?
    action: fetch Notifications for current user, cursor-paginated
    returns: { notifications: Notification[], unread_count, next_cursor }

  route PATCH /notifications/:id:
    input: status (read|archived)
    action: update Notification status
    returns: Notification
    error: if not owner -> 404

  route POST /notifications/mark-all-read:
    action: set status = read on all unread Notifications for current user
    returns: { updated: int }

  route DELETE /notifications/:id:
    action: delete Notification
    returns: { ok: true }

event notification_sent:
  payload: { notification_id, recipient_id, type, title }
  channel: websocket + webhook
  description: emitted when a new notification is delivered to a user

rules:
  - users can only read or delete their own notifications
  - unread_count cached in redis, invalidated on status change
  - notification delivery is always async, never blocks the originating request
  - templates are internal — never exposed via API
