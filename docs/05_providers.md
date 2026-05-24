# Providers & Configuration

IntentLang works with any LLM provider that offers a chat completions API. Configure everything in the top of `intentlang.py`.

---

## Config Block

Open `intentlang.py` and edit lines 17–20:

```python
API_KEY    = ""                                        # ← your key
MODEL      = "claude-sonnet-4-20250514"                # ← model
API_BASE   = "https://api.anthropic.com/v1/messages"   # ← endpoint
MAX_TOKENS = 8000                                      # ← output limit
TEMPERATURE = 0.2                                      # ← 0=consistent, 1=creative
```

---

## Anthropic (Default)

Best results for IntentLang. Recommended.

```python
API_KEY  = "sk-ant-..."
MODEL    = "claude-sonnet-4-20250514"   # recommended
API_BASE = "https://api.anthropic.com/v1/messages"
```

**Models:**

| Model | Speed | Quality | Cost | Best for |
|---|---|---|---|---|
| `claude-sonnet-4-20250514` | Fast | Excellent | Medium | Everything — recommended |
| `claude-opus-4-20250514` | Slow | Best | High | Complex multi-domain projects |
| `claude-haiku-4-5-20251001` | Very fast | Good | Low | IR queries, quick iterations |

Get a key: https://console.anthropic.com

---

## xAI (Grok)

OpenAI-compatible API. Works out of the box.

```python
API_KEY  = "xai-..."
MODEL    = "grok-3"
API_BASE = "https://api.x.ai/v1/chat/completions"
```

**Models:**

| Model | Notes |
|---|---|
| `grok-3` | Most capable — recommended |
| `grok-3-mini` | Faster, cheaper |
| `grok-2` | Previous generation |

Get a key: https://console.x.ai

---

## OpenAI

```python
API_KEY  = "sk-..."
MODEL    = "gpt-4o"
API_BASE = "https://api.openai.com/v1/chat/completions"
```

**Models:**

| Model | Notes |
|---|---|
| `gpt-4o` | Best OpenAI option for code generation |
| `gpt-4o-mini` | Faster, cheaper |
| `o3` | Reasoning model — slower but strong on complex logic |

Get a key: https://platform.openai.com

---

## OpenRouter

Access 100+ models through one API key and endpoint. Good for comparing providers.

```python
API_KEY  = "sk-or-..."
MODEL    = "anthropic/claude-sonnet-4"   # or any OpenRouter model string
API_BASE = "https://openrouter.ai/api/v1/chat/completions"
```

Browse models: https://openrouter.ai/models

Popular choices for code generation:
- `anthropic/claude-sonnet-4` — best results
- `google/gemini-2.5-pro` — strong alternative
- `deepseek/deepseek-coder` — good, low cost
- `meta-llama/llama-3.1-70b-instruct` — open model

---

## Google (Gemini)

```python
API_KEY  = "AIza..."
MODEL    = "gemini-2.5-pro"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
```

Note: Google uses the OpenAI-compatible endpoint for the Gemini API. The `/openai/` path is intentional.

Get a key: https://aistudio.google.com

---

## Local Models (Ollama)

Run models locally — no API key required.

```python
API_KEY  = ""                              # not needed
MODEL    = "qwen2.5-coder:32b"            # or any installed model
API_BASE = "http://localhost:11434/api/chat"
```

**Install Ollama:** https://ollama.com

**Recommended models for code generation:**

```bash
ollama pull qwen2.5-coder:32b      # best local code model
ollama pull deepseek-coder-v2:16b  # strong, faster
ollama pull llama3.1:70b           # general purpose, large
ollama pull codellama:34b          # code-focused
```

**Note on local models:** Smaller local models (7B–13B) often struggle with multi-file context and complex cross-domain generation. 32B+ models perform much better with IntentLang's structured input. The IR summary format helps smaller models significantly — they receive structure rather than ambiguous prose.

---

## Environment Variables

Instead of hardcoding your key in the Python file, use environment variables:

```bash
# .env or shell
export ANTHROPIC_API_KEY=sk-ant-...
export INTENTLANG_API_KEY=sk-ant-...   # alternative name
```

IntentLang checks these automatically if `API_KEY` in the config is blank:

```python
API_KEY = ""   # leave blank — reads from environment
```

Priority order:
1. `API_KEY` in config block (if non-empty)
2. `ANTHROPIC_API_KEY` environment variable
3. `INTENTLANG_API_KEY` environment variable
4. Prompted at startup

---

## Switching Providers Mid-Session

The config is read at startup. To switch providers, edit `intentlang.py` and restart:

```bash
# Edit config block, then:
python intentlang.py
```

---

## Token Limits by Provider

Different providers have different context windows. IntentLang's IR summary is typically 200–500 tokens. A large `.il` file with referenced domains might be 2,000–4,000 tokens. The output is usually 2,000–6,000 tokens.

| Provider | Context Window | Recommended MAX_TOKENS |
|---|---|---|
| Claude Sonnet 4 | 200K | 8000 |
| Claude Opus 4 | 200K | 8000 |
| GPT-4o | 128K | 8000 |
| Grok 3 | 131K | 8000 |
| Gemini 2.5 Pro | 1M | 8000 |
| Ollama qwen2.5:32b | 32K | 4000 |
| Ollama llama3.1:70b | 128K | 6000 |

If you're getting truncated output, increase `MAX_TOKENS`. If you're getting slow responses on a large project, reduce it or split your `.il` into smaller domain files.

---

## Cost Estimates

Rough cost per transpile call (varies by file size):

| Provider / Model | Per transpile |
|---|---|
| Claude Haiku 4.5 | ~$0.001 |
| Claude Sonnet 4 | ~$0.01–0.03 |
| Claude Opus 4 | ~$0.05–0.15 |
| GPT-4o | ~$0.02–0.05 |
| GPT-4o mini | ~$0.002 |
| Grok 3 | ~$0.01–0.03 |
| Ollama (local) | Free |

For a medium project (4–5 domain files), expect 5–10 transpile calls to get the full implementation. Total cost with Sonnet: $0.05–0.30 for a complete project.

---

## Windows Note

If you see a color format error on startup (`ValueError: Wrong color format 'ansibright'`), find this line in `intentlang.py`:

```python
style=PTStyle.from_dict({"prompt": "ansibright magenta bold"})
```

Change to:

```python
style=PTStyle.from_dict({"prompt": "bold #cc88ff"})
```

This is a `prompt_toolkit` compatibility issue on Windows with certain terminal emulators.