// api-gateway/core.il — API gateway consuming auth-service interface
//
// imports: pulls the auth-service interface from a local path.
// In production, swap for: auth: github.com/myorg/auth-service/intent@^1.0
project APIGateway:
  version: 1.0.0
  stack: python + fastapi + postgres
  pattern: REST
  auth: jwt

  domains:
    - gateway
    - users
    - content

  imports:
    auth: ./auth-service

  rules:
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message, request_id }
    - all endpoints validate token via @auth/TokenAPI.GET /auth/validate
    - rate limit: 200/minute/user
