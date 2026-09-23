// 渲染层：把 Agent 事件里的数据变成好读的 DOM。
// 这里只管"长什么样"，不碰连接、状态和授权——那些在 app.js 里。
//
// marked / DOMPurify / highlight.js 从 CDN 加载。万一没加载到（比如断网），
// 退回纯文本显示，页面照样能用，只是没有排版。

const { marked, DOMPurify, hljs } = window;
const RICH = Boolean(marked && DOMPurify);

export function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

// 复制按钮：点一下把 text 放进剪贴板，按钮上的字短暂变成"已复制"作为回应
export function copyButton(text) {
  const btn = el("button", "copy", "复制");
  btn.type = "button";
  btn.onclick = async (e) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = "已复制";
    } catch {
      btn.textContent = "复制失败";
    }
    setTimeout(() => { btn.textContent = "复制"; }, 1500);
  };
  return btn;
}

function lineCount(text) {
  return text ? text.replace(/\n$/, "").split("\n").length : 0;
}

/* ── Markdown ───────────────────────────────────── */

// 流式输出时每帧都会调一次，所以代码高亮只在最后一次（final）做，省得反复重算
export function renderMarkdown(node, text, final) {
  if (!RICH) {
    node.textContent = text;
    node.style.whiteSpace = "pre-wrap";
    return;
  }
  // 模型输出不可信，转成 HTML 之后必须先过一遍 DOMPurify 再放进页面
  node.innerHTML = DOMPurify.sanitize(marked.parse(text, { gfm: true, breaks: true }));
  node.querySelectorAll("a").forEach((a) => {
    a.target = "_blank";
    a.rel = "noopener noreferrer";
  });
  if (!final) return;
  node.querySelectorAll("pre").forEach((pre) => {
    const code = pre.querySelector("code");
    if (code && hljs) hljs.highlightElement(code);
    // 复制按钮只在最后一次渲染时加，流式过程中每帧都会重建 DOM，加了也会被冲掉
    const holder = el("div", "code-holder");
    pre.replaceWith(holder);
    holder.append(pre, copyButton(pre.textContent));
  });
}

/* ── 代码高亮 ───────────────────────────────────── */

const LANG_BY_EXT = {
  py: "python", js: "javascript", mjs: "javascript", ts: "typescript", tsx: "typescript",
  jsx: "javascript", json: "json", md: "markdown", html: "xml", xml: "xml", css: "css",
  sh: "bash", zsh: "bash", yml: "yaml", yaml: "yaml", toml: "ini", go: "go", rs: "rust",
  java: "java", c: "c", h: "c", cpp: "cpp", sql: "sql",
};

function langOf(path) {
  const ext = String(path || "").split(".").pop().toLowerCase();
  return LANG_BY_EXT[ext];
}

function codeInto(pre, text, lang) {
  const code = el("code");
  if (hljs && lang && hljs.getLanguage(lang)) {
    // highlight.js 输出的是已经转义过的 HTML，可以直接放
    code.innerHTML = hljs.highlight(text, { language: lang, ignoreIllegals: true }).value;
    code.className = "hljs";
  } else {
    code.textContent = text;
  }
  pre.append(code);
  return pre;
}

function block(label, body, copyText, badge) {
  const box = el("div", "block");
  const bar = el("div", "block-bar");
  bar.append(el("span", "", label));
  if (badge) bar.append(badge);
  if (copyText) bar.append(copyButton(copyText));
  box.append(bar, body);
  return box;
}

/* ── 工具：标题和一句话摘要 ─────────────────────── */

const DISPLAY = { bash: "Bash", read: "Read", write: "Write", edit: "Edit" };

// 折叠状态下的第一行：工具名 + 最关键的那个参数，例如 Bash ls labs、Read agent.py
export function toolTitle(name, args) {
  // 扩展加进来的工具不认识，就拿第一个文字参数当摘要
  const arg = name === "bash" ? args.command : name in DISPLAY ? args.path : Object.values(args).find((v) => typeof v === "string");
  return { name: DISPLAY[name] || name, arg: arg ? String(arg).split("\n")[0] : "" };
}

const RUNNING = { bash: "运行中…", read: "读取中…", write: "准备写入…", edit: "准备修改…" };
const ASKING = { bash: "等你决定：要运行这条命令吗？", write: "等你决定：要写入这个文件吗？", edit: "等你决定：要做这处修改吗？" };

export function runningText(name) {
  return RUNNING[name] || "执行中…";
}

export function askingText(name) {
  return ASKING[name] || "等你决定：要执行这一步吗？";
}

export function isFailure(text) {
  return text.startsWith("Error:") || text.startsWith("Blocked:");
}

// 折叠状态下的第二行：结果的一句话概括
export function resultSummary(name, args, text) {
  if (text.startsWith("Blocked:")) return text.includes("已停止") ? "任务已停止，这一步没有执行" : "你拒绝了这一步";
  if (text.startsWith("Error:")) return text.slice(6).trim().split("\n")[0];
  if (name === "read") return `读取了 ${lineCount(text)} 行`;
  if (name === "write") return `写入了 ${lineCount(args.content)} 行`;
  if (name === "edit") return `+${lineCount(args.new_text)} −${lineCount(args.old_text)} 行`;
  const exit = splitExit(text);
  if (exit.code !== null) {
    const n = lineCount(exit.body);
    return `exit ${exit.code} · ${n ? `${n} 行输出` : "没有输出"}`;
  }
  return `${lineCount(text)} 行`;
}

function splitExit(text) {
  const match = text.match(/^exit_code=(-?\d+)\n?/);
  return match ? { code: match[1], body: text.slice(match[0].length) } : { code: null, body: text };
}

/* ── 工具：展开后的详情 ─────────────────────────── */

// 参数视图：每个工具用它自己的样子展示，read 的参数标题里已经有了，不再单列
export function argsView(name, args) {
  if (name === "bash") {
    const command = String(args.command ?? "");
    return block("命令", codeInto(el("pre", "wrap"), command, "bash"), command);
  }
  if (name === "write") {
    const content = String(args.content ?? "");
    return block(`将要写入 ${lineCount(content)} 行`, codeInto(el("pre"), content, langOf(args.path)), content);
  }
  if (name === "edit") {
    const pre = el("pre");
    String(args.old_text ?? "").split("\n").forEach((l) => pre.append(el("span", "del", "- " + l)));
    String(args.new_text ?? "").split("\n").forEach((l) => pre.append(el("span", "ins", "+ " + l)));
    return block("将要做的替换", pre, String(args.new_text ?? ""));
  }
  return null;
}

export function resultView(name, args, text) {
  if (isFailure(text)) return block("没有执行", el("pre", "wrap", text));

  if (name === "read") {
    // 复制时去掉行号，拿到的就是文件原文
    const plain = text.split("\n").map((l) => l.replace(/^\d+: ?/, "")).join("\n");
    return block("文件内容", numbered(text, langOf(args.path)), plain);
  }

  const exit = splitExit(text);
  if (exit.code !== null) {
    const badge = el("span", "exit " + (exit.code === "0" ? "ok" : "no"), `exit ${exit.code}`);
    return block("输出", el("pre", "wrap", exit.body || "(没有输出)"), exit.body, badge);
  }
  return block("结果", el("pre", "wrap", text));
}

// read 返回 "12: content" 这样的行。行号拆到左边一栏，右边整体做语法高亮
function numbered(text, lang) {
  const nums = [];
  const lines = [];
  for (const line of text.split("\n")) {
    const cut = line.match(/^(\d+): ?(.*)$/);
    nums.push(cut ? cut[1] : "");
    lines.push(cut ? cut[2] : line);
  }
  const box = el("div", "numbered");
  box.append(el("pre", "gutter", nums.join("\n")), codeInto(el("pre", "code"), lines.join("\n"), lang));
  return box;
}

export function rawView(args) {
  const raw = el("details", "raw");
  raw.append(el("summary", "", "原始 JSON"), el("pre", "wrap", JSON.stringify(args, null, 2)));
  return raw;
}
