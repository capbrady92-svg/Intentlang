// core.il — Interface Showcase
// Demonstrates: interface: blocks, expose:/hide:, preserve:, breaking_changes:
//
// After loading, try:
//   il› query show interfaces
//   il› query show compat
//   il› publish identity
//   il› publish notifications
//   il› transpile identity.il
project Showcase:
  version: 1.0.0
  stack: fastapi + postgres
  pattern: REST
  auth: jwt

  domains:
    - identity
    - notifications
    - content

  rules:
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message, request_id }
    - all endpoints require auth unless marked public
    - tokens expire after 24h
