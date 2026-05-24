// output.il — Output formatting
domain output:

@level: mid
feature Formatting:
  config Modes:
    default: "<hash>  <filename>"  // sha256sum compatible
    flag --json: structured JSON output
    flag --quiet (-q): hash only, no filename
    flag --progress (-p): show progress bar for large files (>10mb)

  config JSON:
    schema: { file, algorithm, digest, bytes, duration_ms }
    pretty: false by default, --pretty flag for indented

  config Progress:
    backend: indicatif crate
    update_rate: 20hz
    format: "[{bar:40}] {bytes}/{total_bytes} {bytes_per_sec} eta {eta}"

rules:
  - output format must be sha256sum-compatible by default
  - json output is always valid json even on error (error key set)
  - progress bar goes to stderr so stdout stays pipe-safe
  - zero exit code only if all operations succeeded
