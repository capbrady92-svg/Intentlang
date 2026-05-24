#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  IntentLang v0.2  —  Terminal IDE                           ║
║  A structured multi-level intent language for AI coding     ║
╚══════════════════════════════════════════════════════════════╝

SETUP:
  pip install httpx rich prompt_toolkit

RUN:
  python intentlang.py

CONFIG (edit the block below):
  API_KEY   — your Anthropic / OpenAI / OpenRouter key
  MODEL     — which model to use
  API_BASE  — endpoint URL (Anthropic default)
"""

# ─── CONFIG ────────────────────────────────────────────────────────────────────
# Edit these to change providers, models, and behaviour.

API_KEY    = ""                                        # ← paste your key here
MODEL      = ""                # ← change model here
API_BASE   = ""   # ← change endpoint here
MAX_TOKENS = 8000
TEMPERATURE = 0.2

# Common model options:
MODELS = {
    # Anthropic
    "sonnet":       "claude-sonnet-4-20250514",
    "opus":         "claude-opus-4-20250514",
    "haiku":        "claude-haiku-4-5-20251001",
    # OpenAI  (set API_BASE = "https://api.openai.com/v1/chat/completions")
    "gpt4o":        "gpt-4o",
    "gpt4o-mini":   "gpt-4o-mini",
    # Google  (set API_BASE = "https://generativelanguage.googleapis.com/...")
    "gemini-pro":   "gemini-2.5-pro",
    "gemini-flash": "gemini-2.0-flash",
    # Local Ollama  (set API_BASE = "http://localhost:11434/api/chat")
    "llama3":       "llama3.1:70b",
    "deepseek":     "deepseek-coder-v2:16b",
}

OUTPUT_DIR = "./intentlang_output"   # where generated files are written
IL_DIR     = "./intent"              # where .il files are loaded from / saved to

# ───────────────────────────────────────────────────────────────────────────────

import os
import re
import sys
import json
import time
import shutil
import textwrap
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ─── DEPENDENCY CHECK ─────────────────────────────────────────────────────────

def check_deps():
    missing = []
    for pkg in ["httpx", "rich", "prompt_toolkit"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print(f"Install with:  pip install {' '.join(missing)}")
        sys.exit(1)

check_deps()

import httpx
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.spinner import Spinner
from rich import box
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style as PTStyle

console = Console()

# ─── PARSER ───────────────────────────────────────────────────────────────────

_uid_counter = 0

def make_uid(node_type, name, filename):
    global _uid_counter
    base = filename.replace(".il", "").replace("/", "-")
    label = name or str(_uid_counter := _uid_counter + 1)
    return f"{base}:{node_type}:{label}"

def parse_value(val: str):
    if val == "true":  return True
    if val == "false": return False
    try:               return int(val)
    except ValueError: pass
    try:               return float(val)
    except ValueError: pass
    if val.startswith("[") and val.endswith("]"):
        return [v.strip() for v in val[1:-1].split(",")]
    return val

def parse_line(content: str, line_num: int, errors: list, filename: str, level: str) -> Optional[dict]:
    # @target / @constraint
    if content.startswith("@target:"):
        return {"type": "directive", "key": "target", "value": content[8:].strip(), "line": line_num, "level": level}
    if re.match(r"^@?constraint:", content):
        return {"type": "constraint", "value": re.sub(r"^@?constraint:\s*", "", content), "line": line_num, "level": level}

    # cross-file xref:  key: @domain/Type[!?]
    m = re.match(r"^([\w.]+)\s*:\s*@([\w]+)/([\w]+)([!?]?)\s*(.*)$", content)
    if m:
        return {"type": "xref_property", "key": m[1], "domain": m[2], "target": m[3],
                "strictness": m[4], "rest": m[5].strip(), "line": line_num, "level": level, "parent_uid": None}

    # block declarations
    m = re.match(r"^(app|service|module|feature|model|route|event|state|component|page|api|auth|db|domain|project|platform|critical_path|inline)\s+([\w./]+)\s*:?$", content)
    if m:
        uid = make_uid(m[1], m[2], filename)
        return {"type": m[1], "name": m[2], "block": True, "children": [], "line": line_num, "uid": uid, "level": level, "filename": filename}

    # anonymous blocks
    m = re.match(r"^(rules?|config|schema|props|actions?|effects?|guards?|meta|environment|domains|dependencies)\s*:$", content)
    if m:
        uid = make_uid(m[1], f"anon_{line_num}", filename)
        return {"type": m[1], "block": True, "children": [], "line": line_num, "uid": uid, "level": level, "filename": filename}

    # route shorthand
    m = re.match(r"^route\s+(GET|POST|PUT|PATCH|DELETE|WS)\s+([\w/:]+)\s*:?$", content)
    if m:
        uid = make_uid("route", f"{m[1]}_{m[2]}", filename)
        return {"type": "route", "method": m[1], "path": m[2], "block": True, "children": [],
                "line": line_num, "uid": uid, "level": level, "filename": filename}

    # key: value
    m = re.match(r"^([\w.@]+)\s*:\s*(.+)$", content)
    if m:
        return {"type": "property", "key": m[1], "value": parse_value(m[2].strip()), "line": line_num, "level": level}

    # rule lines
    if content.startswith("-") or content.startswith("*"):
        return {"type": "rule", "value": content[1:].strip(), "line": line_num, "level": level}

    # field: name (type, modifiers...)
    m = re.match(r"^(\w+)\s*\(([^)]+)\)$", content)
    if m:
        uid = make_uid("field", m[1], filename)
        return {"type": "field", "name": m[1], "modifiers": [s.strip() for s in m[2].split(",")],
                "line": line_num, "uid": uid, "level": level, "filename": filename}

    # local relation: name -> Target
    m = re.match(r"^(\w+)\s*->\s*(\w+)$", content)
    if m:
        return {"type": "relation", "name": m[1], "target": m[2], "local": True, "line": line_num, "level": level}

    errors.append({"line": line_num, "message": f'Unrecognized: "{content}"'})
    return {"type": "unknown", "raw": content, "line": line_num, "level": level}

def parse_intent_lang(source: str, filename: str = "unnamed.il") -> dict:
    global _uid_counter
    _uid_counter = 0

    lines = source.split("\n")
    errors = []
    root = {"type": "root", "filename": filename, "children": [], "uid": f"root:{filename}"}
    stack = [{"node": root, "indent": -1}]
    current_level = "high"

    for line_num, raw in enumerate(lines, 1):
        trimmed = raw.strip()
        if not trimmed or trimmed.startswith("//"):
            continue

        if trimmed.startswith("@level:"):
            m = re.match(r"@level:\s*(high|mid|low|asm)", trimmed)
            if m:
                current_level = m[1]
            continue

        indent = len(raw) - len(raw.lstrip(" \t"))
        while len(stack) > 1 and stack[-1]["indent"] >= indent:
            stack.pop()
        parent = stack[-1]["node"]

        node = parse_line(trimmed, line_num, errors, filename, current_level)
        if node:
            parent.setdefault("children", []).append(node)
            node["parent_uid"] = parent.get("uid")
            if node.get("block"):
                stack.append({"node": node, "indent": indent})
            elif not node.get("block") and not node.get("uid"):
                # give leaf nodes a synthetic uid so IR can index them
                node["uid"] = f"{filename.replace('.il','')}:leaf:{line_num}"

    return {"ast": root, "errors": errors}

# ─── IR BUILDER ───────────────────────────────────────────────────────────────

def flatten_nodes(node: dict, ir: dict, filename: str):
    if not node:
        return
    if "uid" in node:
        ir["nodes"][node["uid"]] = dict(node)
        ir["by_type"].setdefault(node["type"], []).append(node["uid"])
        domain = filename.replace(".il", "")
        ir["domains"].setdefault(domain, []).append(node["uid"])
    for child in node.get("children", []):
        flatten_nodes(child, ir, filename)

def resolve_ref(domain: str, type_name: str, ir: dict) -> Optional[str]:
    for uid in ir["domains"].get(domain, []):
        n = ir["nodes"].get(uid, {})
        if n.get("name") == type_name:
            return uid
    return None

def build_ir(parsed_files: list) -> dict:
    ir = {
        "nodes": {}, "edges": [], "domains": {}, "by_type": {},
        "global_rules": [], "stack": None, "project_name": None, "files": []
    }

    for pf in parsed_files:
        ir["files"].append(pf["name"])
        flatten_nodes(pf["ast"], ir, pf["name"])

    for uid, node in ir["nodes"].items():
        if node["type"] == "xref_property":
            target_uid = resolve_ref(node["domain"], node["target"], ir)
            ir["edges"].append({
                "from": node.get("parent_uid") or uid,
                "to": target_uid or f"unresolved:{node['domain']}/{node['target']}",
                "type": "xref", "resolved": bool(target_uid),
                "key": node["key"], "strictness": node.get("strictness", "")
            })
        if node["type"] == "relation":
            ir["edges"].append({
                "from": node.get("parent_uid") or uid,
                "to": node["target"], "type": "relation", "name": node["name"]
            })

    for uid, n in ir["nodes"].items():
        if n["type"] in ("project", "app", "service") and not ir["project_name"]:
            ir["project_name"] = n.get("name")
        if n["type"] == "property" and n.get("key") == "stack" and not ir["stack"]:
            ir["stack"] = n.get("value")
        if n["type"] == "rule":
            parent = ir["nodes"].get(n.get("parent_uid", ""), {})
            if parent.get("type") in ("rules", "rule", "project", "app"):
                ir["global_rules"].append(n["value"])

    return ir

# ─── IR QUERY ENGINE ──────────────────────────────────────────────────────────

def query_ir(ir: dict, query: str) -> str:
    q = query.strip().lower()

    # list <type>
    m = re.match(r"^(show|list|get)\s+(models?|features?|routes?|events?|fields?|rules?|all)$", q)
    if m:
        type_map = {
            "model": "model", "models": "model", "feature": "feature", "features": "feature",
            "route": "route", "routes": "route", "event": "event", "events": "event",
            "field": "field", "fields": "field", "rule": "rule", "rules": "rule"
        }
        t = type_map.get(m[2])
        if t:
            uids = ir["by_type"].get(t, [])
            if not uids:
                return f"No {t}s found."
            return "\n".join(
                f'[@{ir["nodes"][uid].get("level","high")}] {ir["nodes"][uid]["type"]} '
                f'"{ir["nodes"][uid].get("name") or ir["nodes"][uid].get("value","")}" '
                f'({ir["nodes"][uid].get("filename","")}) uid:{uid}'
                for uid in uids
            )
        if m[2] == "all":
            return "\n".join(
                f'{uid} → {n["type"]}{" "+n["name"] if n.get("name") else ""}'
                for uid, n in ir["nodes"].items()
            )

    # deps of <name>
    m = re.match(r"^dep(?:endencies)? of\s+(\w+)$", q)
    if m:
        name = m[1]
        edges = [e for e in ir["edges"] if name in e["from"].lower()]
        if not edges:
            return f'No dependencies found for "{name}"'
        return "\n".join(
            f'{e["from"]} →[{e["type"]}]→ {e["to"]}{" ⚠ UNRESOLVED" if e.get("resolved") is False else ""}'
            for e in edges
        )

    # used by <name>
    m = re.match(r"^(?:used by|dependents of)\s+(\w+)$", q)
    if m:
        name = m[1]
        edges = [e for e in ir["edges"] if name in e["to"].lower()]
        if not edges:
            return f'Nothing depends on "{name}"'
        return "\n".join(f'{e["from"]} depends on {e["to"]} via [{e["type"]}]' for e in edges)

    # inspect <name>
    m = re.match(r"^inspect\s+(.+)$", q)
    if m:
        term = m[1].strip()
        if term in ir["nodes"]:
            return json.dumps(ir["nodes"][term], indent=2, default=str)
        matches = [(uid, n) for uid, n in ir["nodes"].items()
                   if term in (n.get("name") or "").lower() or term in uid.lower()]
        if not matches:
            return f'No node matching "{term}"'
        return "\n\n".join(f"uid: {uid}\n{json.dumps(n, indent=2, default=str)}" for uid, n in matches)

    # global rules
    if "global rule" in q or q == "rules":
        if not ir["global_rules"]:
            return "No global rules defined."
        return "\n".join(f"{i+1}. {r}" for i, r in enumerate(ir["global_rules"]))

    # stack
    if "stack" in q:
        return f'Stack: {ir["stack"] or "not defined"}\nProject: {ir["project_name"] or "unnamed"}\nFiles: {", ".join(ir["files"])}'

    # graph / edges
    if "edge" in q or "graph" in q:
        if not ir["edges"]:
            return "No edges."
        return "\n".join(
            f'{e["from"]} →[{e["type"]}{":"+e["key"] if e.get("key") else ""}]→ {e["to"]}'
            f'{" ⚠ UNRESOLVED" if e.get("resolved") is False else ""}'
            for e in ir["edges"]
        )

    # domains
    if "domain" in q:
        return "\n".join(f"{d}: {len(uids)} nodes" for d, uids in ir["domains"].items())

    # impact
    if q.startswith("impact"):
        name = re.sub(r"^impact (of )?", "", q).strip()
        direct = [e for e in ir["edges"] if name in e["to"].lower()]
        if not direct:
            return f'No dependents for "{name}"'
        indirect = set()
        for e in direct:
            for e2 in ir["edges"]:
                if e2["to"] == e["from"]:
                    indirect.add(e2["from"])
        lines = ["Direct dependents:"] + [f'  {e["from"]} [{e["type"]}]' for e in direct]
        if indirect:
            lines += ["\nIndirect (2nd-order):"] + [f"  {u}" for u in indirect]
        return "\n".join(lines)

    return "Unknown query. Try: list models, show global rules, deps of <name>, used by <name>, inspect <name>, impact of <name>, show graph, show stack, show domains"

def ir_context_summary(ir: dict) -> str:
    mc = len(ir["by_type"].get("model", []))
    fc = len(ir["by_type"].get("feature", []))
    rc = len(ir["by_type"].get("route", []))
    unresolved = [e for e in ir["edges"] if e.get("resolved") is False]
    rules_text = "\n".join(f"  - {r}" for r in ir["global_rules"])
    return (
        f'PROJECT: {ir["project_name"] or "unnamed"}\n'
        f'STACK: {ir["stack"] or "unspecified"}\n'
        f'FILES: {", ".join(ir["files"])}\n'
        f'NODES: {len(ir["nodes"])} total ({mc} models, {fc} features, {rc} routes)\n'
        f'EDGES: {len(ir["edges"])} ({len(unresolved)} unresolved)\n'
        f'GLOBAL RULES: {len(ir["global_rules"])}\n'
        f'{rules_text}'
    )

# ─── TRANSPILER ───────────────────────────────────────────────────────────────

def build_headers(api_key: str, api_base: str) -> dict:
    if "anthropic.com" in api_base:
        return {"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"}
    return {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

def build_body(system: str, user_prompt: str, api_base: str) -> dict:
    if "anthropic.com" in api_base:
        return {"model": MODEL, "max_tokens": MAX_TOKENS, "stream": True,
                "temperature": TEMPERATURE, "system": system,
                "messages": [{"role": "user", "content": user_prompt}]}
    return {"model": MODEL, "max_tokens": MAX_TOKENS, "stream": True,
            "temperature": TEMPERATURE,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user_prompt}]}

def parse_output_files(text: str) -> list:
    pattern = re.compile(r"// FILE: ([^\n]+)\n(.*?)(?=// FILE: |\Z)", re.DOTALL)
    files = [{"path": m[0].strip(), "content": m[1].strip()} for m in pattern.findall(text)]
    if not files and text.strip():
        files = [{"path": "output.txt", "content": text.strip()}]
    return files

def transpile_stream(parsed_files: list, ir: dict, target_file: str, api_key: str):
    """Generator that yields text chunks from the API stream."""
    ir_summary = ir_context_summary(ir)
    target_src = next((f["content"] for f in parsed_files if f["name"] == target_file), "")
    domain = target_file.replace(".il", "")
    domain_uids = ir["domains"].get(domain, [])

    referenced_domains = list(dict.fromkeys(
        e["to"].split(":")[0] for e in ir["edges"]
        if any(e["from"].startswith(domain + ":") for uid in domain_uids)
        and not e["to"].startswith("unresolved")
    ))
    referenced_domains = [d for d in referenced_domains if d != domain][:5]

    ref_context = ""
    for rd in referenced_domains:
        rf = next((f for f in parsed_files if f["name"] == rd + ".il"), None)
        if rf:
            ref_context += f"\n// REFERENCED: {rd}.il\n{rf['content']}"

    system = """You are the IntentLang transpiler. IntentLang (.il) is a structured multi-level intent language.

ABSTRACTION LEVELS:
- @level: high  → architecture, features, APIs, data models
- @level: mid   → algorithms, business logic, data transforms
- @level: low   → memory layout, performance, system calls, concurrency
- @level: asm   → register hints, instruction preferences, platform-specific

MULTI-FILE SYSTEM:
- @domain/Type  → cross-file reference resolved by IR
- @domain/Type! → strict (fail if unresolved)
- @domain/Type? → optional (emit graceful fallback)
- core.il global rules propagate to ALL generated code

OUTPUT FORMAT:
- Separate each file with: // FILE: path/to/file.ext
- Generate ALL files needed (models, routes, migrations, tests, config)
- No prose outside code comments
- Never edit generated files — .il is sole source of truth
- Match sophistication to @level"""

    user_prompt = f"""IR SUMMARY (full project):
{ir_summary}

TARGET: {target_file}
{target_src}
{f"REFERENCED FILES:{ref_context}" if ref_context else ""}

Generate complete implementation. Begin with first file immediately."""

    with httpx.Client(timeout=120) as client:
        with client.stream(
            "POST", API_BASE,
            headers=build_headers(api_key, API_BASE),
            json=build_body(system, user_prompt, API_BASE)
        ) as response:
            response.raise_for_status()
            buffer = ""
            for raw_chunk in response.iter_text():
                buffer += raw_chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        parsed = json.loads(data)
                        # Anthropic
                        if parsed.get("type") == "content_block_delta":
                            text = parsed.get("delta", {}).get("text", "")
                            if text:
                                yield text
                        # OpenAI
                        elif parsed.get("choices"):
                            text = parsed["choices"][0].get("delta", {}).get("content", "")
                            if text:
                                yield text
                    except json.JSONDecodeError:
                        pass

# ─── FILE I/O ─────────────────────────────────────────────────────────────────

EXAMPLE_PROJECT = {
    "core.il": """\
// core.il — Project root. Global rules propagate everywhere.
project TaskFlow:
  version: 0.1.0
  stack: react + fastapi + postgres
  pattern: REST
  auth: jwt

  domains:
    - identity
    - tasks
    - platform

  rules:
    - all endpoints require auth unless marked public
    - all models get id (uuid pk), created_at, updated_at
    - all errors return { code, message, trace_id }
    - audit log all mutations
    - passwords hashed with bcrypt rounds 12
    - tokens expire after 7d""",

    "identity.il": """\
// identity.il — Users, auth, sessions
domain identity:
  description: "User identity and authentication"

model User:
  id (uuid, pk)
  email (str, required, unique)
  password (str, required, private)
  name (str, required)
  role (str, default "member")
  avatar (str, optional)

model Session:
  id (uuid, pk)
  user -> User
  token (str, required, unique)
  expires_at (datetime, required)
  ip (str, optional)

feature Auth:
  route POST /auth/register:
    auth: public
    input: email, password, name
    action: create User
    returns: { token, user }
    error: if email exists -> 409 "Already registered"

  route POST /auth/login:
    auth: public
    input: email, password
    action: verify credentials, create Session
    returns: { token, user }
    error: if invalid -> 401 "Invalid credentials"

  route GET /auth/me:
    action: return current User
    returns: User""",

    "tasks.il": """\
// tasks.il — Task and project management
domain tasks:
  description: "Task and project management"

model Project:
  id (uuid, pk)
  name (str, required)
  description (str, optional)
  owner: @identity/User!
  members: @identity/User?

model Task:
  id (uuid, pk)
  title (str, required)
  body (str, optional)
  status (str, default "todo")
  priority (str, default "normal")
  project -> Project
  assignee: @identity/User?
  due_date (date, optional)

  @level: low
  search_vector (tsvector, indexed)

feature Projects:
  route GET /projects:
    action: fetch Projects where owner = current_user
    returns: Project[]

  route POST /projects:
    input: name, description?
    action: create Project, set owner = current_user
    returns: Project

feature Tasks:
  route GET /projects/:id/tasks:
    input: status?, priority?
    action: fetch Tasks for project
    returns: Task[]

  route POST /projects/:id/tasks:
    input: title, body?, priority?, assignee?, due_date?
    action: create Task
    returns: Task

  route PATCH /tasks/:id:
    input: title?, body?, status?, priority?, assignee?
    action: update Task
    returns: Task

  @level: mid
  feature Search:
    route GET /search:
      input: q (str, required), project_id?
      action: full-text search Tasks using search_vector
      algorithm: postgres tsvector + tsquery
      returns: Task[]

  rules:
    - only project members can create or edit tasks
    - only assignee or owner can close tasks""",

    "platform.il": """\
// platform.il — Infrastructure and low-level concerns
domain platform:

@level: low
config Database:
  engine: postgres 15
  pool_size: 20
  max_overflow: 10
  statement_timeout: 30s

  @level: asm
  critical_path connection_acquire:
    @target: x86_64-linux
    constraint: no blocking syscall on hot path
    constraint: prefer SO_REUSEPORT
    max_latency_us: 500

@level: mid
config Cache:
  engine: redis 7
  strategy: lru
  max_memory: 512mb

config RateLimit:
  default: 100/minute/ip
  auth_endpoints: 10/minute/ip

environment dev:
  database: localhost:5432/taskflow_dev
  cache: localhost:6379
  debug: true

environment prod:
  database: rds.prod/taskflow + read_replica
  cache: elasticache.prod
  cdn: cloudfront""",
}

def load_il_files(directory: str) -> list:
    """Load all .il files from a directory."""
    path = Path(directory)
    if not path.exists():
        return []
    files = []
    for il_file in sorted(path.glob("*.il")):
        content = il_file.read_text(encoding="utf-8")
        files.append({"name": il_file.name, "content": content})
    return files

def save_il_files(files: list, directory: str):
    """Save all .il files to a directory."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    for f in files:
        (path / f["name"]).write_text(f["content"], encoding="utf-8")

def save_output_files(output_files: list, directory: str):
    """Write generated files to output directory."""
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in output_files:
        out_path = base / f["path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(f["content"], encoding="utf-8")
        saved.append(str(out_path))
    return saved

# ─── DISPLAY HELPERS ──────────────────────────────────────────────────────────

LEVEL_COLORS = {"high": "bright_cyan", "mid": "yellow", "low": "orange1", "asm": "red"}
TYPE_COLORS  = {"model": "bright_magenta", "feature": "bright_blue", "route": "green",
                "project": "bright_white", "domain": "cyan", "config": "yellow", "rule": "dim white"}

def print_header():
    console.print()
    console.print(Panel(
        Text.assemble(
            ("  IntentLang ", "bold bright_magenta"),
            ("v0.2", "dim magenta"),
            ("  —  Terminal IDE\n", "dim white"),
            ("  A structured multi-level intent language for AI coding", "dim white"),
        ),
        border_style="bright_magenta", box=box.DOUBLE_EDGE, padding=(0, 2)
    ))
    console.print()

def print_ir_summary(ir: dict):
    mc = len(ir["by_type"].get("model", []))
    fc = len(ir["by_type"].get("feature", []))
    rc = len(ir["by_type"].get("route", []))
    unresolved = [e for e in ir["edges"] if e.get("resolved") is False]

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="dim white", no_wrap=True)
    table.add_column(style="bright_white")
    table.add_row("Project",  ir["project_name"] or "unnamed")
    table.add_row("Stack",    str(ir["stack"] or "unspecified"))
    table.add_row("Files",    ", ".join(ir["files"]))
    table.add_row("Nodes",    f'{len(ir["nodes"])} ({mc} models, {fc} features, {rc} routes)')
    table.add_row("Edges",    f'{len(ir["edges"])} ({len(unresolved)} unresolved)')
    table.add_row("Rules",    str(len(ir["global_rules"])))

    console.print(Panel(table, title="[bright_magenta]IR Summary[/]", border_style="magenta", box=box.ROUNDED))

def print_query_result(result: str):
    console.print(Panel(
        Text(result, style="bright_white"),
        title="[cyan]Query Result[/]", border_style="cyan", box=box.ROUNDED
    ))

def print_file_tree(files: list):
    console.print("\n[dim]Loaded files:[/]")
    for i, f in enumerate(files):
        prefix = "└─" if i == len(files) - 1 else "├─"
        console.print(f"  [dim]{prefix}[/] [bright_cyan]{f['name']}[/]  [dim]{len(f['content'].splitlines())} lines[/]")
    console.print()

def syntax_preview(content: str, filename: str):
    """Show a syntax-highlighted preview of an .il file."""
    # Rich doesn't have .il syntax, use python as closest approximation
    console.print(Panel(
        Syntax(content, "python", theme="monokai", line_numbers=True, word_wrap=False),
        title=f"[bright_cyan]{filename}[/]", border_style="cyan", box=box.ROUNDED
    ))

# ─── MAIN CLI ─────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    """Resolve API key from config, env var, or prompt."""
    key = API_KEY.strip()
    if not key:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        key = os.environ.get("INTENTLANG_API_KEY", "").strip()
    if not key:
        console.print("\n[yellow]No API key found in config or environment.[/]")
        key = Prompt.ask("[bright_white]Enter your API key[/]", password=True).strip()
    return key

def cmd_list(files: list, ir: dict):
    """List all loaded .il files and IR summary."""
    print_file_tree(files)
    print_ir_summary(ir)

def cmd_view(files: list, args: str):
    """View a specific .il file."""
    name = args.strip()
    if not name.endswith(".il"):
        name += ".il"
    f = next((f for f in files if f["name"] == name), None)
    if not f:
        console.print(f"[red]File not found: {name}[/]")
        return
    syntax_preview(f["content"], f["name"])

def cmd_query(ir: dict, query: str):
    """Run an IR query."""
    if not query.strip():
        console.print("[dim]Usage: query <your query>[/]")
        console.print("[dim]e.g.:  query list models[/]")
        return
    result = query_ir(ir, query)
    print_query_result(result)

def cmd_transpile(files: list, ir: dict, target: str, api_key: str):
    """Transpile a target .il file and stream output."""
    if not target.endswith(".il"):
        target += ".il"
    if target not in [f["name"] for f in files]:
        console.print(f"[red]File not found: {target}[/]")
        console.print(f"[dim]Available: {', '.join(f['name'] for f in files)}[/]")
        return

    parsed = [{"name": f["name"], "content": f["content"],
               "ast": parse_intent_lang(f["content"], f["name"])["ast"]}
              for f in files]

    console.print(f"\n[bright_magenta]Transpiling[/] [bright_cyan]{target}[/] [dim]→ streaming output…[/]\n")

    full_text = ""
    output_files = []

    try:
        for chunk in transpile_stream(parsed, ir, target, api_key):
            full_text += chunk
            print(chunk, end="", flush=True)
            output_files = parse_output_files(full_text)
    except httpx.HTTPStatusError as e:
        console.print(f"\n[red]API error {e.response.status_code}: {e.response.text}[/]")
        return
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/]")
        return

    console.print("\n")

    if not output_files:
        console.print("[yellow]No FILE: markers found in output.[/]")
        return

    # Save files
    saved = save_output_files(output_files, OUTPUT_DIR)

    console.print(Panel(
        "\n".join(f"[bright_green]✓[/]  [bright_white]{p}[/]" for p in saved),
        title=f"[bright_green]Generated {len(saved)} files[/]",
        border_style="green", box=box.ROUNDED
    ))
    console.print(f"\n[dim]Output directory:[/] [bright_cyan]{Path(OUTPUT_DIR).resolve()}[/]\n")

def cmd_new(files: list, name: str) -> list:
    """Create a new .il file."""
    if not name.strip():
        name = Prompt.ask("File name (without .il)")
    if not name.endswith(".il"):
        name += ".il"
    if any(f["name"] == name for f in files):
        console.print(f"[yellow]File already exists: {name}[/]")
        return files
    domain = name.replace(".il", "")
    content = f'// {name}\ndomain {domain}:\n  description: ""\n'
    files = files + [{"name": name, "content": content}]
    console.print(f"[bright_green]Created:[/] [bright_cyan]{name}[/]")
    console.print(f"[dim]Edit it at:[/] [bright_white]{Path(IL_DIR) / name}[/]")
    save_il_files(files, IL_DIR)
    return files

def cmd_edit(files: list, name: str) -> list:
    """Open a file in the system editor."""
    if not name.strip():
        console.print("[dim]Usage: edit <filename>[/]")
        return files
    if not name.endswith(".il"):
        name += ".il"
    f = next((f for f in files if f["name"] == name), None)
    if not f:
        console.print(f"[red]File not found: {name}[/]")
        return files

    # Save current state, open editor
    save_il_files(files, IL_DIR)
    editor = os.environ.get("EDITOR", "nano")
    os.system(f'{editor} "{Path(IL_DIR) / name}"')

    # Reload
    new_files = load_il_files(IL_DIR)
    console.print(f"[bright_green]Reloaded:[/] [bright_cyan]{name}[/]")
    return new_files

def cmd_save(files: list):
    """Save all .il files to disk."""
    save_il_files(files, IL_DIR)
    console.print(f"[bright_green]Saved {len(files)} file(s) to[/] [bright_cyan]{Path(IL_DIR).resolve()}[/]")

def cmd_load(args: str) -> list:
    """Load .il files from a directory."""
    directory = args.strip() or IL_DIR
    loaded = load_il_files(directory)
    if loaded:
        console.print(f"[bright_green]Loaded {len(loaded)} file(s) from[/] [bright_cyan]{Path(directory).resolve()}[/]")
        return loaded
    else:
        console.print(f"[yellow]No .il files found in {directory}[/]")
        console.print("[dim]Starting with example project.[/]")
        return [{"name": k, "content": v} for k, v in EXAMPLE_PROJECT.items()]

def cmd_help():
    table = Table(box=box.SIMPLE, show_header=True, header_style="bright_magenta", padding=(0, 2))
    table.add_column("Command",     style="bright_cyan",  no_wrap=True)
    table.add_column("Args",        style="yellow",       no_wrap=True)
    table.add_column("Description", style="white")

    commands = [
        ("list",      "",              "Show loaded files and IR summary"),
        ("view",      "<file>",        "Preview a .il file with syntax highlighting"),
        ("query",     "<q>",           "Query the IR graph"),
        ("transpile", "<file>",        "Transpile a .il file → generate code"),
        ("new",       "<name>",        "Create a new .il file"),
        ("edit",      "<file>",        "Open a file in $EDITOR"),
        ("save",      "",              "Save all .il files to disk"),
        ("load",      "[dir]",         "Load .il files from directory"),
        ("config",    "",              "Show current configuration"),
        ("example",   "",              "Reset to example project"),
        ("help",      "",              "Show this help"),
        ("exit / q",  "",              "Quit"),
    ]
    for cmd, args, desc in commands:
        table.add_row(cmd, args, desc)

    console.print(Panel(table, title="[bright_magenta]Commands[/]", border_style="magenta", box=box.ROUNDED))
    console.print()
    console.print("[dim]IR Query examples:[/]")
    queries = ["list models", "list features", "show global rules", "show stack",
               "deps of tasks", "used by User", "impact of User", "inspect Auth", "show graph"]
    for q in queries:
        console.print(f"  [dim]›[/] [bright_white]query {q}[/]")
    console.print()

def cmd_config(api_key: str):
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="dim white", no_wrap=True)
    table.add_column(style="bright_white")
    table.add_row("Model",       MODEL)
    table.add_row("API Base",    API_BASE)
    table.add_row("Max Tokens",  str(MAX_TOKENS))
    table.add_row("Temperature", str(TEMPERATURE))
    table.add_row("API Key",     ("✓ set" if api_key else "[red]not set[/]"))
    table.add_row("Output Dir",  str(Path(OUTPUT_DIR).resolve()))
    table.add_row("IL Dir",      str(Path(IL_DIR).resolve()))
    console.print(Panel(table, title="[bright_magenta]Configuration[/]", border_style="magenta", box=box.ROUNDED))

# ─── REPL ─────────────────────────────────────────────────────────────────────

def main():
    print_header()

    # Resolve API key
    api_key = get_api_key()
    console.print(f"[dim]Model:[/] [bright_white]{MODEL}[/]  [dim]API:[/] [bright_white]{API_BASE}[/]\n")

    # Load files — from disk if available, else example project
    existing = load_il_files(IL_DIR)
    if existing:
        console.print(f"[dim]Loading from[/] [bright_cyan]{IL_DIR}[/]")
        files = existing
    else:
        console.print("[dim]No .il files found on disk — loading example project.[/]")
        console.print(f"[dim]Run[/] [bright_white]save[/] [dim]to persist them to[/] [bright_cyan]{IL_DIR}[/]\n")
        files = [{"name": k, "content": v} for k, v in EXAMPLE_PROJECT.items()]

    def rebuild_ir():
        parsed = []
        for f in files:
            result = parse_intent_lang(f["content"], f["name"])
            parsed.append({"name": f["name"], "content": f["content"], "ast": result["ast"], "errors": result["errors"]})
        return build_ir(parsed)

    ir = rebuild_ir()
    print_file_tree(files)
    print_ir_summary(ir)

    # REPL
    session = PromptSession(
        history=InMemoryHistory(),
        style=PTStyle.from_dict({"prompt": "bold #cc88ff"})
    )

    console.print('[dim]Type [/][bright_white]help[/][dim] for commands. Tab history supported.[/]\n')

    while True:
        try:
            raw = session.prompt("il› ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/]")
            break

        if not raw:
            continue

        parts = raw.split(None, 1)
        cmd  = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("exit", "quit", "q"):
            console.print("[dim]Goodbye.[/]")
            break

        elif cmd == "help":
            cmd_help()

        elif cmd == "list":
            cmd_list(files, ir)

        elif cmd == "view":
            cmd_view(files, args)

        elif cmd == "query":
            cmd_query(ir, args)

        elif cmd == "transpile":
            target = args.strip() or (files[0]["name"] if files else "")
            if not target:
                console.print("[red]No files loaded.[/]")
            else:
                cmd_transpile(files, ir, target, api_key)

        elif cmd == "new":
            files = cmd_new(files, args)
            ir = rebuild_ir()

        elif cmd == "edit":
            files = cmd_edit(files, args)
            ir = rebuild_ir()

        elif cmd == "save":
            cmd_save(files)

        elif cmd == "load":
            files = cmd_load(args)
            ir = rebuild_ir()
            print_file_tree(files)

        elif cmd == "config":
            cmd_config(api_key)

        elif cmd == "example":
            files = [{"name": k, "content": v} for k, v in EXAMPLE_PROJECT.items()]
            ir = rebuild_ir()
            console.print("[bright_green]Reset to example project.[/]")
            print_file_tree(files)

        else:
            console.print(f"[red]Unknown command:[/] [bright_white]{cmd}[/]  [dim](type help)[/]")

if __name__ == "__main__":
    main()
