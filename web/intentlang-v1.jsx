import { useState, useCallback, useRef, useEffect } from "react";

// ─── INTENTLANG PARSER ───────────────────────────────────────────────────────

function parseIntentLang(source) {
  const lines = source.split("\n");
  const errors = [];
  const root = { type: "root", children: [] };
  const stack = [{ node: root, indent: -1 }];

  let lineNum = 0;
  for (const raw of lines) {
    lineNum++;
    if (!raw.trim() || raw.trim().startsWith("//")) continue;

    const indent = raw.search(/\S/);
    const content = raw.trim();

    // pop stack to find parent
    while (stack.length > 1 && stack[stack.length - 1].indent >= indent) {
      stack.pop();
    }
    const parent = stack[stack.length - 1].node;

    // parse node
    const node = parseLine(content, lineNum, errors);
    if (node) {
      if (!parent.children) parent.children = [];
      parent.children.push(node);
      if (node.block) {
        stack.push({ node, indent });
      }
    }
  }

  return { ast: root, errors };
}

function parseLine(content, lineNum, errors) {
  // app / service / module declarations
  const blockDecl = content.match(/^(app|service|module|feature|model|route|rule|event|state|component|page|api|auth|db)\s+(\w[\w.]*)\s*:?$/);
  if (blockDecl) {
    return { type: blockDecl[1], name: blockDecl[2], block: true, children: [], line: lineNum };
  }

  // anonymous block keywords
  const anonBlock = content.match(/^(rules?|config|schema|props|actions?|effects?|guards?|meta)\s*:$/);
  if (anonBlock) {
    return { type: anonBlock[1].replace(/:$/, ""), block: true, children: [], line: lineNum };
  }

  // key: value pairs
  const kv = content.match(/^([\w.]+)\s*:\s*(.+)$/);
  if (kv) {
    return { type: "property", key: kv[1], value: parseValue(kv[2].trim()), line: lineNum };
  }

  // bare rule / constraint lines (starting with -)
  if (content.startsWith("-") || content.startsWith("*")) {
    return { type: "rule", value: content.slice(1).trim(), line: lineNum };
  }

  // field definitions: name (type, modifier, ...)
  const field = content.match(/^(\w+)\s*\(([^)]+)\)$/);
  if (field) {
    const mods = field[2].split(",").map(s => s.trim());
    return { type: "field", name: field[1], modifiers: mods, line: lineNum };
  }

  // arrow relations: name -> target
  const arrow = content.match(/^(\w+)\s*->\s*(\w+)$/);
  if (arrow) {
    return { type: "relation", name: arrow[1], target: arrow[2], line: lineNum };
  }

  errors.push({ line: lineNum, message: `Unrecognized syntax: "${content}"` });
  return { type: "unknown", raw: content, line: lineNum };
}

function parseValue(val) {
  if (val === "true") return true;
  if (val === "false") return false;
  if (!isNaN(val)) return Number(val);
  if (val.startsWith("[") && val.endsWith("]")) {
    return val.slice(1, -1).split(",").map(v => v.trim());
  }
  return val;
}

// ─── AST PRETTY PRINTER ──────────────────────────────────────────────────────

function astToDisplay(node, depth = 0) {
  const pad = "  ".repeat(depth);
  if (!node) return "";
  if (node.type === "root") {
    return (node.children || []).map(c => astToDisplay(c, depth)).join("\n");
  }
  let label = "";
  if (node.type === "property") {
    const val = Array.isArray(node.value) ? node.value.join(", ") : String(node.value);
    return `${pad}<prop> ${node.key}: ${val}`;
  }
  if (node.type === "field") {
    return `${pad}<field> ${node.name} [${node.modifiers.join(", ")}]`;
  }
  if (node.type === "relation") {
    return `${pad}<rel> ${node.name} → ${node.target}`;
  }
  if (node.type === "rule") {
    return `${pad}<rule> ${node.value}`;
  }
  if (node.type === "unknown") {
    return `${pad}<??> ${node.raw}`;
  }
  label = `${pad}<${node.type}> ${node.name || ""}`;
  const children = (node.children || []).map(c => astToDisplay(c, depth + 1)).join("\n");
  return children ? `${label}\n${children}` : label;
}

// ─── CLAUDE TRANSPILER ───────────────────────────────────────────────────────

async function transpile(source, ast, targetHint, onChunk) {
  const astSummary = astToDisplay(ast);

  const systemPrompt = `You are the IntentLang transpiler. IntentLang is a structured, indentation-based language for expressing software intent. You receive:
1. The raw IntentLang source
2. Its parsed AST summary

Your job: generate complete, production-ready code in the target stack specified in the file (look for "stack:" property). If no stack is specified, infer the best stack from context.

Rules:
- Output ONLY code files, separated by: // FILE: path/to/file.ext
- No explanations outside of code comments
- Generate all files needed to run the described system
- Respect every constraint, rule, and relationship in the IntentLang
- Add sensible defaults where the IntentLang is silent
- Keep code clean, typed where applicable, and production-grade`;

  const userPrompt = `IntentLang Source:
\`\`\`
${source}
\`\`\`

Parsed AST:
\`\`\`
${astSummary}
\`\`\`

Generate the complete implementation. Start immediately with the first file.`;

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 8000,
      stream: true,
      system: systemPrompt,
      messages: [{ role: "user", content: userPrompt }]
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim();
        if (data === "[DONE]") return;
        try {
          const parsed = JSON.parse(data);
          if (parsed.type === "content_block_delta" && parsed.delta?.text) {
            onChunk(parsed.delta.text);
          }
        } catch {}
      }
    }
  }
}

// ─── FILE PARSER (for output display) ────────────────────────────────────────

function parseOutputFiles(text) {
  const fileRegex = /\/\/ FILE: ([^\n]+)\n([\s\S]*?)(?=\/\/ FILE: |$)/g;
  const files = [];
  let match;
  while ((match = fileRegex.exec(text)) !== null) {
    files.push({ path: match[1].trim(), content: match[2].trim() });
  }
  if (files.length === 0 && text.trim()) {
    files.push({ path: "output.txt", content: text.trim() });
  }
  return files;
}

// ─── SYNTAX HIGHLIGHTER ──────────────────────────────────────────────────────

function highlight(code) {
  const keywords = ["app", "service", "module", "feature", "model", "route", "rule", "event",
    "state", "component", "page", "api", "auth", "db", "config", "schema", "props",
    "actions", "effects", "guards", "meta", "rules"];
  const types = ["str", "int", "float", "bool", "uuid", "date", "datetime", "json", "list", "map"];
  const modifiers = ["required", "optional", "pk", "fk", "unique", "indexed", "default", "nullable",
    "readonly", "private", "public", "protected", "async", "sync"];

  return code
    .split("\n")
    .map(line => {
      let hl = "";
      // comment
      if (line.trimStart().startsWith("//")) {
        return `<span class="il-comment">${escHtml(line)}</span>`;
      }
      // leading indent preserved
      const indent = line.match(/^(\s*)/)[1];
      const rest = line.slice(indent.length);

      let processed = escHtml(rest);

      // block declarations
      processed = processed.replace(
        new RegExp(`\\b(${keywords.join("|")})\\b`, "g"),
        '<span class="il-kw">$1</span>'
      );
      // types
      processed = processed.replace(
        new RegExp(`\\b(${types.join("|")})\\b`, "g"),
        '<span class="il-type">$1</span>'
      );
      // modifiers
      processed = processed.replace(
        new RegExp(`\\b(${modifiers.join("|")})\\b`, "g"),
        '<span class="il-mod">$1</span>'
      );
      // property keys
      processed = processed.replace(
        /^(<span[^>]*>)?(\w+)(<\/span>)?(\s*:)/,
        (m, s1, key, s2, colon) => {
          if (s1) return m;
          return `<span class="il-key">${key}</span>${colon}`;
        }
      );
      // arrows
      processed = processed.replace(/-&gt;/g, '<span class="il-arrow">→</span>');
      // strings
      processed = processed.replace(/"([^"]*)"/g, '<span class="il-str">"$1"</span>');
      // numbers
      processed = processed.replace(/\b(\d+)\b/g, '<span class="il-num">$1</span>');

      return indent + processed;
    })
    .join("\n");
}

function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ─── LANGUAGE DETECTION (for output) ─────────────────────────────────────────

function detectLang(path) {
  if (path.endsWith(".ts") || path.endsWith(".tsx")) return "typescript";
  if (path.endsWith(".js") || path.endsWith(".jsx")) return "javascript";
  if (path.endsWith(".py")) return "python";
  if (path.endsWith(".go")) return "go";
  if (path.endsWith(".rs")) return "rust";
  if (path.endsWith(".sql")) return "sql";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".yaml") || path.endsWith(".yml")) return "yaml";
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".html")) return "html";
  return "text";
}

// ─── EXAMPLE .il FILES ───────────────────────────────────────────────────────

const EXAMPLES = {
  "Todo App": `// TodoApp.il — A simple full-stack todo application
app TodoApp:
  stack: react + express + postgres
  pattern: REST
  auth: jwt

  model User:
    id (uuid, pk)
    email (str, required, unique)
    password (str, required, private)
    name (str, required)
    created_at (datetime, default now)

  model Task:
    id (uuid, pk)
    title (str, required)
    description (str, optional)
    done (bool, default false)
    due_date (date, optional)
    owner -> User
    created_at (datetime, default now)

  feature Auth:
    route POST /register:
      input: email, password, name
      action: create User
      returns: { token, user }

    route POST /login:
      input: email, password
      action: verify credentials
      returns: { token, user }
      error: if invalid -> 401 "Invalid credentials"

  feature Tasks:
    route GET /tasks:
      auth: required
      action: fetch Tasks where owner = current_user
      returns: Task[]

    route POST /tasks:
      auth: required
      input: title, description?, due_date?
      action: create Task, assign owner = current_user
      returns: Task

    route PATCH /tasks/:id:
      auth: required
      input: title?, description?, done?, due_date?
      action: update Task where id = :id, owner = current_user
      returns: Task
      error: if not found -> 404

    route DELETE /tasks/:id:
      auth: required
      action: delete Task where id = :id, owner = current_user
      error: if not found -> 404

  rules:
    - all endpoints require auth unless specified
    - all errors return { code, message }
    - passwords must be hashed with bcrypt
    - tokens expire after 7 days`,

  "SaaS API": `// SaasAPI.il — Multi-tenant SaaS backend
service BillingAPI:
  stack: python + fastapi + postgres
  pattern: REST + webhooks
  auth: api_key + jwt

  model Organization:
    id (uuid, pk)
    name (str, required)
    slug (str, required, unique)
    plan (str, default "free")
    stripe_id (str, optional)

  model Member:
    id (uuid, pk)
    email (str, required)
    role (str, default "member")
    org -> Organization

  model Subscription:
    id (uuid, pk)
    org -> Organization
    plan (str, required)
    status (str, default "active")
    current_period_end (datetime)

  api Billing:
    route POST /subscriptions:
      input: org_id, plan
      action: create Stripe checkout session
      returns: { checkout_url }

    route POST /webhooks/stripe:
      auth: stripe_signature
      action: handle Stripe events
      events: checkout.completed, subscription.updated, subscription.deleted

    route GET /subscriptions/:org_id:
      auth: required
      action: fetch Subscription for org
      returns: Subscription

  rules:
    - rate limit: 100 requests per minute per api_key
    - all mutations are logged to audit_log
    - free plan limited to 3 members
    - paid plan unlimited members`,

  "Realtime Chat": `// Chat.il — Realtime chat application
app ChatApp:
  stack: react + node + socket.io + redis + postgres
  pattern: websocket + REST

  model Room:
    id (uuid, pk)
    name (str, required)
    type (str, default "public")
    created_by -> User

  model Message:
    id (uuid, pk)
    content (str, required)
    room -> Room
    sender -> User
    created_at (datetime, default now)
    edited (bool, default false)

  model User:
    id (uuid, pk)
    username (str, required, unique)
    avatar (str, optional)
    status (str, default "offline")

  feature Rooms:
    route GET /rooms:
      auth: required
      action: fetch public Rooms + joined Rooms
      returns: Room[]

    route POST /rooms:
      auth: required
      input: name, type?
      action: create Room
      returns: Room

  feature Messaging:
    event join_room:
      input: room_id
      action: subscribe user to room channel

    event send_message:
      input: room_id, content
      action: persist Message, broadcast to room
      broadcast: message_received

    event typing:
      input: room_id
      broadcast: user_typing to room, exclude sender

  rules:
    - messages cached in redis for 24h
    - max message length 2000 chars
    - rooms persist last 1000 messages`
};

// ─── MAIN COMPONENT ──────────────────────────────────────────────────────────

export default function IntentLangIDE() {
  const [source, setSource] = useState(EXAMPLES["Todo App"]);
  const [activeTab, setActiveTab] = useState("editor");
  const [astOutput, setAstOutput] = useState("");
  const [parseErrors, setParseErrors] = useState([]);
  const [transpiling, setTranspiling] = useState(false);
  const [rawOutput, setRawOutput] = useState("");
  const [outputFiles, setOutputFiles] = useState([]);
  const [activeFile, setActiveFile] = useState(0);
  const [showExamples, setShowExamples] = useState(false);
  const [parseResult, setParseResult] = useState(null);
  const textareaRef = useRef(null);
  const outputRef = useRef(null);
  const rawRef = useRef("");

  // live parse on source change
  useEffect(() => {
    const { ast, errors } = parseIntentLang(source);
    setParseErrors(errors);
    setAstOutput(astToDisplay(ast));
    setParseResult({ ast, errors });
  }, [source]);

  const handleTranspile = useCallback(async () => {
    if (!parseResult) return;
    setTranspiling(true);
    setRawOutput("");
    setOutputFiles([]);
    rawRef.current = "";
    setActiveTab("output");

    try {
      await transpile(source, parseResult.ast, null, (chunk) => {
        rawRef.current += chunk;
        setRawOutput(rawRef.current);
        const files = parseOutputFiles(rawRef.current);
        setOutputFiles(files);
        if (outputRef.current) {
          outputRef.current.scrollTop = outputRef.current.scrollHeight;
        }
      });
    } catch (e) {
      setRawOutput("// Error: " + e.message);
    } finally {
      setTranspiling(false);
    }
  }, [source, parseResult]);

  const handleKeyDown = (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const ta = textareaRef.current;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newVal = source.substring(0, start) + "  " + source.substring(end);
      setSource(newVal);
      setTimeout(() => { ta.selectionStart = ta.selectionEnd = start + 2; }, 0);
    }
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      handleTranspile();
    }
  };

  const highlighted = highlight(source);
  const hasErrors = parseErrors.length > 0;

  return (
    <div style={{
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
      background: "#0a0a0f",
      color: "#e2e2f0",
      minHeight: "100vh",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden"
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Syne:wght@700;800&display=swap');

        * { box-sizing: border-box; margin: 0; padding: 0; }

        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #0a0a0f; }
        ::-webkit-scrollbar-thumb { background: #2a2a3f; border-radius: 3px; }

        .il-kw   { color: #7c6aff; font-weight: 600; }
        .il-type { color: #38d9a9; }
        .il-mod  { color: #ff9f43; }
        .il-key  { color: #74c0fc; }
        .il-str  { color: #a9e34b; }
        .il-num  { color: #ff6b6b; }
        .il-arrow{ color: #ff6b6b; }
        .il-comment { color: #4a4a6a; font-style: italic; }

        .tab-btn {
          background: none;
          border: none;
          color: #555577;
          padding: 8px 16px;
          font-family: inherit;
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          cursor: pointer;
          border-bottom: 2px solid transparent;
          transition: all 0.15s;
        }
        .tab-btn:hover { color: #9999cc; }
        .tab-btn.active { color: #7c6aff; border-bottom-color: #7c6aff; }

        .transpile-btn {
          background: linear-gradient(135deg, #7c6aff, #a855f7);
          border: none;
          color: #fff;
          padding: 8px 20px;
          font-family: inherit;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          cursor: pointer;
          border-radius: 4px;
          transition: all 0.2s;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .transpile-btn:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 20px rgba(124, 106, 255, 0.4);
        }
        .transpile-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .editor-wrap {
          position: relative;
          flex: 1;
          overflow: hidden;
        }
        .editor-highlight {
          position: absolute;
          top: 0; left: 0; right: 0; bottom: 0;
          padding: 20px;
          font-size: 13px;
          line-height: 1.7;
          white-space: pre;
          overflow: auto;
          pointer-events: none;
          tab-size: 2;
        }
        .editor-textarea {
          position: absolute;
          top: 0; left: 0; right: 0; bottom: 0;
          padding: 20px;
          font-size: 13px;
          line-height: 1.7;
          background: transparent;
          color: transparent;
          caret-color: #7c6aff;
          border: none;
          outline: none;
          resize: none;
          font-family: inherit;
          tab-size: 2;
          white-space: pre;
          overflow: auto;
        }

        .file-tab {
          background: none;
          border: none;
          border-bottom: 2px solid transparent;
          color: #555577;
          padding: 6px 14px;
          font-family: inherit;
          font-size: 11px;
          cursor: pointer;
          white-space: nowrap;
          transition: all 0.15s;
        }
        .file-tab:hover { color: #9999cc; }
        .file-tab.active { color: #38d9a9; border-bottom-color: #38d9a9; }

        .ast-out {
          padding: 20px;
          font-size: 12px;
          line-height: 1.8;
          color: #7777aa;
          white-space: pre;
          overflow: auto;
          height: 100%;
        }
        .ast-out .type { color: #7c6aff; }
        .ast-out .name { color: #74c0fc; }

        .example-btn {
          background: none;
          border: 1px solid #2a2a3f;
          color: #7777aa;
          padding: 6px 12px;
          font-family: inherit;
          font-size: 11px;
          cursor: pointer;
          border-radius: 3px;
          transition: all 0.15s;
        }
        .example-btn:hover { border-color: #7c6aff; color: #e2e2f0; }

        .error-badge {
          background: #ff4444;
          color: white;
          font-size: 10px;
          padding: 1px 6px;
          border-radius: 10px;
          margin-left: 6px;
        }

        .pulse {
          display: inline-block;
          width: 8px; height: 8px;
          background: #7c6aff;
          border-radius: 50%;
          animation: pulse 1s ease-in-out infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.7); }
        }

        .code-output {
          padding: 20px;
          font-size: 12px;
          line-height: 1.7;
          color: #c9d1d9;
          white-space: pre;
          overflow: auto;
          height: 100%;
          tab-size: 2;
        }

        .lang-badge {
          background: #1a1a2e;
          color: #7c6aff;
          font-size: 10px;
          padding: 2px 8px;
          border-radius: 3px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .status-dot {
          width: 6px; height: 6px;
          border-radius: 50%;
          display: inline-block;
        }
      `}</style>

      {/* Header */}
      <div style={{
        background: "#0d0d1a",
        borderBottom: "1px solid #1a1a2e",
        padding: "0 20px",
        display: "flex",
        alignItems: "center",
        gap: "20px",
        height: "52px",
        flexShrink: 0
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            fontFamily: "'Syne', sans-serif",
            fontWeight: 800,
            fontSize: "16px",
            letterSpacing: "-0.02em",
            background: "linear-gradient(135deg, #7c6aff, #a855f7)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent"
          }}>IntentLang</div>
          <div style={{ color: "#2a2a4a", fontSize: "12px" }}>.il</div>
        </div>

        <div style={{ display: "flex", gap: "2px", flex: 1 }}>
          {["editor", "ast", "output"].map(tab => (
            <button
              key={tab}
              className={`tab-btn ${activeTab === tab ? "active" : ""}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
              {tab === "editor" && hasErrors && (
                <span className="error-badge">{parseErrors.length}</span>
              )}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <div style={{ position: "relative" }}>
            <button
              className="example-btn"
              onClick={() => setShowExamples(!showExamples)}
            >
              Examples ▾
            </button>
            {showExamples && (
              <div style={{
                position: "absolute",
                top: "100%",
                right: 0,
                marginTop: "4px",
                background: "#0d0d1a",
                border: "1px solid #2a2a3f",
                borderRadius: "4px",
                overflow: "hidden",
                zIndex: 100,
                minWidth: "160px"
              }}>
                {Object.keys(EXAMPLES).map(name => (
                  <button
                    key={name}
                    onClick={() => { setSource(EXAMPLES[name]); setShowExamples(false); setOutputFiles([]); setRawOutput(""); }}
                    style={{
                      display: "block",
                      width: "100%",
                      background: "none",
                      border: "none",
                      borderBottom: "1px solid #1a1a2e",
                      color: "#9999cc",
                      padding: "10px 14px",
                      font: "inherit",
                      fontSize: "12px",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "background 0.1s"
                    }}
                    onMouseEnter={e => e.target.style.background = "#1a1a2e"}
                    onMouseLeave={e => e.target.style.background = "none"}
                  >
                    {name}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            className="transpile-btn"
            onClick={handleTranspile}
            disabled={transpiling}
          >
            {transpiling ? <><span className="pulse" /> Generating...</> : "⌘↵ Transpile"}
          </button>
        </div>
      </div>

      {/* Status bar */}
      <div style={{
        background: "#0d0d1a",
        borderBottom: "1px solid #1a1a2e",
        padding: "4px 20px",
        display: "flex",
        gap: "16px",
        alignItems: "center",
        fontSize: "11px",
        color: "#444466",
        flexShrink: 0
      }}>
        <span>
          <span className="status-dot" style={{ background: hasErrors ? "#ff4444" : "#38d9a9", marginRight: "6px" }} />
          {hasErrors ? `${parseErrors.length} error${parseErrors.length > 1 ? "s" : ""}` : "Valid .il"}
        </span>
        <span>{source.split("\n").length} lines</span>
        <span>{source.length} chars</span>
        {outputFiles.length > 0 && <span style={{ color: "#38d9a9" }}>{outputFiles.length} files generated</span>}
        {transpiling && <span style={{ color: "#7c6aff" }}>Streaming output…</span>}
        <span style={{ marginLeft: "auto", color: "#2a2a4a" }}>IntentLang v0.1.0</span>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>

        {/* EDITOR TAB */}
        {activeTab === "editor" && (
          <div className="editor-wrap">
            <div
              className="editor-highlight"
              dangerouslySetInnerHTML={{ __html: highlighted }}
            />
            <textarea
              ref={textareaRef}
              className="editor-textarea"
              value={source}
              onChange={e => setSource(e.target.value)}
              onKeyDown={handleKeyDown}
              spellCheck={false}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
            />
          </div>
        )}

        {/* AST TAB */}
        {activeTab === "ast" && (
          <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            {hasErrors && (
              <div style={{
                background: "#1a0a0a",
                borderBottom: "1px solid #3a1a1a",
                padding: "10px 20px",
                flexShrink: 0
              }}>
                {parseErrors.map((e, i) => (
                  <div key={i} style={{ color: "#ff6b6b", fontSize: "12px", marginBottom: "4px" }}>
                    Line {e.line}: {e.message}
                  </div>
                ))}
              </div>
            )}
            <div className="ast-out" style={{ flex: 1 }}>
              {astOutput || "// Write some IntentLang to see the AST"}
            </div>
          </div>
        )}

        {/* OUTPUT TAB */}
        {activeTab === "output" && (
          <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            {outputFiles.length > 0 ? (
              <>
                {/* File tabs */}
                <div style={{
                  background: "#0d0d1a",
                  borderBottom: "1px solid #1a1a2e",
                  display: "flex",
                  gap: "2px",
                  padding: "0 8px",
                  overflowX: "auto",
                  flexShrink: 0
                }}>
                  {outputFiles.map((f, i) => (
                    <button
                      key={i}
                      className={`file-tab ${activeFile === i ? "active" : ""}`}
                      onClick={() => setActiveFile(i)}
                    >
                      {f.path.split("/").pop()}
                    </button>
                  ))}
                </div>

                {/* File path + lang */}
                {outputFiles[activeFile] && (
                  <div style={{
                    padding: "8px 20px",
                    borderBottom: "1px solid #1a1a2e",
                    display: "flex",
                    gap: "12px",
                    alignItems: "center",
                    fontSize: "11px",
                    color: "#444466",
                    flexShrink: 0
                  }}>
                    <span style={{ color: "#555577" }}>{outputFiles[activeFile].path}</span>
                    <span className="lang-badge">{detectLang(outputFiles[activeFile].path)}</span>
                    <span style={{ marginLeft: "auto" }}>{outputFiles[activeFile].content.split("\n").length} lines</span>
                  </div>
                )}

                {/* Code content */}
                <div ref={outputRef} className="code-output" style={{ flex: 1 }}>
                  {outputFiles[activeFile]?.content || ""}
                  {transpiling && activeFile === outputFiles.length - 1 && (
                    <span style={{ borderRight: "2px solid #7c6aff", animation: "pulse 1s infinite", marginLeft: "2px" }}> </span>
                  )}
                </div>
              </>
            ) : (
              <div style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                color: "#2a2a4a",
                fontSize: "13px",
                gap: "12px"
              }}>
                {transpiling ? (
                  <>
                    <div className="pulse" style={{ width: "16px", height: "16px" }} />
                    <span style={{ color: "#444466" }}>Transpiling your IntentLang…</span>
                  </>
                ) : (
                  <>
                    <div style={{ fontSize: "32px", opacity: 0.3 }}>⌘↵</div>
                    <span>Press Transpile to generate code from your .il file</span>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Error panel */}
      {hasErrors && activeTab === "editor" && (
        <div style={{
          background: "#0d0a0a",
          borderTop: "1px solid #2a1a1a",
          padding: "8px 20px",
          flexShrink: 0,
          maxHeight: "80px",
          overflowY: "auto"
        }}>
          {parseErrors.map((e, i) => (
            <div key={i} style={{ fontSize: "11px", color: "#ff6b6b", marginBottom: "2px" }}>
              ✗ Line {e.line}: {e.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
