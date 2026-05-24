// core.il — Multi-tenant SaaS starter
project Launchpad:
  version: 0.1.0
  stack: next.js + fastapi + postgres + stripe + resend
  pattern: REST + webhooks
  auth: jwt + api_key

  domains:
    - identity
    - orgs
    - billing
    - api

  rules:
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message, request_id }
    - all mutations emit audit log entry
    - all endpoints require auth unless marked public
    - row-level security: users only access their org's data
    - api_key and jwt are interchangeable for authentication
    - request_id header echoed on every response
