const EXAMPLES = [
    { label: "Project plan", text: "Create a project plan for building a mobile banking app over 6 months" },
    { label: "Vague board proposal", text: "I need something for the board about moving our team to a new tool, we want it fast but also very thorough, budget is not decided yet" },
    { label: "Meeting minutes", text: "Write meeting minutes for a weekly product team meeting about the upcoming app release" },
  ];
  const REQUEST_TIMEOUT_MS = 4 * 60 * 1000;
  
  const form = document.getElementById("form");
  const input = document.getElementById("request");
  const submitBtn = document.getElementById("submit");
  const countEl = document.getElementById("count");
  const chipsEl = document.getElementById("chips");
  const loadingEl = document.getElementById("loading");
  const loadingNote = document.getElementById("loadingNote");
  const elapsedEl = document.getElementById("elapsed");
  const resultsEl = document.getElementById("results");
  let timerId = null;
  
  // Build elements with textContent (never innerHTML), so model output can't inject HTML.
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  
  function updateCount() {
    countEl.textContent = input.value.length + " / 2000";
  }
  
  function setupExamples() {
    EXAMPLES.forEach((example) => {
      const chip = el("button", "chip", example.label);
      chip.type = "button";
      chip.addEventListener("click", () => {
        input.value = example.text;
        updateCount();
        input.focus();
      });
      chipsEl.appendChild(chip);
    });
  }
  
  function setLoading(on) {
    submitBtn.disabled = on;
    loadingEl.classList.toggle("show", on);
    clearInterval(timerId);
    if (on) {
      const start = Date.now();
      loadingNote.textContent = "This usually takes about a minute.";
      elapsedEl.textContent = "0s";
      timerId = setInterval(() => {
        const seconds = Math.floor((Date.now() - start) / 1000);
        elapsedEl.textContent = seconds + "s";
        if (seconds > 90) {
          loadingNote.textContent =
            "Still working. The server may have just woken up, so this run can take a little longer.";
        }
      }, 1000);
    }
  }
  
  function showError(message) {
    resultsEl.replaceChildren(el("div", "card error", message));
  }
  
  function errorMessage(status, data) {
    const detail = data && data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0 && detail[0].msg) {
      return "Please check your request: " + detail[0].msg.replace(/^Value error, /, "");
    }
    return "Something went wrong (error " + status + "). Please try again.";
  }
  
  function addList(card, heading, items, className) {
    if (!items || items.length === 0) return;
    card.appendChild(el("h3", "", heading));
    const list = el(className === "tasks" ? "ol" : "ul", className || "");
    items.forEach((item) => list.appendChild(item));
    card.appendChild(list);
  }
  
  function showResult(data) {
    const card = el("div", "card");
    card.appendChild(el("h2", "", data.title || "Your document"));
  
    const meta = el("div", "meta");
    const complete = data.status === "success";
    meta.appendChild(
      el("span", "badge " + (complete ? "ok" : "warn"), complete ? "Complete" : "Partially complete")
    );
    if (data.document_type) {
      const type = data.document_type;
      meta.appendChild(el("span", "type", type.charAt(0).toUpperCase() + type.slice(1)));
    }
    card.appendChild(meta);
  
    if (data.download_url) {
      const link = el("a", "download", "Download Word document");
      link.href = data.download_url;
      link.setAttribute("download", "");
      card.appendChild(link);
    }
    if (!complete) {
      card.appendChild(
        el("p", "muted", "Some sections could not be generated. The document lists which ones.")
      );
    }
  
    addList(
      card,
      "The plan the agent created",
      (data.tasks || []).map((task) => {
        const li = el("li", task.status === "done" ? "done" : "failed");
        li.appendChild(el("span", "mark", task.status === "done" ? "\u2713" : "\u2717"));
        li.appendChild(document.createTextNode(task.title));
        return li;
      }),
      "tasks"
    );
  
    addList(
      card,
      "Assumptions the agent made",
      (data.assumptions || []).map((text) => el("li", "", text))
    );
  
    addList(
      card,
      "Quality review",
      (data.review_notes || []).map((text) => el("li", "", text))
    );
  
    resultsEl.replaceChildren(card);
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  
  async function handleSubmit(event) {
    event.preventDefault();
    const text = input.value.trim();
    if (text.length < 10) {
      showError("Please describe the document you need (at least 10 characters).");
      return;
    }
  
    resultsEl.replaceChildren();
    setLoading(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  
    try {
      const response = await fetch("/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: text }),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        showError(errorMessage(response.status, data));
        return;
      }
      showResult(data);
    } catch (error) {
      showError(
        error.name === "AbortError"
          ? "This is taking too long. Please try again in a moment."
          : "Could not reach the server. Check your connection and try again."
      );
    } finally {
      clearTimeout(timeout);
      setLoading(false);
    }
  }
  
  setupExamples();
  input.addEventListener("input", updateCount);
  form.addEventListener("submit", handleSubmit);