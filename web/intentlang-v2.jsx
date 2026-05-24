import { useState, useCallback, useRef, useEffect } from "react";

// ═══════════════════════════════════════════════════════════════════════════════
// INTENTLANG v0.2 — Multi-file, Multi-level, IR-queryable
// ═══════════════════════════════════════════════════════════════════════════════
//
// Configuration lives in intentlang.config.js — set your API key and model there.
// In this artifact, config is inlined below for portability.
// ───────────────────────────────────────────────────────────────────────────────

// ─── INLINE CONFIG (mirrors intentlang.config.js) ────────────────────────────
// In a real project, replace this block with:
//   import { config, getApiKey, getHeaders, buildRequestBody, extractChunk, MODELS } from "./intentlang.config.js"

const MODELS = {
  SONNET:       "claude-sonnet-4-20250514",
  OPUS:         "claude-opus-4-20250514",
  HAIKU:        "claude-haiku-4-5-20251001",
  GPT4O:        "gpt-4o",
  GPT4O_MINI:   "gpt-4o-mini",
  GEMINI_PRO:   "gemini-2.5-pro",
  GEMINI_FLASH: "gemini-2.0-flash",
  LLAMA3:       "llama3.1:70b",
  DEEPSEEK:     "deepseek-coder-v2:16b",
};

const DEFAULT_CONFIG = {
  apiKey:   "",
  model:    MODELS.SONNET,
  apiBase:  "https://api.anthropic.com/v1/messages",
  maxTokens: 8000,
  stream:   true,
  transpiler: { temperature: 0.2, fileSeparator: "// FILE:", maxReferencedDomains: 5 },
};

function getHeaders(apiKey, apiBase) {
  if (apiBase.includes("anthropic.com")) {
    return { "Content-Type":"application/json", "x-api-key":apiKey, "anthropic-version":"2023-06-01" };
  }
  if (apiBase.includes("openai.com")||apiBase.includes("openrouter.ai")) {
    return { "Content-Type":"application/json", "Authorization":`Bearer ${apiKey}` };
  }
  return { "Content-Type":"application/json", "Authorization":`Bearer ${apiKey}` };
}

function buildRequestBody({ system, userPrompt, cfg }) {
  if (cfg.apiBase.includes("anthropic.com")) {
    return { model:cfg.model, max_tokens:cfg.maxTokens, stream:cfg.stream,
      temperature:cfg.transpiler.temperature, system, messages:[{role:"user",content:userPrompt}] };
  }
  return { model:cfg.model, max_tokens:cfg.maxTokens, stream:cfg.stream,
    temperature:cfg.transpiler.temperature,
    messages:[{role:"system",content:system},{role:"user",content:userPrompt}] };
}

function extractChunk(line, apiBase) {
  if (!line.startsWith("data: ")) return null;
  const data = line.slice(6).trim();
  if (data==="[DONE]") return null;
  try {
    const p = JSON.parse(data);
    if (p.type==="content_block_delta"&&p.delta?.text) return p.delta.text; // Anthropic
    if (p.choices?.[0]?.delta?.content) return p.choices[0].delta.content;  // OpenAI
  } catch {}
  return null;
}

let _uidCounter = 0;
function makeUid(type, name, filename) {
  return `${filename.replace(".il","").replace(/\//g,"-")}:${type}:${name||++_uidCounter}`;
}

// ─── PARSER ───────────────────────────────────────────────────────────────────

function parseIntentLang(source, filename = "unnamed.il") {
  const lines = source.split("\n");
  const errors = [];
  const root = { type:"root", filename, children:[], uid:`root:${filename}` };
  const stack = [{ node:root, indent:-1 }];
  let currentLevel = "high";

  for (let lineNum = 1; lineNum <= lines.length; lineNum++) {
    const raw = lines[lineNum-1];
    const trimmed = raw.trim();
    if (!trimmed || trimmed.startsWith("//")) continue;

    if (trimmed.startsWith("@level:")) {
      const m = trimmed.match(/@level:\s*(high|mid|low|asm)/);
      if (m) currentLevel = m[1];
      continue;
    }

    const indent = raw.search(/\S/);
    while (stack.length > 1 && stack[stack.length-1].indent >= indent) stack.pop();
    const parent = stack[stack.length-1].node;

    const node = parseLine(trimmed, lineNum, errors, filename, currentLevel);
    if (node) {
      if (!parent.children) parent.children = [];
      parent.children.push(node);
      node.parent_uid = parent.uid;
      if (node.block) stack.push({ node, indent });
    }
  }
  return { ast:root, errors };
}

function parseLine(content, lineNum, errors, filename, level) {
  // @target / @constraint
  if (content.startsWith("@target:"))
    return { type:"directive", key:"target", value:content.slice(8).trim(), line:lineNum, level };
  if (/^@?constraint:/.test(content))
    return { type:"constraint", value:content.replace(/^@?constraint:\s*/,""), line:lineNum, level };

  // cross-file xref: key: @domain/Type[!?]
  const xref = content.match(/^([\w.]+)\s*:\s*@([\w]+)\/([\w]+)([!?]?)\s*(.*)$/);
  if (xref) return { type:"xref_property", key:xref[1], domain:xref[2], target:xref[3], strictness:xref[4]||"", rest:xref[5].trim(), line:lineNum, level, parent_uid:null };

  // block declarations
  const blockDecl = content.match(/^(app|service|module|feature|model|route|event|state|component|page|api|auth|db|domain|project|platform|critical_path|inline)\s+([\w./]+)\s*:?$/);
  if (blockDecl) {
    const uid = makeUid(blockDecl[1], blockDecl[2], filename);
    return { type:blockDecl[1], name:blockDecl[2], block:true, children:[], line:lineNum, uid, level, filename };
  }

  // anonymous blocks
  const anonBlock = content.match(/^(rules?|config|schema|props|actions?|effects?|guards?|meta|environment|domains|dependencies)\s*:$/);
  if (anonBlock) {
    const uid = makeUid(anonBlock[1], `anon_${lineNum}`, filename);
    return { type:anonBlock[1], block:true, children:[], line:lineNum, uid, level, filename };
  }

  // route shorthand
  const routeDecl = content.match(/^route\s+(GET|POST|PUT|PATCH|DELETE|WS)\s+([\w/:]+)\s*:?$/);
  if (routeDecl) {
    const uid = makeUid("route", `${routeDecl[1]}_${routeDecl[2]}`, filename);
    return { type:"route", method:routeDecl[1], path:routeDecl[2], block:true, children:[], line:lineNum, uid, level, filename };
  }

  // kv
  const kv = content.match(/^([\w.@]+)\s*:\s*(.+)$/);
  if (kv) return { type:"property", key:kv[1], value:parseValue(kv[2].trim()), line:lineNum, level };

  // rules
  if (content.startsWith("-") || content.startsWith("*"))
    return { type:"rule", value:content.slice(1).trim(), line:lineNum, level };

  // field
  const field = content.match(/^(\w+)\s*\(([^)]+)\)$/);
  if (field) {
    const uid = makeUid("field", field[1], filename);
    return { type:"field", name:field[1], modifiers:field[2].split(",").map(s=>s.trim()), line:lineNum, uid, level, filename };
  }

  // local relation
  const arrow = content.match(/^(\w+)\s*->\s*(\w+)$/);
  if (arrow) return { type:"relation", name:arrow[1], target:arrow[2], local:true, line:lineNum, level };

  errors.push({ line:lineNum, message:`Unrecognized: "${content}"` });
  return { type:"unknown", raw:content, line:lineNum, level };
}

function parseValue(val) {
  if (val==="true") return true;
  if (val==="false") return false;
  if (!isNaN(val)) return Number(val);
  if (val.startsWith("[")&&val.endsWith("]")) return val.slice(1,-1).split(",").map(v=>v.trim());
  return val;
}

// ─── IR BUILDER ───────────────────────────────────────────────────────────────

function buildIR(parsedFiles) {
  const ir = {
    nodes:{}, edges:[], domains:{}, byType:{},
    globalRules:[], stack:null, projectName:null, files:[]
  };

  for (const { ast, filename } of parsedFiles) {
    ir.files.push(filename);
    flattenNodes(ast, ir, filename);
  }

  for (const uid of Object.keys(ir.nodes)) {
    const node = ir.nodes[uid];
    if (node.type==="xref_property") {
      const targetUid = resolveRef(node.domain, node.target, ir);
      ir.edges.push({ from:node.parent_uid||uid, to:targetUid||`unresolved:${node.domain}/${node.target}`, type:"xref", resolved:!!targetUid, key:node.key, strictness:node.strictness });
    }
    if (node.type==="relation")
      ir.edges.push({ from:node.parent_uid||uid, to:node.target, type:"relation", name:node.name });
  }

  for (const uid of Object.keys(ir.nodes)) {
    const n = ir.nodes[uid];
    if ((n.type==="project"||n.type==="app"||n.type==="service") && !ir.projectName) ir.projectName = n.name;
    if (n.type==="property" && n.key==="stack" && !ir.stack) ir.stack = n.value;
    if (n.type==="rule") {
      const p = ir.nodes[n.parent_uid];
      if (p && (p.type==="rules"||p.type==="rule"||p.type==="project"||p.type==="app")) ir.globalRules.push(n.value);
    }
  }

  return ir;
}

function flattenNodes(node, ir, filename) {
  if (!node) return;
  if (node.uid) {
    ir.nodes[node.uid] = { ...node };
    if (!ir.byType[node.type]) ir.byType[node.type] = [];
    ir.byType[node.type].push(node.uid);
    const domain = filename.replace(".il","");
    if (!ir.domains[domain]) ir.domains[domain] = [];
    ir.domains[domain].push(node.uid);
  }
  for (const child of (node.children||[])) flattenNodes(child, ir, filename);
}

function resolveRef(domain, typeName, ir) {
  for (const uid of (ir.domains[domain]||[])) {
    const n = ir.nodes[uid];
    if (n && n.name===typeName) return uid;
  }
  return null;
}

// ─── IR QUERY ENGINE ──────────────────────────────────────────────────────────

function queryIR(ir, query) {
  const q = query.trim().toLowerCase();

  const listMatch = q.match(/^(show|list|get)\s+(models?|features?|routes?|events?|fields?|rules?|all)$/);
  if (listMatch) {
    const typeMap = { model:"model",models:"model",feature:"feature",features:"feature",route:"route",routes:"route",event:"event",events:"event",field:"field",fields:"field",rule:"rule",rules:"rule" };
    const t = typeMap[listMatch[2]];
    if (t) {
      const uids = ir.byType[t]||[];
      return uids.map(uid=>{ const n=ir.nodes[uid]; return `[@${n.level||"high"}] ${n.type} "${n.name||n.value}" (${n.filename||""}) uid:${uid}`; }).join("\n")||`No ${t}s found.`;
    }
    if (listMatch[2]==="all") return Object.keys(ir.nodes).map(uid=>{ const n=ir.nodes[uid]; return `${uid} → ${n.type}${n.name?" "+n.name:""}`; }).join("\n");
  }

  const depsMatch = q.match(/^dep(endencies)? of\s+(\w+)$/);
  if (depsMatch) {
    const name = depsMatch[2];
    const edges = ir.edges.filter(e=>e.from.toLowerCase().includes(name));
    if (!edges.length) return `No dependencies found for "${name}"`;
    return edges.map(e=>`${e.from} →[${e.type}]→ ${e.to}${e.resolved===false?" ⚠ UNRESOLVED":""}`).join("\n");
  }

  const usedByMatch = q.match(/^(used by|dependents of)\s+(\w+)$/);
  if (usedByMatch) {
    const name = usedByMatch[2];
    const edges = ir.edges.filter(e=>e.to.toLowerCase().includes(name));
    if (!edges.length) return `Nothing depends on "${name}"`;
    return edges.map(e=>`${e.from} depends on ${e.to} via [${e.type}]`).join("\n");
  }

  const inspectMatch = q.match(/^inspect\s+(.+)$/);
  if (inspectMatch) {
    const term = inspectMatch[1].trim();
    const exact = ir.nodes[term];
    if (exact) return JSON.stringify(exact,null,2);
    const matches = Object.entries(ir.nodes).filter(([uid,n])=>(n.name||"").toLowerCase().includes(term)||uid.toLowerCase().includes(term));
    if (!matches.length) return `No node matching "${term}"`;
    return matches.map(([uid,n])=>`uid: ${uid}\n${JSON.stringify(n,null,2)}`).join("\n\n");
  }

  if (q.includes("global rule")||q===("rules"))
    return ir.globalRules.length ? ir.globalRules.map((r,i)=>`${i+1}. ${r}`).join("\n") : "No global rules defined.";

  if (q.includes("stack"))
    return `Stack: ${ir.stack||"not defined"}\nProject: ${ir.projectName||"unnamed"}\nFiles: ${ir.files.join(", ")}`;

  if (q.includes("edge")||q.includes("graph"))
    return ir.edges.map(e=>`${e.from} →[${e.type}${e.key?":"+e.key:""}]→ ${e.to}${e.resolved===false?" ⚠ UNRESOLVED":""}`).join("\n")||"No edges.";

  if (q.includes("domain"))
    return Object.entries(ir.domains).map(([d,uids])=>`${d}: ${uids.length} nodes`).join("\n");

  if (q.startsWith("impact")) {
    const name = q.replace(/^impact (of )?/,"").trim();
    const direct = ir.edges.filter(e=>e.to.toLowerCase().includes(name));
    if (!direct.length) return `No dependents for "${name}"`;
    const indirect = new Set();
    for (const e of direct) ir.edges.filter(e2=>e2.to===e.from).forEach(e2=>indirect.add(e2.from));
    return ["Direct dependents:",...direct.map(e=>`  ${e.from} [${e.type}]`), indirect.size?"\nIndirect (2nd-order):":"", ...[...indirect].map(u=>`  ${u}`)].filter(Boolean).join("\n");
  }

  return `Unknown query. Try: list models, show global rules, deps of <name>, used by <name>, inspect <name>, impact of <name>, show graph, show stack, show domains`;
}

function irContextSummary(ir) {
  const mc=(ir.byType["model"]||[]).length, fc=(ir.byType["feature"]||[]).length, rc=(ir.byType["route"]||[]).length;
  const unresolved = ir.edges.filter(e=>e.resolved===false);
  return `PROJECT: ${ir.projectName||"unnamed"}\nSTACK: ${ir.stack||"unspecified"}\nFILES: ${ir.files.join(", ")}\nNODES: ${Object.keys(ir.nodes).length} total (${mc} models, ${fc} features, ${rc} routes)\nEDGES: ${ir.edges.length} (${unresolved.length} unresolved)\nGLOBAL RULES: ${ir.globalRules.length}\n${ir.globalRules.map(r=>"  - "+r).join("\n")}`;
}

// ─── TRANSPILER ───────────────────────────────────────────────────────────────

async function transpile(parsedFiles, ir, targetFile, cfg, onChunk) {
  const irSummary = irContextSummary(ir);
  const targetSrc = parsedFiles.find(f=>f.name===targetFile)?.content||"";
  const domain = targetFile.replace(".il","");
  const domainUids = ir.domains[domain]||[];
  const maxDomains = cfg.transpiler?.maxReferencedDomains || 5;
  const referencedDomains = [...new Set(
    ir.edges.filter(e=>domainUids.some(uid=>e.from.startsWith(domain+":"))).map(e=>e.to.split(":")[0])
  )].filter(d=>d!==domain&&!d.startsWith("unresolved")).slice(0, maxDomains);

  const refContext = referencedDomains.map(rd=>{
    const rf = parsedFiles.find(f=>f.name===rd+".il");
    return rf ? `\n// REFERENCED: ${rd}.il\n${rf.content}` : "";
  }).join("\n");

  const system = `You are the IntentLang transpiler. IntentLang (.il) is a structured multi-level intent language.

ABSTRACTION LEVELS:
- @level: high  → architecture, features, APIs, data models
- @level: mid   → algorithms, business logic, data transforms
- @level: low   → memory layout, performance, system calls, concurrency
- @level: asm   → register hints, instruction preferences, platform-specific (emit C with intrinsics or inline asm)

MULTI-FILE SYSTEM:
- @domain/Type  → cross-file reference resolved by IR
- @domain/Type! → strict (fail transpilation if unresolved)
- @domain/Type? → optional (emit graceful fallback if missing)
- core.il global rules propagate to ALL generated code automatically

OUTPUT FORMAT:
- Separate files with: // FILE: path/to/file.ext
- Generate ALL files needed (models, routes, migrations, tests, config)
- No prose outside code comments
- Never edit generated files — .il is sole source of truth
- Match code sophistication to @level`;

  const userPrompt = `IR SUMMARY (full project):
${irSummary}

TARGET: ${targetFile}
${targetSrc}
${refContext?`\nREFERENCED FILES:${refContext}`:""}

Generate complete implementation. Begin with first file immediately.`;

  const resp = await fetch(cfg.apiBase, {
    method: "POST",
    headers: getHeaders(cfg.apiKey, cfg.apiBase),
    body: JSON.stringify(buildRequestBody({ system, userPrompt, cfg }))
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`API ${resp.status}: ${err}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while(true) {
    const {done,value} = await reader.read();
    if(done) break;
    buffer += decoder.decode(value,{stream:true});
    const lines = buffer.split("\n"); buffer = lines.pop();
    for(const line of lines) {
      const chunk = extractChunk(line, cfg.apiBase);
      if(chunk) onChunk(chunk);
    }
  }
}

// ─── SYNTAX HIGHLIGHTER ───────────────────────────────────────────────────────

function highlight(code) {
  const kws = ["app","service","module","feature","model","route","event","state","component","page","api","auth","db","config","schema","project","domain","platform","critical_path","inline","environment","domains","dependencies"];
  const types = ["str","int","float","bool","uuid","date","datetime","json","list","map","bytes","tsvector"];
  const mods = ["required","optional","pk","fk","unique","indexed","default","nullable","readonly","private","public","async","sync","now"];
  const methods = ["GET","POST","PUT","PATCH","DELETE","WS"];

  return code.split("\n").map(line=>{
    if(line.trimStart().startsWith("//")) return `<span class="il-comment">${esc(line)}</span>`;
    const indent=line.match(/^(\s*)/)[1];
    let p=esc(line.slice(indent.length));
    p=p.replace(new RegExp(`\\b(${kws.join("|")})\\b`,"g"),'<span class="il-kw">$1</span>');
    p=p.replace(new RegExp(`\\b(${types.join("|")})\\b`,"g"),'<span class="il-type">$1</span>');
    p=p.replace(new RegExp(`\\b(${mods.join("|")})\\b`,"g"),'<span class="il-mod">$1</span>');
    p=p.replace(new RegExp(`\\b(${methods.join("|")})\\b`,"g"),'<span class="il-method">$1</span>');
    p=p.replace(/@([\w]+)\/([\w]+)([!?]?)/g,'<span class="il-xref">@$1/$2$3</span>');
    p=p.replace(/@(level|target|constraint):/g,'<span class="il-dir">@$1:</span>');
    p=p.replace(/\b(high|mid|low|asm)\b/g,'<span class="il-level">$1</span>');
    p=p.replace(/^(<span[^>]*>)?(\w+)(<\/span>)?(\s*:)/,(m,s1,key,s2,col)=>s1?m:`<span class="il-key">${key}</span>${col}`);
    p=p.replace(/-&gt;/g,'<span class="il-arrow">→</span>');
    p=p.replace(/"([^"]*)"/g,'<span class="il-str">"$1"</span>');
    p=p.replace(/\b(\d+)\b/g,'<span class="il-num">$1</span>');
    return indent+p;
  }).join("\n");
}

function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

function detectLang(path=""){
  if(/\.(ts|tsx)$/.test(path)) return "typescript";
  if(/\.(js|jsx)$/.test(path)) return "javascript";
  if(/\.py$/.test(path)) return "python";
  if(/\.go$/.test(path)) return "go";
  if(/\.rs$/.test(path)) return "rust";
  if(/\.sql$/.test(path)) return "sql";
  if(/\.json$/.test(path)) return "json";
  if(/\.ya?ml$/.test(path)) return "yaml";
  if(/\.(s|asm)$/.test(path)) return "asm";
  if(/\.(c|h)$/.test(path)) return "c";
  if(/\.md$/.test(path)) return "markdown";
  return "text";
}

function parseOutputFiles(text){
  const re=/\/\/ FILE: ([^\n]+)\n([\s\S]*?)(?=\/\/ FILE: |$)/g;
  const files=[]; let m;
  while((m=re.exec(text))!==null) files.push({path:m[1].trim(),content:m[2].trim()});
  if(!files.length&&text.trim()) files.push({path:"output.txt",content:text.trim()});
  return files;
}

// ─── EXAMPLE PROJECT ─────────────────────────────────────────────────────────

const EXAMPLE_PROJECT = {
  "core.il":`// core.il — Project root. Global rules propagate everywhere.
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
    - tokens expire after 7d`,

  "identity.il":`// identity.il — User, auth, sessions
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
    returns: User`,

  "tasks.il":`// tasks.il — Task and project management
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
    - only assignee or owner can close tasks`,

  "platform.il":`// platform.il — Infrastructure and low-level concerns
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
  cdn: cloudfront`
};

// ─── MAIN COMPONENT ──────────────────────────────────────────────────────────

export default function IntentLangIDE() {
  const [cfg, setCfg] = useState(DEFAULT_CONFIG);
  const [showSettings, setShowSettings] = useState(false);
  const [files, setFiles] = useState(()=>Object.entries(EXAMPLE_PROJECT).map(([name,content])=>({name,content})));
  const [activeFile, setActiveFile] = useState(0);
  const [activePanel, setActivePanel] = useState("editor");
  const [ir, setIR] = useState(null);
  const [irErrors, setIrErrors] = useState([]);
  const [queryInput, setQueryInput] = useState("");
  const [queryResult, setQueryResult] = useState("");
  const [queryHistory, setQueryHistory] = useState([]);
  const [transpiling, setTranspiling] = useState(false);
  const [transpileTarget, setTranspileTarget] = useState("core.il");
  const [outputFiles, setOutputFiles] = useState([]);
  const [activeOutputFile, setActiveOutputFile] = useState(0);
  const [newFileName, setNewFileName] = useState("");
  const [showNewFile, setShowNewFile] = useState(false);
  const textareaRef = useRef(null);
  const outputRef = useRef(null);
  const rawRef = useRef("");

  useEffect(()=>{
    _uidCounter = 0;
    const parsed = files.map(f=>{ const {ast,errors}=parseIntentLang(f.content,f.name); return {...f,ast,errors}; });
    setIrErrors(parsed.flatMap(p=>p.errors.map(e=>({...e,file:p.name}))));
    setIR({...buildIR(parsed), _parsedFiles:parsed});
  },[files]);

  const currentFile = files[activeFile];

  const updateFile = useCallback((content)=>{
    setFiles(prev=>prev.map((f,i)=>i===activeFile?{...f,content}:f));
  },[activeFile]);

  const handleKeyDown = (e)=>{
    if(e.key==="Tab"){
      e.preventDefault();
      const ta=textareaRef.current, s=ta.selectionStart, en=ta.selectionEnd;
      updateFile(currentFile.content.substring(0,s)+"  "+currentFile.content.substring(en));
      setTimeout(()=>{ta.selectionStart=ta.selectionEnd=s+2;},0);
    }
    if((e.metaKey||e.ctrlKey)&&e.key==="Enter") handleTranspile();
  };

  const handleQuery = useCallback(()=>{
    if(!ir||!queryInput.trim()) return;
    const result = queryIR(ir, queryInput);
    setQueryResult(result);
    setQueryHistory(h=>[{q:queryInput,r:result},... h.slice(0,9)]);
    setQueryInput("");
  },[ir,queryInput]);

  const handleTranspile = useCallback(async()=>{
    if(!ir) return;
    if(!cfg.apiKey) { setShowSettings(true); return; }
    setTranspiling(true); setOutputFiles([]); rawRef.current=""; setActivePanel("output");
    try {
      await transpile(ir._parsedFiles, ir, transpileTarget, cfg, (chunk)=>{
        rawRef.current+=chunk;
        setOutputFiles(parseOutputFiles(rawRef.current));
        if(outputRef.current) outputRef.current.scrollTop=outputRef.current.scrollHeight;
      });
    } catch(e){ setOutputFiles([{path:"error.txt",content:"Error: "+e.message}]); }
    finally { setTranspiling(false); }
  },[ir,transpileTarget,cfg]);

  const addFile = ()=>{
    if(!newFileName.trim()) return;
    const name = newFileName.endsWith(".il")?newFileName:newFileName+".il";
    if(files.find(f=>f.name===name)) return;
    const newFiles = [...files, {name, content:`// ${name}\ndomain ${name.replace(".il","")}:\n  description: ""\n`}];
    setFiles(newFiles); setActiveFile(newFiles.length-1); setShowNewFile(false); setNewFileName("");
  };

  const removeFile = (idx)=>{
    if(files.length<=1) return;
    setFiles(prev=>prev.filter((_,i)=>i!==idx));
    setActiveFile(Math.max(0,activeFile-(idx<=activeFile?1:0)));
  };

  const hasErrors = irErrors.length>0;
  const unresolvedCount = ir?ir.edges.filter(e=>e.resolved===false).length:0;
  const SUGGESTED = ["list models","list features","show global rules","show stack","show graph","show domains","deps of tasks","used by User","impact of User","inspect User"];

  return (
    <div style={{fontFamily:"'JetBrains Mono','Fira Code',monospace",background:"#080810",color:"#ddddf0",height:"100vh",display:"flex",flexDirection:"column",overflow:"hidden"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Syne:wght@700;800&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        ::-webkit-scrollbar{width:5px;height:5px;}
        ::-webkit-scrollbar-track{background:transparent;}
        ::-webkit-scrollbar-thumb{background:#1e1e30;border-radius:3px;}
        .il-kw{color:#8b7cf8;font-weight:600}
        .il-type{color:#2dd4bf}
        .il-mod{color:#fb923c}
        .il-key{color:#60a5fa}
        .il-str{color:#86efac}
        .il-num{color:#f87171}
        .il-arrow{color:#f87171}
        .il-comment{color:#3a3a58;font-style:italic}
        .il-xref{color:#e879f9;font-weight:600}
        .il-dir{color:#facc15}
        .il-level{color:#facc15;font-weight:600}
        .il-method{color:#34d399;font-weight:700}
        .panel-btn{background:none;border:none;color:#3a3a5a;padding:8px 14px;font-family:inherit;font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;}
        .panel-btn:hover{color:#7777aa;}
        .panel-btn.active{color:#8b7cf8;border-bottom-color:#8b7cf8;}
        .fc{display:flex;align-items:center;gap:4px;padding:5px 10px 5px 12px;font-size:11px;cursor:pointer;border-bottom:2px solid transparent;color:#3a3a5a;transition:all .15s;white-space:nowrap;background:none;border-top:none;border-left:none;border-right:none;font-family:inherit;}
        .fc:hover{color:#8888bb;}
        .fc.active{color:#2dd4bf;border-bottom-color:#2dd4bf;}
        .fc .x{opacity:0;font-size:10px;color:#553344;padding:0 2px;transition:opacity .1s;}
        .fc:hover .x{opacity:1;}
        .fc .x:hover{color:#f87171;}
        .ed-wrap{position:relative;flex:1;overflow:hidden;}
        .ed-hl{position:absolute;inset:0;padding:18px 20px;font-size:12.5px;line-height:1.75;white-space:pre;overflow:auto;pointer-events:none;tab-size:2;}
        .ed-ta{position:absolute;inset:0;padding:18px 20px;font-size:12.5px;line-height:1.75;background:transparent;color:transparent;caret-color:#8b7cf8;border:none;outline:none;resize:none;font-family:inherit;tab-size:2;white-space:pre;overflow:auto;}
        .qi{background:#0c0c1a;border:1px solid #1a1a2c;color:#ddddf0;padding:10px 14px;font-family:inherit;font-size:12px;flex:1;outline:none;border-radius:4px 0 0 4px;transition:border-color .15s;}
        .qi:focus{border-color:#8b7cf8;}
        .qb{background:#8b7cf8;border:none;color:#fff;padding:10px 16px;font-family:inherit;font-size:11px;font-weight:700;cursor:pointer;border-radius:0 4px 4px 0;letter-spacing:.08em;}
        .qb:hover{background:#7c6aff;}
        .tb{background:linear-gradient(135deg,#8b7cf8,#a855f7);border:none;color:#fff;padding:7px 18px;font-family:inherit;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;cursor:pointer;border-radius:4px;transition:all .2s;display:flex;align-items:center;gap:8px;}
        .tb:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 4px 20px rgba(139,124,248,.4);}
        .tb:disabled{opacity:.5;cursor:not-allowed;}
        .oft{background:none;border:none;border-bottom:2px solid transparent;color:#3a3a5a;padding:6px 12px;font-family:inherit;font-size:11px;cursor:pointer;white-space:nowrap;transition:all .15s;}
        .oft:hover{color:#7777aa;}
        .oft.active{color:#2dd4bf;border-bottom-color:#2dd4bf;}
        .sp{background:#0c0c1a;border:1px solid #151525;color:#444466;padding:4px 10px;font-family:inherit;font-size:10px;cursor:pointer;border-radius:12px;transition:all .15s;white-space:nowrap;}
        .sp:hover{border-color:#8b7cf8;color:#9999cc;}
        .pulse{display:inline-block;width:7px;height:7px;background:#8b7cf8;border-radius:50%;animation:pulse .9s ease-in-out infinite;}
        @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(.6)}}
        .ib{background:#0c0c1a;border:1px solid #171728;border-radius:6px;padding:14px 16px;margin-bottom:12px;}
        .il{color:#333355;font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:6px;}
        .iv{color:#8888bb;font-size:12px;line-height:1.7;white-space:pre-wrap;}
        .ih{color:#8b7cf8}.ig{color:#2dd4bf}.iy{color:#facc15}.ir2{color:#f87171}
        select.ts{background:#0c0c1a;border:1px solid #1a1a2c;color:#7777aa;padding:6px 10px;font-family:inherit;font-size:11px;border-radius:4px;outline:none;cursor:pointer;}
      `}</style>

      {/* HEADER */}
      <div style={{background:"#09091a",borderBottom:"1px solid #111120",padding:"0 16px",display:"flex",alignItems:"center",gap:"16px",height:"48px",flexShrink:0}}>
        <div style={{display:"flex",alignItems:"center",gap:"8px"}}>
          <span style={{fontFamily:"'Syne',sans-serif",fontWeight:800,fontSize:"15px",background:"linear-gradient(135deg,#8b7cf8,#e879f9)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>IntentLang</span>
          <span style={{color:"#1e1e30",fontSize:"11px"}}>v0.2</span>
        </div>
        <div style={{display:"flex",gap:"1px",flex:1}}>
          {[{id:"editor",label:"Editor"},{id:"ir",label:"IR Explorer"},{id:"query",label:"Query"},{id:"output",label:"Output"}].map(({id,label})=>(
            <button key={id} className={`panel-btn ${activePanel===id?"active":""}`} onClick={()=>setActivePanel(id)}>
              {label}
              {id==="editor"&&hasErrors&&<span style={{background:"#2a0808",color:"#f87171",fontSize:"9px",padding:"1px 5px",borderRadius:"8px",marginLeft:4,fontWeight:700}}>{irErrors.length}</span>}
              {id==="ir"&&unresolvedCount>0&&<span style={{background:"#1a1400",color:"#facc15",fontSize:"9px",padding:"1px 5px",borderRadius:"8px",marginLeft:4,fontWeight:700}}>{unresolvedCount}⚠</span>}
            </button>
          ))}
        </div>
        <select className="ts" value={transpileTarget} onChange={e=>setTranspileTarget(e.target.value)}>
          {files.map(f=><option key={f.name} value={f.name}>{f.name}</option>)}
        </select>
        <button onClick={()=>setShowSettings(s=>!s)} style={{
          background: showSettings?"#1a1a2c":"none",
          border:"1px solid",
          borderColor: cfg.apiKey?"#1a2a1a":"#2a1a1a",
          color: cfg.apiKey?"#2dd4bf":"#f87171",
          padding:"6px 12px", fontFamily:"inherit", fontSize:"11px",
          borderRadius:"4px", cursor:"pointer", transition:"all .15s",
          display:"flex", alignItems:"center", gap:"6px"
        }}>
          <span style={{fontSize:"8px"}}>●</span>
          {cfg.apiKey ? "Configured" : "Set API Key"}
        </button>
        <button className="tb" onClick={handleTranspile} disabled={transpiling}>
          {transpiling?<><span className="pulse"/>Generating…</>:"⌘↵ Transpile"}
        </button>
      </div>

      {/* FILE TABS */}
      <div style={{background:"#09091a",borderBottom:"1px solid #0e0e1c",display:"flex",alignItems:"center",overflowX:"auto",flexShrink:0,paddingRight:"8px"}}>
        {files.map((f,i)=>(
          <button key={f.name} className={`fc ${activeFile===i?"active":""}`} onClick={()=>setActiveFile(i)}>
            {f.name}
            {files.length>1&&<span className="x" onClick={e=>{e.stopPropagation();removeFile(i);}}>✕</span>}
          </button>
        ))}
        {showNewFile?(
          <div style={{display:"flex",alignItems:"center",gap:"4px",padding:"0 8px"}}>
            <input value={newFileName} onChange={e=>setNewFileName(e.target.value)} onKeyDown={e=>e.key==="Enter"&&addFile()} placeholder="filename" autoFocus
              style={{background:"#0c0c1a",border:"1px solid #8b7cf8",color:"#ddddf0",padding:"4px 8px",font:"inherit",fontSize:"11px",borderRadius:"3px",outline:"none",width:"120px"}}/>
            <span style={{fontSize:"10px",color:"#333355"}}>.il</span>
            <button onClick={addFile} style={{background:"#8b7cf8",border:"none",color:"#fff",padding:"4px 8px",font:"inherit",fontSize:"10px",cursor:"pointer",borderRadius:"3px"}}>+</button>
            <button onClick={()=>setShowNewFile(false)} style={{background:"none",border:"none",color:"#333355",cursor:"pointer",fontSize:"12px"}}>✕</button>
          </div>
        ):(
          <button onClick={()=>setShowNewFile(true)} style={{background:"none",border:"none",color:"#252538",padding:"6px 10px",font:"inherit",fontSize:"13px",cursor:"pointer",transition:"color .15s"}}
            onMouseEnter={e=>e.target.style.color="#8b7cf8"} onMouseLeave={e=>e.target.style.color="#252538"}>+</button>
        )}
      </div>

      {/* STATUS */}
      <div style={{background:"#080810",borderBottom:"1px solid #0e0e1c",padding:"3px 16px",display:"flex",gap:"14px",alignItems:"center",fontSize:"10px",color:"#252538",flexShrink:0}}>
        <span>
          <span style={{display:"inline-block",width:"5px",height:"5px",borderRadius:"50%",background:hasErrors?"#f87171":"#2dd4bf",marginRight:"5px"}}/>
          {hasErrors?`${irErrors.length} error${irErrors.length>1?"s":""}  `:"IR valid"}
        </span>
        {ir&&<><span style={{color:"#111125"}}>│</span><span>{Object.keys(ir.nodes).length} nodes</span><span style={{color:"#111125"}}>│</span><span>{ir.edges.length} edges</span>{unresolvedCount>0&&<><span style={{color:"#111125"}}>│</span><span style={{color:"#facc15"}}>{unresolvedCount} unresolved</span></>}<span style={{color:"#111125"}}>│</span><span>{ir.files.length} files</span></>}
        <span style={{marginLeft:"auto",color:"#0e0e20"}}>IntentLang v0.2.0</span>
      </div>

      {/* MAIN */}
      <div style={{flex:1,overflow:"hidden",display:"flex",flexDirection:"column"}}>

        {/* EDITOR */}
        {activePanel==="editor"&&currentFile&&(
          <div className="ed-wrap">
            <div className="ed-hl" dangerouslySetInnerHTML={{__html:highlight(currentFile.content)}}/>
            <textarea ref={textareaRef} className="ed-ta" value={currentFile.content}
              onChange={e=>updateFile(e.target.value)} onKeyDown={handleKeyDown}
              spellCheck={false} autoComplete="off" autoCorrect="off" autoCapitalize="off"/>
          </div>
        )}

        {/* IR EXPLORER */}
        {activePanel==="ir"&&ir&&(
          <div style={{flex:1,overflow:"auto",padding:"16px",display:"grid",gridTemplateColumns:"1fr 1fr",gap:"10px",alignContent:"start"}}>
            <div className="ib">
              <div className="il">Project</div>
              <div className="iv"><span className="ih">{ir.projectName||"unnamed"}</span>{"\n"}Stack: <span className="ig">{ir.stack||"?"}</span>{"\n"}Files: {ir.files.map((f,i)=><span key={i}><span className="ig">{f}</span>{i<ir.files.length-1?", ":""}</span>)}</div>
            </div>
            <div className="ib">
              <div className="il">Node Types</div>
              <div className="iv" style={{fontSize:"11px"}}>
                {Object.entries(Object.values(ir.nodes).reduce((a,n)=>{a[n.type]=(a[n.type]||0)+1;return a},{})).sort((a,b)=>b[1]-a[1]).map(([t,c])=><div key={t}><span className="ih">{t}</span> ×{c}</div>)}
              </div>
            </div>
            <div className="ib">
              <div className="il">Dependency Edges ({ir.edges.length})</div>
              <div className="iv" style={{fontSize:"11px",maxHeight:"150px",overflow:"auto"}}>
                {ir.edges.length===0?<span style={{color:"#222235"}}>No cross-file refs yet</span>:ir.edges.map((e,i)=>(
                  <div key={i}><span className="ih">{e.from.split(":").pop()}</span><span style={{color:"#1e1e35"}}> →[{e.type}]→ </span><span className={e.resolved===false?"ir2":"ig"}>{e.to.split(":").pop()}{e.resolved===false?" ⚠":""}</span></div>
                ))}
              </div>
            </div>
            <div className="ib">
              <div className="il">Global Rules ({ir.globalRules.length})</div>
              <div className="iv" style={{fontSize:"11px"}}>
                {ir.globalRules.length===0?<span style={{color:"#222235"}}>None in core.il</span>:ir.globalRules.map((r,i)=><div key={i}><span className="iy">→</span> {r}</div>)}
              </div>
            </div>
            <div className="ib">
              <div className="il">Domains</div>
              <div className="iv" style={{fontSize:"11px"}}>
                {Object.entries(ir.domains).map(([d,uids])=><div key={d}><span className="ig">{d}</span><span style={{color:"#333355"}}> · {uids.length} nodes</span></div>)}
              </div>
            </div>
            <div className="ib">
              <div className="il">Abstraction Levels</div>
              <div className="iv" style={{fontSize:"11px"}}>
                {["high","mid","low","asm"].map(lvl=>{
                  const c=Object.values(ir.nodes).filter(n=>(n.level||"high")===lvl).length;
                  return c>0?<div key={lvl}><span className="iy">@level:{lvl}</span> ×{c}</div>:null;
                })}
              </div>
            </div>
            {hasErrors&&(
              <div className="ib" style={{gridColumn:"1/-1",borderColor:"#2a0808"}}>
                <div className="il" style={{color:"#f87171"}}>Parse Errors</div>
                <div className="iv" style={{fontSize:"11px"}}>
                  {irErrors.map((e,i)=><div key={i} className="ir2">{e.file} line {e.line}: {e.message}</div>)}
                </div>
              </div>
            )}
          </div>
        )}

        {/* QUERY */}
        {activePanel==="query"&&(
          <div style={{flex:1,overflow:"hidden",display:"flex",flexDirection:"column",padding:"16px"}}>
            <div style={{marginBottom:"10px"}}>
              <div style={{fontSize:"10px",color:"#333355",marginBottom:"8px",letterSpacing:".1em",textTransform:"uppercase"}}>Query the IR graph</div>
              <div style={{display:"flex"}}>
                <input className="qi" value={queryInput} onChange={e=>setQueryInput(e.target.value)}
                  onKeyDown={e=>e.key==="Enter"&&handleQuery()}
                  placeholder="list models, deps of User, impact of Task, inspect Auth..."/>
                <button className="qb" onClick={handleQuery}>Run</button>
              </div>
            </div>
            <div style={{display:"flex",gap:"6px",flexWrap:"wrap",marginBottom:"14px"}}>
              {SUGGESTED.map(q=><button key={q} className="sp" onClick={()=>setQueryInput(q)}>{q}</button>)}
            </div>
            {queryResult&&(
              <div className="ib" style={{marginBottom:"12px"}}>
                <div className="il">Result</div>
                <div className="iv" style={{fontSize:"11px",maxHeight:"180px",overflow:"auto"}}>{queryResult}</div>
              </div>
            )}
            {queryHistory.length>0&&(
              <div style={{flex:1,overflow:"auto"}}>
                <div style={{fontSize:"10px",color:"#333355",marginBottom:"8px",letterSpacing:".1em",textTransform:"uppercase"}}>History</div>
                {queryHistory.map((h,i)=>(
                  <div key={i} className="ib" style={{marginBottom:"8px",opacity:1-i*.07}}>
                    <div style={{fontSize:"10px",color:"#8b7cf8",marginBottom:"4px"}}>› {h.q}</div>
                    <div className="iv" style={{fontSize:"11px"}}>{h.r.slice(0,400)}{h.r.length>400?"…":""}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* OUTPUT */}
        {activePanel==="output"&&(
          <div style={{flex:1,overflow:"hidden",display:"flex",flexDirection:"column"}}>
            {outputFiles.length>0?(
              <>
                <div style={{background:"#09091a",borderBottom:"1px solid #0e0e1c",display:"flex",overflowX:"auto",flexShrink:0,padding:"0 8px"}}>
                  {outputFiles.map((f,i)=><button key={i} className={`oft ${activeOutputFile===i?"active":""}`} onClick={()=>setActiveOutputFile(i)}>{f.path.split("/").pop()}</button>)}
                </div>
                <div style={{padding:"5px 16px",borderBottom:"1px solid #0e0e1c",display:"flex",gap:"10px",alignItems:"center",fontSize:"10px",color:"#222235",flexShrink:0}}>
                  <span style={{color:"#333355"}}>{outputFiles[activeOutputFile]?.path}</span>
                  <span style={{background:"#0c0c1a",color:"#8b7cf8",fontSize:"9px",padding:"2px 7px",borderRadius:"3px",textTransform:"uppercase",letterSpacing:".08em"}}>{detectLang(outputFiles[activeOutputFile]?.path||"")}</span>
                  <span style={{marginLeft:"auto"}}>{(outputFiles[activeOutputFile]?.content||"").split("\n").length} lines</span>
                  {transpiling&&<span className="pulse"/>}
                </div>
                <div ref={outputRef} style={{flex:1,overflow:"auto",padding:"18px 20px",fontFamily:"inherit",fontSize:"12px",lineHeight:1.7,color:"#9090aa",whiteSpace:"pre",tabSize:2}}>
                  {outputFiles[activeOutputFile]?.content}
                </div>
              </>
            ):(
              <div style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",color:"#1a1a2c",fontSize:"12px",gap:"10px"}}>
                {transpiling?<><span className="pulse" style={{width:"14px",height:"14px"}}/><span style={{color:"#333355"}}>Transpiling {transpileTarget}…</span></>:<><div style={{fontSize:"28px",opacity:.15}}>⌘↵</div><span>Select a target file and press Transpile</span></>}
              </div>
            )}
          </div>
        )}

      </div>
      {/* SETTINGS MODAL */}
      {showSettings&&(
        <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,.7)",zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center"}}
          onClick={()=>setShowSettings(false)}>
          <div style={{background:"#0e0e1c",border:"1px solid #1e1e30",borderRadius:"8px",padding:"28px",width:"480px",maxWidth:"90vw"}}
            onClick={e=>e.stopPropagation()}>
            <div style={{fontFamily:"'Syne',sans-serif",fontWeight:800,fontSize:"14px",marginBottom:"20px",
              background:"linear-gradient(135deg,#8b7cf8,#e879f9)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>
              IntentLang Settings
            </div>

            {/* API Key */}
            <div style={{marginBottom:"16px"}}>
              <div style={{fontSize:"10px",color:"#444466",letterSpacing:".1em",textTransform:"uppercase",marginBottom:"6px"}}>API Key</div>
              <input
                type="password"
                value={cfg.apiKey}
                onChange={e=>setCfg(c=>({...c,apiKey:e.target.value}))}
                placeholder="sk-ant-... or sk-... or leave blank for no auth"
                style={{width:"100%",background:"#0a0a14",border:"1px solid #1e1e30",color:"#ddddf0",
                  padding:"10px 12px",fontFamily:"inherit",fontSize:"12px",borderRadius:"4px",outline:"none"}}
              />
              <div style={{fontSize:"10px",color:"#333355",marginTop:"4px"}}>Never stored externally. Lives in browser memory only.</div>
            </div>

            {/* Model */}
            <div style={{marginBottom:"16px"}}>
              <div style={{fontSize:"10px",color:"#444466",letterSpacing:".1em",textTransform:"uppercase",marginBottom:"6px"}}>Model</div>
              <select value={cfg.model} onChange={e=>setCfg(c=>({...c,model:e.target.value}))}
                style={{width:"100%",background:"#0a0a14",border:"1px solid #1e1e30",color:"#ddddf0",
                  padding:"10px 12px",fontFamily:"inherit",fontSize:"12px",borderRadius:"4px",outline:"none",cursor:"pointer"}}>
                <optgroup label="Anthropic">
                  <option value={MODELS.SONNET}>claude-sonnet-4 (recommended)</option>
                  <option value={MODELS.OPUS}>claude-opus-4 (most capable)</option>
                  <option value={MODELS.HAIKU}>claude-haiku-4.5 (fastest)</option>
                </optgroup>
                <optgroup label="OpenAI">
                  <option value={MODELS.GPT4O}>gpt-4o</option>
                  <option value={MODELS.GPT4O_MINI}>gpt-4o-mini</option>
                </optgroup>
                <optgroup label="Google">
                  <option value={MODELS.GEMINI_PRO}>gemini-2.5-pro</option>
                  <option value={MODELS.GEMINI_FLASH}>gemini-2.0-flash</option>
                </optgroup>
                <optgroup label="Local / Ollama">
                  <option value={MODELS.LLAMA3}>llama3.1:70b</option>
                  <option value={MODELS.DEEPSEEK}>deepseek-coder-v2:16b</option>
                </optgroup>
              </select>
            </div>

            {/* API Base */}
            <div style={{marginBottom:"16px"}}>
              <div style={{fontSize:"10px",color:"#444466",letterSpacing:".1em",textTransform:"uppercase",marginBottom:"6px"}}>API Endpoint</div>
              <input
                value={cfg.apiBase}
                onChange={e=>setCfg(c=>({...c,apiBase:e.target.value}))}
                placeholder="https://api.anthropic.com/v1/messages"
                style={{width:"100%",background:"#0a0a14",border:"1px solid #1e1e30",color:"#ddddf0",
                  padding:"10px 12px",fontFamily:"inherit",fontSize:"12px",borderRadius:"4px",outline:"none"}}
              />
              <div style={{display:"flex",gap:"6px",marginTop:"6px",flexWrap:"wrap"}}>
                {[
                  ["Anthropic","https://api.anthropic.com/v1/messages"],
                  ["OpenAI","https://api.openai.com/v1/chat/completions"],
                  ["OpenRouter","https://openrouter.ai/api/v1/chat/completions"],
                  ["Ollama","http://localhost:11434/api/chat"],
                ].map(([label,url])=>(
                  <button key={label} onClick={()=>setCfg(c=>({...c,apiBase:url}))}
                    style={{background:"#0a0a14",border:`1px solid ${cfg.apiBase===url?"#8b7cf8":"#1e1e30"}`,
                      color:cfg.apiBase===url?"#8b7cf8":"#444466",padding:"3px 10px",fontFamily:"inherit",
                      fontSize:"10px",borderRadius:"3px",cursor:"pointer"}}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Sliders */}
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"12px",marginBottom:"20px"}}>
              <div>
                <div style={{fontSize:"10px",color:"#444466",letterSpacing:".1em",textTransform:"uppercase",marginBottom:"6px"}}>
                  Max Tokens: <span style={{color:"#8b7cf8"}}>{cfg.maxTokens}</span>
                </div>
                <input type="range" min="1000" max="16000" step="1000" value={cfg.maxTokens}
                  onChange={e=>setCfg(c=>({...c,maxTokens:Number(e.target.value)}))}
                  style={{width:"100%",accentColor:"#8b7cf8"}}/>
              </div>
              <div>
                <div style={{fontSize:"10px",color:"#444466",letterSpacing:".1em",textTransform:"uppercase",marginBottom:"6px"}}>
                  Temperature: <span style={{color:"#8b7cf8"}}>{cfg.transpiler.temperature}</span>
                </div>
                <input type="range" min="0" max="1" step="0.1" value={cfg.transpiler.temperature}
                  onChange={e=>setCfg(c=>({...c,transpiler:{...c.transpiler,temperature:Number(e.target.value)}}))}
                  style={{width:"100%",accentColor:"#8b7cf8"}}/>
              </div>
            </div>

            {/* Actions */}
            <div style={{display:"flex",gap:"8px",justifyContent:"flex-end"}}>
              <button onClick={()=>setCfg(DEFAULT_CONFIG)}
                style={{background:"none",border:"1px solid #1e1e30",color:"#444466",padding:"8px 16px",
                  fontFamily:"inherit",fontSize:"11px",borderRadius:"4px",cursor:"pointer"}}>
                Reset
              </button>
              <button onClick={()=>setShowSettings(false)}
                style={{background:"linear-gradient(135deg,#8b7cf8,#a855f7)",border:"none",color:"#fff",
                  padding:"8px 20px",fontFamily:"inherit",fontSize:"11px",fontWeight:700,
                  borderRadius:"4px",cursor:"pointer",letterSpacing:".08em"}}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
