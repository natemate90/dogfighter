(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const sprue = document.getElementById("sprue");
  const build = document.getElementById("build");
  const caption = document.getElementById("caption");
  const frame = sprue.querySelector(".frame");
  const parts = [...sprue.querySelectorAll(".part")].map((el) => {
    const [cx, cy] = el.dataset.c.split(",").map(Number);
    const [sx, sy, r] = el.dataset.s.split(",").map(Number);
    return { el, cx, cy, dx: sx - cx, dy: sy - cy, r };
  });

  const clamp = (v) => Math.min(1, Math.max(0, v));
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const words = ["", "one", "two", "three", "four", "five", "six", "seven", "eight"];

  let last = -1;
  function draw(p) {
    let fitted = 0;
    parts.forEach((part, i) => {
      const t = ease(clamp((p - 0.04 - i * 0.075) / 0.28));
      if (t === 1) fitted++;
      const k = 1 - t;
      const lift = Math.sin(t * Math.PI) * -18;
      part.el.setAttribute(
        "transform",
        `translate(${(part.dx * k).toFixed(2)} ${(part.dy * k + lift).toFixed(2)}) rotate(${(part.r * k).toFixed(2)} ${part.cx} ${part.cy})`
      );
    });
    frame.style.opacity = (1 - 0.82 * clamp(p / 0.75)).toFixed(3);
    const painted = p > 0.9;
    sprue.classList.toggle("painted", painted);

    const state = painted ? 9 : fitted;
    if (state === last) return;
    last = state;
    if (painted) caption.textContent = "Ready to fly.";
    else if (fitted === 0) caption.textContent = "Frame A has eight parts. Scroll to put the kit together.";
    else if (fitted === parts.length) caption.textContent = "Eight of eight parts fitted.";
    else caption.textContent = `${words[fitted][0].toUpperCase() + words[fitted].slice(1)} of eight parts fitted.`;
  }

  const EASE_TIME = 0.4, MAX_RATE = 0.6;
  let target = 0, shown = 0, easing = false, then = 0;
  function readTarget() {
    const rect = build.getBoundingClientRect();
    const run = rect.height - window.innerHeight;
    target = run > 0 ? clamp(-rect.top / run) : 0;
  }
  function follow(now) {
    if (reduce.matches) return (easing = false);
    const dt = Math.min(0.1, (now - then) / 1000);
    then = now;
    const step = (target - shown) * (1 - Math.exp(-dt / EASE_TIME));
    shown += Math.max(-MAX_RATE * dt, Math.min(MAX_RATE * dt, step));
    if (Math.abs(target - shown) < 0.0005) shown = target;
    draw(shown);
    if (shown === target) easing = false;
    else requestAnimationFrame(follow);
  }
  function onScroll() {
    readTarget();
    if (easing) return;
    easing = true;
    then = performance.now();
    requestAnimationFrame(follow);
  }

  const animated = [...document.querySelectorAll("svg")].filter((svg) => svg.querySelector("animate, animateMotion, animateTransform"));
  let started = false;
  function startAnimations() {
    if (started) {
      animated.forEach((svg) => svg.unpauseAnimations());
      return;
    }
    started = true;
    document.querySelectorAll("[data-pose]").forEach((g) => g.removeAttribute("transform"));
    document.querySelectorAll("animate, animateMotion, animateTransform").forEach((el) => {
      el.beginElementAt(Number(el.getAttribute("data-offset") || 0));
    });
  }

  const reveals = document.querySelectorAll(".reveal");
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
      last = -1;
      draw(0);
      caption.textContent = "The whole kit: eight parts on one frame.";
      if (started) animated.forEach((svg) => svg.pauseAnimations());
      reveals.forEach((el) => el.classList.add("in"));
    } else {
      document.documentElement.classList.remove("static");
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll);
      startAnimations();
      last = -1;
      readTarget();
      shown = target;
      draw(shown);
      if (observer) {
        document.documentElement.classList.add("js");
        reveals.forEach((el) => el.classList.contains("in") || observer.observe(el));
      }
    }
  }

  if (reduce.addEventListener) reduce.addEventListener("change", setMode);
  else if (reduce.addListener) reduce.addListener(setMode);
  setMode();

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
