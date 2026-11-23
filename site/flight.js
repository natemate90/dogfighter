(() => {
  const W = 640, EDGE = 40, SPAN = W + 2 * EDGE, TOP = 24, FLOOR = 436, DT = 1 / 120;
  const UNIT = 48, DEG = Math.PI / 180, SPRITE = 0.36, CRUISE = 0.42;
  const TOP_SPEED = 4.1 * UNIT, PULL = 1 * UNIT, CLIMB_LOSS = 0.7 * UNIT, STALL = 1.6 * UNIT;
  const PITCH_UP = 43 * DEG, PITCH_DOWN = 47 * DEG;
  const MUZZLE = 38 * UNIT, BULLET_LIFE = 1.2, GUN_RATE = 8.7, BURST = 0.6;
  const LOCK_CONE = 0.12, FIRE_CONE = 0.12, FIRE_RANGE = 12 * UNIT, MAX_BULLETS = 40, HITS_TO_SMOKE = 18;
  const FALL_ACCEL = 6 * UNIT, FALL_MAX = 6 * UNIT, TAU = Math.PI * 2;
  const SHARD_GRAVITY = 10 * UNIT, SHARDS_EACH = 22, PANE_SHARDS = 12, MAX_SHARDS = 80, PANE_CHANCE = 0.02;
  const STAR_REACH = 0.9 * UNIT, MAX_STARS = 12;

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const angle = (a) => Math.atan2(Math.sin(a), Math.cos(a));
  const wrapDx = (dx) => dx - SPAN * Math.round(dx / SPAN);
  const wrapX = (x) => wrapDx(x - W / 2) + W / 2;
  const rand = (lo, hi) => lo + Math.random() * (hi - lo);
  const facing = (p) => (Math.cos(p.psi) >= 0 ? 1 : -1);
  const nose = (p) => ({ x: Math.cos(p.psi) * Math.cos(p.gam), y: -Math.sin(p.gam) });
  const velocity = (p) => ({ x: p.v * Math.cos(p.psi) * Math.cos(p.gam), y: -p.v * Math.sin(p.gam) });

  function fly(p, dt) {
    if (p.falling) {
      if (p.crashed) return;
      p.vx *= 1 - 0.4 * dt;
      p.vy = Math.min(p.vy + FALL_ACCEL * dt, FALL_MAX);
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.spin += dt;
      p.psi = p.vx >= 0 ? 0 : Math.PI;
      p.gam = Math.atan2(-p.vy, Math.abs(p.vx)) + 0.35 * Math.sin(p.spin * 7);
      return;
    }
    const throttle = p.v < STALL + 0.5 * UNIT ? 1 : p.throttle;
    p.v += (PULL * (throttle - (p.v / p.top) ** 2) - CLIMB_LOSS * Math.sin(p.gam)) * dt;
    p.v = Math.max(p.v, 20);
    p.gam += p.pitch * (p.pitch > 0 || p.looping ? PITCH_UP : PITCH_DOWN) * dt;
    if (p.v < STALL) {
      const drop = angle(-Math.PI / 2 - p.gam);
      p.gam += Math.sign(drop) * Math.min(Math.abs(drop), 1.2 * (1 - p.v / STALL) * dt);
    }
    p.gam = angle(p.gam);
    if (Math.abs(p.gam) > Math.PI / 2) {
      p.psi = Math.PI - p.psi;
      p.gam = angle(Math.PI - p.gam);
    }
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

  function keepInside(p) {
    const steep = Math.asin(clamp(Math.sin(p.gam), -1, 1)), radius = p.v / PITCH_UP + 10;
    const room = radius * (1 - Math.cos(steep)) + p.v * 0.3;
    if (steep < 0.1 && p.y + room > FLOOR) p.pitch = Math.cos(p.gam) >= 0 ? 1 : -1;
    else if (steep > -0.1 && p.y - room < TOP) p.pitch = Math.cos(p.gam) >= 0 ? -1 : 1;
  }

  function makePlane(size, top) {
    return { size, top, x: 0, y: 0, v: 0, gam: 0, psi: 0, pitch: 0, throttle: 1 };
  }

  function world(boxes = []) {
    const glass = boxes.map((b) => ({ ...b, broken: false }));
    const s = { prey: makePlane(1.05, TOP_SPEED), hunter: makePlane(0.92, TOP_SPEED), bullets: [], sparks: [], puffs: [], shards: [], stars: [], glass, t: 0 };
    reset(s);
    return s;
  }

  function place(p, x, y, dir, v) {
    const psi = dir > 0 ? 0 : Math.PI;
    Object.assign(p, { x, y, v, gam: 0, psi, pitch: 0, throttle: 1, wrap: false, leaving: false, gone: false });
  }

  function reset(s) {
    const dir = Math.random() < 0.5 ? 1 : -1, y = rand(150, 330);
    place(s.prey, dir > 0 ? -EDGE - 10 : W + EDGE + 10, y, dir, 2.65 * UNIT);
    place(s.hunter, dir > 0 ? -EDGE - 220 : W + EDGE + 220, y + rand(-30, 30), dir, 2.9 * UNIT);
    Object.assign(s.prey, { falling: false, crashed: false, throttle: CRUISE, mode: "cruise", timer: rand(2, 3), alt: y, hits: 0, smoke: 0, smokeAt: 0, turned: 0, jink: false });
    Object.assign(s.hunter, { mode: "chase", burst: 0, cool: 0.6, shotAt: 0, gun: 1, close: false, turnDir: 0, obj: null, objUntil: 0, objNext: s.t + rand(4, 8) });
    s.exitTime = 0;
    s.fade = 1;
    s.calm = s.t + 2.5;
    s.started = s.t;
    for (const g of s.glass) g.broken = false;
    s.stars.length = 0;
  }

  function canLoop(p) {
    return p.v > 2.3 * UNIT && p.v < 2.75 * UNIT && p.y > TOP + 10 + (2 * p.v) / PITCH_UP && p.y < 415 && Math.abs(p.gam) < 0.3;
  }

  function nextMove(p) {
    const moves = [];
    if (canLoop(p)) moves.push("loop", "loop", "half");
    if (p.y < 330) moves.push("dive", "dive");
    if (p.y > 220 && p.v > 2.4 * UNIT) moves.push("climb");
    if (!p.jink || !moves.length) moves.push("cruise");
    p.jink = false;
    p.mode = moves[Math.floor(Math.random() * moves.length)];
    p.throttle = CRUISE;
    p.loopV = p.v;
    p.turned = 0;
    p.loopDir = -facing(p);
    p.timer = p.mode === "cruise" ? rand(1.5, 3.5) : 12;
    if (p.mode === "cruise") p.alt = clamp(p.y + rand(-80, 80), 120, 380);
  }

  function evade(s, dt) {
    const p = s.prey;
    p.looping = false;
    if (p.falling) return;
    p.timer -= dt;
    if (p.mode === "loop" || p.mode === "half") {
      p.turned += PITCH_UP * Math.abs(p.pitch) * dt;
      if (p.turned < (p.mode === "loop" ? TAU - 0.1 : Math.PI - 0.05) && p.timer > 0) {
        p.pitch = -p.loopDir * Math.cos(p.psi);
        p.looping = true;
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
        p.loopDir = -facing(p);
        p.turned = 0;
        p.timer = 12;
      } else if (p.y > 345 && Math.abs(p.gam) < 0.05) nextMove(p);
    } else if (p.mode === "climb") {
      pitchTo(p, 0.6);
      if (p.y < 120 || p.v < 2 * UNIT) nextMove(p);
    } else {
      pitchTo(p, clamp((p.y - p.alt) * 0.006, -0.4, 0.4));
      if (p.mode === "leave") p.leaving = true;
      else if (p.timer <= 0 && p.wrap) nextMove(p);
    }
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

  function objectAim(h, g) {
    const x = wrapDx(g.x + g.w / 2 - h.x), y = g.y + g.h / 2 - h.y;
    return { x, y, dist: Math.hypot(x, y) };
  }

  function hunt(s, dt) {
    const h = s.hunter, p = s.prey;
    h.cool -= dt;
    if (h.mode === "leave") {
      h.leaving = true;
      pitchTo(h, s.prey.falling ? 0.5 : 0.35);
      keepInside(h);
      return;
    }
    if (h.obj && (h.obj.broken || s.t > h.objUntil)) h.obj = null;
    if (!h.obj && s.t > h.objNext && !h.close && !h.turnDir) {
      h.objNext = s.t + rand(6, 12);
      const ahead = s.glass.filter((g) => {
        const dx = (g.x + g.w / 2 - h.x) * facing(h);
        return g.target && !g.broken && dx > 80 && dx < FIRE_RANGE && Math.abs(g.y + g.h / 2 - h.y) < dx;
      });
      if (ahead.length) {
        h.obj = ahead[Math.floor(Math.random() * ahead.length)];
        h.objUntil = s.t + 3.5;
      }
    }
    const aim = h.obj ? objectAim(h, h.obj) : lead(h, p);
    if (!h.obj && aim.dist < 2.5 * UNIT) h.close = true;
    else if (aim.dist > 3.5 * UNIT) h.close = false;
    h.throttle = aim.dist < 4 * UNIT ? 0.3 : aim.dist > 8 * UNIT ? 0.8 : 0.5;
    if (h.close) {
      pitchTo(h, p.y > h.y || h.y > FLOOR - 80 ? 0.6 : -0.6);
    } else {
      let want = Math.atan2(-(aim.y + 6 * Math.sin(s.t * 1.3)), aim.x * facing(h));
      if (Math.abs(want) > 2) {
        if (!h.turnDir) {
          const room = (2.4 * Math.max(h.v, 3.5 * UNIT)) / PITCH_UP + 30;
          h.turnDir = h.y - room > TOP ? 1 : h.y + room < FLOOR ? -1 : 0;
        }
        want = h.turnDir * (Math.PI / 2 + 0.4);
      } else h.turnDir = 0;
      pitchTo(h, want, 4);
    }
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
    const clear = h.obj ? h.x > 0 && h.x < W : !p.smoke && p.x > 30 && p.x < W - 30;
    if (h.cool <= 0 && s.t > s.calm && clear && !h.close && aim.dist < FIRE_RANGE && off < FIRE_CONE) {
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
    const side = 2.6 * h.gun, front = 14.4 * h.size;
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
    if (len < 0.3) return dx * dx + dy * dy < 7 * 7;
    const along = (dx * n.x + dy * n.y) / len, across = (-dx * n.y + dy * n.x) / len;
    return (along / (15 * p.size * len)) ** 2 + (across / 5.4) ** 2 < 1;
  }

  function shatter(s, g, b, hx, hy) {
    g.broken = true;
    const pane = g.kind === "pane";
    const push = Math.sign(b.vx) * 40;
    for (let k = 0; k < (pane ? PANE_SHARDS : SHARDS_EACH) && s.shards.length < MAX_SHARDS; k++) {
      const x = pane ? clamp(hx + rand(-40, 40), g.x, g.x + g.w) : g.x + rand(0, g.w);
      const y = pane ? clamp(hy + rand(-35, 35), g.y, g.y + g.h) : g.y + rand(0, g.h);
      const out = Math.atan2(y - hy, x - hx), speed = pane ? rand(60, 190) : 0;
      s.shards.push({
        x, y,
        vx: pane ? Math.cos(out) * speed + push : rand(-110, 110) + push,
        vy: pane ? Math.sin(out) * speed - 60 : rand(-170, -20),
        a: rand(0, TAU), spin: pane ? rand(-6, 6) : rand(-14, 14), size: pane ? rand(8, 20) : rand(3, 6.5),
        k: [1, rand(0.3, 0.6), rand(0.7, 1)], o: [rand(2.2, 2.7), rand(3.8, 4.4)],
        floor: rand(306, 392), life: rand(1.8, 2.6), bounced: false, rest: false,
      });
    }
    if (s.stars.length < MAX_STARS) s.stars.push({ x: g.x + g.w / 2, y: g.y + g.h / 2, phase: rand(0, TAU) });
  }

  function shotDown(p) {
    const v = velocity(p);
    Object.assign(p, { falling: true, smoke: 0.001, smokeAt: 0, spin: 0, vx: v.x, vy: v.y, leaving: true, wrap: false, mode: "fall" });
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
          puff(s, x, y, 2.4, 8.4, 0.6, "hit");
          p.hits++;
          p.jink = true;
          if (p.mode === "cruise") p.timer = 0;
          if (p.hits >= HITS_TO_SMOKE) shotDown(p);
          b.life = 0;
          break;
        }
      }
      for (const g of s.glass) {
        if (g.broken || b.life <= 0) continue;
        const mx = (x0 + b.x) / 2, my = (y0 + b.y) / 2;
        const hit = [[x0, y0], [mx, my], [b.x, b.y]].find(([x, y]) => x > g.x && x < g.x + g.w && y > g.y && y < g.y + g.h);
        if (hit && (g.kind !== "pane" || Math.random() < PANE_CHANCE)) {
          shatter(s, g, b, hit[0], hit[1]);
          b.life = 0;
        }
      }
      if (b.life <= 0) s.bullets.splice(i, 1);
    }
    for (let i = s.stars.length - 1; i >= 0; i--) {
      const st = s.stars[i];
      const taker = [p, h].find((q) => !q.falling && Math.hypot(wrapDx(q.x - st.x), q.y - st.y) < STAR_REACH);
      if (!taker) continue;
      s.sparks.push({ x: st.x, y: st.y, age: 0, spin: rand(0, 1) });
      s.stars.splice(i, 1);
    }
    for (let i = s.shards.length - 1; i >= 0; i--) {
      const f = s.shards[i];
      f.life -= dt;
      if (!f.rest) {
        f.vy += SHARD_GRAVITY * dt;
        f.x += f.vx * dt;
        f.y += f.vy * dt;
        f.a += f.spin * dt;
        if (f.y > f.floor && f.vy > 0) {
          f.y = f.floor;
          if (f.bounced) f.rest = true;
          else Object.assign(f, { vy: -0.35 * f.vy, vx: 0.5 * f.vx, spin: 0.5 * f.spin, bounced: true });
        }
      }
      if (f.life <= 0) s.shards.splice(i, 1);
    }
    for (let i = s.sparks.length - 1; i >= 0; i--) if ((s.sparks[i].age += dt) > 0.2) s.sparks.splice(i, 1);
    for (let i = s.puffs.length - 1; i >= 0; i--) if ((s.puffs[i].age += dt) > s.puffs[i].life) s.puffs.splice(i, 1);

    if (p.falling) {
      p.smoke += dt;
      p.smokeAt -= dt;
      if (p.smokeAt <= 0 && !p.crashed) {
        p.smokeAt = 0.035;
        const n = nose(p), tail = -10 * p.size;
        puff(s, p.x + n.x * tail, p.y + n.y * tail, 2, 5, 0.3, "fire");
        if (Math.random() < 0.5) puff(s, p.x + n.x * tail * 1.5, p.y + n.y * tail * 1.5, 3, 13, 1.8, "dark");
      }
      if (p.smoke > 0.4) h.mode = "leave";
      if (!p.crashed && (p.y > 446 || p.x < -EDGE || p.x > W + EDGE)) {
        p.crashed = true;
        s.endAt = s.t + 3;
        if (p.y > 446 && p.x > -20 && p.x < W + 20) {
          for (let k = 0; k < 3; k++) s.sparks.push({ x: p.x + rand(-6, 6), y: 450 + rand(-4, 2), age: rand(-0.1, 0), spin: rand(0, 1) });
          puff(s, p.x, 448, 6, 22, 0.9, "hit");
          for (let k = 0; k < 4; k++) puff(s, p.x + rand(-10, 10), 446 - k * 4, 6, 20, 2.2, "dark");
        }
      }
      if (p.crashed && s.t > s.endAt) s.fade = h.gone ? 0 : s.fade - dt / 0.6;
    } else if (s.t - s.started > 45 && p.mode === "cruise") {
      p.mode = h.mode = "leave";
    }
    if (p.mode === "leave") s.exitTime += dt;
    for (const q of [p, h]) if (q.leaving && (q.x < -EDGE || q.x > W + EDGE)) q.gone = true;
    if (s.exitTime > 12) s.fade -= dt / 0.6;
    if ((!p.falling && p.gone && h.gone) || s.fade <= 0) reset(s);
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
  const glassEls = [...scene.querySelectorAll(".glass")];
  const brokenEls = glassEls.map((el) => (el.nextElementSibling && el.nextElementSibling.classList.contains("pane-broken") ? el.nextElementSibling : null));
  const boxes = glassEls.map((el) => {
    const [x, y, w, h] = el.dataset.box.split(",").map(Number);
    return { x, y, w, h, kind: el.dataset.kind || "glass", target: el.dataset.target === "1" };
  });
  const shardPath = layer("path", "shards", sprites.hunter);
  const starPath = layer("path", "stars", sprites.hunter);
  const circles = [];

  let state = null, running = false, onScreen = true, last = 0, acc = 0, pending = 0;

  const n = (v) => v.toFixed(1);
  function draw(s) {
    for (const key of ["prey", "hunter"]) {
      const p = s[key];
      const sx = Math.cos(p.psi) * SPRITE;
      sprites[key].setAttribute("transform", `translate(${n(p.x)} ${n(p.y)}) scale(${sx.toFixed(3)} ${SPRITE}) rotate(${n((-p.gam * 180) / Math.PI)})`);
      sprites[key].style.opacity = p.crashed ? "0" : s.fade < 1 ? Math.max(0, s.fade).toFixed(2) : "";
    }
    let d = "";
    for (const b of s.bullets) d += `M${n(b.x)} ${n(b.y)}L${n(b.x - b.vx * 0.0144)} ${n(b.y - b.vy * 0.0144)}`;
    tracers.setAttribute("d", d);
    d = "";
    for (const sp of s.sparks) {
      const t = Math.max(0, sp.age) / 0.2, r0 = 1.8 + 3.6 * t, r1 = 4.8 + 7.2 * t;
      for (let i = 0; i < 6; i++) {
        const a = (i + sp.spin) * (TAU / 6);
        d += `M${n(sp.x + Math.cos(a) * r0)} ${n(sp.y + Math.sin(a) * r0)}L${n(sp.x + Math.cos(a) * r1)} ${n(sp.y + Math.sin(a) * r1)}`;
      }
    }
    sparks.setAttribute("d", d);
    d = "";
    for (const f of s.shards) {
      const r = f.size * Math.min(1, f.life / 0.6);
      const pt = (off, k) => `${n(f.x + Math.cos(f.a + off) * r * k)} ${n(f.y + Math.sin(f.a + off) * r * k)}`;
      d += `M${pt(0, f.k[0])}L${pt(f.o[0], f.k[1])}L${pt(f.o[1], f.k[2])}Z`;
    }
    shardPath.setAttribute("d", d);
    d = "";
    for (const st of s.stars) {
      const cx = st.x, cy = st.y + 3 * Math.sin(s.t * 2.2 + st.phase), turn = s.t * 1.2 + st.phase;
      for (let i = 0; i < 10; i++) {
        const a = turn + (i * Math.PI) / 5, rr = i % 2 ? 3.4 : 8;
        d += `${i ? "L" : "M"}${n(cx + Math.sin(a) * rr)} ${n(cy - Math.cos(a) * rr)}`;
      }
      d += "Z";
    }
    starPath.setAttribute("d", d);
    s.glass.forEach((g, i) => {
      glassEls[i].style.display = g.broken ? "none" : "";
      if (brokenEls[i]) brokenEls[i].style.display = g.broken ? "" : "none";
    });
    s.puffs.forEach((f, i) => {
      let c = circles[i];
      if (!c) {
        c = circles[i] = document.createElementNS(NS, "circle");
        smoke.appendChild(c);
      }
      const t = f.age / f.life;
      c.setAttribute("class", f.kind);
      c.setAttribute("cx", n(f.x));
      c.setAttribute("cy", n(f.y - (f.kind === "smoke" || f.kind === "dark" ? 10 * t : 0)));
      c.setAttribute("r", n(f.r0 + (f.r1 - f.r0) * Math.sqrt(t)));
      c.style.opacity = ((1 - t) * (f.kind === "fire" ? 0.95 : f.kind === "hit" ? 0.8 : 0.6)).toFixed(2);
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
      shardPath.setAttribute("d", "");
      starPath.setAttribute("d", "");
      glassEls.forEach((el) => (el.style.display = ""));
      brokenEls.forEach((el) => el && (el.style.display = "none"));
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
    if (!state) state = world(boxes);
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
