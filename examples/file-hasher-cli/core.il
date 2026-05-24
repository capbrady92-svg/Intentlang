// core.il — Fast File Hasher CLI tool
// Non-web project. Shows @level:low and @level:asm usage.
project Fhash:
  version: 0.1.0
  stack: rust
  pattern: CLI
  auth: none

  domains:
    - hasher
    - output

  rules:
    - all errors printed to stderr, exit code 1
    - all output is deterministic given same input
    - no heap allocation on the hot path
    - support stdin if no file argument given
