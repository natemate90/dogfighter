(() => {
  const form = document.getElementById("release-form");
  if (!form) return;
  const section = document.getElementById("release");
  const survey = document.getElementById("release-survey");
  const stage = survey.querySelector(".survey-stage");
  const bar = survey.querySelector(".survey-bar");
  const live = document.getElementById("release-live");
  const result = document.getElementById("release-result");
  const sendButton = form.querySelector('button[type="submit"]');
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const PRODUCTION = ["dogfighter.net", "www.dogfighter.net"].includes(location.hostname);
  const WINDOW = 30 * 60 * 1000;
  const BEAT = 450;
  const GAP = 1100;

  const QUESTIONS = [
    { id: "devices", text: "Which device would you play on?", multi: true, options: ["Windows", "Mac", "Linux / Steam Deck", "iPad"] },
    { id: "store", text: "Where would you buy it?", options: ["Steam", "GOG", "dogfighter.net", "No preference"] },
    { id: "online", text: "Would you play online with friends?", options: ["Yes", "Maybe", "No"] },
    { id: "played", text: "Did you play the original?", options: ["Yes, back then", "Yes, recently", "No"] },
    { id: "cd", text: "Do you still have the original CD?", options: ["Yes", "No", "Not sure"] },
    { id: "wishes", text: "What should the re-release add or fix?", multi: true, other: "Something else…", options: ["Online multiplayer", "Widescreen", "Controller support", "New missions", "Level editor"] },
  ];

  const fields = {
    email: { error: document.getElementById("release-email-error"), target: document.getElementById("release-email") },
    consent: { error: document.getElementById("release-consent-error"), target: form.querySelector('input[name="consent"]') },
    turnstile: { error: document.getElementById("release-turnstile-error"), target: null },
  };
  const MESSAGES = {
    email: "Enter the email address we should write to.",
    consent: "Tick the box so we may send that one email.",
    turnstile: "The spam check has not finished yet. Wait a moment and try again.",
  };
  const BLOCKED = "The spam check could not load. A blocker may stop it. Reload the page, or try again with the blocker paused for this site.";

  let widgetId = null;
  let token = "";
  let turnstileFailed = false;
  let hooked = false;
  let sending = false;

  const showError = (name, text) => {
    const field = fields[name];
    field.error.textContent = text || "";
    field.error.hidden = !text;
    if (field.target) {
      if (text) field.target.setAttribute("aria-invalid", "true");
      else field.target.removeAttribute("aria-invalid");
    }
  };

  const render = () => {
    if (widgetId !== null || !window.turnstile) return;
    const sitekey = document.getElementById("contact-form")?.dataset.sitekey;
    widgetId = window.turnstile.render("#release-turnstile", {
      sitekey: PRODUCTION && sitekey ? sitekey : "1x00000000000000000000AA",
      action: "notify",
      theme: "auto",
      "response-field": false,
      callback: (value) => {
        token = value;
        turnstileFailed = false;
        showError("turnstile", "");
      },
      "expired-callback": () => (token = ""),
      "error-callback": () => {
        token = "";
        turnstileFailed = true;
        showError("turnstile", BLOCKED);
      },
    });
  };
  const loadTurnstile = () => {
    if (window.turnstile) return render();
    if (hooked) return;
    hooked = true;
    const previous = window.onDogfighterTurnstile;
    window.onDogfighterTurnstile = () => {
      if (typeof previous === "function") previous();
      render();
    };
    let script = document.querySelector("script[data-turnstile]");
    if (!script) {
      script = document.createElement("script");
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=onDogfighterTurnstile";
      script.async = true;
      script.dataset.turnstile = "";
      document.head.appendChild(script);
    }
    script.addEventListener("error", () => {
      turnstileFailed = true;
      showError("turnstile", BLOCKED);
    });
  };
  if ("IntersectionObserver" in window) {
    const watcher = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        watcher.disconnect();
        loadTurnstile();
      }
    }, { rootMargin: "600px 0px" });
    watcher.observe(section);
  } else {
    loadTurnstile();
  }
  form.addEventListener("focusin", loadTurnstile);

  const showResult = (ok, title, text) => {
    result.replaceChildren();
    const heading = document.createElement("p");
    heading.className = "result-title";
    heading.textContent = title;
    const body = document.createElement("p");
    body.textContent = text;
    result.append(heading, body);
    result.classList.toggle("failed", !ok);
    result.hidden = false;
    result.focus();
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (sending) return;
    const data = new FormData(form);
    const email = String(data.get("email") || "").trim();
    const consent = data.get("consent") === "yes";
    const invalid = [];
    if (!email || email.length > 254 || !/^[^\s@"<>]+@[^\s@"<>]+\.[^\s@"<>]+$/.test(email)) invalid.push("email");
    if (!consent) invalid.push("consent");
    if (!token) {
      invalid.push("turnstile");
      loadTurnstile();
    }
    Object.keys(fields).forEach((name) => showError(name, invalid.includes(name) ? (name === "turnstile" && turnstileFailed ? BLOCKED : MESSAGES[name]) : ""));
    if (invalid.length) {
      (fields[invalid[0]].target || fields[invalid[0]].error).focus();
      return;
    }
    sending = true;
    sendButton.disabled = true;
    sendButton.textContent = "Sending…";
    result.hidden = true;
    let answer = null;
    try {
      const response = await fetch("/api/notify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, consent: "yes", website: data.get("website") || "", "cf-turnstile-response": token }),
      });
      answer = await response.json().catch(() => null);
    } catch {
      answer = null;
    }
    sending = false;
    sendButton.disabled = false;
    sendButton.textContent = "Put me on the list";
    token = "";
    if (widgetId !== null) window.turnstile.reset(widgetId);
    if (answer && answer.ok && answer.ticket) {
      form.reset();
      form.hidden = true;
      startSurvey(answer.ticket, Boolean(answer.dryRun));
      return;
    }
    if (answer && answer.error === "invalid" && Array.isArray(answer.fields)) {
      const known = answer.fields.filter((name) => fields[name]);
      known.forEach((name) => showError(name, MESSAGES[name]));
      if (known.length) {
        (fields[known[0]].target || fields[known[0]].error).focus();
        return;
      }
    }
    showResult(false, "You are not on the list yet.", "Something went wrong on the way. Your email is still in the form. Try again in a moment.");
  });

  let ticket = "";
  let dryRun = false;
  let deadline = 0;
  let index = 0;
  let closed = false;
  let expired = false;
  let timer = 0;
  let advance = 0;
  const picks = new Map();
  const others = new Map();

  let chain = Promise.resolve();
  let lastSent = 0;
  const latest = new Map();
  const queued = new Set();
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const post = async (question, value) => {
    for (let attempt = 0; attempt < 2; attempt++) {
      const pause = lastSent + GAP - Date.now();
      if (pause > 0) await wait(pause);
      if (expired) return;
      lastSent = Date.now();
      let status = 0;
      try {
        const response = await fetch("/api/notify/answer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ticket, question, value }),
        });
        status = response.status;
      } catch {
        status = 0;
      }
      if (status === 200) {
        live.textContent = "";
        setTimeout(() => (live.textContent = "Saved"), 50);
        return;
      }
      if (status === 404 || status === 410) return finish(true);
      if (status === 422 || status === 400) return;
    }
  };
  const save = (question, value) => {
    if (closed) return;
    latest.set(question, value);
    if (queued.has(question)) return;
    queued.add(question);
    chain = chain.then(() => {
      queued.delete(question);
      return post(question, latest.get(question));
    });
  };

  const valueOf = (question) => {
    const chosen = question.options.filter((option) => picks.get(question.id)?.has(option));
    if (question.other && picks.get(question.id)?.has(question.other)) {
      const text = (others.get(question.id) || "").replace(/\s+/g, " ").trim().slice(0, 200);
      if (text) chosen.push(`Other: ${text}`);
    }
    return question.multi ? chosen : chosen[0];
  };

  const setProgress = () => {
    const done = Math.min(index, QUESTIONS.length);
    bar.setAttribute("aria-valuenow", String(done));
    bar.setAttribute("aria-valuetext", done < QUESTIONS.length ? `Question ${done + 1} of ${QUESTIONS.length}` : "All questions done");
    bar.style.setProperty("--done", String(done / QUESTIONS.length));
  };

  const optionButton = (question, label, number) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "opt";
    button.setAttribute("aria-pressed", "false");
    button.dataset.value = label;
    const roundel = document.createElement("span");
    roundel.className = "roundel";
    roundel.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.className = "opt-text";
    text.textContent = label;
    const key = document.createElement("kbd");
    key.className = "opt-key";
    key.setAttribute("aria-hidden", "true");
    key.textContent = String(number);
    button.append(roundel, text, key);
    return button;
  };

  const show = () => {
    clearTimeout(advance);
    setProgress();
    if (index >= QUESTIONS.length) return finish();
    const question = QUESTIONS[index];
    const card = document.createElement("div");
    card.className = "q";
    if (!reduce.matches) card.classList.add("q-in");
    const count = document.createElement("p");
    count.className = "q-count";
    count.textContent = `${index + 1} of ${QUESTIONS.length}`;
    const heading = document.createElement("h3");
    heading.className = "q-title";
    heading.id = `release-q-${question.id}`;
    heading.tabIndex = -1;
    heading.textContent = question.text;
    const hint = document.createElement("p");
    hint.className = "q-hint";
    hint.textContent = question.multi ? "Pick any, then Next." : "Pick one.";
    const list = document.createElement("div");
    list.className = "q-options";
    list.setAttribute("role", "group");
    list.setAttribute("aria-labelledby", heading.id);
    const labels = question.other ? [...question.options, question.other] : question.options;
    const set = picks.get(question.id) || new Set();
    picks.set(question.id, set);
    const buttons = labels.map((label, i) => {
      const button = optionButton(question, label, i + 1);
      button.setAttribute("aria-pressed", String(set.has(label)));
      list.append(button);
      return button;
    });
    let otherBox = null;
    if (question.other) {
      otherBox = document.createElement("div");
      otherBox.className = "q-other";
      otherBox.hidden = !set.has(question.other);
      const label = document.createElement("label");
      label.className = "field-label";
      label.htmlFor = "release-other";
      label.textContent = "What else?";
      const input = document.createElement("input");
      input.id = "release-other";
      input.type = "text";
      input.maxLength = 200;
      input.autocomplete = "off";
      input.value = others.get(question.id) || "";
      let typing = 0;
      input.addEventListener("input", () => {
        others.set(question.id, input.value);
        clearTimeout(typing);
        typing = setTimeout(() => save(question.id, valueOf(question)), 700);
      });
      otherBox.append(label, input);
    }
    const nav = document.createElement("div");
    nav.className = "q-nav";
    const skip = document.createElement("button");
    skip.type = "button";
    skip.className = "button small ghost";
    skip.textContent = "Skip";
    skip.addEventListener("click", () => next(false));
    nav.append(skip);
    if (question.multi) {
      const go = document.createElement("button");
      go.type = "button";
      go.className = "button";
      go.textContent = index === QUESTIONS.length - 1 ? "Done" : "Next";
      go.addEventListener("click", () => next(true));
      nav.append(go);
    }

    list.addEventListener("click", (event) => {
      const button = event.target.closest(".opt");
      if (!button || closed) return;
      pick(question, button, buttons, otherBox);
    });

    card.append(count, heading, hint, list);
    if (otherBox) card.append(otherBox);
    card.append(nav);
    stage.replaceChildren(card);
    heading.focus({ preventScroll: true });
    if (survey.getBoundingClientRect().top < 0) survey.scrollIntoView({ block: "start", behavior: reduce.matches ? "auto" : "smooth" });
  };

  const pick = (question, button, buttons, otherBox) => {
    const label = button.dataset.value;
    const set = picks.get(question.id);
    if (question.multi) {
      if (set.has(label)) set.delete(label);
      else set.add(label);
      button.setAttribute("aria-pressed", String(set.has(label)));
      if (otherBox && label === question.other) {
        otherBox.hidden = !set.has(label);
        if (!otherBox.hidden) otherBox.querySelector("input").focus();
      }
      save(question.id, valueOf(question));
      return;
    }
    set.clear();
    set.add(label);
    buttons.forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
    save(question.id, valueOf(question));
    clearTimeout(advance);
    advance = setTimeout(() => next(false), BEAT);
  };

  const next = (flush) => {
    if (closed) return;
    const question = QUESTIONS[index];
    if (flush && question.other) save(question.id, valueOf(question));
    index++;
    show();
  };

  const finish = (late = false) => {
    if (late) expired = true;
    if (closed) return;
    closed = true;
    clearTimeout(advance);
    clearInterval(timer);
    index = QUESTIONS.length;
    setProgress();
    const card = document.createElement("div");
    card.className = "q q-done";
    if (!reduce.matches) card.classList.add("q-in");
    const heading = document.createElement("h3");
    heading.className = "q-title";
    heading.tabIndex = -1;
    heading.textContent = "Thanks, you're on the list.";
    const stamp = document.createElement("p");
    stamp.className = "stamp-line";
    const mark = document.createElement("span");
    mark.className = "stamp in";
    mark.style.setProperty("--stamp-tilt", "-4deg");
    mark.textContent = "On the list";
    stamp.append(mark);
    const body = document.createElement("p");
    body.className = "q-hint";
    body.textContent = dryRun ? "Preview: this test copy of the site keeps nothing for the real list." : "One email when Dogfighter is released. Nothing else.";
    card.append(heading, stamp, body);
    stage.replaceChildren(card);
    heading.focus({ preventScroll: true });
  };

  const startSurvey = (value, preview) => {
    ticket = value;
    dryRun = preview;
    deadline = Date.now() + WINDOW;
    survey.hidden = false;
    timer = setInterval(() => {
      if (Date.now() >= deadline) finish(true);
    }, 1000);
    show();
  };

  document.addEventListener("keydown", (event) => {
    if (survey.hidden || closed || event.metaKey || event.ctrlKey || event.altKey) return;
    if (!survey.contains(document.activeElement) && document.activeElement !== document.body) return;
    const typing = event.target.closest?.("input, textarea");
    const question = QUESTIONS[index];
    if (!question) return;
    if (event.key === "Enter") {
      if (event.target.closest?.("button")) return;
      event.preventDefault();
      next(true);
      return;
    }
    if (typing || !/^[1-9]$/.test(event.key)) return;
    const button = stage.querySelectorAll(".opt")[Number(event.key) - 1];
    if (!button) return;
    event.preventDefault();
    button.click();
  });
  document.addEventListener("visibilitychange", () => {
    if (!survey.hidden && !closed && Date.now() >= deadline) finish(true);
  });
})();
