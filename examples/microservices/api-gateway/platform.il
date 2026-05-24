// api-gateway/platform.il — Gateway infrastructure with preserve rules

domain platform:

preserve:
  - migrations/*
  - .env
  - .env.*
  - config/secrets.yaml
  - scripts/*

@level: low
config Database:
  engine: postgres 15
  pool_size: 15
  statement_timeout: 20s

config Redis:
  host: localhost
  port: 6379
  db: 0
  key_prefix: gateway:

config AuthService:
  base_url: http://auth-service:8001
  timeout: 5s
  retry: 2
  reason: auth-service must be reachable — circuit break after 3 consecutive failures

environment dev:
  database: localhost:5432/gateway_dev
  redis: localhost:6379
  auth_service: http://localhost:8001
  debug: true

environment prod:
  database: rds.prod/gateway + read_replica
  redis: elasticache.prod
  auth_service: http://auth-service.internal:8001
