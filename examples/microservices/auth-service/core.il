// auth-service/core.il — Standalone auth microservice
// This service PUBLISHES an interface that other services consume.
// Run: il› publish auth  to generate the SDK
project AuthService:
  version: 1.0.0
  stack: go + grpc + postgres
  pattern: gRPC + REST
  auth: internal

  domains:
    - auth

  rules:
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message }
    - internal service-to-service calls use mutual TLS
    - tokens are short-lived JWTs (15 min access, 7 day refresh)
