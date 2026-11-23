(() => {
  const W = 640, EDGE = 40, SPAN = W + 2 * EDGE, TOP = 24, FLOOR = 436, DT = 1 / 120;
  const UNIT = 48, DEG = Math.PI / 180, SPRITE = 0.3, CRUISE = 0.42;
  const TOP_SPEED = 4.1 * UNIT, PULL = 1 * UNIT, CLIMB_LOSS = 0.7 * UNIT, STALL = 1.6 * UNIT;
  const PITCH_UP = 43 * DEG, PITCH_DOWN = 47 * DEG, YAW = 62 * DEG, TURN_SINK = 20 * DEG, SINK_RATE = 15 * DEG, ROLL = Math.PI;
  const MUZZLE = 38 * UNIT, BULLET_LIFE = 1.2, GUN_RATE = 8.7, BURST = 0.6;
  const LOCK_CONE = 0.12, FIRE_CONE = 0.12, FIRE_RANGE = 12 * UNIT, MAX_BULLETS = 40, HITS_TO_SMOKE = 12;
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
    const throttle = p.v < STALL + 0.5 * UNIT ? 1 : p.throttle;
    p.v += (PULL * (throttle - (p.v / p.top) ** 2) - CLIMB_LOSS * Math.sin(p.gam)) * dt;
    p.v = Math.max(p.v, 20);
    p.gam += p.pitch * (p.pitch > 0 ? PITCH_UP : PITCH_DOWN) * dt;
    if (turning(p)) {
      p.psi += clamp(p.yawTo - p.psi, -YAW * dt, YAW * dt);
      if (Math.abs(p.pitch) < 0.1 && p.gam > -TURN_SINK) p.gam -= Math.min(p.gam + TURN_SINK, SINK_RATE * dt);
    }
    p.since += dt;
    if (p.v < STALL) {
      const drop = angle(-Math.PI / 2 - p.gam);
      p.gam += Math.sign(drop) * Math.min(Math.abs(drop), 1.2 * (1 - p.v / STALL) * dt);
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

  function pitchTo(p, want, gain = 3) {
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
    const steep = Math.asin(clamp(Math.sin(p.gam), -1, 1)), radius = p.v / PITCH_UP + 10;
    const room = radius * (1 - Math.cos(steep)) + p.v * 0.3;
    if (steep < 0.1 && p.y + room > FLOOR) p.pitch = Math.cos(p.gam) >= 0 ? 1 : -1;
    else if (steep > -0.1 && p.y - room < TOP) p.pitch = Math.cos(p.gam) >= 0 ? -1 : 1;
  }

  function makePlane(size, top) {
    return { size, top, x: 0, y: 0, v: 0, gam: 0, psi: 0, yawTo: 0, pitch: 0, roll: 1, throttle: 1 };
  }

  function world() {
    const s = { prey: makePlane(1.05, TOP_SPEED), hunter: makePlane(0.92, TOP_SPEED), bullets: [], sparks: [], puffs: [], t: 0 };
    reset(s);
    return s;
  }

  function place(p, x, y, dir, v) {
    const psi = dir > 0 ? 0 : Math.PI;
    Object.assign(p, { x, y, v, gam: 0, psi, yawTo: psi, pitch: 0, roll: 1, throttle: 1, wrap: false, leaving: false, gone: false, since: 0 });
  }

  function reset(s) {
    const dir = Math.random() < 0.5 ? 1 : -1, y = rand(150, 330);
    place(s.prey, dir > 0 ? -EDGE - 10 : W + EDGE + 10, y, dir, 2.65 * UNIT);
    place(s.hunter, dir > 0 ? -EDGE - 220 : W + EDGE + 220, y + rand(-30, 30), dir, 2.9 * UNIT);
    Object.assign(s.prey, { throttle: CRUISE, mode: "cruise", timer: rand(2, 3), alt: y, hits: 0, smoke: 0, smokeAt: 0, turned: 0, jink: false });
    Object.assign(s.hunter, { mode: "chase", burst: 0, cool: 0.6, shotAt: 0, gun: 1, close: false });
    s.exitTime = 0;
    s.fade = 1;
    s.calm = s.t + 2.5;
    s.started = s.t;
  }

  function canLoop(p) {
    return p.v > 2.3 * UNIT && p.v < 2.75 * UNIT && p.y > TOP + 10 + (2 * p.v) / PITCH_UP && p.y < 415 && Math.abs(p.gam) < 0.3 && p.roll === 1 && !turning(p);
  }

  function nextMove(p) {
    const moves = [];
    if (canLoop(p)) moves.push("loop", "loop", "half");
    if (p.y < 330) moves.push("dive", "dive");
    if (p.y > 220 && p.v > 2.4 * UNIT) moves.push("climb");
    if (p.x > 120 && p.x < W - 120 && Math.abs(p.gam) < 0.5) moves.push("reverse");
    if (!p.jink || !moves.length) moves.push("cruise");
    p.jink = false;
    p.mode = moves[Math.floor(Math.random() * moves.length)];
    p.throttle = CRUISE;
    p.loopV = p.v;
    p.turned = 0;
    p.timer = p.mode === "cruise" ? rand(1.5, 3.5) : 12;
    if (p.mode === "cruise") p.alt = clamp(p.y + rand(-80, 80), 120, 380);
  }

  function evade(s, dt) {
    const p = s.prey;
    p.timer -= dt;
    if (p.mode === "loop" || p.mode === "half") {
      p.turned += p.pitch * PITCH_UP * dt;
      if (p.turned < (p.mode === "loop" ? TAU - 0.1 : Math.PI) && p.timer > 0) {
        p.pitch = 1;
        p.throttle = clamp((p.loopV / p.top) ** 2 + (CLIMB_LOSS / PULL) * Math.sin(p.gam) + (p.loopV - p.v) / UNIT, 0, 1);
        return;
      }
      p.throttle = CRUISE;
      p.mode = "cruise";
      p.timer = rand(1, 2);
      p.alt = clamp(p.y, 120, 380);
    }
    if (p.mode === "dive") {
      pitchTo(p, p.y > 345 ? 0 : -0.45);
      p.throttle = p.v > 2.6 * UNIT ? 0.1 : CRUISE;
      if (canLoop(p)) {
        p.mode = "loop";
        p.loopV = p.v;
        p.turned = 0;
        p.timer = 12;
      } else if (p.y > 345 && Math.abs(p.gam) < 0.05) nextMove(p);
    } else if (p.mode === "climb") {
      pitchTo(p, 0.6);
      if (p.y < 120 || p.v < 2 * UNIT) nextMove(p);
    } else if (p.mode === "reverse") {
      if (p.timer > 11.9) reverse(p);
      pitchTo(p, 0, 2);
      if (!turning(p) && p.timer < 11.5) nextMove(p);
    } else {
      pitchTo(p, clamp((p.y - p.alt) * 0.006, -0.4, 0.4));
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
    if (aim.dist < 2.5 * UNIT) h.close = true;
    else if (aim.dist > 3.5 * UNIT) h.close = false;
    h.throttle = aim.dist < 4 * UNIT ? 0.3 : aim.dist > 8 * UNIT ? 0.8 : 0.5;
    if (h.close) {
      pitchTo(h, p.y > h.y || h.y > FLOOR - 80 ? 0.6 : -0.6);
    } else {
      const want = aimAt(h, aim.x, aim.y + 6 * Math.sin(s.t * 1.3), 4);
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
    const a = Math.atan2(dy, dx) + rand(-0.015, 0.015), hv = velocity(h);
    h.gun = -h.gun;
    const side = 2.2 * h.gun, front = 12 * h.size;
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
    if (len < 0.3) return dx * dx + dy * dy < 6 * 6;
    const along = (dx * n.x + dy * n.y) / len, across = (-dx * n.y + dy * n.x) / len;
    return (along / (12.5 * p.size * len)) ** 2 + (across / 4.5) ** 2 < 1;
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
      b.x += b.vx * dt;
      b.y += b.vy * dt;
      b.life -= dt;
      if (b.x < -EDGE || b.x > W + EDGE || b.y < 0 || b.y > 460) b.life = 0;
      if (!p.smoke) {
        for (let k = 1; k <= 5; k++) {
          const x = x0 + (b.vx * dt * k) / 5, y = y0 + (b.vy * dt * k) / 5;
          if (!hits(p, x, y)) continue;
          s.sparks.push({ x, y, age: 0, spin: rand(0, 1) });
          puff(s, x, y, 2, 7, 0.6, "hit");
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
        p.smokeAt = 0.08;
        const n = nose(p), tail = -12 * p.size;
        puff(s, p.x + n.x * tail, p.y + n.y * tail, 2, 9, 1.6, "smoke");
      }
      if (p.smoke > 1.5 && h.mode !== "leave") h.mode = "leave";
      if (p.smoke > 3 && p.mode !== "leave" && p.mode !== "loop" && p.mode !== "half") {
        p.mode = "leave";
        p.alt = clamp(p.y + 30, 150, FLOOR - 30);
      }
    } else if (s.t - s.started > 45 && p.mode === "cruise") {
      p.mode = h.mode = "leave";
    }
    if (p.mode === "leave") s.exitTime += dt;
    for (const q of [p, h]) if (q.leaving && (q.x < -EDGE || q.x > W + EDGE)) q.gone = true;
    if (s.exitTime > 12) s.fade -= dt / 0.6;
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
      const sx = atLeast(Math.cos(p.psi), 0.25) * (turning(p) ? 0.9 : 1) * SPRITE;
      const sy = atLeast(Math.sin((p.roll * Math.PI) / 2), 0.3) * (1 - 0.1 * Math.abs(p.pitch));
      sprites[key].setAttribute("transform", `translate(${n(p.x)} ${n(p.y)}) scale(${sx.toFixed(3)} ${SPRITE}) rotate(${n((-p.gam * 180) / Math.PI)}) scale(1 ${sy.toFixed(3)})`);
      sprites[key].style.opacity = s.fade < 1 ? Math.max(0, s.fade).toFixed(2) : "";
    }
    let d = "";
    for (const b of s.bullets) d += `M${n(b.x)} ${n(b.y)}L${n(b.x - b.vx * 0.012)} ${n(b.y - b.vy * 0.012)}`;
    tracers.setAttribute("d", d);
    d = "";
    for (const sp of s.sparks) {
      const t = sp.age / 0.2, r0 = 1.5 + 3 * t, r1 = 4 + 6 * t;
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
