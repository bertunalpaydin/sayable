/* Sayable front end: recording, showing results and checking scripts.
   Plain JavaScript, no build step. Each page says what it is with
   <body data-page="..."> and only that page's code runs. */

(() => {
  "use strict";

  const MAX_SECONDS = 90;
  const STATUS_TEXT = {
    misheard: "heard as something else",
    missed: "not heard",
    unclear: "heard, but only just",
  };

  // Helpers ------------------------------------------------------------

  function csrfToken() {
    const cookie = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
  }

  async function request(url, options) {
    let response;
    try {
      response = await fetch(url, {
        credentials: "same-origin",
        ...options,
        headers: { "X-CSRFToken": csrfToken(), ...(options.headers || {}) },
      });
    } catch (err) {
      throw new Error("Could not reach Sayable. Check that it is still running.");
    }
    let data = {};
    try {
      data = await response.json();
    } catch (err) {
      /* not JSON, handled below */
    }
    if (!response.ok) {
      throw new Error(data.error || `Something went wrong (${response.status}). Reload the page and try again.`);
    }
    return data;
  }

  function postJSON(url, body) {
    return request(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  function show(el, visible) {
    if (el) el.hidden = !visible;
  }

  function showError(el, message) {
    if (!el) return;
    el.textContent = message || "";
    el.hidden = !message;
  }

  function el(tag, attrs = {}, text = "") {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "className") node.className = value;
      else node.setAttribute(key, value);
    }
    if (text) node.textContent = text;
    return node;
  }

  /* Rebuild `container` from `text`, wrapping the given spans.
     `spans` are {start, end, ...} sorted by start; `make` builds the node. */
  function renderSpans(container, text, spans, make) {
    container.replaceChildren();
    let cursor = 0;
    spans.forEach((span, index) => {
      if (span.start > cursor) container.append(text.slice(cursor, span.start));
      container.append(make(span, text.slice(span.start, span.end), index));
      cursor = span.end;
    });
    if (cursor < text.length) container.append(text.slice(cursor));
  }

  function renderResult(container, text, tokens) {
    const problems = tokens.filter((t) => t.status !== "ok");
    renderSpans(container, text, problems, (token, word) => {
      const span = el("span", { className: `word is-${token.status}` }, word);
      const label = token.status === "misheard" && token.heard
        ? `${word}, heard as ${token.heard}`
        : `${word}, ${STATUS_TEXT[token.status]}`;
      span.setAttribute("aria-label", label);
      span.title = label;
      if (token.status === "misheard" && token.heard) span.dataset.heard = token.heard;
      return span;
    });
  }

  function capitaliseLike(original, replacement) {
    if (original[0] && original[0] === original[0].toUpperCase() && original[0] !== original[0].toLowerCase()) {
      return replacement[0].toUpperCase() + replacement.slice(1);
    }
    return replacement;
  }

  // Recorder -------------------------------------------------------------

  function pickMimeType() {
    if (!window.MediaRecorder) return "";
    const options = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg;codecs=opus"];
    return options.find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }

  function extensionFor(type) {
    if (type.includes("mp4")) return ".m4a";
    if (type.includes("ogg")) return ".ogg";
    return ".webm";
  }

  class Recorder {
    constructor(root, onRecording) {
      this.button = root.querySelector("[data-record]");
      this.label = root.querySelector("[data-record-label]");
      this.time = root.querySelector("[data-record-time]");
      this.onRecording = onRecording;
      this.state = "idle";
      this.idleText = this.label.textContent;
      this.button.addEventListener("click", () => this.toggle());
    }

    setState(state, text) {
      this.state = state;
      this.button.classList.toggle("is-recording", state === "recording");
      this.button.classList.toggle("is-busy", state === "busy");
      this.button.disabled = state === "busy" || state === "starting";
      this.button.setAttribute("aria-label", state === "recording" ? "Stop recording" : "Start recording");
      this.label.textContent = text;
    }

    reset() {
      this.setState("idle", this.idleText);
      this.time.textContent = "";
    }

    toggle() {
      if (this.state === "idle") this.start();
      else if (this.state === "recording") this.stop();
    }

    async start() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
        this.onError("This browser cannot record here. Recording needs a secure (https) connection or localhost.");
        return;
      }
      this.setState("starting", "Asking for the microphone…");
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err) {
        this.reset();
        this.onError("The microphone is blocked. Allow microphone access for this site and try again.");
        return;
      }
      this.type = pickMimeType();
      this.chunks = [];
      this.media = new MediaRecorder(this.stream, this.type ? { mimeType: this.type } : undefined);
      this.media.addEventListener("dataavailable", (event) => {
        if (event.data.size) this.chunks.push(event.data);
      });
      this.media.addEventListener("stop", () => this.finish());
      this.media.start();
      this.startedAt = Date.now();
      this.setState("recording", "Recording. Press again when you have finished.");
      this.timer = setInterval(() => this.tick(), 250);
      this.onError("");
    }

    tick() {
      const seconds = Math.floor((Date.now() - this.startedAt) / 1000);
      this.time.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
      if (seconds >= MAX_SECONDS) this.stop();
    }

    stop() {
      clearInterval(this.timer);
      this.setState("busy", "Listening to your recording…");
      this.media.stop();
      this.stream.getTracks().forEach((track) => track.stop());
    }

    finish() {
      const type = this.media.mimeType || this.type || "audio/webm";
      const blob = new Blob(this.chunks, { type });
      this.onRecording(blob, type);
    }

    onError() {}
  }

  // Profile sentences and rehearsal share one flow ------------------------

  function setUpSession(root, { extraFields, onDone }) {
    const errorBox = root.querySelector("[data-error]");
    const result = root.querySelector("[data-result]");
    const after = root.querySelector("[data-after]");
    const recorderRoot = root.querySelector("[data-recorder]");

    const recorder = new Recorder(recorderRoot, async (blob, type) => {
      const form = new FormData();
      form.append("audio", blob, `take${extensionFor(type)}`);
      form.append("kind", root.dataset.kind);
      for (const [key, value] of Object.entries(extraFields())) form.append(key, value);
      try {
        const data = await request(root.dataset.recordUrl, { method: "POST", body: form });
        renderResult(result.querySelector("[data-result-text]"), data.text, data.tokens);
        result.querySelector("[data-result-heard]").textContent = data.heard;
        result.querySelector("[data-result-title]").textContent = !data.counted
          ? "This take was not counted"
          : data.problems
            ? `${data.problems} word${data.problems === 1 ? "" : "s"} to look at`
            : "Every word was heard clearly";
        show(result.querySelector("[data-not-counted]"), !data.counted);
        show(result, true);
        show(recorderRoot, false);
        show(after, true);
        if (onDone) onDone(data);
        (after.querySelector(".primary") || after).focus();
      } catch (err) {
        showError(errorBox, err.message);
      }
      recorder.reset();
    });
    recorder.onError = (message) => showError(errorBox, message);

    function again(focus = true) {
      show(result, false);
      show(after, false);
      show(recorderRoot, true);
      showError(errorBox, "");
      if (focus) recorder.button.focus();
    }
    root.querySelector("[data-again]").addEventListener("click", () => again());
    return { again };
  }

  function initProfile() {
    const root = document.querySelector("[data-session]");
    setUpSession(root, { extraFields: () => ({ sentence_key: root.dataset.sentenceKey }) });
  }

  function initRehearse() {
    const root = document.querySelector("[data-session]");
    const pieces = JSON.parse(document.getElementById("pieces").textContent);
    const textBox = root.querySelector("[data-text]");
    const step = root.querySelector("[data-step]");
    const prev = root.querySelector("[data-prev]");
    const next = root.querySelector("[data-next]");
    const cont = root.querySelector("[data-continue]");
    const prepNote = root.querySelector("[data-prep-note]");
    let index = Math.min(Math.max(parseInt((location.hash.match(/part-(\d+)/) || [])[1] || "1", 10) - 1, 0), pieces.length - 1);

    const session = setUpSession(root, { extraFields: () => ({ script_id: root.dataset.scriptId, chunk: index }) });

    function showPiece(i, focus = true) {
      index = i;
      const piece = pieces[index];
      renderSpans(textBox, piece.text, piece.flags, (flag, word) => {
        const span = el("span", { className: `mark is-prep is-${flag.level}` }, word);
        span.title = flag.reason;
        return span;
      });
      show(prepNote, piece.flags.length > 0);
      step.textContent = `Part ${index + 1} of ${pieces.length}`;
      prev.disabled = index === 0;
      next.disabled = index === pieces.length - 1;
      cont.textContent = index === pieces.length - 1 ? "Start again from the top" : "Next part";
      history.replaceState(null, "", `#part-${index + 1}`);
      session.again(focus);
    }

    prev.addEventListener("click", () => showPiece(index - 1));
    next.addEventListener("click", () => showPiece(index + 1));
    cont.addEventListener("click", () => showPiece(index === pieces.length - 1 ? 0 : index + 1));
    showPiece(index, false);
  }

  // Script check ----------------------------------------------------------

  function initScript() {
    const form = document.querySelector("[data-script-form]");
    const textarea = form.querySelector("textarea");
    const panel = document.querySelector("[data-check-panel]");
    const summary = panel.querySelector("[data-check-summary]");
    const marked = panel.querySelector("[data-check-text]");
    const profileNote = panel.querySelector("[data-profile-note]");
    const wordPanel = panel.querySelector("[data-word-panel]");
    const errorBox = document.querySelector("[data-error]");
    const checkButton = form.querySelector("[data-check]");
    const claudeOn = form.dataset.claude === "on";
    let checkedText = "";
    let flags = [];

    async function check() {
      const text = textarea.value;
      if (!text.trim()) {
        showError(errorBox, "Write or paste your script first.");
        return;
      }
      checkButton.disabled = true;
      checkButton.textContent = "Checking…";
      showError(errorBox, "");
      try {
        const data = await postJSON(form.dataset.checkUrl, { text });
        checkedText = text;
        flags = data.flags;
        renderSpans(marked, text, flags, (flag, word, i) => {
          const button = el("button", { type: "button", className: `mark is-${flag.level}`, "aria-pressed": "false" }, word);
          button.setAttribute("aria-label", `${word}, ${flag.level === "high" ? "likely" : "might be"} misheard. Show details.`);
          button.addEventListener("click", () => select(i, button));
          return button;
        });
        const count = flags.length;
        summary.textContent = count
          ? `${count} of ${data.content_words} words to look at. Select a marked word to see why, and easier options.`
          : `Nothing flagged in ${data.content_words} words. This script looks safe for your voice.`;
        show(profileNote, !data.profile_ready);
        show(wordPanel, false);
        show(panel, true);
        if (count) marked.querySelector(".mark").focus();
      } catch (err) {
        showError(errorBox, err.message);
      } finally {
        checkButton.disabled = false;
        checkButton.textContent = "Check script";
      }
    }

    function optionList(options, flag) {
      const list = el("ul", { className: "options" });
      options.forEach((option) => {
        const item = el("li");
        const button = el("button", { type: "button", className: "button small" }, `Use “${option.text}”`);
        button.addEventListener("click", () => replace(flag, option.text));
        item.append(button);
        list.append(item);
      });
      return list;
    }

    function select(index, button) {
      const flag = flags[index];
      marked.querySelectorAll(".mark").forEach((m) => m.setAttribute("aria-pressed", "false"));
      button.setAttribute("aria-pressed", "true");
      wordPanel.querySelector("[data-panel-word]").textContent = flag.word;
      wordPanel.querySelector("[data-panel-reason]").textContent = flag.reason;
      const options = wordPanel.querySelector("[data-panel-options]");
      options.replaceChildren();
      if (flag.alternatives.length) {
        options.append(el("p", { className: "options-label small" }, "Easier for you (check the meaning fits):"));
        options.append(optionList(flag.alternatives, flag));
      } else {
        options.append(el("p", { className: "muted small" },
          "No easier synonym in the built-in thesaurus. Say this word slowly, or rephrase the sentence."));
      }
      const claudeButton = wordPanel.querySelector("[data-panel-claude]");
      show(claudeButton, claudeOn);
      claudeButton.onclick = () => askClaude(flag, claudeButton);
      showError(wordPanel.querySelector("[data-panel-error]"), "");
      show(wordPanel, true);
    }

    async function askClaude(flag, button) {
      const errorEl = wordPanel.querySelector("[data-panel-error]");
      button.disabled = true;
      button.textContent = "Asking Claude…";
      showError(errorEl, "");
      try {
        const data = await postJSON(form.dataset.suggestUrl, { word: flag.word, sentence: flag.sentence });
        const options = wordPanel.querySelector("[data-panel-options]");
        options.append(el("p", { className: "options-label small" }, "From Claude, fitted to the sentence:"));
        if (data.alternatives.length) options.append(optionList(data.alternatives, flag));
        else options.append(el("p", { className: "muted small" }, "Claude's options were no easier for your voice."));
        show(button, false);
      } catch (err) {
        showError(errorEl, err.message);
      } finally {
        button.disabled = false;
        button.textContent = "Ask Claude for options that fit the sentence";
      }
    }

    async function replace(flag, replacement) {
      if (textarea.value !== checkedText) {
        showError(errorBox, "The script changed since the check. Check it again first.");
        return;
      }
      const text = checkedText;
      const used = capitaliseLike(flag.word, replacement);
      textarea.value = text.slice(0, flag.start) + used + text.slice(flag.end);
      await check();
      summary.textContent = `Replaced “${flag.word}” with “${used}”. Save the script to keep it. ${summary.textContent}`;
    }

    checkButton.addEventListener("click", check);
    textarea.addEventListener("input", () => {
      if (!panel.hidden && textarea.value !== checkedText) {
        summary.textContent = "The script has changed. Check it again to update the marks.";
        show(wordPanel, false);
      }
    });
  }

  // Start up --------------------------------------------------------------

  const pages = { profile: initProfile, rehearse: initRehearse, script: initScript };
  const page = document.body.dataset.page;
  if (pages[page]) pages[page]();

  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
})();
