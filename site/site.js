(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const narrow = window.matchMedia("(max-width: 900px)");
  const sprue = document.getElementById("sprue");
  const caption = document.getElementById("caption");
  const cards = [...document.querySelectorAll(".istep")];
  const install = document.getElementById("install");
  const bar = document.getElementById("topbar");
  const PART_STEP = [0, 0, 1, 1, 2, 3, 4, 5];
  const GROUPS = ["wings", "tailplanes", "fuselage", "canopy", "propeller", "spinner"];
  const NOTES = ["wings going on", "tailplanes going on", "fuselage going on", "canopy going on", "propeller going on", "spinner on, ready to fly"];

  const clamp = (v) => Math.min(1, Math.max(0, v));
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

  function kit(svg) {
    const frame = svg.querySelector(".frame");
    const parts = [...svg.querySelectorAll(".part")].map((el) => {
      const [cx, cy] = el.dataset.c.split(",").map(Number);
      const [sx, sy, r] = el.dataset.s.split(",").map(Number);
      return { el, cx, cy, dx: sx - cx, dy: sy - cy, r };
    });
    const transfers = [...svg.querySelectorAll(".transfer")];
    return function draw(n) {
      parts.forEach((part, i) => {
        const t = ease(clamp(n - PART_STEP[i]));
        part.el.classList.toggle("painted", t === 1);
        const k = 1 - t;
        const lift = Math.sin(t * Math.PI) * -18;
        part.el.setAttribute("transform", `translate(${(part.dx * k - lift).toFixed(2)} ${(part.dy * k).toFixed(2)}) rotate(${(part.r * k).toFixed(2)} ${part.cx} ${part.cy})`);
      });
      frame.style.opacity = (1 - 0.82 * clamp(n / (GROUPS.length - 1.5))).toFixed(3);
      svg.classList.toggle("painted", n >= GROUPS.length);
      transfers.forEach((el) => el.classList.toggle("on", n >= Number(el.dataset.at)));
      return Math.floor(n);
    };
  }

  const drawMain = sprue ? kit(sprue) : null;

  function planeBadge() {
    const ns = "http://www.w3.org/2000/svg";
    const el = document.createElement("span");
    el.className = "plane-badge";
    el.setAttribute("aria-hidden", "true");
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "240 30 580 580");
    const plane = document.createElementNS(ns, "g");
    plane.setAttribute("transform", "rotate(90 530 320)");
    sprue.querySelectorAll(".part .plastic").forEach((path) => plane.append(path.cloneNode()));
    svg.append(plane);
    const num = document.createElement("span");
    num.className = "plane-num";
    el.append(svg, num);
    return el;
  }
  const badge = sprue ? planeBadge() : null;
  const note = document.createElement("span");
  note.className = "plane-note";
  note.setAttribute("aria-hidden", "true");

  function mark(i) {
    cards.forEach((card, k) => {
      card.classList.toggle("active", k === i);
      card.classList.toggle("done", k < i);
    });
    if (!badge) return;
    const from = narrow.matches && badge.isConnected ? badge.getBoundingClientRect().top : null;
    if (i < 0) {
      badge.remove();
      note.remove();
      return;
    }
    badge.querySelectorAll("path").forEach((path, j) => path.setAttribute("class", PART_STEP[j] < i || i === cards.length - 1 ? "fit" : PART_STEP[j] === i ? "going" : "ghost"));
    badge.lastChild.textContent = cards[i].querySelector(".inum").textContent;
    note.textContent = NOTES[i];
    cards[i].append(badge, note);
    if (from === null || reduce.matches) return;
    badge.getAnimations().forEach((a) => a.cancel());
    const gap = from - badge.getBoundingClientRect().top;
    if (Math.abs(gap) < 2) return;
    badge.animate([{ transform: `translateY(${gap}px)` }, { transform: "none" }], flight(Math.abs(gap), gap > 0));
  }

  function flight(distance, climbing) {
    const accel = climbing ? 520 : 900, top = climbing ? 620 : 950, brake = 2400, drag = accel / (top * top), dt = 1 / 240;
    let t = 0, x = 0, v = 0, braking = false;
    const samples = [[0, 0]];
    while (x < distance && t < 6) {
      if (!braking && distance - x <= (v * v) / (2 * brake)) braking = true;
      v = braking ? Math.max(v - brake * dt, 40) : v + (accel - drag * v * v) * dt;
      x = Math.min(distance, x + v * dt);
      t += dt;
      samples.push([t, x / distance]);
    }
    const duration = Math.round(t * 1000);
    if (!CSS.supports("animation-timing-function", "linear(0, 1)")) return { duration, easing: "cubic-bezier(0.5, 0, 0.3, 1)" };
    const step = Math.max(1, Math.floor(samples.length / 32));
    const stops = samples.filter((_, k) => k % step === 0 || k === samples.length - 1).map(([s, p]) => `${p.toFixed(4)} ${((s / t) * 100).toFixed(2)}%`);
    return { duration, easing: `linear(${stops.join(", ")})` };
  }
  let lastState = -1;
  function drawBig(n) {
    const state = drawMain(n);
    if (state === lastState) return;
    lastState = state;
    if (state === GROUPS.length) caption.textContent = "Spinner on. Ready to fly.";
    else if (state === 0) caption.textContent = "Frame A has eight parts.";
    else if (state === GROUPS.length - 1) caption.textContent = `Step ${state}: ${GROUPS[state - 1]} on. Decals going on.`;
    else caption.textContent = `Step ${state}: ${GROUPS[state - 1]} on.`;
  }

  /** Each step's group flies for FLIGHT ms, then waits HOLD ms so its paint shows before the next group leaves the frame. */
  const FLIGHT = 320, HOLD = 0;
  let level = 0, wanted = 0, playing = false, active = -1, generation = 0;
  function play() {
    if (level === wanted) {
      playing = false;
      if (level === cards.length && doneAt === null) finished();
      return;
    }
    playing = true;
    if (Math.abs(wanted - level) > 1) {
      level = wanted - Math.sign(wanted - level);
      drawBig(level);
    }
    const dir = Math.sign(wanted - level), from = level, to = level + dir;
    const t0 = performance.now(), gen = generation;
    const tick = (now) => {
      if (gen !== generation) return;
      if (reduce.matches) return (playing = false);
      const t = clamp((now - t0) / FLIGHT);
      drawBig(from + (to - from) * t);
      if (now - t0 < FLIGHT + HOLD) return requestAnimationFrame(tick);
      level += dir;
      play();
    };
    requestAnimationFrame(tick);
  }
  function setLevel(k) {
    wanted = k;
    if (!playing) play();
  }

  /**
   * On desktop the scroll from "first card fully in view" to "last card's top at the activation line" is cut into
   * equal parts, one per step, so tall and short cards get the same scroll distance and the kit builds evenly.
   * Phones keep the plain rule (a card is active once its top passes the line), which their snap relies on.
   */
  function activeCard() {
    const mid = window.innerHeight * (narrow.matches ? 0.85 : 0.67);
    let found = -1;
    cards.forEach((card, i) => {
      const box = card.getBoundingClientRect();
      if (box.top < mid || (i === 0 && box.top >= 0 && box.bottom <= window.innerHeight)) found = i;
    });
    if (narrow.matches || cards.length < 2) return found;
    const y = window.scrollY;
    const start = cards[0].getBoundingClientRect().bottom + y - window.innerHeight;
    const end = cards[cards.length - 1].getBoundingClientRect().top + y - mid;
    if (end - start < cards.length * 40) return found;
    if (y < start && cards[0].getBoundingClientRect().top >= mid) return -1;
    const steps = cards.length - 1;
    return Math.max(0, Math.min(steps, Math.floor(((y - start) / (end - start)) * steps)));
  }

  const plane = sprue && sprue.querySelector(".parts");
  const prop = sprue && sprue.querySelectorAll(".part")[6];
  const shadow = plane && document.createElementNS("http://www.w3.org/2000/svg", "g");
  if (shadow) {
    shadow.setAttribute("class", "shadow");
    sprue.querySelectorAll(".part .plastic").forEach((path) => shadow.appendChild(path.cloneNode()).removeAttribute("class"));
    plane.before(shadow);
  }
  const smooth = (a, b, v) => {
    const t = clamp((v - a) / (b - a));
    return t * t * (3 - 2 * t);
  };

  const HOLD_FINISHED = 2500, PINNED_LEFT = 0.75, ZOOM = 1100, CLIMB = 2600, FAR = 0.6, MID_X = 540, MID_Y = 320;
  const steps = document.querySelector(".install-steps");
  const story = document.getElementById("story-h");
  let flown = false, inFlight = false, retired = false, steered = false, trip = 0, waiting = 0, gliding = 0;
  let goingDown = false, scrolledTo = window.scrollY, doneAt = null, doneTime = 0;
  function finished() {
    doneAt = window.scrollY;
    doneTime = performance.now();
  }
  function onScreen() {
    const box = sprue.getBoundingClientRect();
    return box.bottom > 0 && box.top < window.innerHeight;
  }
  function takeOff() {
    flown = inFlight = retired = true;
    steered = false;
    const id = ++trip;
    const box = sprue.getBoundingClientRect();
    const unit = Math.min(box.width / 640, box.height / 1000);
    const oy = box.height / 2 + (500 - MID_X) * unit;
    const reach = (box.top + oy + 60) / (unit * FAR) + 360;
    const blade = prop.getAttribute("transform");
    sprue.style.transformOrigin = `${box.width / 2}px ${oy}px`;
    sprue.querySelector(".frame").style.opacity = 0;
    caption.parentElement.classList.add("away");
    let t0 = 0, last = 0, right = 0, down = 0, travelled = 0, turn = 0;
    const tick = (now) => {
      if (id !== trip) return;
      if (!t0) t0 = last = now;
      const t = now - t0;
      const dt = (now - last) / 1000;
      last = now;
      sprue.style.transform = `scale(${(1 - (1 - FAR) * ease(clamp(t / ZOOM))).toFixed(4)})`;
      const blur = clamp((t - 150) / 1000) ** 2;
      turn += (5 + 34 * blur) * dt;
      prop.setAttribute("transform", `${blade} translate(721 320) scale(1 ${(Math.cos(turn) * (1 - blur) + blur).toFixed(3)}) translate(-721 -320)`);
      prop.style.opacity = (1 - 0.55 * blur).toFixed(3);
      const u = clamp((t - ZOOM) / CLIMB);
      const s = reach * u ** 2.4;
      const heading = -15 * smooth(0.1, 0.8, u);
      const rad = (heading * Math.PI) / 180;
      right += Math.sin(rad) * (s - travelled);
      down -= Math.cos(rad) * (s - travelled);
      travelled = s;
      const wings = 1 - 0.16 * Math.sin(Math.PI * smooth(0.05, 0.85, u));
      const place = (x, y, g) => `translate(${(-y).toFixed(2)} ${x.toFixed(2)}) rotate(${heading.toFixed(2)} ${MID_X} ${MID_Y}) translate(${MID_X} ${MID_Y}) scale(${g.toFixed(3)} ${(g * wings).toFixed(3)}) translate(${-MID_X} ${-MID_Y})`;
      plane.setAttribute("transform", place(right, down, 1 + 0.14 * smooth(0, 1, u)));
      const lift = smooth(0, 0.55, u);
      shadow.setAttribute("transform", place(right + 40 * lift, down + 60 * lift, 1));
      shadow.style.opacity = u > 0 ? (0.2 * (1 - lift)).toFixed(3) : 0;
      if (u < 1) return requestAnimationFrame(tick);
      inFlight = false;
      plane.style.visibility = "hidden";
      if (!onScreen()) return restore();
      if (!steered) glide();
    };
    requestAnimationFrame(tick);
  }
  function restore() {
    clearTimeout(waiting);
    waiting = 0;
    if (!flown) return;
    const seen = onScreen();
    flown = inFlight = false;
    trip++;
    sprue.style.transform = "";
    plane.removeAttribute("transform");
    plane.style.visibility = "";
    shadow.removeAttribute("transform");
    shadow.style.opacity = "";
    prop.style.opacity = "";
    caption.parentElement.classList.remove("away");
    lastState = -1;
    drawBig(level);
    if (seen && !reduce.matches && plane.animate) plane.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, easing: "ease-out" });
  }
  function ready() {
    if (flown || retired || doneAt === null || reduce.matches || narrow.matches || playing || active !== cards.length - 1 || level !== cards.length) return false;
    if (steps.getBoundingClientRect().bottom - window.innerHeight > window.innerHeight * PINNED_LEFT) return false;
    const box = sprue.getBoundingClientRect();
    return box.top + box.height * 0.46 > 0;
  }
  function maybeFly() {
    if (waiting || !goingDown || !ready()) return;
    waiting = setTimeout(() => {
      waiting = 0;
      if (ready()) takeOff();
    }, Math.max(0, doneTime + HOLD_FINISHED - performance.now()));
  }

  function glide() {
    if (!story) return;
    const from = window.scrollY;
    const to = from + story.getBoundingClientRect().top - bar.offsetHeight - window.innerHeight * 0.1;
    if (to <= from + 1) return;
    let t0 = 0;
    const tick = (now) => {
      if (!gliding) return;
      if (!t0) t0 = now;
      const t = clamp((now - t0) / 1100);
      window.scrollTo({ top: from + (to - from) * ease(t), behavior: "instant" });
      if (t < 1) return (gliding = requestAnimationFrame(tick));
      gliding = 0;
      afterScroll();
    };
    gliding = requestAnimationFrame(tick);
  }
  function stopGlide() {
    cancelAnimationFrame(gliding);
    gliding = 0;
  }
  ["wheel", "touchstart"].forEach((type) => window.addEventListener(type, stopGlide, { passive: true }));
  ["keydown", "pointerdown", "hashchange"].forEach((type) => window.addEventListener(type, () => {
    steered = true;
    stopGlide();
  }, { passive: true }));

  function cutSpacer() {
    if (!retired || inFlight || gliding || steps.style.paddingBottom === "0px") return;
    const pad = parseFloat(getComputedStyle(steps).paddingBottom);
    if (!pad) return;
    const gapTop = steps.getBoundingClientRect().bottom - pad;
    if (gapTop >= window.innerHeight) return (steps.style.paddingBottom = "0px");
    const hidden = Math.min(pad, -gapTop);
    if (hidden < 1) return;
    const y = window.scrollY;
    steps.style.paddingBottom = `${pad - hidden}px`;
    window.scrollTo({ top: y - hidden, behavior: "instant" });
    scrolledTo = window.scrollY;
  }
  let idleTimer = 0;
  function afterScroll() {
    clearTimeout(idleTimer);
    if (!sprue || narrow.matches || gliding) return;
    if (flown && !inFlight && !onScreen()) restore();
    cutSpacer();
    rearm();
  }
  function rearm() {
    if (!retired || flown || active >= cards.length - 1 || steps.getBoundingClientRect().bottom < window.innerHeight) return;
    retired = false;
    steps.style.paddingBottom = "";
  }
  if ("onscrollend" in window) window.addEventListener("scrollend", afterScroll);
  else window.addEventListener("scroll", () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(afterScroll, 150);
  }, { passive: true });
  function passedBy() {
    if (retired || narrow.matches || sprue.getBoundingClientRect().bottom >= 0) return;
    retired = true;
    clearTimeout(waiting);
    waiting = 0;
  }
  const arrival = location.hash && document.getElementById(location.hash.slice(1));
  if (arrival && steps && install && !install.contains(arrival) && install.compareDocumentPosition(arrival) & Node.DOCUMENT_POSITION_FOLLOWING) {
    retired = true;
    steps.style.paddingBottom = "0px";
  }

  let badgeFlown = false, flyer = null, badgeDoneAt = null, badgeDoneTime = 0;
  function badgeTakeOff() {
    badgeFlown = true;
    const art = badge.querySelector("svg");
    const box = art.getBoundingClientRect();
    flyer = art.cloneNode(true);
    flyer.classList.add("badge-flyer");
    Object.assign(flyer.style, { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` });
    document.body.append(flyer);
    art.style.visibility = "hidden";
    const rise = box.top + box.height * 2 + 40;
    const frames = [];
    for (let k = 0; k <= 40; k++) {
      const t = k / 40;
      const u = clamp((t - 0.18) / 0.82);
      const grow = 1 + 0.6 * (1 - (1 - clamp(t / 0.3)) ** 3) + 0.1 * u;
      const wings = 1 - 0.18 * Math.sin(Math.PI * smooth(0, 0.9, u));
      const lift = smooth(0, 0.3, t);
      frames.push({
        offset: t,
        transform: `translate(${(50 * lift + 70 * smooth(0, 1, u)).toFixed(1)}px, ${(-8 * lift - rise * u ** 2.2).toFixed(1)}px) rotate(${(18 * smooth(0.05, 0.6, u)).toFixed(2)}deg) scale(${(grow * wings).toFixed(3)}, ${grow.toFixed(3)})`,
        filter: `drop-shadow(${(6 * lift).toFixed(1)}px ${(10 * lift).toFixed(1)}px ${(1 + 3 * lift).toFixed(1)}px rgb(0 0 0 / ${(0.3 * (1 - u)).toFixed(2)}))`,
      });
    }
    const run = flyer.animate(frames, { duration: 2200, easing: "linear", fill: "forwards" });
    run.onfinish = () => {
      if (flyer) flyer.remove();
      flyer = null;
    };
  }
  function restoreBadge() {
    if (flyer) flyer.remove();
    flyer = null;
    const art = badge && badge.querySelector("svg");
    if (!art || !art.style.visibility) return;
    art.style.visibility = "";
    if (badge.isConnected && !reduce.matches) art.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 250, easing: "ease-out" });
  }
  function badgeCheck() {
    if (!badge || active !== cards.length - 1 || reduce.matches) return;
    if (badgeDoneAt === null) {
      badgeDoneAt = window.scrollY;
      badgeDoneTime = performance.now() + Math.max(0, ...badge.getAnimations().map((a) => (a.effect.getComputedTiming().endTime || 0) - (a.currentTime || 0)));
      return;
    }
    if (badgeFlown) {
      if (!goingDown && !flyer) restoreBadge();
      return;
    }
    if (performance.now() < badgeDoneTime + 1500) return (badgeDoneAt = window.scrollY);
    if (!goingDown || window.scrollY - badgeDoneAt < 24) return;
    const box = badge.getBoundingClientRect();
    if (box.top > 0 && box.bottom < window.innerHeight) badgeTakeOff();
  }

  function onScroll() {
    if (!drawMain) return;
    const y = window.scrollY;
    if (y !== scrolledTo) goingDown = y > scrolledTo;
    scrolledTo = y;
    const i = activeCard();
    if (i !== active) {
      active = i;
      if (i !== cards.length - 1) {
        restore();
        doneAt = badgeDoneAt = null;
        badgeFlown = false;
      }
      restoreBadge();
      mark(i);
      setLevel(i + 1);
    }
    if (narrow.matches) return badgeCheck();
    passedBy();
    if (flown && !gliding && (!onScreen() || (!inFlight && !goingDown))) restore();
    maybeFly();
  }

  const animated = [...document.querySelectorAll("svg")].filter((svg) => svg.querySelector("animate, animateMotion, animateTransform"));
  let started = false;
  function startAnimations() {
    if (started) return animated.forEach((svg) => svg.unpauseAnimations());
    started = true;
    document.querySelectorAll("[data-pose]").forEach((g) => g.removeAttribute("transform"));
    document.querySelectorAll("animate, animateMotion, animateTransform").forEach((el) => el.beginElementAt(Number(el.getAttribute("data-offset") || 0)));
  }

  const reveals = document.querySelectorAll(".reveal, .stamp, .usp-grid");
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
    restore();
    restoreBadge();
    badgeDoneAt = null;
    if (reduce.matches) {
      document.documentElement.classList.add("static");
      bar.classList.remove("tucked");
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      mark(-1);
      if (drawMain) {
        lastState = -1;
        generation++;
        playing = false;
        level = wanted = GROUPS.length;
        drawBig(level);
      }
      if (started) animated.forEach((svg) => svg.pauseAnimations());
      reveals.forEach((el) => el.classList.add("in"));
      icons.forEach((ico) => ico.classList.remove("turning"));
      return;
    }
    document.documentElement.classList.remove("static");
    startSpin();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    startAnimations();
    if (drawMain) {
      active = activeCard();
      mark(active);
      lastState = -1;
      generation++;
      playing = false;
      level = wanted = active + 1;
      doneAt = null;
      if (level === cards.length) finished();
      drawBig(level);
    }
    if (observer) {
      document.documentElement.classList.add("js");
      reveals.forEach((el) => el.classList.contains("in") || observer.observe(el));
    }
    if (drawMain) {
      passedBy();
      cutSpacer();
    }
  }

  const uspGrid = document.querySelector(".usp-grid");
  const icons = [...document.querySelectorAll(".usp-ico[data-turn]")];
  const TURN_FRAMES = 26;
  const TURN_COLS = 13;
  const TURN_ROWS = 2;
  const blend = window.CSS && CSS.supports && CSS.supports("mix-blend-mode", "plus-lighter");
  let turnsAsked = false;
  let gridSeen = false;
  let spinning = false;
  let last = 0;
  const cell = (f) => `translate(${(f % TURN_COLS) * -100 / TURN_COLS}%, ${Math.floor(f / TURN_COLS) * -100 / TURN_ROWS}%)`;
  const spins = icons.map(() => ({ at: Math.random(), period: 6500 + Math.random() * 2500, wobble: 0.0004 + Math.random() * 0.0004, phase: Math.random() * 6.3 }));

  function show(ico, pos) {
    const [now, next] = ico.querySelectorAll(".usp-turn i");
    const f = blend ? Math.floor(pos) : Math.round(pos);
    now.style.transform = cell(f % TURN_FRAMES);
    next.style.transform = cell((f + 1) % TURN_FRAMES);
    const mix = blend ? pos - f : 0;
    now.style.opacity = 1 - mix;
    next.style.opacity = mix;
  }

  /**
   * Every pickup turns on its own, without pauses: each has its own turn time, start angle and a slow drift in speed,
   * so the six never line up. With plus-lighter the next of the 26 frames fades in over the current one.
   */
  function spin(time) {
    if (!gridSeen || document.hidden || reduce.matches) {
      spinning = false;
      return;
    }
    const dt = last ? Math.min(100, time - last) : 0;
    last = time;
    icons.forEach((ico, k) => {
      if (!ico.dataset.ready) return;
      const s = spins[k];
      s.at = (s.at + (dt / s.period) * (1 + 0.15 * Math.sin(time * s.wobble + s.phase))) % 1;
      ico.classList.add("turning");
      show(ico, s.at * TURN_FRAMES);
    });
    requestAnimationFrame(spin);
  }

  function startSpin() {
    if (spinning || !gridSeen || document.hidden || reduce.matches) return;
    spinning = true;
    last = 0;
    requestAnimationFrame(spin);
  }

  function loadTurns() {
    if (turnsAsked || reduce.matches || !uspGrid || !Element.prototype.animate) return;
    turnsAsked = true;
    icons.forEach((ico) => {
      const sheet = new Image();
      sheet.onload = () => {
        const done = () => {
          const box = document.createElement("span");
          box.className = "usp-turn";
          for (let k = 0; k < 2; k++) box.appendChild(document.createElement("i")).style.backgroundImage = `url("${sheet.src}")`;
          ico.appendChild(box);
          ico.dataset.ready = "1";
          show(ico, spins[icons.indexOf(ico)].at * TURN_FRAMES);
        };
        if (sheet.decode) sheet.decode().then(done, done);
        else done();
      };
      sheet.src = `img/pickups/${ico.dataset.turn}-turn.webp`;
    });
    new IntersectionObserver((entries) => {
      gridSeen = entries[0].isIntersecting;
      startSpin();
    }, { threshold: 0.1 }).observe(uspGrid);
    document.addEventListener("visibilitychange", startSpin);
  }

  if (uspGrid && "IntersectionObserver" in window) {
    const near = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      near.disconnect();
      if (document.readyState === "complete") loadTurns();
      else window.addEventListener("load", loadTurns, { once: true });
    }, { rootMargin: "300px 0px" });
    near.observe(uspGrid);
  }

  document.querySelectorAll(".usp-tile").forEach((tile) => {
    tile.addEventListener("mouseenter", () => {
      if (reduce.matches) return;
      const ico = tile.querySelector(".usp-ico");
      if (!ico || !ico.animate || ico.lift) return;
      ico.lift = ico.animate([{ transform: "none" }, { transform: "translateY(-10%) scale(1.06)" }, { transform: "none" }], { duration: 1600, easing: "cubic-bezier(0.45, 0, 0.55, 1)", composite: "add" });
      ico.lift.onfinish = ico.lift.oncancel = () => (ico.lift = null);
    });
  });

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

  const updateStick = () => document.documentElement.style.setProperty("--stick", `${Math.round(bar.offsetHeight + 12)}px`);
  updateStick();
  window.addEventListener("resize", updateStick);
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
    if (!narrow.matches || reduce.matches || touching || settling || performance.now() < settleQuiet) return;
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
      email: "Enter an email address the maintainer can reply to.",
      turnstile: "The spam check has not finished yet. Wait a moment and send again.",
    };
    const BLOCKED = "The spam check could not load. A blocker may stop it. Reload the page, or try again with the blocker paused for this site.";
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
        sitekey: ["dogfighter.net", "www.dogfighter.net"].includes(location.hostname) ? contactForm.dataset.sitekey : "1x00000000000000000000AA",
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
        fallback.textContent = "Your text is still in the form. Try again in a moment.";
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
      if (email.length > 254 || !/^[^\s@"<>]+@[^\s@"<>]+\.[^\s@"<>]+$/.test(email)) invalid.push("email");
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
        else showResult(true, "It is on its way to the maintainer, who will answer at the email you gave.");
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
