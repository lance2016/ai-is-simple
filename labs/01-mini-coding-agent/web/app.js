// 核心逻辑：连上事件流，按事件更新页面，把你的输入和授权发回后端。
// 每种东西具体长什么样交给 render.js。
import {
  el, renderMarkdown, toolTitle, runningText, askingText,
  isFailure, resultSummary, argsView, resultView, rawView,
} from "./render.js";

const feed = document.querySelector("#feed");
const stream = document.querySelector("#stream");
const input = document.querySelector("#input");
const sendBtn = document.querySelector("#send");
const clearBtn = document.querySelector("#clear");
const stateBox = document.querySelector("#state");
const stateText = document.querySelector("#stateText");
const rootPath = document.querySelector("#root");
const beacon = document.querySelector("#beacon");
const newer = document.querySelector("#newer");
const hint = document.querySelector("#hint");
const BASE_TITLE = document.title;

let cursor = 0;          // 已经消费到第几号事件，重连时带上它
let busy = false;
let turn = null;         // 当前这一轮对话的容器
const tools = new Map(); // call_id -> 这次工具调用的行
let openTool = null;     // 最近一个还没出结果的工具调用
let pending = null;      // 正在等你决定的那一行
let live = null;         // 模型正在流式输出的那段文字
let spinner = null;      // "思考中" 提示，模型一有产出就撤掉
let lastTask = "";       // 最近一次发出的任务，出错后可以一键重发

// 流式片段最多每 50ms 重绘一次。不用 requestAnimationFrame：
// 窗口被挡住、切到别的标签页时浏览器会暂停它，文字就会憋到最后一次性出现。
const REPAINT_MS = 50;

/* ── 放置与滚动 ─────────────────────────────────── */

function atBottom() {
  return stream.scrollHeight - stream.scrollTop - stream.clientHeight < 140;
}

// 只在你本来就在底部时才跟着滚，免得翻历史的时候被拽走；
// 不跟的时候亮出"有新内容"，让你知道下面有东西
function follow(change) {
  const stick = atBottom();
  change();
  if (stick) stream.scrollTop = stream.scrollHeight;
  else if (!pending) newer.classList.add("show");  // 有待决授权时，"去看看"更要紧，只留它一个
}

stream.addEventListener("scroll", () => {
  if (atBottom()) newer.classList.remove("show");
});
newer.onclick = () => stream.scrollTo({ top: stream.scrollHeight, behavior: "smooth" });

function place(node) {
  follow(() => (turn || openTurn()).append(node));
  return node;
}

function openTurn(text) {
  turn = el("section", "turn");
  if (text !== undefined) turn.append(el("div", "user", text));
  follow(() => feed.append(turn));
  return turn;
}

/* ── 模型文字（流式） ───────────────────────────── */

function onDelta(e) {
  if (!live) {
    const item = place(el("div", "item text"));
    live = { node: el("div", "md"), text: "", frame: 0 };
    item.append(live.node);
  }
  live.text += e.content;
  // 片段来得很密，攒一小会儿再统一渲染一次 Markdown
  if (!live.frame) {
    const target = live;
    target.frame = setTimeout(() => {
      target.frame = 0;
      follow(() => renderMarkdown(target.node, target.text, false));
    }, REPAINT_MS);
  }
}

// 完整文字到了：以它为准再渲染一次，这次带代码高亮
function onSay(e) {
  if (!e.content) return;
  let node;
  if (live) {
    clearTimeout(live.frame);
    node = live.node;
  } else {
    node = el("div", "md");
    place(el("div", "item text")).append(node);
  }
  follow(() => renderMarkdown(node, e.content, true));
  live = null;
}

/* ── 思考中 ─────────────────────────────────────── */

function showSpinner(label, since) {
  if (!spinner) {
    const node = el("div", "spinner");
    const text = el("span");
    const clock = el("span", "t");
    node.append(text, clock);
    const start = (since || Date.now() / 1000) * 1000;
    const tick = () => { clock.textContent = `${Math.round((Date.now() - start) / 1000)}s`; };
    tick();
    spinner = { node, text, timer: setInterval(tick, 1000) };
    place(node);
  }
  spinner.text.textContent = label;
}

function dropSpinner() {
  if (!spinner) return;
  clearInterval(spinner.timer);
  spinner.node.remove();
  spinner = null;
}

/* ── 工具调用：默认折叠成两行 ───────────────────── */

function onToolCall(e) {
  const args = typeof e.arguments === "object" && e.arguments ? e.arguments : {};
  const title = toolTitle(e.name, args);

  const node = el("details", "item tool");
  node.dataset.state = "run";
  node.dataset.tool = e.name;  // 工具名标签按工具上色，和配图一致
  const head = el("summary");
  const line = el("div", "t-line");
  line.append(el("span", "t-name", title.name), el("span", "t-arg", title.arg), el("span", "t-caret", "▶"));
  const sub = el("div", "t-sub", runningText(e.name));
  head.append(line, sub);

  const body = el("div", "t-body");
  const view = argsView(e.name, args);
  if (view) body.append(view);
  const raw = rawView(e.arguments);
  body.append(raw);
  node.append(head, body);
  place(node);

  const record = { node, sub, body, raw, name: e.name, args };
  tools.set(e.call_id, record);
  openTool = record;
}

function onAsk(e) {
  // Agent 是顺序执行的，同一时刻最多一个待决请求，它一定属于最近那次调用
  const record = openTool;
  if (!record) return;
  record.node.dataset.state = "ask";
  record.sub.textContent = askingText(record.name);

  const gate = el("div", "gate");
  gate.append(el("p", "", "这一步会改动工作区，看清上面的内容再决定。"));
  const yes = el("button", "allow");
  const no = el("button", "deny");
  yes.append("允许", el("kbd", "", "Y"));
  no.append("拒绝", el("kbd", "", "N"));
  yes.type = no.type = "button";
  yes.onclick = () => answer(e.request_id, true, gate);
  no.onclick = () => answer(e.request_id, false, gate);
  gate.append(yes, no);
  record.body.insertBefore(gate, record.raw);

  // 要你决定的那一步必须摊开给你看
  follow(() => { record.node.open = true; });
  pending = { record, gate, yes, no };
  watchPending();
  // 输入框里没在打字，就把焦点交给"允许"，这样 Y / N 键立刻能用
  if (!input.value.trim()) yes.focus({ preventScroll: true });
}

function onAskDone(e) {
  if (!pending) return;
  const { record, gate } = pending;
  gate.remove();
  record.node.dataset.state = e.allowed ? "run" : "bad";
  record.sub.textContent = e.allowed ? runningText(record.name) : "你拒绝了这一步";
  // 决定完就收起来，和其他工具一样只留两行
  record.node.open = false;
  pending = null;
  watchPending();
}

function onToolResult(e) {
  const record = tools.get(e.call_id);
  if (!record) return;
  const text = e.content || "";
  record.node.dataset.state = isFailure(text) ? "bad" : "ok";
  record.sub.textContent = resultSummary(record.name, record.args, text);
  record.body.insertBefore(resultView(record.name, record.args, text), record.raw);
  if (openTool === record) openTool = null;
}

function onFail(e) {
  live = null;  // 流在半路断了，下次的文字不能再接到这段后面
  const item = el("div", "item fail");
  item.append(el("p", "", `这一轮没跑完：${e.content}`));
  const task = lastTask;
  if (task) {
    const retry = el("button", "ghost", "重新发送这个任务");
    retry.type = "button";
    retry.onclick = () => { input.value = task; send(); };
    item.append(retry);
  }
  place(item);
}

function onStopped() {
  place(el("div", "item note", "已停止。已经改动的文件不会回滚，可以接着说下一步。"));
}

function reset() {
  feed.replaceChildren();
  tools.clear();
  turn = openTool = pending = live = null;
  dropSpinner();
  watchPending();
  showBlank();
}

/* ── 待决提示：那一行滚出屏幕时在底部提醒 ───────── */

let watcher = null;
function watchPending() {
  if (watcher) { watcher.disconnect(); watcher = null; }
  // 切到别的标签页时，也能从标签标题看出 Agent 正停着等你
  document.title = pending ? `等你决定 | ${BASE_TITLE}` : BASE_TITLE;
  showHint();
  if (!pending) { beacon.classList.remove("show"); return; }
  newer.classList.remove("show");
  watcher = new IntersectionObserver(
    ([entry]) => beacon.classList.toggle("show", !entry.isIntersecting),
    { root: stream, threshold: 0.35 }
  );
  watcher.observe(pending.gate);
}

document.querySelector("#jump").onclick = () => {
  if (pending) pending.gate.scrollIntoView({ block: "center", behavior: "smooth" });
};

/* ── 状态与空状态 ───────────────────────────────── */

// 运行中，发送按钮变成停止按钮：同一个位置，永远是"此刻最该按的那个"
function setBusy(value) {
  busy = value;
  sendBtn.textContent = value ? "停止" : "发送";
  sendBtn.classList.toggle("stop", value);
  clearBtn.disabled = value;
  stateText.textContent = value ? "运行中" : "就绪";
  stateBox.className = "state" + (value ? " on" : "");
  showHint();
  if (!value) input.focus({ preventScroll: true });
}

// 输入框下面那一行：告诉你此刻能按哪些键；出错时换成错误说明
function showHint(error) {
  hint.classList.toggle("error", Boolean(error));
  if (error) hint.textContent = error;
  else if (pending) hint.textContent = "Y 允许，N 拒绝，Esc 停止任务";
  else if (busy) hint.textContent = "Esc 停止任务";
  else hint.textContent = "Enter 发送，Shift + Enter 换行";
}

// 没挂扩展时用这两条；用 --lab 启动时，换成那个实战自带的示例
let samples = [
  "看看 labs 目录里有什么，读一下里面的 README",
  "agent.py 里定义了哪几个工具？各自要不要授权？",
];

function showBlank() {
  const box = el("div", "blank");
  box.append(el("h2", "", "还没有任务"));
  box.append(el("p", "", "每次工具调用会折叠成两行：调用了什么、结果如何。点开能看到参数和完整返回。会改动文件的步骤会自动展开，等你点头。"));
  const list = el("div", "try");
  samples.forEach((text) => {
    const b = el("button", "", text);
    b.type = "button";
    b.onclick = () => { input.value = text; resize(); input.focus(); };
    list.append(b);
  });
  box.append(list);
  feed.append(box);
}

/* ── 分发 ───────────────────────────────────────── */

const HANDLERS = {
  ready: (e) => {
    // 路径太长时只留尾部两段，那才是分得清项目的部分
    const parts = e.workspace.split("/").filter(Boolean);
    rootPath.textContent = parts.length > 2 ? "…/" + parts.slice(-2).join("/") : e.workspace;
    if (e.extensions?.length) rootPath.textContent += ` · ${e.extensions.join(" + ")}`;
    rootPath.title = e.workspace;
    if (e.samples?.length) {
      samples = e.samples;
      // 空状态已经按默认示例画好了，换成这个实战的示例再画一遍
      if (feed.querySelector(".blank")) { feed.querySelector(".blank").remove(); showBlank(); }
    }
  },
  user_message: (e) => { live = null; lastTask = e.content; openTurn(e.content); },
  thinking: (e) => showSpinner("思考中…", e.time),
  tool_call_pending: (e) => showSpinner(`正在生成 ${toolTitle(e.name, {}).name} 的参数…`, e.time),
  assistant_delta: onDelta,
  assistant_message: onSay,
  tool_call: onToolCall,
  tool_result: onToolResult,
  permission_request: onAsk,
  permission_result: onAskDone,
  error: onFail,
  stopped: onStopped,
  // 扩展想对你说的话，比如验收结果，不属于模型的回复
  note: (e) => place(el("div", "item note", e.content)),
  busy: () => setBusy(true),
  idle: () => setBusy(false),
  reset,
};

function handle(event) {
  cursor = event.id;
  if (event.type !== "ready" && event.type !== "reset") feed.querySelector(".blank")?.remove();
  // 除了这两种"还在等"的事件，其他事件一到就说明模型已经有产出了
  if (event.type !== "thinking" && event.type !== "tool_call_pending") dropSpinner();
  HANDLERS[event.type]?.(event);
}

/* ── 连接与输入 ─────────────────────────────────── */

function connect() {
  const source = new EventSource(`/api/events?after=${cursor}`);
  source.onmessage = (m) => handle(JSON.parse(m.data));
  source.onopen = () => {
    if (!busy) { stateText.textContent = "就绪"; stateBox.className = "state"; }
  };
  source.onerror = () => {
    source.close();
    stateText.textContent = "连接断开，重连中";
    stateBox.className = "state off";
    setTimeout(connect, 1200);
  };
}

async function stop() {
  sendBtn.disabled = true;  // 停止要等当前这一步收尾，先防止连点
  try {
    await fetch("/api/stop", { method: "POST" });
  } finally {
    sendBtn.disabled = false;
  }
}

async function answer(requestId, allowed, gate) {
  gate.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  await fetch("/api/permission", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, allowed }),
  });
}

async function send() {
  const message = input.value.trim();
  if (!message || busy) return;
  input.value = "";
  resize();
  let res;
  try {
    res = await fetch("/api/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
  } catch {
    res = null;
  }
  if (res && res.ok) return;
  // 没发出去就把原文放回输入框，免得你要重打一遍
  input.value = message;
  resize();
  showHint(res ? "上一个任务还没结束，等它跑完或者先停止。" : "发不出去：连不上本地服务，看看 server.py 还在不在运行。");
}

function resize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 144) + "px";
}

document.querySelector("#composer").onsubmit = (e) => { e.preventDefault(); busy ? stop() : send(); };
clearBtn.onclick = () => fetch("/api/reset", { method: "POST" });
input.oninput = () => { resize(); showHint(); };

document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
  if (e.key === "Escape" && busy) { e.preventDefault(); stop(); return; }
  // 在输入框里打字时 Y / N 就是普通字母，不能被当成授权
  if (!pending || e.target === input) return;
  const key = e.key.toLowerCase();
  if (key === "y") { e.preventDefault(); pending.yes.click(); }
  if (key === "n") { e.preventDefault(); pending.no.click(); }
});
input.onkeydown = (e) => {
  // 输入法选词时的回车不算发送
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
};

showBlank();
showHint();
resize();
connect();
