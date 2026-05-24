// core.il — URL Shortener
// Simple single-domain project. Good first IntentLang example.
project Snip:
  version: 0.1.0
  stack: fastapi + postgres + redis
  pattern: REST
  auth: api_key

  domains:
    - links

  rules:
    - all errors return { code, message }
    - all models get id (uuid pk), created_at
    - rate limit all endpoints: 60/minute/ip
    - api_key required unless endpoint marked public
