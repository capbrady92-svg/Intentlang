#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  IntentLang v0.3  —  Terminal IDE                           ║
║  Multi-file · IR graph · Interface layer · Git imports      ║
╚══════════════════════════════════════════════════════════════╝

SETUP:
  pip install httpx rich prompt_toolkit gitpython

RUN:
  python intentlang.py

CONFIG (edit the block below):
  API_KEY   — your Anthropic / OpenAI / xAI / OpenRouter key
  MODEL     — which model to use
  API_BASE  — endpoint URL (Anthropic default)
"""

# ─── CONFIG ────────────────────────────────────────────────────────────────────

API_KEY     = ""                                        # ← paste your key here
MODEL       = "claude-sonnet-4-20250514"                # ← change model here
API_BASE    = "https://api.anthropic.com/v1/messages"   # ← change endpoint here
MAX_TOKENS  = 8000
TEMPERATURE = 0.2

MODELS = {
    "sonnet":       "claude-sonnet-4-20250514",
    "opus":         "claude-opus-4-20250514",
    "haiku":        "claude-haiku-4-5-20251001",
    "gpt4o":        "gpt-4o",
    "gpt4o-mini":   "gpt-4o-mini",
    "grok3":        "grok-3",
    "gemini-pro":   "gemini-2.5-pro",
    "gemini-flash": "gemini-2.0-flash",
    "llama3":       "llama3.1:70b",
    "deepseek":     "deepseek-coder-v2:16b",
}

OUTPUT_DIR    = "./intentlang_output"    # generated code lands here
IL_DIR        = "./intent"              # .il source files
INTERFACE_DIR = "./intentlang_output/interface"  # published interface schemas
IMPORTS_DIR   = "./.il_imports"         # cached git imports

# ───────────────────────────────────────────────────────────────────────────────

import os, re, sys, json, time, shutil, hashlib, subprocess, tempfile
from pathlib import Path
from typing import Optional
from copy import deepcopy

# ─── DEPENDENCY CHECK ─────────────────────────────────────────────────────────

def check_deps():
    missing = []
    for pkg in ["httpx", "rich", "prompt_toolkit"]:
        try: __import__(pkg)
        except ImportError: missing.append(pkg)
    if missing:
        print(f"Missing: pip install {' '.join(missing)}")
        sys.exit(1)

check_deps()

import httpx
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt
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
    if content.startswith("@target:"):
        return {"type": "directive", "key": "target", "value": content[8:].strip(), "line": line_num, "level": level}
    if re.match(r"^@?constraint:", content):
        return {"type": "constraint", "value": re.sub(r"^@?constraint:\s*", "", content), "line": line_num, "level": level}

    # cross-file xref
    m = re.match(r"^([\w.]+)\s*:\s*@([\w-]+)/([\w]+)([!?]?)\s*(.*)$", content)
    if m:
        return {"type": "xref_property", "key": m[1], "domain": m[2], "target": m[3],
                "strictness": m[4], "rest": m[5].strip(), "line": line_num, "level": level, "parent_uid": None}

    # block declarations — added interface, preserve, imports
    m = re.match(
        r"^(app|service|module|feature|model|route|event|state|component|page|api|auth|db"
        r"|domain|project|platform|critical_path|inline|interface|preserve|imports|config|environment)\s+([\w./\-@^]+)\s*:?$",
        content
    )
    if m:
        uid = make_uid(m[1], m[2], filename)
        return {"type": m[1], "name": m[2], "block": True, "children": [],
                "line": line_num, "uid": uid, "level": level, "filename": filename}

    # anonymous blocks — added expose, hide, breaking_changes, deprecated
    m = re.match(
        r"^(rules?|config|schema|props|actions?|effects?|guards?|meta"
        r"|environment|domains|dependencies|expose|hide|breaking_changes|deprecated|imports|interface|preserve)\s*:$",
        content
    )
    if m:
        uid = make_uid(m[1], f"anon_{line_num}", filename)
        return {"type": m[1], "block": True, "children": [], "line": line_num, "uid": uid,
                "level": level, "filename": filename}

    # route shorthand
    m = re.match(r"^route\s+(GET|POST|PUT|PATCH|DELETE|WS)\s+([\w/:\-]+)\s*:?$", content)
    if m:
        uid = make_uid("route", f"{m[1]}_{m[2]}", filename)
        return {"type": "route", "method": m[1], "path": m[2], "block": True, "children": [],
                "line": line_num, "uid": uid, "level": level, "filename": filename}

    # kv
    m = re.match(r"^([\w.@]+)\s*:\s*(.+)$", content)
    if m:
        return {"type": "property", "key": m[1], "value": parse_value(m[2].strip()), "line": line_num, "level": level}

    if content.startswith("-") or content.startswith("*"):
        return {"type": "rule", "value": content[1:].strip(), "line": line_num, "level": level}

    m = re.match(r"^(\w+)\s*\(([^)]+)\)$", content)
    if m:
        uid = make_uid("field", m[1], filename)
        return {"type": "field", "name": m[1], "modifiers": [s.strip() for s in m[2].split(",")],
                "line": line_num, "uid": uid, "level": level, "filename": filename}

    m = re.match(r"^(\w+)\s*->\s*(\w+)$", content)
    if m:
        return {"type": "relation", "name": m[1], "target": m[2], "local": True, "line": line_num, "level": level}

    errors.append({"line": line_num, "message": f'Unrecognized: "{content}"'})
    return {"type": "unknown", "raw": content, "line": line_num, "level": level}

def parse_intent_lang(source: str, filename: str = "unnamed.il") -> dict:
    global _uid_counter
    _uid_counter = 0
    lines  = source.split("\n")
    errors = []
    root   = {"type": "root", "filename": filename, "children": [], "uid": f"root:{filename}"}
    stack  = [{"node": root, "indent": -1}]
    current_level = "high"

    for line_num, raw in enumerate(lines, 1):
        trimmed = raw.strip()
        if not trimmed or trimmed.startswith("//"):
            continue
        if trimmed.startswith("@level:"):
            m = re.match(r"@level:\s*(high|mid|low|asm)", trimmed)
            if m: current_level = m[1]
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
            elif not node.get("uid"):
                node["uid"] = f"{filename.replace('.il','')}:leaf:{line_num}"

    return {"ast": root, "errors": errors}

# ─── INTERFACE SCHEMA ─────────────────────────────────────────────────────────
# Extracts the public interface from a parsed domain file.

def extract_interface_schema(parsed_file: dict, ir: dict) -> Optional[dict]:
    """
    Reads interface: block from a parsed .il file and builds a schema dict.
    Returns None if no interface block declared.
    """
    ast      = parsed_file["ast"]
    filename = parsed_file["name"]
    domain   = filename.replace(".il", "")

    # find interface block
    iface_node = None
    for child in ast.get("children", []):
        if child.get("type") == "interface":
            iface_node = child
            break
        for grandchild in child.get("children", []):
            if grandchild.get("type") == "interface":
                iface_node = grandchild
                break

    if not iface_node:
        return None

    # extract version, expose list, hide list, breaking_changes, deprecated
    version          = "0.0.0"
    expose_names     = []
    hide_names       = []
    breaking_changes = []
    deprecated       = []

    for child in iface_node.get("children", []):
        if child.get("type") == "property":
            if child["key"] == "version":
                version = str(child["value"])
        elif child.get("type") == "expose":
            for item in child.get("children", []):
                if item.get("type") == "rule":
                    expose_names.append(item["value"].split("(")[0].strip())
        elif child.get("type") == "hide":
            for item in child.get("children", []):
                if item.get("type") == "rule":
                    hide_names.append(item["value"].split("(")[0].strip())
        elif child.get("type") == "breaking_changes":
            for item in child.get("children", []):
                if item.get("type") == "rule":
                    breaking_changes.append(item["value"])
        elif child.get("type") == "deprecated":
            for item in child.get("children", []):
                if item.get("type") == "rule":
                    deprecated.append(item["value"])

    # collect public models and features
    public_models   = {}
    public_features = {}
    public_events   = {}

    def should_expose(name):
        if expose_names and name not in expose_names:
            return False
        if name in hide_names:
            return False
        return True

    for child in ast.get("children", []):
        name = child.get("name", "")
        if child.get("type") == "model" and should_expose(name):
            # filter private fields
            fields = []
            for f in child.get("children", []):
                if f.get("type") == "field":
                    if "private" not in f.get("modifiers", []) and name not in hide_names:
                        fields.append({"name": f["name"], "modifiers": f.get("modifiers", [])})
            public_models[name] = {"fields": fields}

        elif child.get("type") == "feature" and should_expose(name):
            routes = []
            for f in child.get("children", []):
                if f.get("type") == "route":
                    props = {p["key"]: p["value"] for p in f.get("children", []) if p.get("type") == "property"}
                    routes.append({
                        "method": f.get("method"),
                        "path":   f.get("path"),
                        "input":  props.get("input"),
                        "returns": props.get("returns"),
                        "auth":   props.get("auth", "required"),
                    })
            public_features[name] = {"routes": routes}

        elif child.get("type") == "event" and should_expose(name):
            props = {p["key"]: p["value"] for p in child.get("children", []) if p.get("type") == "property"}
            public_events[name] = props

    schema = {
        "domain":           domain,
        "version":          version,
        "models":           public_models,
        "features":         public_features,
        "events":           public_events,
        "breaking_changes": breaking_changes,
        "deprecated":       deprecated,
        "generated_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return schema

def generate_typescript_types(schema: dict) -> str:
    """Generate TypeScript type definitions from an interface schema."""
    lines = [
        f"// IntentLang Interface — {schema['domain']} v{schema['version']}",
        f"// Generated: {schema['generated_at']}",
        f"// DO NOT EDIT — regenerate with: il› publish {schema['domain']}",
        "",
    ]

    if schema.get("deprecated"):
        lines.append("// DEPRECATED:")
        for d in schema["deprecated"]:
            lines.append(f"//   {d}")
        lines.append("")

    type_map = {
        "str": "string", "int": "number", "float": "number",
        "bool": "boolean", "uuid": "string", "date": "string",
        "datetime": "string", "json": "Record<string, unknown>",
        "list": "unknown[]", "map": "Record<string, unknown>", "bytes": "Uint8Array",
    }

    for model_name, model in schema["models"].items():
        lines.append(f"export interface {model_name} {{")
        for field in model["fields"]:
            mods    = field["modifiers"]
            ft      = next((m for m in mods if m in type_map), "string")
            ts_type = type_map.get(ft, "string")
            optional = "optional" in mods and "required" not in mods
            lines.append(f"  {field['name']}{'?' if optional else ''}: {ts_type};")
        lines.append("}")
        lines.append("")

    # API client
    lines += [
        f"export class {schema['domain'].capitalize()}Client {{",
        "  constructor(private baseUrl: string, private apiKey?: string) {}",
        "",
        "  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {",
        "    const res = await fetch(`${this.baseUrl}${path}`, {",
        "      method,",
        "      headers: {",
        "        'Content-Type': 'application/json',",
        "        ...(this.apiKey ? { 'Authorization': `Bearer ${this.apiKey}` } : {}),",
        "      },",
        "      body: body ? JSON.stringify(body) : undefined,",
        "    });",
        "    if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);",
        "    return res.json();",
        "  }",
        "",
    ]

    for feat_name, feat in schema["features"].items():
        for route in feat["routes"]:
            method     = route["method"] or "GET"
            path       = route["path"] or "/"
            fn_name    = path.replace("/", "_").replace(":", "By").replace("-", "_").strip("_")
            fn_name    = f"{method.lower()}_{fn_name}"
            return_type = "unknown"
            lines.append(f"  async {fn_name}(params?: unknown): Promise<{return_type}> {{")
            lines.append(f"    return this.request('{method}', `{path}`{', params' if method != 'GET' else ''});")
            lines.append("  }")
            lines.append("")

    lines.append("}")
    return "\n".join(lines)

def generate_python_client(schema: dict) -> str:
    """Generate a Python client SDK from an interface schema."""
    domain  = schema["domain"]
    version = schema["version"]
    lines   = [
        f'"""',
        f'IntentLang Interface — {domain} v{version}',
        f'Generated: {schema["generated_at"]}',
        f'DO NOT EDIT — regenerate with: il› publish {domain}',
        f'"""',
        "",
        "import httpx",
        "from typing import Any, Optional",
        "",
    ]

    type_map = {
        "str": "str", "int": "int", "float": "float", "bool": "bool",
        "uuid": "str", "date": "str", "datetime": "str",
        "json": "dict", "list": "list", "map": "dict", "bytes": "bytes",
    }

    for model_name, model in schema["models"].items():
        lines.append(f"class {model_name}:")
        lines.append(f'    """Model from {domain} interface."""')
        lines.append("    def __init__(self, data: dict):")
        for field in model["fields"]:
            mods = field["modifiers"]
            lines.append(f"        self.{field['name']} = data.get('{field['name']}')")
        lines.append("")
        lines.append("    def to_dict(self) -> dict:")
        lines.append("        return self.__dict__")
        lines.append("")

    lines += [
        f"class {domain.capitalize()}Client:",
        f'    """Client for the {domain} IntentLang interface."""',
        "",
        "    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: int = 30):",
        "        self.base_url = base_url.rstrip('/')",
        "        self.headers  = {'Content-Type': 'application/json'}",
        "        if api_key:",
        "            self.headers['Authorization'] = f'Bearer {api_key}'",
        "        self.timeout = timeout",
        "",
        "    def _request(self, method: str, path: str, **kwargs) -> Any:",
        "        url = f'{self.base_url}{path}'",
        "        with httpx.Client(timeout=self.timeout) as client:",
        "            response = client.request(method, url, headers=self.headers, **kwargs)",
        "            response.raise_for_status()",
        "            return response.json()",
        "",
    ]

    for feat_name, feat in schema["features"].items():
        for route in feat["routes"]:
            method  = (route["method"] or "GET").lower()
            path    = route["path"] or "/"
            fn_name = re.sub(r"[^a-z0-9_]", "_", path.lower()).strip("_")
            fn_name = f"{method}_{fn_name}"
            lines.append(f"    def {fn_name}(self, **kwargs) -> Any:")
            lines.append(f"        return self._request('{method.upper()}', f'{path}', **kwargs)")
            lines.append("")

    return "\n".join(lines)

def generate_openapi_spec(schema: dict, ir: dict) -> dict:
    """Generate an OpenAPI 3.0 spec from an interface schema."""
    domain  = schema["domain"]
    version = schema["version"]
    paths   = {}

    for feat_name, feat in schema["features"].items():
        for route in feat["routes"]:
            path   = route["path"] or "/"
            method = (route["method"] or "GET").lower()
            # convert :param to {param}
            oapi_path = re.sub(r":(\w+)", r"{\1}", path)
            if oapi_path not in paths:
                paths[oapi_path] = {}
            paths[oapi_path][method] = {
                "summary":     f"{feat_name} — {method.upper()} {path}",
                "operationId": f"{feat_name}_{method}_{path.replace('/','_').replace(':','').strip('_')}",
                "parameters":  [],
                "responses":   {"200": {"description": str(route.get("returns", "Success"))},
                                "401": {"description": "Unauthorized"},
                                "422": {"description": "Validation error"}},
                "security":    [] if route.get("auth") == "public" else [{"bearerAuth": []}],
            }

    schemas = {}
    for model_name, model in schema["models"].items():
        props   = {}
        required = []
        type_map = {"str":"string","int":"integer","float":"number","bool":"boolean",
                    "uuid":"string","date":"string","datetime":"string","json":"object",
                    "list":"array","map":"object","bytes":"string"}
        for field in model["fields"]:
            mods = field["modifiers"]
            ft   = next((m for m in mods if m in type_map), "string")
            props[field["name"]] = {"type": type_map.get(ft, "string")}
            if "required" in mods:
                required.append(field["name"])
        schemas[model_name] = {"type": "object", "properties": props,
                               "required": required if required else None}

    return {
        "openapi": "3.0.3",
        "info": {"title": f"{domain} Interface", "version": version,
                 "description": f"IntentLang generated interface for {domain}"},
        "paths": paths,
        "components": {
            "schemas":         schemas,
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
        },
    }

# ─── GIT IMPORT SYSTEM ────────────────────────────────────────────────────────

def _run(cmd: list, cwd=None) -> tuple[int, str, str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()

def parse_git_import(ref: str) -> Optional[dict]:
    """
    Parse a git import reference like:
      github.com/org/repo/intent/identity@^1.2
      github.com/org/repo@v2.0
      ../local/path
      /absolute/path
    """
    ref = ref.strip()
    # local path: relative or absolute, or anything that isn't a known git host
    git_hosts = ("github.com", "gitlab.com", "bitbucket.org")
    is_git = any(ref.startswith(h) for h in git_hosts)
    if not is_git:
        return {"type": "local", "path": ref}

    m = re.match(
        r"^(github\.com|gitlab\.com|bitbucket\.org)/([\w\-]+)/([\w\-]+)"
        r"(?:/([\w/\-]+))?(?:@([\w.\^\~><=*]+))?$",
        ref
    )
    if m:
        return {
            "type":    "git",
            "host":    m[1],
            "org":     m[2],
            "repo":    m[3],
            "subpath": m[4] or "intent",
            "version": m[5] or "main",
            "url":     f"https://{m[1]}/{m[2]}/{m[3]}.git",
        }
    return None

def resolve_git_import(ref: str, domain_alias: str) -> Optional[list]:
    """
    Fetch .il files from a git reference or local path.
    Returns list of {name, content} dicts or None on failure.
    """
    parsed = parse_git_import(ref)
    if not parsed:
        console.print(f"[red]Cannot parse import ref: {ref}[/]")
        return None

    if parsed["type"] == "local":
        path = Path(parsed["path"])
        if not path.exists():
            console.print(f"[red]Local import path not found: {path}[/]")
            return None
        files = []
        for il in sorted(path.glob("*.il")):
            files.append({"name": il.name, "content": il.read_text("utf-8"),
                          "source": str(path.resolve()), "imported": True, "alias": domain_alias})
        console.print(f"[dim]  Resolved local import {domain_alias} from {path}[/]")
        return files

    # git import
    cache_key  = hashlib.sha256(ref.encode()).hexdigest()[:12]
    cache_dir  = Path(IMPORTS_DIR) / cache_key
    marker     = cache_dir / ".il_import_meta.json"

    # check cache
    if marker.exists():
        meta = json.loads(marker.read_text())
        console.print(f"[dim]  Using cached import {domain_alias} ({meta.get('ref')}) from {cache_dir}[/]")
    else:
        console.print(f"[dim]  Cloning {parsed['url']} …[/]")
        cache_dir.mkdir(parents=True, exist_ok=True)
        code, out, err = _run(["git", "clone", "--depth=1", parsed["url"], str(cache_dir)])
        if code != 0:
            console.print(f"[red]git clone failed: {err}[/]")
            return None
        # checkout version if not main
        version = parsed["version"]
        if version not in ("main", "master"):
            # try tag then branch
            clean_ver = version.lstrip("^~><=*")
            _run(["git", "checkout", f"v{clean_ver}"], cwd=cache_dir)
            _run(["git", "checkout", clean_ver], cwd=cache_dir)
        marker.write_text(json.dumps({"ref": ref, "parsed": parsed,
                                       "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}))

    # read .il files from subpath
    subpath = cache_dir / parsed.get("subpath", "intent")
    if not subpath.exists():
        # fallback: look for .il files anywhere
        il_files = list(cache_dir.rglob("*.il"))
    else:
        il_files = list(sorted(subpath.glob("*.il")))

    if not il_files:
        console.print(f"[yellow]No .il files found in import {ref}[/]")
        return []

    files = []
    for il in il_files:
        files.append({"name": il.name, "content": il.read_text("utf-8"),
                      "source": ref, "imported": True, "alias": domain_alias})
    console.print(f"[dim]  Resolved git import {domain_alias}: {len(files)} files[/]")
    return files

def load_imports(core_files: list, source_dir: str = None) -> list:
    """
    Scan core.il for imports: block and resolve each one.
    Resolves local paths relative to the directory core.il was loaded from.
    Returns additional .il files to merge into the project.
    """
    core = next((f for f in core_files if f["name"] == "core.il"), None)
    if not core:
        return []

    # resolve relative to where core.il lives, not where we launched from
    base_dir = Path(source_dir).resolve() if source_dir else Path(core.get("source_dir", ".")).resolve()

    ast    = parse_intent_lang(core["content"], "core.il")["ast"]
    extras = []

    def find_imports(node):
        if node.get("type") == "imports":
            for child in node.get("children", []):
                if child.get("type") == "property":
                    alias = child["key"]
                    ref   = str(child["value"])
                    # resolve local paths relative to core.il location
                    resolved_ref = ref
                    if ref.startswith("./") or ref.startswith("../") or (not ref.startswith("http") and "/" in ref and not any(h in ref for h in ["github.com","gitlab.com","bitbucket.org"])):
                        resolved_ref = str((base_dir / ref).resolve())
                    console.print(f"[bright_magenta]Resolving import:[/] [bright_cyan]{alias}[/] ← {resolved_ref}")
                    resolved = resolve_git_import(resolved_ref, alias)
                    if resolved:
                        extras.extend(resolved)
        for child in node.get("children", []):
            find_imports(child)

    find_imports(ast)
    return extras

def update_git_import(alias: str, files: list) -> list:
    """
    Re-fetch a specific git import and update cached files.
    """
    core = next((f for f in files if f["name"] == "core.il"), None)
    if not core:
        console.print("[red]No core.il loaded[/]")
        return files

    ast = parse_intent_lang(core["content"], "core.il")["ast"]

    def find_ref(node):
        if node.get("type") == "imports":
            for child in node.get("children", []):
                if child.get("type") == "property" and child["key"] == alias:
                    return str(child["value"])
        for child in node.get("children", []):
            r = find_ref(child)
            if r: return r
        return None

    ref = find_ref(ast)
    if not ref:
        console.print(f"[red]No import named '{alias}' in core.il[/]")
        return files

    # clear cache
    cache_key = hashlib.sha256(ref.encode()).hexdigest()[:12]
    cache_dir = Path(IMPORTS_DIR) / cache_key
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        console.print(f"[dim]Cleared cache for {alias}[/]")

    # re-resolve
    resolved = resolve_git_import(ref, alias)
    if not resolved:
        return files

    # replace old imported files for this alias
    non_imported = [f for f in files if not (f.get("imported") and f.get("alias") == alias)]
    return non_imported + resolved

# ─── PRESERVE SYSTEM ──────────────────────────────────────────────────────────

def load_preserve_patterns(files: list) -> list:
    """Read preserve: blocks from any .il file and return glob patterns."""
    patterns = []
    for f in files:
        ast = parse_intent_lang(f["content"], f["name"])["ast"]
        def find_preserve(node):
            if node.get("type") == "preserve":
                for child in node.get("children", []):
                    if child.get("type") == "rule":
                        patterns.append(child["value"].strip())
            for child in node.get("children", []):
                find_preserve(child)
        find_preserve(ast)
    return patterns

def should_preserve(file_path: str, patterns: list) -> bool:
    """Check if a generated file path matches any preserve pattern."""
    import fnmatch
    for pattern in patterns:
        if fnmatch.fnmatch(file_path, pattern):
            return True
        if fnmatch.fnmatch(Path(file_path).name, pattern):
            return True
    return False

def save_output_files(output_files: list, directory: str, preserve_patterns: list = None) -> tuple:
    """Write generated files, skipping preserved ones. Returns (saved, skipped)."""
    base    = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    saved   = []
    skipped = []

    for f in output_files:
        if preserve_patterns and should_preserve(f["path"], preserve_patterns):
            # only skip if file already exists on disk
            existing = base / f["path"]
            if existing.exists():
                skipped.append(f["path"])
                continue
        out = base / f["path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f["content"], encoding="utf-8")
        saved.append(str(out))

    return saved, skipped

# ─── IR BUILDER ───────────────────────────────────────────────────────────────

def flatten_nodes(node: dict, ir: dict, filename: str):
    if not node: return
    if "uid" in node:
        ir["nodes"][node["uid"]] = dict(node)
        ir["by_type"].setdefault(node["type"], []).append(node["uid"])
        domain = filename.replace(".il", "")
        ir["domains"].setdefault(domain, []).append(node["uid"])
    for child in node.get("children", []): flatten_nodes(child, ir, filename)

def resolve_ref(domain: str, type_name: str, ir: dict) -> Optional[str]:
    for uid in ir["domains"].get(domain, []):
        n = ir["nodes"].get(uid, {})
        if n.get("name") == type_name: return uid
    return None

def build_ir(parsed_files: list) -> dict:
    ir = {"nodes":{}, "edges":[], "domains":{}, "by_type":{},
          "global_rules":[], "stack":None, "project_name":None, "files":[],
          "interfaces":{}, "imports":{}, "preserve_patterns":[]}

    for pf in parsed_files:
        ir["files"].append(pf["name"])
        flatten_nodes(pf["ast"], ir, pf["name"])

    for uid, node in ir["nodes"].items():
        if node["type"] == "xref_property":
            target_uid = resolve_ref(node["domain"], node["target"], ir)
            ir["edges"].append({
                "from": node.get("parent_uid") or uid,
                "to":   target_uid or f"unresolved:{node['domain']}/{node['target']}",
                "type": "xref", "resolved": bool(target_uid),
                "key":  node["key"], "strictness": node.get("strictness","")
            })
        if node["type"] == "relation":
            ir["edges"].append({
                "from": node.get("parent_uid") or uid,
                "to":   node["target"], "type": "relation", "name": node["name"]
            })

    for uid, n in ir["nodes"].items():
        if n["type"] in ("project","app","service") and not ir["project_name"]:
            ir["project_name"] = n.get("name")
        if n["type"] == "property" and n.get("key") == "stack" and not ir["stack"]:
            ir["stack"] = n.get("value")
        if n["type"] == "rule":
            parent = ir["nodes"].get(n.get("parent_uid",""), {})
            if parent.get("type") in ("rules","rule","project","app"):
                ir["global_rules"].append(n["value"])
        if n["type"] == "property" and n.get("key") in ir["domains"]:
            # detect imports block children
            pass

    # collect interface declarations
    for pf in parsed_files:
        schema = extract_interface_schema(pf, ir)
        if schema:
            ir["interfaces"][schema["domain"]] = schema

    # collect preserve patterns
    for pf in parsed_files:
        def find_preserve(node):
            if node.get("type") == "preserve":
                for child in node.get("children", []):
                    if child.get("type") == "rule":
                        ir["preserve_patterns"].append(child["value"].strip())
            for child in node.get("children", []): find_preserve(child)
        find_preserve(pf["ast"])

    return ir

# ─── IR QUERY ENGINE ──────────────────────────────────────────────────────────

def query_ir(ir: dict, query: str) -> str:
    q = query.strip().lower()

    m = re.match(r"^(show|list|get)\s+(models?|features?|routes?|events?|fields?|rules?|interfaces?|imports?|all)$", q)
    if m:
        type_map = {"model":"model","models":"model","feature":"feature","features":"feature",
                    "route":"route","routes":"route","event":"event","events":"event",
                    "field":"field","fields":"field","rule":"rule","rules":"rule",
                    "interface":"interface","interfaces":"interface"}
        t = type_map.get(m[2])
        if t:
            uids = ir["by_type"].get(t,[])
            if not uids: return f"No {t}s found."
            return "\n".join(
                f'[@{ir["nodes"][uid].get("level","high")}] {ir["nodes"][uid]["type"]} '
                f'"{ir["nodes"][uid].get("name") or ir["nodes"][uid].get("value","")}" '
                f'({ir["nodes"][uid].get("filename","")}) uid:{uid}'
                for uid in uids)
        if m[2] in ("import","imports"):
            if not ir.get("imports"):
                return "No imports resolved yet."
            return "\n".join(f"  {k}: {v}" for k,v in ir["imports"].items())
        if m[2] == "all":
            return "\n".join(f'{uid} → {n["type"]}{" "+n["name"] if n.get("name") else ""}' for uid,n in ir["nodes"].items())

    m = re.match(r"^dep(?:endencies)? of\s+(\w+)$", q)
    if m:
        name  = m[1]
        edges = [e for e in ir["edges"] if name in e["from"].lower()]
        if not edges: return f'No dependencies found for "{name}"'
        return "\n".join(f'{e["from"]} →[{e["type"]}]→ {e["to"]}{" ⚠ UNRESOLVED" if e.get("resolved") is False else ""}' for e in edges)

    m = re.match(r"^(?:used by|dependents of)\s+(\w+)$", q)
    if m:
        name  = m[1]
        edges = [e for e in ir["edges"] if name in e["to"].lower()]
        if not edges: return f'Nothing depends on "{name}"'
        return "\n".join(f'{e["from"]} depends on {e["to"]} via [{e["type"]}]' for e in edges)

    m = re.match(r"^inspect\s+(.+)$", q)
    if m:
        term  = m[1].strip()
        exact = ir["nodes"].get(term)
        if exact: return json.dumps(exact, indent=2, default=str)
        matches = [(uid,n) for uid,n in ir["nodes"].items()
                   if term in (n.get("name") or "").lower() or term in uid.lower()]
        if not matches: return f'No node matching "{term}"'
        return "\n\n".join(f"uid: {uid}\n{json.dumps(n,indent=2,default=str)}" for uid,n in matches)

    if "interface" in q:
        if not ir["interfaces"]:
            return "No interface: blocks declared. Add one to a domain file."
        return "\n".join(
            f"{domain} v{s['version']} — {len(s['models'])} models, {len(s['features'])} features"
            for domain,s in ir["interfaces"].items())

    if "preserve" in q:
        if not ir["preserve_patterns"]:
            return "No preserve patterns declared."
        return "\n".join(f"  - {p}" for p in ir["preserve_patterns"])

    if "global rule" in q or q == "rules":
        return "\n".join(f"{i+1}. {r}" for i,r in enumerate(ir["global_rules"])) or "No global rules."

    if "stack" in q:
        return f'Stack: {ir["stack"] or "not defined"}\nProject: {ir["project_name"] or "unnamed"}\nFiles: {", ".join(ir["files"])}'

    if "edge" in q or "graph" in q:
        if not ir["edges"]: return "No edges."
        return "\n".join(
            f'{e["from"]} →[{e["type"]}{":"+e["key"] if e.get("key") else ""}]→ {e["to"]}'
            f'{" ⚠ UNRESOLVED" if e.get("resolved") is False else ""}' for e in ir["edges"])

    if "domain" in q:
        return "\n".join(f"{d}: {len(uids)} nodes" for d,uids in ir["domains"].items())

    if q.startswith("impact"):
        name   = re.sub(r"^impact (of )?","",q).strip()
        direct = [e for e in ir["edges"] if name in e["to"].lower()]
        if not direct: return f'No dependents for "{name}"'
        indirect = set()
        for e in direct:
            for e2 in ir["edges"]:
                if e2["to"] == e["from"]: indirect.add(e2["from"])
        lines = ["Direct dependents:"] + [f'  {e["from"]} [{e["type"]}]' for e in direct]
        if indirect: lines += ["\nIndirect (2nd-order):"] + [f"  {u}" for u in indirect]
        return "\n".join(lines)

    if "compat" in q:
        # basic compatibility check across interfaces
        issues = []
        for domain, schema in ir["interfaces"].items():
            for bc in schema.get("breaking_changes", []):
                issues.append(f"[{domain} v{schema['version']}] BREAKING: {bc}")
            for dep in schema.get("deprecated", []):
                issues.append(f"[{domain} v{schema['version']}] DEPRECATED: {dep}")
        return "\n".join(issues) if issues else "No breaking changes or deprecations declared."

    return "Unknown query. Try: list models, show interfaces, show preserve, deps of <name>, used by <name>, inspect <name>, impact of <name>, show graph, show stack, show domains, show compat"

def ir_context_summary(ir: dict) -> str:
    mc = len(ir["by_type"].get("model",[]))
    fc = len(ir["by_type"].get("feature",[]))
    rc = len(ir["by_type"].get("route",[]))
    unresolved  = [e for e in ir["edges"] if e.get("resolved") is False]
    rules_text  = "\n".join(f"  - {r}" for r in ir["global_rules"])
    iface_text  = "\n".join(
        f"  {d} v{s['version']}: {', '.join(s['models'].keys()) or 'no public models'}"
        for d,s in ir["interfaces"].items()) if ir["interfaces"] else ""
    return (
        f'PROJECT: {ir["project_name"] or "unnamed"}\n'
        f'STACK: {ir["stack"] or "unspecified"}\n'
        f'FILES: {", ".join(ir["files"])}\n'
        f'NODES: {len(ir["nodes"])} total ({mc} models, {fc} features, {rc} routes)\n'
        f'EDGES: {len(ir["edges"])} ({len(unresolved)} unresolved)\n'
        f'GLOBAL RULES: {len(ir["global_rules"])}\n{rules_text}'
        + (f'\nPUBLIC INTERFACES:\n{iface_text}' if iface_text else '')
        + (f'\nPRESERVE PATTERNS: {", ".join(ir["preserve_patterns"])}' if ir["preserve_patterns"] else '')
    )

# ─── TRANSPILER ───────────────────────────────────────────────────────────────

def build_headers(api_key: str, api_base: str) -> dict:
    if "anthropic.com" in api_base:
        return {"Content-Type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"}
    return {"Content-Type":"application/json","Authorization":f"Bearer {api_key}"}

def build_body(system: str, user_prompt: str, api_base: str) -> dict:
    if "anthropic.com" in api_base:
        return {"model":MODEL,"max_tokens":MAX_TOKENS,"stream":True,"temperature":TEMPERATURE,
                "system":system,"messages":[{"role":"user","content":user_prompt}]}
    return {"model":MODEL,"max_tokens":MAX_TOKENS,"stream":True,"temperature":TEMPERATURE,
            "messages":[{"role":"system","content":system},{"role":"user","content":user_prompt}]}

def parse_output_files(text: str) -> list:
    pattern = re.compile(r"// FILE: ([^\n]+)\n(.*?)(?=// FILE: |\Z)", re.DOTALL)
    files   = [{"path":m[0].strip(),"content":m[1].strip()} for m in pattern.findall(text)]
    if not files and text.strip():
        files = [{"path":"output.txt","content":text.strip()}]
    return files

def transpile_stream(parsed_files: list, ir: dict, target_file: str, api_key: str):
    ir_summary = ir_context_summary(ir)
    target_src = next((f["content"] for f in parsed_files if f["name"] == target_file), "")
    domain     = target_file.replace(".il","")
    domain_uids = ir["domains"].get(domain,[])

    referenced_domains = list(dict.fromkeys(
        e["to"].split(":")[0] for e in ir["edges"]
        if any(e["from"].startswith(domain+":") for uid in domain_uids)
        and not e["to"].startswith("unresolved")
    ))
    referenced_domains = [d for d in referenced_domains if d != domain][:5]

    ref_context = ""
    for rd in referenced_domains:
        rf = next((f for f in parsed_files if f["name"] == rd+".il"), None)
        if rf: ref_context += f"\n// REFERENCED: {rd}.il\n{rf['content']}"

    # include imported interface schemas as context
    iface_context = ""
    for d, schema in ir["interfaces"].items():
        if d != domain:
            iface_context += f"\n// INTERFACE SCHEMA: {d} v{schema['version']}\n"
            iface_context += json.dumps({"models":schema["models"],"features":schema["features"]}, indent=2)

    system = """You are the IntentLang transpiler v0.3. IntentLang (.il) is a structured multi-level intent language.

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

INTERFACE SYSTEM:
- interface: blocks declare the public API surface of a domain
- expose: lists what is public; hide: lists what is private
- imported interfaces provide types and client SDKs for cross-project references

PRESERVE SYSTEM:
- preserve: blocks list file patterns that must not be overwritten
- migrations/* — never regenerate applied migrations
- .env — never overwrite env files

OUTPUT FORMAT:
- Separate each file with: // FILE: path/to/file.ext
- Generate ALL files needed: models, routes, migrations, tests, config
- If domain has interface: block, also generate interface/ output files
- No prose outside code comments
- Never edit generated files — .il is sole source of truth
- Match sophistication to @level"""

    user_prompt = f"""IR SUMMARY (full project):
{ir_summary}

TARGET: {target_file}
{target_src}
{f"REFERENCED FILES:{ref_context}" if ref_context else ""}
{f"IMPORTED INTERFACE SCHEMAS:{iface_context}" if iface_context else ""}

Generate complete implementation. Begin with first file immediately."""

    with httpx.Client(timeout=180) as client:
        with client.stream("POST", API_BASE,
                           headers=build_headers(api_key, API_BASE),
                           json=build_body(system, user_prompt, API_BASE)) as response:
            response.raise_for_status()
            buffer = ""
            for raw_chunk in response.iter_text():
                buffer += raw_chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line.startswith("data: "): continue
                    data = line[6:].strip()
                    if data == "[DONE]": return
                    try:
                        p = json.loads(data)
                        if p.get("type") == "content_block_delta":
                            t = p.get("delta",{}).get("text","")
                            if t: yield t
                        elif p.get("choices"):
                            t = p["choices"][0].get("delta",{}).get("content","")
                            if t: yield t
                    except json.JSONDecodeError:
                        pass

# ─── INTERFACE PUBLISH ────────────────────────────────────────────────────────

def cmd_publish(files: list, ir: dict, domain_arg: str):
    """Generate interface schema + SDK files for a domain."""
    domain = domain_arg.strip().replace(".il","")
    schema = ir["interfaces"].get(domain)

    if not schema:
        console.print(f"[red]No interface: block found in {domain}.il[/]")
        console.print("[dim]Add an interface: block with expose: and version: to declare the public surface.[/]")
        return

    out_base = Path(INTERFACE_DIR) / domain
    out_base.mkdir(parents=True, exist_ok=True)

    # 1. schema.json
    schema_path = out_base / f"{domain}.schema.json"
    schema_path.write_text(json.dumps(schema, indent=2), "utf-8")
    console.print(f"[bright_green]✓[/] {schema_path}")

    # 2. TypeScript types + client
    ts_path = out_base / f"{domain}.client.ts"
    ts_path.write_text(generate_typescript_types(schema), "utf-8")
    console.print(f"[bright_green]✓[/] {ts_path}")

    # 3. Python client
    py_path = out_base / f"{domain}_client.py"
    py_path.write_text(generate_python_client(schema), "utf-8")
    console.print(f"[bright_green]✓[/] {py_path}")

    # 4. OpenAPI spec
    spec      = generate_openapi_spec(schema, ir)
    spec_path = out_base / f"{domain}.openapi.yaml"
    try:
        import yaml
        spec_path.write_text(yaml.dump(spec, default_flow_style=False), "utf-8")
    except ImportError:
        spec_path = out_base / f"{domain}.openapi.json"
        spec_path.write_text(json.dumps(spec, indent=2), "utf-8")
    console.print(f"[bright_green]✓[/] {spec_path}")

    console.print(Panel(
        f"[bright_white]{domain}[/] v[bright_cyan]{schema['version']}[/]\n"
        f"[dim]{len(schema['models'])} public models · {len(schema['features'])} features[/]\n\n"
        f"[dim]Share the [/][bright_white]interface/{domain}/[/][dim] folder with consumers.[/]\n"
        f"[dim]They can reference it in their core.il:[/]\n"
        f"[bright_cyan]  imports:\n    {domain}: ../path/to/interface/{domain}[/]",
        title=f"[bright_green]Interface published[/]",
        border_style="green", box=box.ROUNDED
    ))

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

interface:
  version: 1.0.0
  expose:
    - model User
    - feature Auth
  hide:
    - model Session
    - field User.password

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

  rules:
    - only project members can create or edit tasks
    - only assignee or owner can close tasks""",

    "platform.il": """\
// platform.il — Infrastructure and preserve rules
domain platform:

preserve:
  - migrations/*
  - .env
  - .env.*
  - backend/custom/*

@level: low
config Database:
  engine: postgres 15
  pool_size: 20
  statement_timeout: 30s

@level: mid
config Cache:
  engine: redis 7
  strategy: lru
  max_memory: 512mb

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
    path = Path(directory)
    if not path.exists(): return []
    return [{"name": f.name, "content": f.read_text("utf-8"), "source_dir": str(path.resolve())}
            for f in sorted(path.glob("*.il"))]

def save_il_files(files: list, directory: str):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    for f in files:
        if not f.get("imported"):  # never write back imported files
            (path / f["name"]).write_text(f["content"], "utf-8")

# ─── DISPLAY HELPERS ──────────────────────────────────────────────────────────

def print_header():
    console.print()
    console.print(Panel(
        Text.assemble(
            ("  IntentLang ", "bold bright_magenta"), ("v0.3", "dim magenta"),
            ("  —  Terminal IDE\n", "dim white"),
            ("  Multi-file · IR graph · Interface layer · Git imports", "dim white"),
        ), border_style="bright_magenta", box=box.DOUBLE_EDGE, padding=(0,2)))
    console.print()

def print_ir_summary(ir: dict):
    mc = len(ir["by_type"].get("model",[]))
    fc = len(ir["by_type"].get("feature",[]))
    rc = len(ir["by_type"].get("route",[]))
    unresolved = [e for e in ir["edges"] if e.get("resolved") is False]
    table = Table(box=box.SIMPLE, show_header=False, padding=(0,2))
    table.add_column(style="dim white", no_wrap=True)
    table.add_column(style="bright_white")
    table.add_row("Project",    ir["project_name"] or "unnamed")
    table.add_row("Stack",      str(ir["stack"] or "unspecified"))
    table.add_row("Files",      ", ".join(f for f in ir["files"] if not any(
        x.get("imported") and x["name"]==f for x in [])))
    table.add_row("Nodes",      f'{len(ir["nodes"])} ({mc} models, {fc} features, {rc} routes)')
    table.add_row("Edges",      f'{len(ir["edges"])} ({len(unresolved)} unresolved)')
    table.add_row("Rules",      str(len(ir["global_rules"])))
    if ir["interfaces"]:
        table.add_row("Interfaces", ", ".join(f"{d} v{s['version']}" for d,s in ir["interfaces"].items()))
    if ir["preserve_patterns"]:
        table.add_row("Preserve",   ", ".join(ir["preserve_patterns"][:3]) + ("…" if len(ir["preserve_patterns"])>3 else ""))
    console.print(Panel(table, title="[bright_magenta]IR Summary[/]", border_style="magenta", box=box.ROUNDED))

def print_file_tree(files: list):
    console.print("\n[dim]Loaded files:[/]")
    local    = [f for f in files if not f.get("imported")]
    imported = [f for f in files if f.get("imported")]
    for i, f in enumerate(local):
        prefix = "└─" if i == len(local)-1 and not imported else "├─"
        console.print(f"  [dim]{prefix}[/] [bright_cyan]{f['name']}[/]  [dim]{len(f['content'].splitlines())} lines[/]")
    if imported:
        console.print(f"  [dim]└─ imports ({len(imported)} files)[/]")
        seen = set()
        for f in imported:
            alias = f.get("alias","?")
            if alias not in seen:
                count = sum(1 for x in imported if x.get("alias")==alias)
                console.print(f"     [dim]└─[/] [magenta]{alias}[/]  [dim]{count} file(s)[/]")
                seen.add(alias)
    console.print()

def syntax_preview(content: str, filename: str):
    console.print(Panel(
        Syntax(content, "python", theme="monokai", line_numbers=True, word_wrap=False),
        title=f"[bright_cyan]{filename}[/]", border_style="cyan", box=box.ROUNDED))

# ─── CLI COMMANDS ─────────────────────────────────────────────────────────────

def get_api_key() -> str:
    key = API_KEY.strip()
    if not key: key = os.environ.get("ANTHROPIC_API_KEY","").strip()
    if not key: key = os.environ.get("INTENTLANG_API_KEY","").strip()
    if not key:
        console.print("\n[yellow]No API key found.[/]")
        key = Prompt.ask("[bright_white]Enter your API key[/]", password=True).strip()
    return key

def cmd_transpile(files: list, ir: dict, target: str, api_key: str):
    if not target.endswith(".il"): target += ".il"
    if target not in [f["name"] for f in files]:
        console.print(f"[red]File not found: {target}[/]")
        return
    parsed = [{"name":f["name"],"content":f["content"],
               "ast":parse_intent_lang(f["content"],f["name"])["ast"]} for f in files]
    console.print(f"\n[bright_magenta]Transpiling[/] [bright_cyan]{target}[/] [dim]→ streaming…[/]\n")
    full_text = ""
    try:
        for chunk in transpile_stream(parsed, ir, target, api_key):
            full_text += chunk
            print(chunk, end="", flush=True)
    except httpx.HTTPStatusError as e:
        console.print(f"\n[red]API {e.response.status_code}: {e.response.text}[/]"); return
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/]"); return

    console.print("\n")
    output_files = parse_output_files(full_text)
    if not output_files:
        console.print("[yellow]No FILE: markers in output.[/]"); return

    preserve = ir.get("preserve_patterns", [])
    saved, skipped = save_output_files(output_files, OUTPUT_DIR, preserve)

    lines = [f"[bright_green]✓[/]  [bright_white]{p}[/]" for p in saved]
    if skipped:
        lines += [f"[dim]⊘  {p} (preserved)[/]" for p in skipped]
    console.print(Panel("\n".join(lines),
        title=f"[bright_green]{len(saved)} generated[/]" + (f"[dim], {len(skipped)} preserved[/]" if skipped else ""),
        border_style="green", box=box.ROUNDED))
    console.print(f"\n[dim]Output:[/] [bright_cyan]{Path(OUTPUT_DIR).resolve()}[/]\n")

def cmd_help():
    table = Table(box=box.SIMPLE, show_header=True, header_style="bright_magenta", padding=(0,2))
    table.add_column("Command",     style="bright_cyan",  no_wrap=True)
    table.add_column("Args",        style="yellow",       no_wrap=True)
    table.add_column("Description", style="white")
    commands = [
        ("list",      "",                "Show loaded files and IR summary"),
        ("view",      "<file>",          "Preview a .il file"),
        ("query",     "<q>",             "Query the IR graph"),
        ("transpile", "<file>",          "Generate code from a .il file"),
        ("publish",   "<domain>",        "Generate interface schema + SDK files"),
        ("import",    "update <alias>",  "Re-fetch a git import from source"),
        ("new",       "<name>",          "Create a new .il file"),
        ("edit",      "<file>",          "Open in $EDITOR, auto-reload"),
        ("save",      "",                "Persist .il files to disk"),
        ("load",      "[dir]",           "Load .il files from directory"),
        ("config",    "",                "Show current configuration"),
        ("example",   "",                "Reset to example project"),
        ("help",      "",                "Show this help"),
        ("exit",      "",                "Quit"),
    ]
    for c,a,d in commands: table.add_row(c,a,d)
    console.print(Panel(table, title="[bright_magenta]Commands[/]", border_style="magenta", box=box.ROUNDED))
    console.print("\n[dim]IR query examples:[/]")
    for q in ["list models","show interfaces","show preserve","deps of User",
              "impact of User","inspect Auth","show compat","show graph"]:
        console.print(f"  [dim]›[/] [bright_white]query {q}[/]")
    console.print()

def cmd_config(api_key: str):
    table = Table(box=box.SIMPLE, show_header=False, padding=(0,2))
    table.add_column(style="dim white", no_wrap=True)
    table.add_column(style="bright_white")
    table.add_row("Model",        MODEL)
    table.add_row("API Base",     API_BASE)
    table.add_row("Max Tokens",   str(MAX_TOKENS))
    table.add_row("Temperature",  str(TEMPERATURE))
    table.add_row("API Key",      "✓ set" if api_key else "[red]not set[/]")
    table.add_row("Output Dir",   str(Path(OUTPUT_DIR).resolve()))
    table.add_row("IL Dir",       str(Path(IL_DIR).resolve()))
    table.add_row("Imports Dir",  str(Path(IMPORTS_DIR).resolve()))
    table.add_row("Interface Dir",str(Path(INTERFACE_DIR).resolve()))
    console.print(Panel(table, title="[bright_magenta]Configuration[/]", border_style="magenta", box=box.ROUNDED))

# ─── REPL ─────────────────────────────────────────────────────────────────────

def main():
    print_header()
    api_key = get_api_key()
    console.print(f"[dim]Model:[/] [bright_white]{MODEL}[/]  [dim]API:[/] [bright_white]{API_BASE}[/]\n")

    existing = load_il_files(IL_DIR)
    if existing:
        console.print(f"[dim]Loading from[/] [bright_cyan]{IL_DIR}[/]")
        files = existing
    else:
        console.print("[dim]No .il files found — loading example project.[/]")
        files = [{"name":k,"content":v} for k,v in EXAMPLE_PROJECT.items()]

    # resolve imports declared in core.il — path relative to where files were loaded from
    _src_dir = files[0].get("source_dir", ".") if files else "."
    imported = load_imports(files, _src_dir)
    if imported:
        files = files + imported
        console.print(f"[bright_green]Resolved {len(imported)} imported file(s)[/]")

    def rebuild_ir():
        parsed = []
        for f in files:
            result = parse_intent_lang(f["content"], f["name"])
            parsed.append({"name":f["name"],"content":f["content"],
                           "ast":result["ast"],"errors":result["errors"]})
        return build_ir(parsed)

    ir = rebuild_ir()
    print_file_tree(files)
    print_ir_summary(ir)

    session = PromptSession(history=InMemoryHistory(),
                            style=PTStyle.from_dict({"prompt":"bold #cc88ff"}))
    console.print('[dim]Type [/][bright_white]help[/][dim] for commands.[/]\n')

    while True:
        try:
            raw = session.prompt("il› ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/]"); break

        if not raw: continue
        parts = raw.split(None, 1)
        cmd   = parts[0].lower()
        args  = parts[1] if len(parts) > 1 else ""

        if cmd in ("exit","quit","q"):
            console.print("[dim]Goodbye.[/]"); break

        elif cmd == "help":    cmd_help()
        elif cmd == "list":    print_file_tree(files); print_ir_summary(ir)
        elif cmd == "view":
            name = args.strip()
            if not name.endswith(".il"): name += ".il"
            f = next((f for f in files if f["name"]==name), None)
            if f: syntax_preview(f["content"], f["name"])
            else: console.print(f"[red]Not found: {name}[/]")

        elif cmd == "query":
            if not args.strip():
                console.print("[dim]Usage: query <your query>[/]")
            else:
                console.print(Panel(Text(query_ir(ir, args), style="bright_white"),
                    title="[cyan]Result[/]", border_style="cyan", box=box.ROUNDED))

        elif cmd == "transpile":
            target = args.strip() or (files[0]["name"] if files else "")
            if target: cmd_transpile(files, ir, target, api_key)
            else:      console.print("[red]No files loaded.[/]")

        elif cmd == "publish":
            cmd_publish(files, ir, args)

        elif cmd == "import":
            sub_parts = args.split(None, 1)
            sub = sub_parts[0].lower() if sub_parts else ""
            alias = sub_parts[1].strip() if len(sub_parts) > 1 else ""
            if sub == "update" and alias:
                files = update_git_import(alias, files)
                ir    = rebuild_ir()
                console.print(f"[bright_green]Updated import:[/] [bright_cyan]{alias}[/]")
                print_ir_summary(ir)
            else:
                console.print("[dim]Usage: import update <alias>[/]")

        elif cmd == "new":
            name = args.strip()
            if not name: name = Prompt.ask("File name (without .il)")
            if not name.endswith(".il"): name += ".il"
            if any(f["name"]==name for f in files):
                console.print(f"[yellow]Already exists: {name}[/]")
            else:
                domain  = name.replace(".il","")
                content = f'// {name}\ndomain {domain}:\n  description: ""\n'
                files   = files + [{"name":name,"content":content}]
                ir      = rebuild_ir()
                save_il_files(files, IL_DIR)
                console.print(f"[bright_green]Created:[/] [bright_cyan]{name}[/]")

        elif cmd == "edit":
            name = args.strip()
            if not name.endswith(".il"): name += ".il"
            f = next((f for f in files if f["name"]==name), None)
            if not f:
                console.print(f"[red]Not found: {name}[/]")
            else:
                save_il_files(files, IL_DIR)
                os.system(f'{os.environ.get("EDITOR","nano")} "{Path(IL_DIR)/name}"')
                local = load_il_files(IL_DIR)
                imported_files = [f for f in files if f.get("imported")]
                files = local + imported_files
                ir    = rebuild_ir()
                console.print(f"[bright_green]Reloaded:[/] [bright_cyan]{name}[/]")

        elif cmd == "save":
            save_il_files(files, IL_DIR)
            local_count = sum(1 for f in files if not f.get("imported"))
            console.print(f"[bright_green]Saved {local_count} file(s) to[/] [bright_cyan]{Path(IL_DIR).resolve()}[/]")

        elif cmd == "load":
            directory = args.strip() or IL_DIR
            loaded    = load_il_files(directory)
            if loaded:
                files    = loaded
                _src_dir2 = files[0].get("source_dir", ".") if files else "."
                imported = load_imports(files, _src_dir2)
                if imported: files = files + imported
                ir = rebuild_ir()
                console.print(f"[bright_green]Loaded {len(loaded)} file(s)[/]")
                print_file_tree(files)
                print_ir_summary(ir)
            else:
                console.print(f"[yellow]No .il files in {directory}[/]")

        elif cmd == "config":  cmd_config(api_key)

        elif cmd == "example":
            files = [{"name":k,"content":v} for k,v in EXAMPLE_PROJECT.items()]
            ir    = rebuild_ir()
            console.print("[bright_green]Reset to example project.[/]")
            print_file_tree(files)

        else:
            console.print(f"[red]Unknown:[/] [bright_white]{cmd}[/]  [dim](type help)[/]")

if __name__ == "__main__":
    main()
