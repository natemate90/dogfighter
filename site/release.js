(() => {
  const form = document.getElementById("release-form");
  if (!form) return;
  const section = document.getElementById("release");
  const card = document.getElementById("release-card");
  const letter = document.getElementById("release-letter");
  const postmark = card.querySelector(".pc-pm");
  const censor = card.querySelector(".pc-censor");
  const slot = card.querySelector(".pc-slot");
  const survey = document.getElementById("release-survey");
  const stage = survey.querySelector(".pc-stage");
  const bar = survey.querySelector(".pc-boxes");
  const boxes = [...bar.querySelectorAll("li")];
  const count = document.getElementById("release-count");
  const live = document.getElementById("release-live");
  const foot = survey.querySelector(".pc-foot");
  const status = document.getElementById("release-status");
  const result = document.getElementById("release-result");
  const sendButton = form.querySelector('button[type="submit"]');
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const PRODUCTION = ["dogfighter.net", "www.dogfighter.net"].includes(location.hostname);
  document.getElementById("release-test").hidden = PRODUCTION;
  const WINDOW = 30 * 60 * 1000;
  const BEAT = 450;
  const GAP = 3000;
  const SETTLE = 1300;
  const WORDS = ["no", "one", "two", "three", "four", "five", "six"];

  const LETTERS = {
    sent: ["You are on the list, thank you.", " If you can spare a minute, I would love to hear how you would play: six small questions, and you may skip any of them."],
    done: ["Thank you, that is everything I wanted to ask. You are on the list, and you get one note from me, the day the new edition is out."],
    closed: ["The questions have closed, but you are still on the list. What you answered is saved, and you get one note from me, the day the new edition is out."],
  };

  const QUESTIONS = [
    {
      id: "devices",
      text: "Which devices would you play on?",
      multi: true,
      groups: [
        ["Computers", ["Windows PC", "Mac", "Linux", "Steam Deck"]],
        ["Mobile devices", ["iPhone", "iPad", "Android phone", "Android tablet"]],
        ["TV and consoles", ["Apple TV", "Nintendo Switch", "PlayStation", "Xbox"]],
      ],
    },
    { id: "store", text: "Where would you buy it?", multi: true, alone: "No preference", options: ["Steam", "GOG", "dogfighter.net", "App Store", "Google Play", "No preference"] },
    { id: "online", text: "Would you play online with friends?", options: ["Yes", "Maybe", "No"] },
    { id: "played", text: "Did you play the original?", options: ["Yes, back then", "Yes, recently", "No"] },
    { id: "cd", text: "Do you still have the original CD?", options: ["Yes", "No", "Not sure"] },
    { id: "wishes", text: "What should the new edition add or fix?", multi: true, other: "Something else…", options: ["Online multiplayer", "Widescreen", "Controller support", "New missions", "Level editor"] },
  ];
  QUESTIONS.forEach((question) => {
    if (question.groups) question.options = question.groups.flatMap(([, options]) => options);
  });

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

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };
  const replay = (node, name) => {
    node.classList.remove(name);
    void node.offsetWidth;
    node.classList.add(name);
  };

  const showError = (name, text) => {
    const field = fields[name];
    const was = field.error.textContent;
    field.error.textContent = text || "";
    field.error.hidden = !text;
    if (text && text !== was) replay(field.error, "nudge");
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
      appearance: "interaction-only",
      "response-field": false,
      "before-interactive-callback": () => slot.classList.add("asks"),
      "after-interactive-callback": () => slot.classList.remove("asks"),
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
    const heading = element("p", "result-title", title);
    result.append(heading, element("p", "", text));
    result.classList.add("failed");
    result.hidden = false;
    result.focus();
  };

  const write = ([first, more]) => {
    letter.replaceChildren(first);
    if (more) letter.append(element("span", "pc-more", more));
  };

  const today = () => {
    const date = new Date();
    return { day: date.getDate(), month: date.toLocaleString("en-GB", { month: "short" }).toUpperCase(), year: date.getFullYear() };
  };

  const strike = () => {
    const { day, month, year } = today();
    postmark.querySelector(".pm-date").textContent = `${day} ${month} ${String(year).slice(2)}`;
    postmark.setAttribute("aria-label", `Postmark: Dogfighter field post, on the list, ${day} ${month} ${year}`);
    postmark.removeAttribute("hidden");
    postmark.classList.add("struck");
    censor.hidden = false;
    censor.classList.add("struck");
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (sending || card.classList.contains("listed")) return;
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
    form.setAttribute("aria-busy", "true");
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
    form.removeAttribute("aria-busy");
    token = "";
    if (widgetId !== null) window.turnstile.reset(widgetId);
    if (answer && answer.ok && answer.ticket) {
      sendButton.textContent = "Signed up";
      card.classList.add("listed");
      form.querySelectorAll("input").forEach((input) => (input.readOnly = true));
      strike();
      write(LETTERS.sent);
      status.textContent = "Posted. The first question comes up in a moment.";
      setTimeout(() => startSurvey(answer.ticket), SETTLE);
      return;
    }
    sendButton.disabled = false;
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
  let savedNote = null;
  const picks = new Map();
  const others = new Map();
  const answered = new Set();

  let seq = 0;
  let dirty = false;
  let lastSent = 0;
  let flushTimer = 0;
  let retries = 0;
  let kept = "";
  let inFlight = 0;

  const say = (text) => {
    live.textContent = "";
    setTimeout(() => (live.textContent = text), 50);
  };

  const fullSet = () => Object.fromEntries(QUESTIONS.map((question) => [question.id, valueOf(question) ?? ""]));

  const flush = async (now = false, final = false) => {
    clearTimeout(flushTimer);
    if (!ticket || expired || !dirty) return;
    const pause = lastSent + GAP - Date.now();
    if (!now && pause > 0) {
      flushTimer = setTimeout(() => flush(false, final), pause);
      return;
    }
    dirty = false;
    const answers = fullSet();
    const text = JSON.stringify(answers);
    if (text === kept && !inFlight) return;
    lastSent = Date.now();
    let code = 0;
    let result = null;
    inFlight++;
    try {
      const response = await fetch("/api/notify/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket, seq: ++seq, answers, final }),
        keepalive: true,
      });
      code = response.status;
      result = await response.json().catch(() => null);
    } catch {
      code = 0;
    }
    inFlight--;
    if (code === 200 && result?.kept === "limit") {
      if (!final) dirty = true;
      else if (savedNote) savedNote.textContent = "You are on the list, and you get one email, on the day the new edition is out. Nothing else.";
      return;
    }
    if (code === 200) {
      retries = 0;
      if (result?.kept !== "newer") kept = text;
      answered.clear();
      Object.entries(answers).forEach(([name, value]) => (Array.isArray(value) ? value.length : value) && answered.add(name));
      if (!closed) say("Saved");
      return;
    }
    if (code === 404 || code === 410) return finish(true);
    if (code === 400 || code === 422) return;
    dirty = true;
    if (retries++ < 2) flushTimer = setTimeout(() => flush(), GAP);
    if (!closed) say("Not saved");
    else if (savedNote) savedNote.textContent = "Some answers did not save. You are still on the list, and you get one email, on the day the new edition is out.";
  };
  const save = () => {
    if (!closed) dirty = true;
  };

  const valueOf = (question) => {
    const chosen = question.options.filter((option) => picks.get(question.id)?.has(option));
    if (question.other && picks.get(question.id)?.has(question.other)) {
      const text = (others.get(question.id) || "").replace(/\s+/g, " ").trim().slice(0, 200);
      if (text) chosen.push(`Other: ${text}`);
    }
    return question.multi ? chosen : chosen[0];
  };

  const setProgress = (state, fresh = -1) => {
    const total = QUESTIONS.length;
    boxes.forEach((box, i) => {
      const done = state === "off" ? answered.has(QUESTIONS[i].id) : state === "done" || i < index;
      box.className = done ? "done" : state === "now" && i === index ? "now" : "";
      if (i === fresh && done) replay(box, "fresh");
    });
    bar.classList.toggle("off", state === "off");
    const text = state === "now" ? `Question ${index + 1} of ${total}` : state === "off" ? `${answered.size} of ${total} answered` : "All six questions done";
    count.textContent = text;
    bar.setAttribute("aria-valuenow", String(state === "now" ? index : state === "off" ? answered.size : total));
    bar.setAttribute("aria-valuetext", state === "off" ? `${text}, questions closed` : text);
  };

  const marker = (question) => {
    const mark = element("span", question.multi ? "pc-box" : "pc-rnd");
    mark.setAttribute("aria-hidden", "true");
    return mark;
  };
  const choice = (question, label, className) => {
    const wrap = element("label", className);
    const input = element("input");
    input.type = question.multi ? "checkbox" : "radio";
    input.name = `release-${question.id}`;
    input.value = label;
    input.checked = picks.get(question.id).has(label);
    wrap.append(input, marker(question), label);
    return wrap;
  };
  const linkButton = (label, onClick) => {
    const button = element("button", "linklike", label);
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  };

  const place = (nodes, direction, quiet = false) => {
    const here = survey.contains(document.activeElement) || document.activeElement === document.body;
    stage.replaceChildren(...nodes);
    stage.classList.remove("fwd", "back");
    if (direction) replay(stage, direction);
    if (quiet && !here) return;
    stage.querySelector(".pc-q")?.focus({ preventScroll: true });
    if (!quiet && card.getBoundingClientRect().top < 0) card.scrollIntoView({ block: "start", behavior: reduce.matches ? "auto" : "smooth" });
  };

  const show = (direction = "fwd", fresh = -1, quiet = false) => {
    clearTimeout(advance);
    if (index >= QUESTIONS.length) return finish();
    setProgress("now", fresh);
    const question = QUESTIONS[index];
    if (!picks.has(question.id)) picks.set(question.id, new Set());
    const field = element("fieldset", "pc-qset");
    const heading = element("legend", "pc-q", question.text);
    heading.id = `release-q-${question.id}`;
    heading.tabIndex = -1;
    const hint = element("p", "pc-hint", question.alone ? `Pick all that apply, or ${question.alone}.` : question.multi ? "Pick all that apply." : "Tap an answer to go on.");
    hint.id = `release-hint-${question.id}`;
    field.setAttribute("aria-describedby", hint.id);
    let list;
    if (question.groups) {
      list = element("div", "pc-groups");
      question.groups.forEach(([name, options]) => {
        const group = element("div", "pc-group");
        group.setAttribute("role", "group");
        group.setAttribute("aria-label", name);
        group.append(element("p", "pc-cap", name), ...options.map((label) => choice(question, label, "pc-pick")));
        list.append(group);
      });
    } else if (question.multi) {
      list = element("div", "pc-picks");
      (question.other ? [...question.options, question.other] : question.options).forEach((label) => list.append(choice(question, label, "pc-pick")));
    } else {
      list = element("div", "pc-opts");
      question.options.forEach((label) => list.append(choice(question, label, "pc-opt")));
    }
    field.append(heading, hint, list);

    let otherBox = null;
    if (question.other) {
      otherBox = element("div", "pc-other");
      otherBox.hidden = !picks.get(question.id).has(question.other);
      const area = element("textarea", "pc-ta");
      area.id = "release-other";
      area.maxLength = 200;
      area.placeholder = "What else?";
      area.setAttribute("aria-label", "What else should the new edition add or fix?");
      area.value = others.get(question.id) || "";
      area.addEventListener("input", () => {
        others.set(question.id, area.value);
        save();
      });
      otherBox.append(area);
      field.append(otherBox);
    }

    let arrowed = false;
    let tapped = null;
    list.addEventListener("pointerdown", (event) => {
      arrowed = false;
      const input = event.target.closest("label")?.querySelector("input");
      tapped = input?.type === "radio" && input.checked ? input : null;
    });
    list.addEventListener("click", (event) => {
      if (!tapped || event.target !== tapped || closed) return;
      tapped = null;
      moveOn();
    });
    list.addEventListener("keydown", (event) => {
      if (event.key.startsWith("Arrow")) arrowed = true;
      const input = event.target;
      if (input.type !== "radio" || closed) return;
      if (event.key === "Enter" || (event.key === " " && input.checked)) {
        event.preventDefault();
        event.stopPropagation();
        if (!input.checked) {
          input.checked = true;
          pick(question, input, list, otherBox);
        }
        moveOn();
      }
    });
    list.addEventListener("change", (event) => {
      if (closed) return;
      const byArrow = arrowed;
      arrowed = false;
      pick(question, event.target, list, otherBox);
      if (event.target.type === "radio" && !byArrow) moveOn();
    });

    const parts = [];
    if (index > 0) parts.push(linkButton("Back", back));
    const acts = element("div", "pc-acts");
    acts.append(linkButton("Skip", () => next()));
    if (question.multi) {
      const go = element("button", "button", index === QUESTIONS.length - 1 ? "Finish" : "Continue");
      go.type = "button";
      go.addEventListener("click", () => next());
      acts.append(go);
    }
    parts.push(acts);
    foot.replaceChildren(...parts);
    foot.classList.toggle("wide", Boolean(question.multi));
    place([field], direction, quiet);
  };

  const moveOn = () => {
    clearTimeout(advance);
    advance = setTimeout(() => next(), BEAT);
  };

  const pick = (question, input, list, otherBox) => {
    const label = input.value;
    const set = picks.get(question.id);
    input.closest("label").classList.add("pc-inked");
    if (!question.multi) {
      set.clear();
      set.add(label);
      save();
      return;
    }
    if (input.checked) set.add(label);
    else set.delete(label);
    if (question.alone && input.checked) {
      const boxes = [...list.querySelectorAll("input")];
      const cleared = boxes.filter((box) => box !== input && box.checked && (label === question.alone || box.value === question.alone));
      cleared.forEach((box) => {
        box.checked = false;
        set.delete(box.value);
      });
      if (cleared.length) say(label === question.alone ? `${question.alone}: the stores are unticked` : `${question.alone} unticked`);
    }
    if (otherBox && label === question.other) {
      otherBox.hidden = !input.checked;
      if (!otherBox.hidden) otherBox.querySelector("textarea").focus();
    }
    save();
  };

  const next = () => {
    if (closed) return;
    index++;
    show("fwd", index - 1);
    flush(false, index >= QUESTIONS.length);
  };

  const back = () => {
    if (closed || index === 0) return;
    index--;
    show("back");
    flush();
  };

  const finish = (late = false) => {
    if (late) expired = true;
    if (closed) return;
    closed = true;
    clearTimeout(advance);
    clearInterval(timer);
    card.classList.remove("asking");
    const { day, month, year } = today();
    const view = element("div", "pc-end");
    const heading = element("h3", "pc-q", late ? "The questions have closed." : "That is everything. Thank you.");
    heading.tabIndex = -1;
    const stamp = element("span", late ? "pc-hs pc-cl struck" : "pc-hs pc-rc struck");
    stamp.setAttribute("aria-hidden", "true");
    if (late) {
      setProgress("off");
      write(LETTERS.closed);
      const said = answered.size;
      stamp.append("Post closed", element("b", "", "30 minutes"));
      view.append(heading, element("p", "", `They stay open for 30 minutes after you sign up. You are still on the list${said ? `, and the ${said === 1 ? "answer" : `${WORDS[said]} answers`} you gave ${said === 1 ? "is" : "are"} saved` : ""}.`));
      const more = element("p", "pc-hint", "Something you still want to tell us? Use the ");
      const contact = element("a", "", "contact form");
      contact.href = "#contact";
      more.append(contact, ".");
      view.append(more);
    } else {
      setProgress("done");
      write(LETTERS.done);
      stamp.append("Received", element("b", "", `${day} ${month} ${year}`), "Release list");
      savedNote = element("p", "", "Your answers are saved. You get one email, on the day the new edition is out. Nothing else.");
      const more = element("p", "pc-hint", "Changed your mind? Use the ");
      const contact = element("a", "", "contact form");
      contact.href = "#contact";
      more.append(contact, " and we take you off the list.");
      view.append(heading, savedNote, more);
    }
    const row = element("div", "pc-row");
    row.append(stamp);
    view.append(row);
    const play = element("a", "linklike", "Play it today from your own CD");
    play.href = "#install";
    const acts = element("div", "pc-acts");
    acts.append(play);
    foot.replaceChildren(acts);
    foot.classList.remove("wide");
    live.textContent = "";
    place([view], reduce.matches ? "" : "fwd", late);
  };

  const startSurvey = (value) => {
    ticket = value;
    deadline = Date.now() + WINDOW;
    const here = form.contains(document.activeElement) || document.activeElement === document.body;
    const stay = here ? null : document.activeElement;
    form.hidden = true;
    survey.hidden = false;
    card.classList.add("asking");
    timer = setInterval(() => {
      if (Date.now() >= deadline) finish(true);
    }, 1000);
    show("fwd", -1, !here);
    if (stay && document.activeElement !== stay) stay.focus({ preventScroll: true });
  };

  document.addEventListener("keydown", (event) => {
    if (survey.hidden || closed || event.isComposing || event.metaKey || event.ctrlKey || event.altKey) return;
    if (!survey.contains(document.activeElement) && document.activeElement !== document.body) return;
    const typing = event.target.closest?.("textarea, input[type=text], input[type=email]");
    const question = QUESTIONS[index];
    if (!question) return;
    if (event.key === "Enter") {
      if (event.target.closest?.("button, a, textarea")) return;
      event.preventDefault();
      next();
      return;
    }
    if (typing || !/^[1-9]$/.test(event.key)) return;
    const input = stage.querySelectorAll(".pc-opt input, .pc-pick input")[Number(event.key) - 1];
    if (!input) return;
    event.preventDefault();
    if (input.type === "radio" && input.checked) moveOn();
    else input.click();
  });
  window.addEventListener("pagehide", () => flush(true, true));
  document.addEventListener("visibilitychange", () => {
    if (survey.hidden) return;
    if (!closed && Date.now() >= deadline) finish(true);
    else if (document.visibilityState === "hidden") flush();
  });
})();
