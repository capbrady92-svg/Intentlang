// ═══════════════════════════════════════════════════════════════════════════════
// INTENTLANG — CONFIG & ENTRY POINT
// ═══════════════════════════════════════════════════════════════════════════════
//
// This is the single place to configure IntentLang.
// Import this into intentlang-v2.jsx (or any future version) and it will
// pick up all settings automatically.
//
// Usage:
//   import { config, getModel, getHeaders, MODELS } from "./intentlang.config.js"
// ───────────────────────────────────────────────────────────────────────────────

// ─── API KEY ──────────────────────────────────────────────────────────────────
// Set your Anthropic API key here, or leave as "" to be prompted in the UI.
// Never commit a real key to version control — use an env variable in production.

const API_KEY = "";

// ─── MODEL SELECTION ──────────────────────────────────────────────────────────
// Pick one of the presets below, or define your own model string.

export const MODELS = {
  // Anthropic
  SONNET:       "claude-sonnet-4-20250514",   // recommended — best balance
  OPUS:         "claude-opus-4-20250514",      // most capable, slower
  HAIKU:        "claude-haiku-4-5-20251001",   // fastest, lowest cost

  // OpenAI  (requires changing API_BASE and headers below)
  GPT4O:        "gpt-4o",
  GPT4O_MINI:   "gpt-4o-mini",
  O3:           "o3",

  // Google  (requires changing API_BASE and headers below)
  GEMINI_PRO:   "gemini-2.5-pro",
  GEMINI_FLASH: "gemini-2.0-flash",

  // Local / Ollama  (requires OLLAMA base url below)
  LLAMA3:       "llama3.1:70b",
  QWEN:         "qwen2.5-coder:32b",
  DEEPSEEK:     "deepseek-coder-v2:16b",
};

// ─── ACTIVE CONFIG ────────────────────────────────────────────────────────────

export const config = {

  // ── Model ───────────────────────────────────────────────────────────────────
  model: MODELS.SONNET,        // ← change this to switch models

  // ── API base URL ────────────────────────────────────────────────────────────
  // Anthropic (default):
  apiBase: "https://api.anthropic.com/v1/messages",
  // OpenAI:
  // apiBase: "https://api.openai.com/v1/chat/completions",
  // Ollama (local):
  // apiBase: "http://localhost:11434/api/chat",
  // OpenRouter (multi-provider):
  // apiBase: "https://openrouter.ai/api/v1/chat/completions",

  // ── Token limits ────────────────────────────────────────────────────────────
  maxTokens: 8000,             // max output tokens per transpile call
  maxContextTokens: 180000,    // context window cap (used to truncate IR summary)

  // ── Streaming ───────────────────────────────────────────────────────────────
  stream: true,                // set false to disable streaming output

  // ── Transpiler behaviour ────────────────────────────────────────────────────
  transpiler: {
    // How many files to include as cross-domain context when transpiling
    maxReferencedDomains: 5,

    // Include IR summary in every transpile call
    includeIRSummary: true,

    // Include global rules preamble
    includeGlobalRules: true,

    // File separator token used in output — change if your model uses different markers
    fileSeparator: "// FILE:",

    // Temperature (0 = deterministic, 1 = creative) — lower = more consistent code
    temperature: 0.2,
  },

  // ── Project defaults ────────────────────────────────────────────────────────
  project: {
    defaultStack:   "react + fastapi + postgres",
    defaultPattern: "REST",
    defaultAuth:    "jwt",
    // Default global rules injected into every project that doesn't define its own
    defaultRules: [
      "all models get id (uuid pk), created_at, updated_at",
      "all errors return { code, message, trace_id }",
    ],
  },

  // ── UI preferences ──────────────────────────────────────────────────────────
  ui: {
    theme:           "dark",          // "dark" | "light" (light not yet implemented)
    fontSize:        12.5,            // editor font size in px
    lineHeight:      1.75,            // editor line height
    tabSize:         2,               // spaces per indent level
    showStatusBar:   true,
    showLevelBadges: true,            // show @level badges in IR explorer
    maxQueryHistory: 10,              // how many past queries to keep
  },

};

// ─── HELPERS ──────────────────────────────────────────────────────────────────
// These are consumed by the transpiler — no need to edit unless adding a new provider.

/**
 * Returns the active API key.
 * Priority: config > env variable > empty string (prompts UI input).
 */
export function getApiKey() {
  return API_KEY
    || (typeof process !== "undefined" && process.env?.INTENTLANG_API_KEY)
    || (typeof import.meta !== "undefined" && import.meta.env?.VITE_INTENTLANG_API_KEY)
    || "";
}

/**
 * Returns the model string to use for a given call type.
 * callType: "transpile" | "query" | "explain"
 */
export function getModel(callType = "transpile") {
  // Could use different models for different call types if desired
  return config.model;
}

/**
 * Returns request headers for the configured provider.
 * Detects provider from apiBase URL.
 */
export function getHeaders(apiKey) {
  const base = config.apiBase;
  if (base.includes("anthropic.com")) {
    return {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    };
  }
  if (base.includes("openai.com") || base.includes("openrouter.ai")) {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${apiKey}`,
    };
  }
  if (base.includes("localhost:11434")) {
    // Ollama — no auth needed
    return { "Content-Type": "application/json" };
  }
  // fallback
  return {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${apiKey}`,
  };
}

/**
 * Normalises the request body for different provider APIs.
 * Anthropic and OpenAI have different shapes.
 */
export function buildRequestBody({ system, userPrompt, apiKey }) {
  const base = config.apiBase;
  const model = getModel("transpile");

  if (base.includes("anthropic.com")) {
    return {
      model,
      max_tokens: config.maxTokens,
      stream: config.stream,
      temperature: config.transpiler.temperature,
      system,
      messages: [{ role: "user", content: userPrompt }],
    };
  }

  // OpenAI / OpenRouter / Ollama shape
  return {
    model,
    max_tokens: config.maxTokens,
    stream: config.stream,
    temperature: config.transpiler.temperature,
    messages: [
      { role: "system", content: system },
      { role: "user",   content: userPrompt },
    ],
  };
}

/**
 * Extracts text chunks from SSE stream lines.
 * Handles Anthropic and OpenAI stream formats.
 */
export function extractChunk(line) {
  if (!line.startsWith("data: ")) return null;
  const data = line.slice(6).trim();
  if (data === "[DONE]") return null;
  try {
    const parsed = JSON.parse(data);
    // Anthropic format
    if (parsed.type === "content_block_delta" && parsed.delta?.text) {
      return parsed.delta.text;
    }
    // OpenAI format
    if (parsed.choices?.[0]?.delta?.content) {
      return parsed.choices[0].delta.content;
    }
  } catch {}
  return null;
}

export default config;
