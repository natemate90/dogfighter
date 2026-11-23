(() => {
  const W = 640, EDGE = 90, SPAN = W + 2 * EDGE, TOP = 44, FLOOR = 268, DT = 1 / 120;
  const TOP_SPEED = 400, PULL = 200, CLIMB_LOSS = 112, STALL = 120;
  const PITCH_UP = 6, PITCH_DOWN = 6.6, YAW = 8, TURN_SINK = 0.4, ROLL = 10;
  const MUZZLE = 2900, BULLET_LIFE = 0.2, GUN_RATE = 12, BURST = 0.4;
  const LOCK_CONE = 0.05, FIRE_CONE = 0.12, FIRE_RANGE = 470, MAX_BULLETS = 40, HITS_TO_SMOKE = 10;
  const TAU = Math.PI * 2;

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const angle = (a) => Math.atan2(Math.sin(a), Math.cos(a));
  const wrapDx = (dx) => dx - SPAN * Math.round(dx / SPAN);
  const wrapX = (x) => wrapDx(x - W / 2) + W / 2;
  const rand = (lo, hi) => lo + Math.random() * (hi - lo);
  const facing = (p) => (Math.cos(p.psi) >= 0 ? 1 : -1);
  const turning = (p) => p.psi !== p.yawTo;
  const nose = (p) => ({ x: Math.cos(p.psi) * Math.cos(p.gam), y: -Math.sin(p.gam) });
  const velocity = (p) => ({ x: p.v * Math.cos(p.psi) * Math.cos(p.gam), y: -p.v * Math.sin(p.gam) });

  function fly(p, dt) {
    p.v += (PULL * (p.throttle - (p.v / p.top) ** 2) - CLIMB_LOSS * Math.sin(p.gam)) * dt;
    p.v = Math.max(p.v, 20);
    p.gam += p.pitch * (p.pitch > 0 ? PITCH_UP : PITCH_DOWN) * dt;
    if (turning(p)) {
      p.psi += clamp(p.yawTo - p.psi, -YAW * dt, YAW * dt);
      if (Math.abs(p.pitch) < 0.1 && p.gam > -TURN_SINK) p.gam -= Math.min(p.gam + TURN_SINK, 2 * dt);
    }
    p.since += dt;
    if (p.v < STALL) {
      const drop = angle(-Math.PI / 2 - p.gam);
      p.gam += Math.sign(drop) * Math.min(Math.abs(drop), 4 * (1 - p.v / STALL) * dt);
    }
    p.gam = angle(p.gam);
    p.roll = Math.min(1, p.roll + (2 * ROLL * dt) / Math.PI);
    const vel = velocity(p);
    p.x += vel.x * dt;
    p.y += vel.y * dt;
    if (p.leaving) p.wrap = false;
    else if (p.wrap) p.x = wrapX(p.x);
    else if (p.x > -EDGE && p.x < W + EDGE) p.wrap = true;
  }

  function pitchTo(p, want, gain = 5) {
    p.pitch = clamp(angle(want - p.gam) * gain, -1, 1);
  }

  function aimAt(p, dx, dy, gain) {
    const want = Math.atan2(-dy, dx * facing(p));
    pitchTo(p, want, gain);
    return want;
  }

  function reverse(p) {
    if (turning(p) || p.since < 0.6 || Math.abs(p.gam) > 0.8) return;
    p.yawTo = p.yawTo === 0 ? Math.PI : 0;
    p.since = 0;
  }

  function rollUpright(p) {
    if (turning(p) || p.roll < 1 || Math.abs(p.gam) < 2.3) return;
    p.psi = p.yawTo = Math.PI - p.psi;
    p.gam = angle(Math.PI - p.gam);
    p.roll = -1;
  }

  function keepInside(p) {
    const ahead = p.y - Math.sin(p.gam) * p.v * 0.35;
    if (Math.max(p.y, ahead) > FLOOR - 10 && Math.sin(p.gam) < 0.4) p.pitch = Math.cos(p.gam) >= 0 ? 1 : -1;
    else if (Math.min(p.y, ahead) < TOP + 10 && Math.sin(p.gam) > -0.3) p.pitch = Math.cos(p.gam) >= 0 ? -1 : 1;
  }

  function makePlane(size, top) {
    return { size, top, x: 0, y: 0, v: 0, gam: 0, psi: 0, yawTo: 0, pitch: 0, roll: 1, throttle: 1 };
  }

  function world() {
    const s = { prey: makePlane(1.05, TOP_SPEED), hunter: makePlane(0.92, TOP_SPEED * 1.06), bullets: [], sparks: [], puffs: [], t: 0 };
    reset(s);
    return s;
  }

  function place(p, x, y, dir, v) {
    const psi = dir > 0 ? 0 : Math.PI;
    Object.assign(p, { x, y, v, gam: 0, psi, yawTo: psi, pitch: 0, roll: 1, throttle: 1, wrap: false, leaving: false, gone: false, since: 0 });
  }

  function reset(s) {
    const dir = Math.random() < 0.5 ? 1 : -1, y = rand(110, 200);
    place(s.prey, dir > 0 ? -EDGE - 10 : W + EDGE + 10, y, dir, TOP_SPEED);
    place(s.hunter, dir > 0 ? -EDGE - 330 : W + EDGE + 330, y + rand(-30, 30), dir, TOP_SPEED * 1.06);
    Object.assign(s.prey, { mode: "cruise", timer: rand(0.5, 1), alt: y, hits: 0, smoke: 0, smokeAt: 0, turned: 0, jink: false });
    Object.assign(s.hunter, { mode: "chase", burst: 0, cool: 0.6, shotAt: 0, gun: 1, close: false });
    s.exitTime = 0;
    s.fade = 1;
    s.calm = s.t + 1.5;
  }

  function canLoop(p) {
    return p.v > 0.75 * TOP_SPEED && p.y > 190 && p.y < FLOOR && Math.abs(p.gam) < 0.35 && p.roll === 1 && !turning(p);
  }

  function nextMove(p) {
    const moves = [];
    if (canLoop(p)) moves.push("loop", "loop", "half");
    if (p.y < 190) moves.push("dive", "dive");
    if (p.y > 140 && p.v > 0.65 * TOP_SPEED) moves.push("climb");
    if (p.x > 120 && p.x < W - 120 && Math.abs(p.gam) < 0.5) moves.push("reverse");
    if (!p.jink || !moves.length) moves.push("cruise");
    p.jink = false;
    p.mode = moves[Math.floor(Math.random() * moves.length)];
    p.turned = 0;
    p.timer = p.mode === "cruise" ? rand(0.4, 1.1) : 3;
    if (p.mode === "cruise") p.alt = clamp(p.y + rand(-60, 60), 90, 230);
  }

  function evade(s, dt) {
    const p = s.prey;
    p.timer -= dt;
    if (p.mode === "loop" || p.mode === "half") {
      p.turned += p.pitch * PITCH_UP * dt;
      if (p.turned < (p.mode === "loop" ? TAU - 0.1 : Math.PI) && p.timer > 0) {
        p.pitch = 1;
        return;
      }
      p.mode = "cruise";
      p.timer = rand(0.3, 0.8);
      p.alt = clamp(p.y, 90, 230);
    }
    if (p.mode === "dive") {
      pitchTo(p, -0.8);
      if (p.y > 215) {
        p.mode = canLoop(p) ? "loop" : "climb";
        p.turned = 0;
        p.timer = 3;
      }
    } else if (p.mode === "climb") {
      pitchTo(p, 0.75);
      if (p.y < 95 || p.v < 0.6 * TOP_SPEED) nextMove(p);
    } else if (p.mode === "reverse") {
      if (p.timer > 2.9) reverse(p);
      pitchTo(p, 0, 2);
      if (!turning(p) && p.timer < 2.6) nextMove(p);
    } else {
      pitchTo(p, clamp((p.y - p.alt) * 0.012, -0.5, 0.5));
      if (p.mode === "leave") p.leaving = true;
      else if (p.timer <= 0 && p.wrap) nextMove(p);
    }
    rollUpright(p);
    keepInside(p);
  }

  function lead(h, p) {
    const dx = wrapDx(p.x - h.x), dy = p.y - h.y, dist = Math.hypot(dx, dy);
    const pv = velocity(p), speed = h.v + MUZZLE;
    let t = dist / speed, ax = dx, ay = dy;
    for (let i = 0; i < 2; i++) {
      ax = dx + pv.x * t;
      ay = dy + pv.y * t;
      t = Math.hypot(ax, ay) / speed;
    }
    return { x: ax, y: ay, dist };
  }

  function hunt(s, dt) {
    const h = s.hunter, p = s.prey;
    h.cool -= dt;
    if (h.mode === "leave") {
      h.leaving = true;
      pitchTo(h, 0.35);
      keepInside(h);
      return;
    }
    const aim = lead(h, p);
    if (aim.dist < 45) h.close = true;
    else if (aim.dist > 120) h.close = false;
    h.throttle = aim.dist < 140 ? 0.3 : 1;
    if (h.close) {
      pitchTo(h, p.y > h.y ? 0.6 : -0.6);
    } else {
      const want = aimAt(h, aim.x, aim.y + 30 * Math.sin(s.t * 2.3), 6);
      if (Math.abs(want) > 1.7 && Math.abs(wrapDx(p.x - h.x)) > 40) reverse(h);
    }
    rollUpright(h);
    keepInside(h);
    if (h.burst > 0) {
      h.burst -= dt;
      h.shotAt -= dt;
      while (h.shotAt <= 0 && h.burst > 0) {
        shoot(s, h, aim);
        h.shotAt += 1 / GUN_RATE;
      }
      return;
    }
    const n = nose(h), off = Math.acos(clamp((n.x * aim.x + n.y * aim.y) / (Math.hypot(n.x, n.y) * aim.dist || 1), -1, 1));
    if (h.cool <= 0 && s.t > s.calm && !p.smoke && !h.close && p.x > 30 && p.x < W - 30 && aim.dist < FIRE_RANGE && off < FIRE_CONE) {
      h.burst = BURST;
      h.shotAt = 0;
      h.cool = BURST + rand(0.4, 0.9);
    }
  }

  function shoot(s, h, aim) {
    if (s.bullets.length >= MAX_BULLETS) return;
    const n = nose(h), len = Math.hypot(n.x, n.y) || 1;
    let dx = n.x / len, dy = n.y / len;
    const aimLen = Math.hypot(aim.x, aim.y);
    if (Math.acos(clamp((dx * aim.x + dy * aim.y) / aimLen, -1, 1)) < LOCK_CONE) {
      dx = aim.x / aimLen;
      dy = aim.y / aimLen;
    }
    const a = Math.atan2(dy, dx) + rand(-0.05, 0.05), hv = velocity(h);
    h.gun = -h.gun;
    const side = 3 * h.gun, front = 34 * h.size;
    s.bullets.push({
      x: h.x + n.x * front - Math.sin(a) * side,
      y: h.y + n.y * front + Math.cos(a) * side,
      vx: hv.x + Math.cos(a) * MUZZLE,
      vy: hv.y + Math.sin(a) * MUZZLE,
      life: BULLET_LIFE,
    });
  }

  function hits(p, x, y) {
    const n = nose(p), len = Math.hypot(n.x, n.y);
    const dx = wrapDx(x - p.x), dy = y - p.y;
    if (len < 0.3) return dx * dx + dy * dy < 14 * 14;
    const along = (dx * n.x + dy * n.y) / len, across = (-dx * n.y + dy * n.x) / len;
    return (along / (40 * len)) ** 2 + (across / 11) ** 2 < 1;
  }

  function puff(s, x, y, r0, r1, life, kind) {
    if (s.puffs.length >= 40) s.puffs.shift();
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
      const x0 = b.x, y0 = b.y;
      b.x = wrapX(b.x + b.vx * dt);
      b.y += b.vy * dt;
      b.life -= dt;
      if (!p.smoke) {
        for (let k = 1; k <= 3; k++) {
          const x = x0 + (b.vx * dt * k) / 3, y = y0 + (b.vy * dt * k) / 3;
          if (!hits(p, x, y)) continue;
          s.sparks.push({ x: wrapX(x), y, age: 0, spin: rand(0, 1) });
          puff(s, wrapX(x), y, 3, 11, 0.5, "hit");
          p.hits++;
          p.jink = true;
          if (p.mode === "cruise") p.timer = 0;
          if (p.hits >= HITS_TO_SMOKE) p.smoke = 0.001;
          b.life = 0;
          break;
        }
      }
      if (b.life <= 0) s.bullets.splice(i, 1);
    }
    for (let i = s.sparks.length - 1; i >= 0; i--) if ((s.sparks[i].age += dt) > 0.2) s.sparks.splice(i, 1);
    for (let i = s.puffs.length - 1; i >= 0; i--) if ((s.puffs[i].age += dt) > s.puffs[i].life) s.puffs.splice(i, 1);

    if (p.smoke) {
      p.smoke += dt;
      p.smokeAt -= dt;
      if (p.smokeAt <= 0) {
        p.smokeAt = 0.03;
        const n = nose(p), tail = -36 * p.size;
        puff(s, p.x + n.x * tail, p.y + n.y * tail, 3, 13, 1, "smoke");
      }
      if (p.smoke > 0.6 && h.mode !== "leave") h.mode = "leave";
      if (p.smoke > 1.4 && p.mode !== "leave" && p.mode !== "loop" && p.mode !== "half") {
        p.mode = "leave";
        p.alt = clamp(p.y + 40, 120, FLOOR - 20);
      }
      if (p.mode === "leave") s.exitTime += dt;
    }
    for (const q of [p, h]) if (q.leaving && (q.x < -EDGE || q.x > W + EDGE)) q.gone = true;
    if (s.exitTime > 5) s.fade -= dt / 0.6;
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

  let state = null, running = false, onScreen = true, last = 0, acc = 0, pending = 0;

  const n = (v) => v.toFixed(1);
  const atLeast = (v, min) => (v < 0 ? -1 : 1) * Math.max(Math.abs(v), min);
  function draw(s) {
    for (const key of ["prey", "hunter"]) {
      const p = s[key];
      const sx = atLeast(Math.cos(p.psi), 0.25) * (turning(p) ? 0.9 : 1);
      const sy = atLeast(Math.sin((p.roll * Math.PI) / 2), 0.3) * (1 - 0.1 * Math.abs(p.pitch));
      sprites[key].setAttribute("transform", `translate(${n(p.x)} ${n(p.y)}) scale(${sx.toFixed(3)} 1) rotate(${n((-p.gam * 180) / Math.PI)}) scale(1 ${sy.toFixed(3)})`);
      sprites[key].style.opacity = s.fade < 1 ? Math.max(0, s.fade).toFixed(2) : "";
    }
    let d = "";
    for (const b of s.bullets) d += `M${n(b.x)} ${n(b.y)}L${n(b.x - b.vx * 0.013)} ${n(b.y - b.vy * 0.013)}`;
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
    acc += clamp((now - last) / 1000, 0, 0.25);
    last = now;
    while (acc >= DT) {
      step(state, DT);
      acc -= DT;
    }
    draw(state);
    pending = requestAnimationFrame(frame);
  }

  function update() {
    const go = !reduce.matches && onScreen && !document.hidden;
    if (reduce.matches && state) {
      state = null;
      scene.classList.remove("flying");
      for (const key of ["prey", "hunter"]) {
        sprites[key].setAttribute("transform", poses[key]);
        sprites[key].style.opacity = "";
      }
      tracers.setAttribute("d", "");
      sparks.setAttribute("d", "");
      circles.forEach((c) => (c.style.display = "none"));
    }
    if (go === running) return;
    running = go;
    if (!go) {
      cancelAnimationFrame(pending);
      if (!reduce.matches) scene.pauseAnimations();
      return;
    }
    if (!state) state = world();
    scene.classList.add("flying");
    scene.unpauseAnimations();
    last = performance.now();
    acc = 0;
    pending = requestAnimationFrame(frame);
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
