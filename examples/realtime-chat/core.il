// core.il — Realtime Chat
project Relay:
  version: 0.1.0
  stack: react + node + socket.io + redis + postgres
  pattern: websocket + REST
  auth: jwt

  domains:
    - identity
    - rooms
    - messaging

  rules:
    - all models get id (uuid pk), created_at
    - all REST errors return { code, message }
    - jwt required for all connections
    - max message length: 4000 chars
    - all times in UTC ISO 8601
