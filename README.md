# IntentLang (.il)

> A structured, multi-level intent language that gives AI coding agents the context, memory, and constraints they need to generate reliable code — at any abstraction level, across any stack.

---

## Quick Start

### 1. Install dependencies

```bash
pip install httpx rich prompt_toolkit
```

### 2. Set your API key

Open `intentlang.py` and edit line 17:

```python
API_KEY = "sk-ant-your-key-here"
```

Supports Anthropic, OpenAI, xAI (Grok), OpenRouter, and local Ollama — see [docs/05-providers.md](docs/05-providers.md).

### 3. Run

```bash
python intentlang.py
```

### 4. Try it immediately

```
il› load ./examples/url-shortener
il› list
il› transpile links.il
```

Watch it generate a complete FastAPI + Postgres + Redis URL shortener from a 60-line `.il` file.

---

## What Is IntentLang?

IntentLang is an **intermediate intent language** — not a programming language, not prose specs, not pseudocode. It sits between human intent and generated code.

```
You write .il  →  Parser builds IR  →  AI transpiles to any target stack
```

The `.il` file is your **only source of truth**. You never edit generated code. If something needs to change, you change the `.il` and regenerate. This discipline is the entire value proposition.

---

## The Problem It Solves

AI coding tools accept natural language prompts. Natural language is the most ambiguous communication format humans have. Every underspecified prompt is a micro-decision silently outsourced to a model with no memory of what it decided last time.

The result: code that looks right, runs in dev, and silently accumulates architectural decisions nobody made consciously — at the speed of AI generation.

IntentLang fixes the input side. It gives the AI:

- A structured, parseable description of your system
- A queryable IR graph of all dependencies and relationships
- Global rules that propagate everywhere automatically
- Precise abstraction level instructions from architecture down to assembly

The output is reliable because the input is precise.

---

## CLI Commands

```
il› list                        show loaded files and IR summary
il› view <file>                 preview a .il file with syntax highlighting
il› query <q>                   query the IR graph
il› transpile <file>            generate code from a .il file
il› new <name>                  create a new .il file
il› edit <file>                 open in $EDITOR, auto-reload on save
il› save                        persist .il files to ./intent/
il› load [dir]                  load .il files from a directory
il› config                      show current configuration
il› example                     reset to built-in example project
il› help                        show all commands
il› exit                        quit
```

---

## IR Query Commands

```
list models                     all models across all files
list features                   all features
list routes                     all routes
list all                        every node in the IR

show global rules               rules from core.il
show stack                      stack, project name, files
show graph                      all dependency edges
show domains                    domain → node count

deps of <name>                  what does this depend on?
used by <name>                  what depends on this?
impact of <name>                direct + indirect dependents
inspect <name>                  full IR node as JSON
```

---

## Example Projects

```bash
python examples.py              # list available projects
python examples.py url-shortener
python examples.py all          # write all 5 projects
```

| Project | Stack | Complexity |
|---|---|---|
| url-shortener | fastapi + postgres + redis | Small — start here |
| expense-tracker | react + express + sqlite | Medium |
| realtime-chat | node + socket.io + redis | Medium, WebSocket events |
| file-hasher-cli | rust | No web, shows @level:asm |
| saas-starter | next.js + fastapi + stripe | Large, multi-domain |

---

## Documentation

| File | Contents |
|---|---|
| [docs/01-language.md](docs/01-language.md) | Full language reference — every keyword, syntax, and directive |
| [docs/02-projects.md](docs/02-projects.md) | Multi-file projects, domains, core.il, cross-file references |
| [docs/03-ir.md](docs/03-ir.md) | The IR graph — how it works, how to query it, impact analysis |
| [docs/04-transpiler.md](docs/04-transpiler.md) | How transpilation works, prompting strategy, output format |
| [docs/05-providers.md](docs/05-providers.md) | Configuring Anthropic, OpenAI, Grok, Ollama and others |

---

## Design Principles

**Never edit generated code.** The `.il` file is the source of truth. Editing generated code creates two sources of truth and destroys the value. Change the `.il` and regenerate.

**Structure is not overhead — it's the product.** Every `rule:`, every `@level:`, every `constraint:` is load-bearing. The richer the `.il`, the more reliable the output.

**The IR is the memory.** The compiled IR gives the AI complete project context without flooding it with source code. It rebuilds on every change.

**Levels are instructions, not labels.** `@level:asm` tells the transpiler to emit low-level code. Use it intentionally.

**Cross-file references are contracts.** `@identity/User!` declares that User must exist in the identity domain. It fails loudly if it doesn't.

---

## Roadmap

- [ ] Watch mode — auto-regenerate on `.il` save
- [ ] IR diff — what changed between versions
- [ ] Incremental transpilation — only regenerate changed nodes
- [ ] LSP — editor integration for VS Code
- [ ] `inline:` blocks — escape hatch for literal code injection
- [ ] `intentlang check` — validate all refs without transpiling
- [ ] Multi-target — same `.il` → multiple output stacks simultaneously

---

*IntentLang v0.2.0 — the source of truth is the intent, not the code.*
