const messagesEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("input");

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function addErrorBanner(text) {
  const div = document.createElement("div");
  div.className = "bubble system";
  div.textContent = `⚠ ${text}`;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addConfirmCards(pending) {
  for (const p of pending) {
    const card = document.createElement("div");
    card.className = "confirm-card";

    const title = document.createElement("div");
    title.className = "title";
    title.textContent = `Confirm: ${p.tool_name}`;
    card.appendChild(title);

    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(p.tool_input, null, 2);
    card.appendChild(pre);

    const actions = document.createElement("div");
    actions.className = "actions";

    const confirmBtn = document.createElement("button");
    confirmBtn.className = "danger";
    confirmBtn.textContent = "Confirm";
    confirmBtn.onclick = () => resolveConfirmation(p.tool_use_id, "confirm", card);

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.onclick = () => resolveConfirmation(p.tool_use_id, "cancel", card);

    actions.appendChild(confirmBtn);
    actions.appendChild(cancelBtn);
    card.appendChild(actions);

    messagesEl.appendChild(card);
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setComposerEnabled(enabled) {
  input.disabled = !enabled;
  form.querySelector("button").disabled = !enabled;
}

async function postJSON(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (resp.status === 401) {
    window.location.href = "/chat/login";
    throw new Error("not authenticated");
  }
  if (!resp.ok) {
    throw new Error(`request failed: ${resp.status}`);
  }
  return resp.json();
}

function handleResponse(data) {
  if (data.type === "confirmation_required") {
    addConfirmCards(data.pending);
    setComposerEnabled(false);
  } else {
    addBubble("assistant", data.text);
    if (data.truncated) {
      addErrorBanner("Stopped after too many tool calls — try rephrasing.");
    }
    setComposerEnabled(true);
    input.focus();
  }
}

async function resolveConfirmation(toolUseId, decision, cardEl) {
  cardEl.querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    const data = await postJSON("/chat/api/confirm", {
      tool_use_id: toolUseId,
      decision,
    });
    cardEl.remove();
    handleResponse(data);
  } catch (e) {
    addErrorBanner(e.message);
    setComposerEnabled(true);
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  addBubble("user", text);
  input.value = "";
  setComposerEnabled(false);
  try {
    const data = await postJSON("/chat/api/message", { message: text });
    handleResponse(data);
  } catch (err) {
    addErrorBanner(err.message);
    setComposerEnabled(true);
  }
});
