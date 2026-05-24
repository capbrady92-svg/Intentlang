// hasher.il — Hashing engine
domain hasher:
  description: "Core hashing logic — performance critical"

model HashResult:
  algorithm (str, required)
  hex_digest (str, required)
  byte_count (int, required)
  duration_us (int, required)

@level: mid
feature Algorithms:
  config Supported:
    - sha256
    - sha512
    - blake3
    - md5
    - xxhash64

  config Selection:
    default: sha256
    flag: --algo (-a)
    error: if unknown algo -> print supported list, exit 1

@level: low
feature FileHashing:
  config BufferedRead:
    buffer_size: 65536
    strategy: read file in fixed chunks, update hasher incrementally
    constraint: single heap allocation for read buffer
    constraint: no mmap — portable across all targets

  config ParallelHashing:
    strategy: if multiple files given, hash concurrently using rayon thread pool
    threads: default to cpu count
    constraint: each thread gets its own hasher state — no locking on hot path

  @level: asm
  critical_path inner_hash_loop:
    @target: x86_64
    constraint: prefer AVX2 for blake3 and sha256
    constraint: align read buffer to 64 bytes for SIMD
    constraint: unroll 4x minimum

  @level: asm
  critical_path inner_hash_loop:
    @target: aarch64
    constraint: prefer NEON/SHA2 intrinsics
    constraint: align to 16 bytes

feature Verification:
  config CheckMode:
    flag: --check (-c)
    input: checksum file (sha256sum format)
    action: read expected digests, hash files, compare, report mismatches
    output: OK / FAILED per file, summary count
    exit_code: 0 if all pass, 1 if any fail
