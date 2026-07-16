const messagesEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const clearBtn = document.getElementById("clear-btn");

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInline(text) {
  text = text.replace(/`([^`]+)`/g, (_, code) => `<code>${code}</code>`);
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, label, url) => {
    if (!/^https?:\/\//i.test(url)) return match;
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });
  return text;
}

// Small hand-rolled renderer for the markdown subset Claude actually
// produces (bold/italic, inline code, headings, lists, links) — no
// external library/CDN, consistent with this frontend's no-build-step
// approach. Input is HTML-escaped first, so any structural markup below
// is the only real HTML ever inserted.
function renderMarkdown(raw) {
  const lines = escapeHtml(raw).split("\n");
  const html = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 2, 6);
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      i++;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length) {
        if (/^[-*]\s+/.test(lines[i])) {
          items.push(`<li>${renderInline(lines[i].replace(/^[-*]\s+/, ""))}</li>`);
          i++;
        } else if (lines[i].trim() === "" && /^[-*]\s+/.test(lines[i + 1] || "")) {
          // Blank line between items of the same list ("loose" list) —
          // skip it rather than ending the list, so the items still
          // render as one <ul> instead of several single-item ones.
          i++;
        } else {
          break;
        }
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length) {
        if (/^\d+\.\s+/.test(lines[i])) {
          items.push(`<li>${renderInline(lines[i].replace(/^\d+\.\s+/, ""))}</li>`);
          i++;
        } else if (lines[i].trim() === "" && /^\d+\.\s+/.test(lines[i + 1] || "")) {
          // Same "loose list" handling as above — a blank separator line
          // shouldn't split the list and reset the <ol> numbering to 1.
          i++;
        } else {
          break;
        }
      }
      html.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    const paraLines = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^[-*]\s+/.test(lines[i]) &&
      !/^\d+\.\s+/.test(lines[i]) &&
      !/^#{1,6}\s+/.test(lines[i])
    ) {
      paraLines.push(renderInline(lines[i]));
      i++;
    }
    html.push(`<p>${paraLines.join("<br>")}</p>`);
  }

  return html.join("");
}

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  if (role === "assistant") {
    div.innerHTML = renderMarkdown(text);
  } else {
    div.textContent = text;
  }
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

function addThinkingIndicator() {
  const div = document.createElement("div");
  div.className = "bubble assistant thinking";
  div.innerHTML = "<span class=\"dot\"></span><span class=\"dot\"></span><span class=\"dot\"></span>";
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
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
  // Disabled for the same span as the composer: prevents "New chat" from
  // resetting the session mid-flight, which would otherwise let an
  // in-flight /chat/api/message or /chat/api/confirm response append its
  // reply back into the just-cleared session.
  clearBtn.disabled = !enabled;
}

async function postJSON(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
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
  const thinking = addThinkingIndicator();
  try {
    const data = await postJSON("/chat/api/confirm", {
      tool_use_id: toolUseId,
      decision,
    });
    thinking.remove();
    cardEl.remove();
    handleResponse(data);
  } catch (e) {
    thinking.remove();
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
  const thinking = addThinkingIndicator();
  try {
    const data = await postJSON("/chat/api/message", { message: text });
    thinking.remove();
    handleResponse(data);
  } catch (err) {
    thinking.remove();
    addErrorBanner(err.message);
    setComposerEnabled(true);
  }
});

clearBtn.addEventListener("click", async () => {
  clearBtn.disabled = true;
  try {
    await postJSON("/chat/api/clear");
    messagesEl.innerHTML = "";
    setComposerEnabled(true);
    input.focus();
  } catch (e) {
    addErrorBanner(e.message);
  } finally {
    clearBtn.disabled = false;
  }
});
