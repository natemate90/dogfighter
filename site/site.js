(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const narrow = window.matchMedia("(max-width: 900px)");
  const sprue = document.getElementById("sprue");
  const caption = document.getElementById("caption");
  const cards = [...document.querySelectorAll(".istep")];
  const install = document.getElementById("install");
  const bar = document.getElementById("topbar");
  const STAGES = [0.16, 0.3, 0.46, 0.62, 0.82, 1];
  const NAMES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight"];

  const clamp = (v) => Math.min(1, Math.max(0, v));
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

  function kit(svg) {
    const frame = svg.querySelector(".frame");
    const parts = [...svg.querySelectorAll(".part")].map((el) => {
      const [cx, cy] = el.dataset.c.split(",").map(Number);
      const [sx, sy, r] = el.dataset.s.split(",").map(Number);
      return { el, cx, cy, dx: sx - cx, dy: sy - cy, r };
    });
    return function draw(p) {
      let fitted = 0;
      parts.forEach((part, i) => {
        const t = ease(clamp((p - 0.04 - i * 0.075) / 0.28));
        if (t === 1) fitted++;
        const k = 1 - t;
        const lift = Math.sin(t * Math.PI) * -18;
        part.el.setAttribute("transform", `translate(${(part.dx * k).toFixed(2)} ${(part.dy * k + lift).toFixed(2)}) rotate(${(part.r * k).toFixed(2)} ${part.cx} ${part.cy})`);
      });
      frame.style.opacity = (1 - 0.82 * clamp(p / 0.75)).toFixed(3);
      svg.classList.toggle("painted", p > 0.9);
      return p > 0.9 ? 9 : fitted;
    };
  }

  const drawMain = sprue ? kit(sprue) : null;
  let lastState = -1;
  function drawBig(p) {
    const state = drawMain(p);
    if (state === lastState) return;
    lastState = state;
    if (state === 9) caption.textContent = "Ready to fly.";
    else if (state === 0) caption.textContent = "Frame A has eight parts.";
    else caption.textContent = `${NAMES[state][0].toUpperCase() + NAMES[state].slice(1)} of eight parts fitted.`;
  }

  const LEVELS = [0, ...STAGES];
  let level = 0, wanted = 0, playing = false, active = -1, generation = 0;
  function play() {
    if (level === wanted) return (playing = false);
    playing = true;
    const dir = Math.sign(wanted - level), from = LEVELS[level], to = LEVELS[level + dir];
    const duration = Math.abs(wanted - level) > 1 ? 300 : 700;
    const t0 = performance.now(), gen = generation;
    const tick = (now) => {
      if (gen !== generation) return;
      if (reduce.matches) return (playing = false);
      const t = Math.min(1, (now - t0) / duration);
      drawBig(from + (to - from) * t);
      if (t < 1) return requestAnimationFrame(tick);
      level += dir;
      play();
    };
    requestAnimationFrame(tick);
  }
  function setLevel(k) {
    wanted = k;
    if (!playing) play();
  }

  function activeCard() {
    const kit = install.querySelector(".kit-col");
    const kitSticks = narrow.matches && getComputedStyle(kit).position === "sticky";
    const mid = kitSticks ? kit.getBoundingClientRect().bottom + 120 : (parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--stick")) || 72) + 100;
    let found = -1;
    cards.forEach((card, i) => {
      if (card.getBoundingClientRect().top < mid) found = i;
    });
    return found;
  }

  function onScroll() {
    if (!drawMain) return;
    const i = activeCard();
    if (i === active) return;
    active = i;
    cards.forEach((card, k) => card.classList.toggle("active", k === i));
    setLevel(i + 1);
  }

  const animated = [...document.querySelectorAll("svg")].filter((svg) => svg.querySelector("animate, animateMotion, animateTransform"));
  let started = false;
  function startAnimations() {
    if (started) return animated.forEach((svg) => svg.unpauseAnimations());
    started = true;
    document.querySelectorAll("[data-pose]").forEach((g) => g.removeAttribute("transform"));
    document.querySelectorAll("animate, animateMotion, animateTransform").forEach((el) => el.beginElementAt(Number(el.getAttribute("data-offset") || 0)));
  }

  const reveals = document.querySelectorAll(".reveal, .stamp");
  const observer = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("in");
          observer.unobserve(entry.target);
        });
      }, { rootMargin: "0px 0px -12% 0px", threshold: 0.15 })
    : null;

  function setMode() {
    if (reduce.matches) {
      document.documentElement.classList.add("static");
      bar.classList.remove("tucked");
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cards.forEach((card) => card.classList.remove("active"));
      if (drawMain) {
        lastState = -1;
        generation++;
        playing = false;
        level = wanted = LEVELS.length - 1;
        drawBig(1);
      }
      if (started) animated.forEach((svg) => svg.pauseAnimations());
      reveals.forEach((el) => el.classList.add("in"));
      return;
    }
    document.documentElement.classList.remove("static");
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    startAnimations();
    if (drawMain) {
      active = activeCard();
      cards.forEach((card, k) => card.classList.toggle("active", k === active));
      lastState = -1;
      generation++;
      playing = false;
      level = wanted = active + 1;
      drawBig(LEVELS[level]);
    }
    if (observer) {
      document.documentElement.classList.add("js");
      reveals.forEach((el) => el.classList.contains("in") || observer.observe(el));
    }
  }

  if (reduce.addEventListener) reduce.addEventListener("change", setMode);
  else if (reduce.addListener) reduce.addListener(setMode);
  if (narrow.addEventListener) narrow.addEventListener("change", setMode);
  setMode();

  document.querySelectorAll(".code .copy").forEach((button) => {
    button.addEventListener("click", async () => {
      const text = button.parentElement.querySelector("code").textContent.split("\n").map((line) => line.trim()).filter(Boolean).join(" && ");
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
        const box = button.parentElement;
        track("copy_command", { step: Number(box.dataset.step), command_id: box.dataset.command });
      } catch {
        const range = document.createRange();
        range.selectNodeContents(button.parentElement.querySelector("code"));
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        button.textContent = "Selected";
      }
      setTimeout(() => (button.textContent = "Copy"), 1800);
    });
  });

  function updateStick(inInstall) {
    const kit = install.querySelector(".kit-col");
    const sticky = inInstall && getComputedStyle(kit).position === "sticky";
    const barH = bar.offsetHeight;
    document.documentElement.style.setProperty("--stick", `${Math.round((sticky ? kit.getBoundingClientRect().height : barH) + 12)}px`);
  }
  window.addEventListener("resize", () => {
    const box = install.getBoundingClientRect();
    updateStick(narrow.matches && box.top < 60 && box.bottom > 200);
  });
  let touching = false, skipSettle = false, settling = 0, settleQuiet = 0, settleTimer = 0;
  const cancelSettle = () => {
    if (settling) cancelAnimationFrame(settling);
    settling = 0;
  };
  window.addEventListener("wheel", () => {
    skipSettle = false;
    cancelSettle();
  }, { passive: true });
  window.addEventListener("touchstart", () => {
    touching = true;
    skipSettle = false;
    cancelSettle();
  }, { passive: true });
  window.addEventListener("touchend", () => (touching = false), { passive: true });
  window.addEventListener("keydown", () => {
    skipSettle = true;
    cancelSettle();
  });
  window.addEventListener("hashchange", () => (skipSettle = true));
  document.addEventListener("click", (event) => {
    if (event.target.closest && event.target.closest('a[href^="#"]')) skipSettle = true;
  });
  function settle() {
    if (skipSettle) return (skipSettle = false);
    if (reduce.matches || touching || settling || performance.now() < settleQuiet) return;
    const box = install.getBoundingClientRect();
    if (box.top > 0 || box.bottom < window.innerHeight * 0.5) return;
    const ideal = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--stick")) || 72;
    let best = null;
    cards.forEach((card) => {
      const gap = card.getBoundingClientRect().top - ideal;
      if (!best || Math.abs(gap) < Math.abs(best)) best = gap;
    });
    if (best === null || Math.abs(best) > 90 || Math.abs(best) < 2) return;
    const from = window.scrollY, t0 = performance.now(), duration = 520;
    const tick = (now) => {
      const t = Math.min(1, (now - t0) / duration);
      window.scrollTo({ top: from + best * (1 - Math.pow(1 - t, 3)), behavior: "instant" });
      if (t < 1) settling = requestAnimationFrame(tick);
      else {
        settling = 0;
        settleQuiet = performance.now() + 300;
      }
    };
    settling = requestAnimationFrame(tick);
  }
  if ("onscrollend" in window) window.addEventListener("scrollend", settle);
  else window.addEventListener("scroll", () => {
    clearTimeout(settleTimer);
    settleTimer = setTimeout(settle, 180);
  }, { passive: true });
  const menu = document.getElementById("menu");
  const menuButton = document.querySelector(".menu-btn");
  let lastY = window.scrollY;
  bar.addEventListener("focusin", () => bar.classList.remove("tucked"));
  window.addEventListener("scroll", () => {
    const y = window.scrollY;
    const box = install.getBoundingClientRect();
    const inInstall = narrow.matches && box.top < 60 && box.bottom > 200;
    const hide = (inInstall || (y > 80 && y > lastY)) && !(menu && !menu.hidden);
    updateStick(inInstall);
    bar.classList.toggle("tucked", hide);
    lastY = y;
  }, { passive: true });

  function focusables() {
    return [...menu.querySelectorAll("a, button")];
  }
  function openMenu() {
    menu.hidden = false;
    menuButton.setAttribute("aria-expanded", "true");
    document.documentElement.classList.add("menu-open");
    menu.querySelector(".menu-close").focus();
  }
  function closeMenu(restore = true) {
    menu.hidden = true;
    menuButton.setAttribute("aria-expanded", "false");
    document.documentElement.classList.remove("menu-open");
    if (restore) menuButton.focus();
  }
  if (menu && menuButton) {
    menuButton.addEventListener("click", openMenu);
    menu.querySelector(".menu-close").addEventListener("click", () => closeMenu());
    menu.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => closeMenu(false)));
    menu.addEventListener("keydown", (event) => {
      if (event.key === "Escape") return closeMenu();
      if (event.key !== "Tab") return;
      const items = focusables();
      const first = items[0], lastItem = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  const drifter = document.querySelector(".drifter");
  const wide = window.matchMedia("(min-width: 1300px)");
  let flyTimer = 0;
  function nextPass(seconds) {
    clearTimeout(flyTimer);
    flyTimer = setTimeout(pass, seconds * 1000);
  }
  function pass() {
    if (reduce.matches || !wide.matches || document.hidden) return nextPass(30 + Math.random() * 60);
    const up = Math.random() < 0.5;
    drifter.classList.toggle("right", Math.random() < 0.5);
    drifter.style.setProperty("--dur", `${(20 + Math.random() * 20).toFixed(1)}s`);
    drifter.style.setProperty("--dir", up ? "reverse" : "normal");
    drifter.style.setProperty("--r", up ? "0deg" : "180deg");
    drifter.classList.add("pass");
  }
  if (drifter) {
    drifter.addEventListener("animationend", (event) => {
      if (event.animationName !== "drift-by") return;
      drifter.classList.remove("pass");
      nextPass(30 + Math.random() * 60);
    });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden || !drifter.classList.contains("pass")) return;
      drifter.classList.remove("pass");
      nextPass(30 + Math.random() * 60);
    });
    nextPass(8 + Math.random() * 12);
  }

  const GA_ID = "G-S35GY95CV8";
  let analyticsLoaded = false;
  function track(name, params) {
    if (analyticsLoaded && typeof window.gtag === "function") window.gtag("event", name, params);
  }
  document.querySelectorAll(".code").forEach((box) => {
    box.addEventListener("copy", () => track("copy_command_manual", { step: Number(box.dataset.step), command_id: box.dataset.command }));
  });
  document.querySelectorAll("[data-cta]").forEach((link) => {
    link.addEventListener("click", () => track("install_cta_click", { location: link.dataset.cta }));
  });

  const contactForm = document.getElementById("contact-form");
  if (contactForm) {
    const FALLBACK = "https://docs.google.com/forms/d/e/1FAIpQLSepS1A8sET4w9kPUKrlcmSQZ52lQl7x_If7ggnzYrP47VJSJQ/viewform";
    const result = document.getElementById("contact-result");
    const sendButton = contactForm.querySelector('button[type="submit"]');
    const fields = {
      topic: { error: document.getElementById("topic-error"), target: contactForm.querySelector(".topics"), focus: () => contactForm.querySelector('input[name="topic"]') },
      message: { error: document.getElementById("message-error"), target: document.getElementById("contact-message") },
      email: { error: document.getElementById("email-error"), target: document.getElementById("contact-email") },
      turnstile: { error: document.getElementById("turnstile-error"), target: null },
    };
    const MESSAGES = {
      topic: "Choose what it is about.",
      message: "Write a message of at most 5000 characters.",
      email: "This does not look like an email address. Leave it empty if you don't want a reply.",
      turnstile: "The spam check has not finished yet. Wait a moment and send again.",
    };
    const BLOCKED = "The spam check could not load. A blocker may stop it. Reload the page, or use the Google Form below.";
    let widgetId = null;
    let turnstileFailed = false;
    let token = "";
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
    const focusField = (name) => {
      const field = fields[name];
      const element = field.focus ? field.focus() : field.target;
      (element || field.error).focus?.();
    };

    window.onDogfighterTurnstile = () => {
      widgetId = window.turnstile.render("#contact-turnstile", {
        sitekey: ["localhost", "127.0.0.1"].includes(location.hostname) ? "1x00000000000000000000AA" : contactForm.dataset.sitekey,
        action: "contact",
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
      if (document.querySelector("script[data-turnstile]")) return;
      const script = document.createElement("script");
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=onDogfighterTurnstile";
      script.async = true;
      script.dataset.turnstile = "";
      script.addEventListener("error", () => {
        turnstileFailed = true;
        showError("turnstile", BLOCKED);
      });
      document.head.appendChild(script);
    };
    if ("IntersectionObserver" in window) {
      const watcher = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          watcher.disconnect();
          loadTurnstile();
        }
      }, { rootMargin: "600px 0px" });
      watcher.observe(document.getElementById("contact"));
    } else {
      loadTurnstile();
    }
    contactForm.addEventListener("focusin", loadTurnstile);

    const showResult = (sent, text) => {
      result.replaceChildren();
      const heading = document.createElement("p");
      heading.className = "result-title";
      heading.textContent = sent ? "Message sent. Thank you!" : "Your message was not sent.";
      const body = document.createElement("p");
      body.textContent = text;
      result.append(heading, body);
      if (!sent) {
        const fallback = document.createElement("p");
        fallback.append("Your text is still in the form. You can try again, or send it through the ");
        const link = document.createElement("a");
        link.href = FALLBACK;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = "Google Form";
        fallback.append(link, ".");
        result.append(fallback);
      }
      result.classList.toggle("failed", !sent);
      result.hidden = false;
      result.focus();
    };

    contactForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (sending) return;
      const data = new FormData(contactForm);
      const topic = data.get("topic") || "";
      const message = String(data.get("message") || "").trim();
      const email = String(data.get("email") || "").trim();
      const invalid = [];
      if (!topic) invalid.push("topic");
      if (!message || message.length > 5000) invalid.push("message");
      if (email && !fields.email.target.checkValidity()) invalid.push("email");
      if (!token) {
        invalid.push("turnstile");
        loadTurnstile();
      }
      Object.keys(fields).forEach((name) => showError(name, invalid.includes(name) ? (name === "turnstile" && turnstileFailed ? BLOCKED : MESSAGES[name]) : ""));
      if (invalid.length) {
        focusField(invalid[0]);
        return;
      }
      sending = true;
      sendButton.disabled = true;
      sendButton.textContent = "Sending…";
      result.hidden = true;
      let answer = null;
      try {
        const response = await fetch("/api/contact", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic, message, email, website: data.get("website") || "", "cf-turnstile-response": token }),
        });
        answer = await response.json().catch(() => null);
      } catch {
        answer = null;
      }
      sending = false;
      sendButton.disabled = false;
      sendButton.textContent = "Send";
      token = "";
      if (widgetId !== null) window.turnstile.reset(widgetId);
      if (answer && answer.ok) {
        track("contact_submit", { topic });
        contactForm.reset();
        contactForm.hidden = true;
        if (answer.dryRun) showResult(true, "Preview: message not sent. This test copy of the site checks the form but passes nothing on.");
        else showResult(true, email ? "It is on its way to the maintainer, who will answer at the email you gave." : "It is on its way to the maintainer.");
        return;
      }
      if (answer && answer.error === "invalid" && Array.isArray(answer.fields)) {
        const known = answer.fields.filter((name) => fields[name]);
        known.forEach((name) => showError(name, MESSAGES[name]));
        if (known.length) {
          focusField(known[0]);
          return;
        }
      }
      showResult(false, "Something went wrong on the way.");
    });
  }
  const depths = [25, 50, 75, 90, 100], sentDepths = new Set();
  window.addEventListener("scroll", () => {
    if (!analyticsLoaded) return;
    const doc = document.documentElement;
    const percent = ((window.scrollY + window.innerHeight) / doc.scrollHeight) * 100;
    depths.forEach((d) => {
      if (percent + 0.5 >= d && !sentDepths.has(d)) {
        sentDepths.add(d);
        track("scroll_depth", { percent: d });
      }
    });
  }, { passive: true });
  const consent = document.getElementById("consent");
  const readChoice = () => {
    try {
      return localStorage.getItem("consent");
    } catch {
      return null;
    }
  };
  const saveChoice = (value) => {
    try {
      localStorage.setItem("consent", value);
    } catch {}
  };
  function loadAnalytics() {
    window[`ga-disable-${GA_ID}`] = false;
    if (analyticsLoaded) return;
    analyticsLoaded = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() {
      window.dataLayer.push(arguments);
    };
    window.gtag("js", new Date());
    window.gtag("config", GA_ID);
    const tag = document.createElement("script");
    tag.async = true;
    tag.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
    document.head.appendChild(tag);
  }
  function dropAnalyticsCookies() {
    window[`ga-disable-${GA_ID}`] = true;
    const host = location.hostname.split(".");
    const domains = ["", ...host.map((_, i) => "." + host.slice(i).join("."))];
    document.cookie.split(";").map((c) => c.split("=")[0].trim()).filter((name) => name.startsWith("_ga")).forEach((name) => {
      domains.forEach((domain) => {
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${domain ? `; domain=${domain}` : ""}`;
      });
    });
  }
  let consentReturn = null;
  function showConsent() {
    consentReturn = document.activeElement;
    consent.hidden = false;
    document.documentElement.classList.add("consent-open");
  }
  function hideConsent() {
    const hadFocus = consent.contains(document.activeElement);
    consent.hidden = true;
    document.documentElement.classList.remove("consent-open");
    if (hadFocus && consentReturn && consentReturn !== document.body && consentReturn.isConnected) consentReturn.focus();
  }
  if (consent) {
    consent.querySelectorAll("[data-consent]").forEach((button) => {
      button.addEventListener("click", () => {
        const value = button.dataset.consent;
        saveChoice(value);
        hideConsent();
        if (value === "granted") loadAnalytics();
        else dropAnalyticsCookies();
      });
    });
    const settings = document.getElementById("cookie-settings");
    if (settings) settings.addEventListener("click", () => {
      showConsent();
      consent.querySelector("button").focus();
    });
    const choice = readChoice();
    if (choice === "granted") loadAnalytics();
    else if (choice !== "denied") setTimeout(showConsent, 1200);
  }

  const viewer = document.getElementById("viewer");
  const shots = [...document.querySelectorAll(".shot")];
  if (viewer && typeof viewer.showModal === "function" && shots.length) {
    const img = viewer.querySelector(".viewer-img");
    const caption = viewer.querySelector(".viewer-caption");
    let current = 0, opener = null, touchX = null;
    const show = (i) => {
      current = (i + shots.length) % shots.length;
      const thumb = shots[current].querySelector("img");
      img.src = shots[current].getAttribute("href");
      img.alt = thumb.alt;
      caption.textContent = thumb.alt;
    };
    const close = () => viewer.close();
    shots.forEach((shot, i) => {
      shot.addEventListener("click", (event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
        event.preventDefault();
        opener = shot;
        show(i);
        document.documentElement.classList.add("viewer-open");
        viewer.showModal();
        viewer.querySelector(".viewer-close").focus();
      });
    });
    viewer.addEventListener("close", () => {
      document.documentElement.classList.remove("viewer-open");
      img.removeAttribute("src");
      if (opener) opener.focus();
    });
    viewer.querySelector(".viewer-prev").addEventListener("click", () => show(current - 1));
    viewer.querySelector(".viewer-next").addEventListener("click", () => show(current + 1));
    viewer.querySelector(".viewer-close").addEventListener("click", close);
    viewer.addEventListener("click", (event) => {
      if (event.target === viewer || event.target.classList.contains("viewer-figure")) close();
    });
    viewer.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") show(current - 1);
      else if (event.key === "ArrowRight") show(current + 1);
    });
    viewer.addEventListener("touchstart", (event) => (touchX = event.touches[0].clientX), { passive: true });
    viewer.addEventListener("touchend", (event) => {
      if (touchX === null) return;
      const dx = event.changedTouches[0].clientX - touchX;
      touchX = null;
      if (Math.abs(dx) > 40) show(current + (dx < 0 ? 1 : -1));
    }, { passive: true });
  }

  document.querySelectorAll(".yt").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      const player = document.createElement("iframe");
      player.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(link.dataset.id)}?autoplay=1`;
      player.title = link.dataset.title;
      player.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
      player.allowFullscreen = true;
      player.referrerPolicy = "strict-origin-when-cross-origin";
      link.replaceWith(player);
      player.focus();
    });
  });
})();
