(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const narrow = window.matchMedia("(max-width: 900px)");
  const sprue = document.getElementById("sprue");
  const caption = document.getElementById("caption");
  const cards = [...document.querySelectorAll(".istep")];
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

  const EASE_TIME = 0.4, MAX_RATE = 0.6;
  let target = 0, shown = 0, easing = false, then = 0, active = -1;
  function follow(now) {
    if (reduce.matches) return (easing = false);
    const dt = Math.max(0, Math.min(0.1, (now - then) / 1000));
    then = now;
    const step = (target - shown) * (1 - Math.exp(-dt / EASE_TIME));
    shown += Math.max(-MAX_RATE * dt, Math.min(MAX_RATE * dt, step));
    if (Math.abs(target - shown) < 0.0005) shown = target;
    drawBig(shown);
    if (shown === target) easing = false;
    else requestAnimationFrame(follow);
  }
  function setTarget(p) {
    target = p;
    if (easing) return;
    easing = true;
    then = performance.now();
    requestAnimationFrame(follow);
  }

  function activeCard() {
    const mid = window.innerHeight * 0.55;
    let found = -1;
    cards.forEach((card, i) => {
      if (card.getBoundingClientRect().top < mid) found = i;
    });
    return found;
  }

  function onScroll() {
    if (!drawMain || narrow.matches) return;
    const i = activeCard();
    if (i === active) return;
    active = i;
    cards.forEach((card, k) => card.classList.toggle("active", k === i));
    setTarget(i < 0 ? 0 : STAGES[i]);
  }

  const miniDone = new WeakSet();
  function playMini(card) {
    if (miniDone.has(card)) return;
    miniDone.add(card);
    const i = cards.indexOf(card);
    const from = i > 0 ? STAGES[i - 1] : 0, to = STAGES[i];
    const draw = card.miniDraw;
    if (!draw) return;
    const t0 = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - t0) / 900);
      draw(from + (to - from) * t);
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  let minisBuilt = false;
  function buildMinis() {
    if (minisBuilt || !sprue) return;
    minisBuilt = true;
    cards.forEach((card, i) => {
      const holder = card.querySelector(".mini-kit");
      if (!holder) return;
      const copy = sprue.cloneNode(true);
      copy.removeAttribute("id");
      copy.removeAttribute("aria-labelledby");
      copy.setAttribute("aria-hidden", "true");
      copy.querySelectorAll("[id]").forEach((el) => el.removeAttribute("id"));
      copy.querySelectorAll("title").forEach((el) => el.remove());
      holder.appendChild(copy);
      card.miniDraw = kit(copy);
      card.miniDraw(i > 0 ? STAGES[i - 1] : 0);
    });
  }

  const miniObserver = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) playMini(entry.target);
        });
      }, { rootMargin: "0px 0px -25% 0px", threshold: 0.2 })
    : null;

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
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cards.forEach((card) => card.classList.remove("active"));
      if (drawMain) {
        lastState = -1;
        shown = target = 1;
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
    if (narrow.matches && miniObserver) {
      buildMinis();
      cards.forEach((card) => miniObserver.observe(card));
    }
    if (drawMain) {
      active = narrow.matches ? -1 : activeCard();
      cards.forEach((card, k) => card.classList.toggle("active", k === active));
      lastState = -1;
      shown = target = active < 0 ? 0 : STAGES[active];
      drawBig(shown);
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
      const text = button.parentElement.querySelector("code").textContent;
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
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

  const bar = document.getElementById("topbar");
  const menu = document.getElementById("menu");
  const menuButton = document.querySelector(".menu-btn");
  let lastY = window.scrollY;
  window.addEventListener("scroll", () => {
    const y = window.scrollY;
    const hide = y > 80 && y > lastY && !(menu && !menu.hidden);
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
