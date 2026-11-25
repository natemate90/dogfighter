(() => {
  const form = document.getElementById("release-form");
  if (!form) return;
  const section = document.getElementById("release");
  const card = document.getElementById("release-card");
  const intro = card.querySelector(".pc-intro");
  const listed = card.querySelector(".pc-listed");
  const postmark = card.querySelector(".pc-postmark");
  const survey = document.getElementById("release-survey");
  const stage = survey.querySelector(".survey-stage");
  const bar = survey.querySelector(".pc-progress");
  const segments = [...bar.children];
  const count = document.getElementById("release-count");
  const live = document.getElementById("release-live");
  const result = document.getElementById("release-result");
  const sendButton = form.querySelector('button[type="submit"]');
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const PRODUCTION = ["dogfighter.net", "www.dogfighter.net"].includes(location.hostname);
  const WINDOW = 30 * 60 * 1000;
  const BEAT = 450;
  const GAP = 1100;
  const SEND_LABEL = "Put me on the list";

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
    email: "Enter the full address, like you@example.com.",
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
      theme: "light",
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
    if (!document.querySelector("script[data-turnstile]")) document.getElementById("contact-form")?.dispatchEvent(new FocusEvent("focusin"));
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
    setTimeout(() => {
      if (!window.turnstile) turnstileFailed = true;
    }, 10000);
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

  const showResult = (title, text) => {
    result.replaceChildren();
    const heading = document.createElement("p");
    heading.className = "result-title";
    heading.textContent = title;
    const body = document.createElement("p");
    body.textContent = text;
    result.append(heading, body);
    result.classList.add("failed");
    result.hidden = false;
    result.focus();
  };

  const setSending = (on) => {
    sending = on;
    sendButton.disabled = on;
    if (on) form.setAttribute("aria-busy", "true");
    else form.removeAttribute("aria-busy");
    sendButton.replaceChildren();
    if (on) {
      const spin = document.createElement("span");
      spin.className = "pc-spin";
      spin.setAttribute("aria-hidden", "true");
      sendButton.append(spin, "Putting you on the list…");
    } else {
      sendButton.textContent = SEND_LABEL;
    }
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
    setSending(true);
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
    setSending(false);
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
    showResult("You are not on the list yet.", "Something went wrong on the way. Your email is still in the form. Try again in a moment.");
  });

  let ticket = "";
  let deadline = 0;
  let index = 0;
  let closed = false;
  let expired = false;
  let timer = 0;
  let advance = 0;
  const picks = new Map();
  const others = new Map();
  const answered = new Set();

  let chain = Promise.resolve();
  let lastSent = 0;
  const latest = new Map();
  const queued = new Set();
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const say = (text) => {
    live.textContent = "";
    setTimeout(() => (live.textContent = text), 50);
  };

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
        if (Array.isArray(value) ? value.length : value) answered.add(question);
        else answered.delete(question);
        if (!closed) say("Saved");
        return;
      }
      if (status === 404 || status === 410) return finish(true);
      if (status === 422 || status === 400) return;
    }
    if (!closed) say("Not saved");
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

  const setProgress = (state) => {
    const total = QUESTIONS.length;
    segments.forEach((segment, i) => {
      segment.className = state === "now" ? (i < index ? "done" : i === index ? "now" : "") : state === "off" ? (answered.has(QUESTIONS[i].id) ? "done" : "") : "done";
    });
    bar.classList.toggle("off", state === "off");
    const text = state === "now" ? `Question ${index + 1} of ${total}` : state === "off" ? `${answered.size} of ${total} answered` : "All six questions done";
    count.textContent = text;
    bar.setAttribute("aria-valuenow", String(state === "now" ? index : state === "off" ? answered.size : total));
    bar.setAttribute("aria-valuetext", state === "off" ? `${text}, questions closed` : text);
  };

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };

  const optionButton = (question, label, number) => {
    const button = element("button", "opt");
    button.type = "button";
    button.setAttribute("aria-pressed", "false");
    button.dataset.value = label;
    const marker = element("span", question.multi ? "pc-box" : "roundel");
    marker.setAttribute("aria-hidden", "true");
    const key = element("kbd", "opt-key", String(number));
    key.setAttribute("aria-hidden", "true");
    button.append(marker, element("span", "opt-text", label), key);
    return button;
  };

  const linkButton = (label, onClick) => {
    const button = element("button", "pc-link", label);
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  };

  const place = (view) => {
    if (!reduce.matches) view.classList.add("q-in");
    stage.replaceChildren(view);
    view.querySelector(".q-title").focus({ preventScroll: true });
    if (card.getBoundingClientRect().top < 0) card.scrollIntoView({ block: "start", behavior: reduce.matches ? "auto" : "smooth" });
  };

  const show = () => {
    clearTimeout(advance);
    if (index >= QUESTIONS.length) return finish();
    setProgress("now");
    const question = QUESTIONS[index];
    const view = element("div", "q");
    const heading = element("h3", "q-title", question.text);
    heading.id = `release-q-${question.id}`;
    heading.tabIndex = -1;
    const hint = element("p", "q-hint", question.multi ? "Pick all that apply." : "Tap an answer to go on.");
    const list = element("div", "q-options");
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
      otherBox = element("div", "pc-other");
      otherBox.hidden = !set.has(question.other);
      const label = element("label", "pc-label-text", "What else?");
      label.htmlFor = "release-other";
      const input = element("input");
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
    const foot = element("div", "q-foot");
    if (index > 0) foot.append(linkButton("Back", back));
    const acts = element("div", "q-acts");
    acts.append(linkButton("Skip", () => next(false)));
    if (question.multi) {
      const go = element("button", "button", index === QUESTIONS.length - 1 ? "Finish" : "Continue");
      go.type = "button";
      go.addEventListener("click", () => next(true));
      acts.append(go);
    }
    foot.append(acts);

    list.addEventListener("click", (event) => {
      const button = event.target.closest(".opt");
      if (!button || closed) return;
      pick(question, button, buttons, otherBox);
    });

    view.append(heading, hint, list);
    if (otherBox) view.append(otherBox);
    view.append(foot);
    place(view);
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

  const back = () => {
    if (closed || index === 0) return;
    index--;
    show();
  };

  const finish = (late = false) => {
    if (late) expired = true;
    if (closed) return;
    closed = true;
    clearTimeout(advance);
    clearInterval(timer);
    const view = element("div", "q q-done");
    const foot = element("div", "q-foot");
    const play = element("a", "pc-link", "Play it today from your own CD");
    play.href = "#install";
    foot.append(play);
    if (late) {
      setProgress("off");
      const said = answered.size;
      view.append(
        element("h3", "q-title", "The questions have closed."),
        element("p", "", `They stay open for 30 minutes after you sign up. You are still on the list${said ? `, and the ${said === 1 ? "answer" : `${said} answers`} you gave ${said === 1 ? "is" : "are"} saved` : ""}.`),
      );
    } else {
      setProgress("done");
      view.append(element("h3", "q-title", "Thanks. That is everything."), element("p", "", "Your answers are saved. You hear from us once, on the day Dogfighter is released. Nothing else."));
    }
    const remove = element("p", "pc-soft", "Changed your mind? Use the ");
    const contact = element("a", "", "contact form");
    contact.href = "#contact";
    remove.append(contact, " and we take you off the list.");
    view.append(remove, foot);
    view.querySelector(".q-title").tabIndex = -1;
    live.textContent = "";
    place(view);
  };

  const strike = () => {
    const date = new Date();
    postmark.querySelector(".pm-date").textContent = `${date.getDate()} ${date.toLocaleString("en-GB", { month: "short" }).toUpperCase()} ${date.getFullYear()}`;
    postmark.removeAttribute("hidden");
    postmark.classList.add("struck");
    card.classList.add("listed");
    intro.hidden = true;
    listed.hidden = false;
  };

  const startSurvey = (value, preview) => {
    ticket = value;
    deadline = Date.now() + WINDOW;
    listed.querySelector(".pc-preview").hidden = !preview;
    strike();
    survey.hidden = false;
    timer = setInterval(() => {
      if (Date.now() >= deadline) finish(true);
    }, 1000);
    show();
  };

  document.addEventListener("keydown", (event) => {
    if (survey.hidden || closed || event.isComposing || event.metaKey || event.ctrlKey || event.altKey) return;
    if (!survey.contains(document.activeElement) && document.activeElement !== document.body) return;
    const typing = event.target.closest?.("input, textarea");
    const question = QUESTIONS[index];
    if (!question) return;
    if (event.key === "Enter") {
      if (event.target.closest?.("button, a")) return;
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
