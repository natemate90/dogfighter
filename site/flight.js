(() => {
  const W = 640, EDGE = 90, SPAN = W + 2 * EDGE, TOP = 44, FLOOR = 268;
  const DT = 1 / 120, G = 130, THRUST = 110, DRAG = THRUST / (190 * 190), TURN_DRAG = 0.07;
  const LIFT = G / (85 * 85), MAX_PULL = 640, ROLL_RATE = 8;
  const MUZZLE = 380, BULLET_DROP = 70, BULLET_LIFE = 0.6, MAX_BULLETS = 40, HITS_TO_SMOKE = 5;
  const TAU = Math.PI * 2;

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const angle = (a) => Math.atan2(Math.sin(a), Math.cos(a));
  const wrapDx = (dx) => dx - SPAN * Math.round(dx / SPAN);
  const rand = (lo, hi) => lo + Math.random() * (hi - lo);
  const facing = (p) => (Math.cos(p.th) >= 0 ? 1 : -1);
  const heading = (dir, pitch) => (dir > 0 ? -pitch : Math.PI + pitch);
  const liftSign = (p) => Math.cos(p.roll);
  const maxPull = (p) => Math.min(LIFT * p.v * p.v, MAX_PULL);

  function makePlane(size) {
    return { size, x: 0, y: 0, th: 0, v: 0, roll: 0, rollTo: 0, pull: 0, rate: 0, throttle: 1, wrap: false, push: 0 };
  }

  function fly(p, dt) {
    const pull = clamp(p.pull, (p.urgent ? -1 : -0.5) * maxPull(p), maxPull(p));
    p.rate = (-liftSign(p) * pull + G * Math.cos(p.th)) / Math.max(p.v, 40);
    p.th = angle(p.th + p.rate * dt);
    p.v += (THRUST * p.throttle - DRAG * p.v * p.v + G * Math.sin(p.th) - TURN_DRAG * Math.abs(pull)) * dt;
    p.v = Math.max(p.v, 30);
    p.x += p.v * Math.cos(p.th) * dt;
    p.y += p.v * Math.sin(p.th) * dt;
    if (p.leaving) p.wrap = false;
    else if (p.wrap) p.x = wrapDx(p.x - W / 2) + W / 2;
    else if (p.x > -EDGE && p.x < W + EDGE) p.wrap = true;
    p.roll += clamp(p.rollTo - p.roll, -ROLL_RATE * dt, ROLL_RATE * dt);
  }

  function steer(p, want, dt, gain = 4) {
    const err = angle(want - p.th);
    const rate = clamp(err * gain, -3.5, 3.5);
    const c = liftSign(p);
    const need = rate * p.v - G * Math.cos(p.th);
    p.pull = Math.abs(c) < 0.3 ? 0 : -need / c;
    p.since += dt;
    if (p.roll !== p.rollTo || p.since < 0.8 || p.urgent) return;
    const limit = maxPull(p);
    p.push = p.pull < -0.5 * limit ? p.push + dt : 0;
    const inverted = c * Math.cos(p.th) < -0.2 && p.pull < 0.3 * limit;
    if (p.push > 0.15 || inverted) {
      p.rollTo = p.rollTo === 0 ? Math.PI : 0;
      p.push = 0;
      p.since = 0;
    }
  }

  function keepInside(p, want) {
    const dir = facing(p);
    const pitch = -Math.sin(p.th) * dir;
    const ahead = p.y + Math.sin(p.th) * p.v * 0.7;
    p.urgent = true;
    if (Math.max(p.y, ahead) > FLOOR - 10 && Math.sin(p.th) > -0.35) return heading(dir, Math.max(0.45, pitch));
    if (Math.min(p.y, ahead) < TOP + 10 && Math.sin(p.th) < 0.25 && Math.abs(Math.cos(p.th)) > 0.3) return heading(dir, Math.min(-0.3, pitch));
    p.urgent = false;
    return want;
  }

  function world() {
    const s = { prey: makePlane(1.05), hunter: makePlane(0.92), bullets: [], sparks: [], puffs: [], t: 0 };
    reset(s);
    return s;
  }

  function reset(s) {
    const dir = Math.random() < 0.5 ? 1 : -1;
    const y = rand(120, 200);
    place(s.prey, dir > 0 ? -EDGE - 10 : W + EDGE + 10, y, dir, 185);
    place(s.hunter, dir > 0 ? -EDGE - 230 : W + EDGE + 230, y + rand(-30, 30), dir, 205);
    Object.assign(s.prey, { mode: "cruise", timer: rand(1.2, 2.2), alt: y, hits: 0, smoke: 0, smokeAt: 0, turned: 0 });
    Object.assign(s.hunter, { mode: "chase", burst: 0, cool: 1, shotAt: 0 });
    s.exitTime = 0;
    s.calm = s.t + 4;
    s.fade = 1;
  }

  function place(p, x, y, dir, v) {
    const roll = dir > 0 ? 0 : Math.PI;
    Object.assign(p, { x, y, v, th: dir > 0 ? 0 : Math.PI, roll, rollTo: roll, wrap: false, leaving: false, gone: false, push: 0, since: 0, urgent: false, rate: 0, throttle: 1 });
  }

  function canLoop(p) {
    return p.v > 165 && p.y > 185 && p.y < FLOOR - 4 && Math.abs(Math.sin(p.th)) < 0.4 && liftSign(p) * Math.cos(p.th) > 0.5 && p.roll === p.rollTo;
  }

  function nextMove(p) {
    const moves = [];
    if (canLoop(p)) moves.push("loop", "loop", "half");
    if (p.y < 200) moves.push("dive", "dive");
    if (p.y > 130 && p.v > 150) moves.push("climb");
    if (!p.jink || !moves.length) moves.push("cruise");
    p.jink = false;
    p.mode = moves[Math.floor(Math.random() * moves.length)];
    p.turned = 0;
    p.timer = p.mode === "cruise" ? rand(0.8, 2) : 6;
    if (p.mode === "cruise") p.alt = clamp(p.y + rand(-50, 50), 90, 230);
  }

  function evade(s, dt) {
    const p = s.prey;
    const dir = facing(p);
    p.timer -= dt;
    if (p.mode === "loop" || p.mode === "half") {
      p.turned += p.rate * dt;
      const goal = p.mode === "loop" ? TAU - 0.35 : Math.PI - 0.15;
      if (Math.abs(p.turned) < goal && p.timer > 0) {
        p.pull = maxPull(p);
        p.push = 0;
        return;
      }
      p.mode = "cruise";
      p.timer = rand(0.6, 1.4);
      p.alt = clamp(p.y, 90, 230);
    }
    let want;
    if (p.mode === "dive") {
      want = heading(dir, -0.85);
      if (p.y > 222) {
        p.mode = canLoop(p) ? "loop" : "climb";
        p.turned = 0;
        p.timer = 6;
        if (p.mode === "loop") return;
      }
    } else if (p.mode === "climb") {
      want = heading(dir, 0.75);
      if (p.y < 95 || p.v < 110) nextMove(p);
    } else {
      want = heading(dir, clamp((p.y - p.alt) * 0.006, -0.5, 0.5));
      if (p.mode === "leave") p.leaving = true;
    }
    if (p.mode === "cruise" && p.timer <= 0 && p.wrap) nextMove(p);
    steer(p, keepInside(p, want), dt);
  }

  function lead(h, p) {
    const vb = h.v + MUZZLE, dx = wrapDx(p.x - h.x), dy = p.y - h.y, dist = Math.hypot(dx, dy);
    let t = dist / vb, ax = dx, ay = dy;
    for (let i = 0; i < 3; i++) {
      ax = dx + p.v * Math.cos(p.th) * t;
      ay = dy + p.v * Math.sin(p.th) * t - 0.5 * BULLET_DROP * t * t;
      t = Math.hypot(ax, ay) / vb;
    }
    return { x: ax, y: ay, dist };
  }

  function hunt(s, dt) {
    const h = s.hunter, p = s.prey;
    if (h.mode === "leave") {
      h.leaving = true;
      h.throttle = 1.2;
      steer(h, keepInside(h, heading(facing(h), 0.35)), dt);
      return;
    }
    const aim = lead(h, p);
    const want = Math.atan2(aim.y, aim.x) + 0.08 * Math.sin(s.t * 1.7) + 0.05 * Math.sin(s.t * 4.3 + 1);
    h.throttle = aim.dist < 110 ? 0.6 : aim.dist > 260 ? 1.35 : 1;
    steer(h, keepInside(h, want), dt, 5);
    h.cool -= dt;
    if (h.burst > 0) {
      h.burst -= dt;
      h.shotAt -= dt;
      if (h.shotAt <= 0) {
        shoot(s, h);
        h.shotAt = 1 / 15;
      }
    } else if (h.cool <= 0 && s.t > s.calm && !p.smoke && p.x > 30 && p.x < W - 30 && aim.dist < 300 && Math.abs(angle(want - h.th)) < 0.07) {
      h.burst = 0.3;
      h.shotAt = 0;
      h.cool = rand(0.7, 1.3);
      if (p.mode === "cruise" && Math.random() < 0.5) p.timer = 0;
    }
  }

  function shoot(s, h) {
    if (s.bullets.length >= MAX_BULLETS) return;
    const th = h.th + rand(-0.045, 0.045), speed = h.v + MUZZLE, nose = 38 * h.size;
    s.bullets.push({ x: h.x + Math.cos(h.th) * nose, y: h.y + Math.sin(h.th) * nose, vx: Math.cos(th) * speed, vy: Math.sin(th) * speed, life: BULLET_LIFE });
  }

  function hits(p, b) {
    const dx = wrapDx(b.x - p.x), dy = b.y - p.y;
    const along = dx * Math.cos(p.th) + dy * Math.sin(p.th);
    const across = -dx * Math.sin(p.th) + dy * Math.cos(p.th);
    return (along / 40) ** 2 + (across / 11) ** 2 < 1;
  }

  function puff(s, x, y, r0, r1, life, kind) {
    if (s.puffs.length >= 32) s.puffs.shift();
    s.puffs.push({ x, y, r0, r1, life, age: 0, kind });
  }

  function step(s, dt) {
    s.t += dt;
    const p = s.prey, h = s.hunter;
    evade(s, dt);
    hunt(s, dt);
    fly(p, dt);
    fly(h, dt);

    for (let i = s.bullets.length - 1; i >= 0; i--) {
      const b = s.bullets[i];
      b.vy += BULLET_DROP * dt;
      b.x = wrapDx(b.x + b.vx * dt - W / 2) + W / 2;
      b.y += b.vy * dt;
      b.life -= dt;
      if (!p.smoke && hits(p, b)) {
        s.sparks.push({ x: b.x, y: b.y, age: 0, spin: rand(0, 1) });
        puff(s, b.x, b.y, 3, 11, 0.5, "hit");
        p.hits++;
        if (p.mode === "cruise") p.timer = 0;
        p.jink = true;
        if (p.hits >= HITS_TO_SMOKE) p.smoke = 0.001;
        b.life = 0;
      }
      if (b.life <= 0) s.bullets.splice(i, 1);
    }
    for (let i = s.sparks.length - 1; i >= 0; i--) if ((s.sparks[i].age += dt) > 0.2) s.sparks.splice(i, 1);
    for (let i = s.puffs.length - 1; i >= 0; i--) if ((s.puffs[i].age += dt) > s.puffs[i].life) s.puffs.splice(i, 1);

    if (p.smoke) {
      p.smoke += dt;
      p.smokeAt -= dt;
      if (p.smokeAt <= 0) {
        p.smokeAt = 0.07;
        const tail = -36 * p.size;
        puff(s, p.x + Math.cos(p.th) * tail, p.y + Math.sin(p.th) * tail, 3, 13, 1.3, "smoke");
      }
      if (p.smoke > 1.2 && h.mode !== "leave") h.mode = "leave";
      if (p.smoke > 2.6 && p.mode !== "leave" && p.mode !== "loop" && p.mode !== "half") {
        p.mode = "leave";
        p.alt = clamp(p.y + 40, 120, FLOOR - 20);
      }
      if (p.mode === "leave") s.exitTime += dt;
    }
    for (const q of [p, h]) if (q.leaving && (q.x < -EDGE || q.x > W + EDGE)) q.gone = true;
    if (s.exitTime > 8) s.fade -= dt / 0.6;
    if ((p.gone && h.gone) || s.fade <= 0) reset(s);
  }

  const scene = document.getElementById("scene");
  if (!scene || !window.requestAnimationFrame) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const NS = "http://www.w3.org/2000/svg";
  const sprites = { prey: scene.querySelector(".flyer.prey"), hunter: scene.querySelector(".flyer.hunter") };
  const poses = { prey: sprites.prey.getAttribute("transform"), hunter: sprites.hunter.getAttribute("transform") };
  const layer = (tag, cls, before) => {
    const el = document.createElementNS(NS, tag);
    el.setAttribute("class", cls);
    scene.insertBefore(el, before);
    return el;
  };
  const smoke = layer("g", "puffs", sprites.hunter);
  const tracers = layer("path", "tracers", null);
  const sparks = layer("path", "sparks", null);
  const circles = [];

  let state = null, running = false, onScreen = true, last = 0, acc = 0;

  const n = (v) => v.toFixed(1);
  function draw(s) {
    for (const key of ["prey", "hunter"]) {
      const p = s[key];
      const c = liftSign(p);
      const sy = (c < 0 ? -1 : 1) * Math.max(Math.abs(c), 0.3) * (1 - 0.14 * Math.min(1, Math.abs(p.pull) / MAX_PULL));
      sprites[key].setAttribute("transform", `translate(${n(p.x)} ${n(p.y)}) rotate(${n((p.th * 180) / Math.PI)}) scale(1 ${sy.toFixed(3)})`);
      sprites[key].style.opacity = s.fade < 1 ? Math.max(0, s.fade).toFixed(2) : "";
    }
    let d = "";
    for (const b of s.bullets) d += `M${n(b.x)} ${n(b.y)}L${n(b.x - b.vx * 0.028)} ${n(b.y - b.vy * 0.028)}`;
    tracers.setAttribute("d", d);
    d = "";
    for (const sp of s.sparks) {
      const t = sp.age / 0.2, r0 = 2 + 6 * t, r1 = 5 + 9 * t;
      for (let i = 0; i < 6; i++) {
        const a = (i + sp.spin) * (TAU / 6);
        d += `M${n(sp.x + Math.cos(a) * r0)} ${n(sp.y + Math.sin(a) * r0)}L${n(sp.x + Math.cos(a) * r1)} ${n(sp.y + Math.sin(a) * r1)}`;
      }
    }
    sparks.setAttribute("d", d);
    s.puffs.forEach((f, i) => {
      let c = circles[i];
      if (!c) {
        c = circles[i] = document.createElementNS(NS, "circle");
        smoke.appendChild(c);
      }
      const t = f.age / f.life;
      c.setAttribute("class", f.kind);
      c.setAttribute("cx", n(f.x));
      c.setAttribute("cy", n(f.y - (f.kind === "smoke" ? 10 * t : 0)));
      c.setAttribute("r", n(f.r0 + (f.r1 - f.r0) * Math.sqrt(t)));
      c.style.opacity = ((1 - t) * (f.kind === "smoke" ? 0.55 : 0.8)).toFixed(2);
      c.style.display = "";
    });
    for (let i = s.puffs.length; i < circles.length; i++) circles[i].style.display = "none";
  }

  function frame(now) {
    if (!running) return;
    acc += Math.min(0.25, (now - last) / 1000);
    last = now;
    while (acc >= DT) {
      step(state, DT);
      acc -= DT;
    }
    draw(state);
    requestAnimationFrame(frame);
  }

  function update() {
    const go = !reduce.matches && onScreen && !document.hidden;
    if (go === running) return;
    running = go;
    if (go) {
      if (!state) state = world();
      scene.classList.add("flying");
      scene.unpauseAnimations();
      last = performance.now();
      acc = 0;
      requestAnimationFrame(frame);
      return;
    }
    if (reduce.matches) {
      state = null;
      scene.classList.remove("flying");
      for (const key of ["prey", "hunter"]) {
        sprites[key].setAttribute("transform", poses[key]);
        sprites[key].style.opacity = "";
      }
      tracers.setAttribute("d", "");
      sparks.setAttribute("d", "");
      circles.forEach((c) => (c.style.display = "none"));
    } else {
      scene.pauseAnimations();
    }
  }

  if ("IntersectionObserver" in window) {
    new IntersectionObserver((entries) => {
      onScreen = entries[entries.length - 1].isIntersecting;
      update();
    }).observe(scene);
  }
  document.addEventListener("visibilitychange", update);
  if (reduce.addEventListener) reduce.addEventListener("change", update);
  else if (reduce.addListener) reduce.addListener(update);
  update();
})();
