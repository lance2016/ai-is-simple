const timeline = document.querySelector("#timeline");
const emptyState = document.querySelector("#emptyState");
const promptForm = document.querySelector("#promptForm");
const promptInput = document.querySelector("#promptInput");
const sendButton = document.querySelector("#sendButton");
const resetButton = document.querySelector("#resetButton");
const stateText = document.querySelector("#stateText");
const liveState = document.querySelector(".live-state");
const workspacePath = document.querySelector("#workspacePath");
const workspaceShort = document.querySelector("#workspaceShort");

let cursor = 0;
let running = false;
const toolCards = new Map();
const permissionCards = new Map();

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function setRunning(value) {
  running = value;
  sendButton.disabled = value;
  stateText.textContent = value ? "运行中" : "就绪";
  liveState.classList.toggle("running", value);
  if (!value) liveState.classList.remove("error");
}

function removeEmptyState() {
  if (emptyState) emptyState.remove();
}

function appendUser(event) {
  removeEmptyState();
  const article = makeElement("article", "event event-user");
  article.append(makeElement("div", "user-copy", event.content));
  timeline.append(article);
}

function appendAssistant(event) {
  removeEmptyState();
  if (!event.content) return;
  const article = makeElement("article", "event event-assistant");
  article.append(makeElement("div", "assistant-copy", event.content));
  timeline.append(article);
}

function appendToolCall(event) {
  removeEmptyState();
  const article = makeElement("article", "event tool-event");
  article.dataset.toolId = event.id;
  const top = makeElement("div", "event-topline");
  top.append(makeElement("span", "event-kind", "FUNCTION CALL"));
  top.append(makeElement("span", "event-status", "执行中"));
  const name = makeElement("div", "tool-name");
  name.append(makeElement("code", "", event.name));
  name.append(makeElement("span", "", "模型请求调用"));
  const args = makeElement("pre", "arguments", JSON.stringify(event.arguments || {}, null, 2));
  article.append(top, name, args);
  timeline.append(article);
  toolCards.set(event.id, article);
}

function appendToolResult(event) {
  const article = toolCards.get(event.id);
  if (!article) return;
  article.classList.add("is-done");
  article.querySelector(".event-status").textContent = "已完成";
  const result = makeElement("div", "result-card");
  const toggle = makeElement("button", "result-toggle");
  toggle.type = "button";
  toggle.append(makeElement("span", "", "工具返回"), makeElement("span", "", "展开"));
  const content = makeElement("pre", "result-content", event.content || "(无输出)");
  content.hidden = true;
  toggle.addEventListener("click", () => {
    content.hidden = !content.hidden;
    toggle.lastChild.textContent = content.hidden ? "展开" : "收起";
  });
  result.append(toggle, content);
  article.append(result);
}

async function resolvePermission(permissionId, allowed, card) {
  card.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  await fetch("/api/permission", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ permission_id: permissionId, allowed }),
  });
}

function appendPermission(event) {
  removeEmptyState();
  const article = makeElement("article", "event permission-event");
  article.dataset.permissionId = event.permission_id;
  const top = makeElement("div", "permission-topline");
  top.append(makeElement("span", "event-kind", "AUTHORIZATION GATE"));
  top.append(makeElement("span", "event-status", "等待你的决定"));
  const title = makeElement("h3", "", "这一步会改变工作区");
  const action = makeElement("pre", "permission-action", event.action);
  const actions = makeElement("div", "permission-actions");
  const allow = makeElement("button", "allow-button", "允许执行");
  const deny = makeElement("button", "deny-button", "拒绝");
  allow.type = deny.type = "button";
  allow.addEventListener("click", () => resolvePermission(event.permission_id, true, article));
  deny.addEventListener("click", () => resolvePermission(event.permission_id, false, article));
  actions.append(allow, deny);
  article.append(top, title, action, actions);
  timeline.append(article);
  permissionCards.set(event.permission_id, article);
}

function resolvePermissionCard(event) {
  const card = permissionCards.get(event.permission_id);
  if (!card) return;
  card.classList.add("resolved");
  card.querySelector(".event-status").textContent = event.allowed ? "已允许" : "已拒绝";
  card.querySelectorAll("button").forEach((button) => { button.disabled = true; });
}

function appendError(event) {
  removeEmptyState();
  const article = makeElement("article", "event error-event", event.content);
  timeline.append(article);
  stateText.textContent = "发生错误";
  liveState.classList.add("error");
}

function handleEvent(event) {
  cursor = Math.max(cursor, event.id || 0);
  switch (event.type) {
    case "user_message": appendUser(event); break;
    case "assistant_message": appendAssistant(event); break;
    case "tool_call": appendToolCall(event); break;
    case "tool_result": appendToolResult(event); break;
    case "permission_requested": appendPermission(event); break;
    case "permission_resolved": resolvePermissionCard(event); break;
    case "error": appendError(event); break;
    case "reset":
      timeline.innerHTML = "";
      timeline.append(emptyState);
      toolCards.clear();
      permissionCards.clear();
      break;
    case "run_finished": setRunning(false); break;
    default: break;
  }
  timeline.scrollTop = timeline.scrollHeight;
}

async function poll() {
  try {
    const response = await fetch(`/api/events?after=${cursor}`, { cache: "no-store" });
    const state = await response.json();
    if (state.workspace) {
      workspacePath.textContent = state.workspace;
      workspaceShort.textContent = state.workspace.split("/").pop() || state.workspace;
    }
    setRunning(state.running);
    state.events.forEach(handleEvent);
  } catch (error) {
    stateText.textContent = "连接断开";
    liveState.classList.add("error");
  }
}

promptForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = promptInput.value.trim();
  if (!message || running) return;
  const response = await fetch("/api/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (response.ok) {
    promptInput.value = "";
    setRunning(true);
  }
});

promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    promptForm.requestSubmit();
  }
});

resetButton.addEventListener("click", async () => {
  if (running) return;
  await fetch("/api/reset", { method: "POST" });
});

poll();
setInterval(poll, 500);
