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
    if (painted) caption.textContent = "Painted. Decals on. Ready to fly.";
    else if (fitted === 0) caption.textContent = "Frame A has eight parts. Scroll to put the kit together.";
    else if (fitted === parts.length) caption.textContent = "All eight parts fitted. Now the paint.";
    else caption.textContent = `${words[fitted][0].toUpperCase() + words[fitted].slice(1)} of eight parts fitted.`;
  }

  let ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      ticking = false;
      const rect = build.getBoundingClientRect();
      const run = rect.height - window.innerHeight;
      draw(run > 0 ? clamp(-rect.top / run) : 0);
    });
  }

  const loop = document.querySelector(".diagram.fly");

  function setMode() {
    if (reduce.matches) {
      document.documentElement.classList.add("static");
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      last = -1;
      draw(0);
      caption.textContent = "Frame A has eight parts of a fighter. They are ready to cut out.";
      if (loop) {
        loop.pauseAnimations();
        loop.setCurrentTime(2.2);
      }
    } else {
      document.documentElement.classList.remove("static");
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll);
      if (loop) loop.unpauseAnimations();
      last = -1;
      onScroll();
    }
  }

  reduce.addEventListener("change", setMode);
  setMode();
})();
