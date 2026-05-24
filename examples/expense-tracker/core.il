// core.il — Expense Tracker
project Ledger:
  version: 0.1.0
  stack: react + express + sqlite
  pattern: REST
  auth: jwt

  domains:
    - users
    - expenses
    - reports

  rules:
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message }
    - users can only access their own data
    - tokens expire after 30d
    - all monetary values stored as integers (cents)
