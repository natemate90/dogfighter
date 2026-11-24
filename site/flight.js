(() => {
  const W = 640, H = 460, EDGE = 50, SPAN_X = W + 2 * EDGE, SPAN_Y = H + 2 * EDGE, DT = 1 / 120;
  const DEG = Math.PI / 180, TAU = Math.PI * 2, SPRITE = 0.36;
  const G = 50, THRUST = 45, TOP_SPEED = 150, CRUISE_SPEED = 80, CRUISE = (CRUISE_SPEED / TOP_SPEED) ** 2;
  const STALL = 45, MAX_G = 3.5, ROLL_RATE = 3.5, TURN_DRAG = 1.5;
  const CRUISE_H = 120, EYE = 480, SHADOW_X = 0.14, SHADOW_Y = 0.2, LOOP_R = 55, LOOP_V = 120;
  const MUZZLE = 1800, BULLET_LIFE = 1.2, GUN_RATE = 8.7, BURST = 0.6, SPREAD = 0.035;
  const LOCK_CONE = 0.12, FIRE_CONE = 0.12, FIRE_RANGE = 260, MAX_BULLETS = 40, HITS_TO_SMOKE = 12;
  const FALL_ACCEL = 30, FALL_MAX = 70, LAG = 0.35;
  const SHARD_GRAVITY = 480, SHARDS_EACH = 22, PANE_SHARDS = 12, MAX_SHARDS = 80, PANE_CHANCE = 0.02;
  const STAR_REACH = 43, MAX_STARS = 12;

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const angle = (a) => Math.atan2(Math.sin(a), Math.cos(a));
  const rand = (lo, hi) => lo + Math.random() * (hi - lo);
  const wrapDx = (d) => d - SPAN_X * Math.round(d / SPAN_X);
  const wrapDy = (d) => d - SPAN_Y * Math.round(d / SPAN_Y);
  const inBox = (q, m) => q.x > m && q.x < W - m && q.y > m && q.y < H - m;
  const nose = (p) => ({ x: Math.cos(p.psi) * Math.cos(p.th), y: Math.sin(p.psi) * Math.cos(p.th) });
  const velocity = (p) => {
    const n = nose(p);
    return { x: p.v * n.x, y: p.v * n.y };
  };
  const perspective = (h) => (EYE - CRUISE_H) / (EYE - h);
  const bankLimit = (v) => Math.acos(1 / clamp((v / STALL) ** 2, 1.01, MAX_G));

  function fly(p, dt) {
    if (p.falling) {
      if (p.crashed) return;
      p.spin += dt;
      p.v += (55 - p.v) * 0.5 * dt;
      p.sink = Math.min(p.sink + FALL_ACCEL * dt, FALL_MAX);
      p.h -= p.sink * dt;
      p.psi = angle(p.psi + p.spinDir * Math.min(4, 1.2 + 1.2 * p.spin) * dt);
      p.th += (-0.9 - p.th) * 2 * dt;
      p.phi = p.spinDir * (1.15 + 0.2 * Math.sin(p.spin * 9));
      move(p, dt);
      return;
    }
    const n = 1 / Math.cos(p.phi);
    const throttle = p.v < STALL + 15 ? 1 : p.throttle;
    p.v += (THRUST * (throttle - (p.v / TOP_SPEED) ** 2) - G * Math.sin(p.th) - (p.drag || TURN_DRAG) * (n * n - 1)) * dt;
    p.v = Math.max(p.v, p.h > 5 ? 30 : 0);
    if (p.looping) {
      p.th += (p.v / LOOP_R) * dt;
      p.h += p.v * Math.sin(p.th) * dt;
      if (p.th >= TAU) Object.assign(p, { th: 0, h: CRUISE_H, looping: false });
    } else p.h += (CRUISE_H - p.h) * dt;
    const bank = bankLimit(p.v);
    const want = p.looping ? 0 : clamp(Math.atan((p.turn * p.v) / G), -bank, bank);
    p.phi += clamp(want - p.phi, -ROLL_RATE * dt, ROLL_RATE * dt);
    if (!p.looping) p.psi = angle(p.psi + ((G * Math.tan(p.phi)) / p.v) * dt);
    move(p, dt);
  }

  function move(p, dt) {
    const vel = velocity(p);
    p.x += vel.x * dt;
    p.y += vel.y * dt;
    if (p.leaving) p.wrap = false;
    else if (p.wrap && Math.abs(p.h - CRUISE_H) < 10) {
      p.x = wrapDx(p.x - W / 2) + W / 2;
      p.y = wrapDy(p.y - H / 2) + H / 2;
    } else if (inBox(p, -EDGE)) p.wrap = true;
  }

  function steer(p, heading, gain) {
    p.turn = angle(heading - p.psi) * gain;
  }

  function makePlane(size) {
    return { size, x: 0, y: 0, h: CRUISE_H, v: 0, psi: 0, th: 0, phi: 0, turn: 0, throttle: CRUISE };
  }

  function world(boxes = []) {
    const glass = boxes.map((b) => ({ ...b, broken: false }));
    const s = { prey: makePlane(1.05), hunter: makePlane(0.92), bullets: [], sparks: [], puffs: [], shards: [], stars: [], glass, t: 0 };
    reset(s);
    return s;
  }

  function place(p, x, y, psi, v) {
    Object.assign(p, { x, y, v, psi, h: CRUISE_H, th: 0, phi: 0, turn: 0, throttle: CRUISE, looping: false, wrap: false, leaving: false, gone: false, falling: false, crashed: false });
  }

  function reset(s) {
    const right = Math.random() < 0.5, psi = (right ? 0 : Math.PI) + rand(-0.3, 0.3);
    const x = right ? -EDGE - 10 : W + EDGE + 10, y = rand(110, 350), back = rand(200, 240);
    place(s.prey, x, y, psi, CRUISE_SPEED);
    place(s.hunter, x - Math.cos(psi) * back, y - Math.sin(psi) * back, psi, CRUISE_SPEED + 10);
    Object.assign(s.prey, { mode: "cruise", want: psi, timer: rand(3, 5), hits: 0, smoke: 0, smokeAt: 0 });
    Object.assign(s.hunter, { mode: "chase", track: psi, burst: 0, cool: 0.6, shotAt: 0, gun: 1, follow: null, obj: null, objUntil: 0, objNext: s.t + rand(4, 8) });
    s.trickAt = s.t + rand(3, 8);
    s.exitTime = 0;
    s.fade = 1;
    s.calm = s.t + 2.5;
    s.started = s.t;
    for (const g of s.glass) g.broken = false;
    s.stars.length = 0;
  }

  function startLoop(s, p) {
    Object.assign(p, { looping: true, th: 0, mode: "loop" });
    const h = s.hunter, dx = wrapDx(p.x - h.x), dy = wrapDy(p.y - h.y);
    const behind = dx * Math.cos(p.psi) + dy * Math.sin(p.psi);
    if (!h.looping && h.mode === "chase" && !h.obj && behind > 0 && Math.hypot(dx, dy) < 280 && Math.abs(angle(h.psi - p.psi)) < 0.6) {
      h.follow = { x: p.x, y: p.y, psi: p.psi, until: s.t + 4 };
    }
  }

  function nextMove(s, p) {
    if (s.t > s.trickAt) {
      s.trickAt = s.t + rand(12, 18);
      if (Math.random() < 0.6) Object.assign(p, { mode: "setup", timer: 3, want: p.psi });
      else Object.assign(p, { mode: "circle", turned: 0, last: p.psi, want: p.psi, circleDir: Math.random() < 0.5 ? 1 : -1 });
      return;
    }
    const side = Math.random() < 0.5 ? 1 : -1;
    Object.assign(p, { mode: "break", want: angle(p.psi + side * rand(60, 150) * DEG) });
  }

  function evade(s, dt) {
    const p = s.prey;
    if (p.falling) return;
    p.timer -= dt;
    if (p.mode === "loop") {
      p.turn = 0;
      p.throttle = 1;
      if (!p.looping) Object.assign(p, { mode: "cruise", want: p.psi, timer: rand(2, 4) });
      return;
    }
    if (p.mode === "setup") {
      steer(p, p.want, 1.5);
      p.throttle = 1;
      if (p.v >= LOOP_V || p.timer <= 0) startLoop(s, p);
    } else if (p.mode === "circle") {
      p.turn = p.circleDir * 9;
      p.throttle = CRUISE;
      p.turned += Math.abs(angle(p.psi - p.last));
      p.last = p.psi;
      if (p.turned > TAU - 0.6) Object.assign(p, { mode: "cruise", timer: rand(3, 6) });
    } else if (p.mode === "break") {
      steer(p, p.want, 3);
      p.throttle = CRUISE;
      if (Math.abs(angle(p.want - p.psi)) < 0.08) Object.assign(p, { mode: "cruise", want: p.psi, timer: rand(4, 8) });
    } else {
      steer(p, p.want, 1.5);
      p.throttle = CRUISE;
      p.out = inBox(p, 0) ? 0 : (p.out || 0) + dt;
      if (p.mode === "leave") p.leaving = true;
      else if (p.out > 2 && p.wrap) Object.assign(p, { mode: "break", out: 0, want: Math.atan2(H / 2 - p.y, W / 2 - p.x) + rand(-0.5, 0.5) });
      else if (p.timer <= 0 && p.wrap) nextMove(s, p);
    }
  }

  function lead(h, p) {
    const dx = wrapDx(p.x - h.x), dy = wrapDy(p.y - h.y), dist = Math.hypot(dx, dy);
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
    const x = g.x + g.w / 2 - h.x, y = g.y + g.h / 2 - h.y;
    return { x, y, dist: Math.hypot(x, y) };
  }

  function hunt(s, dt) {
    const h = s.hunter, p = s.prey;
    h.cool -= dt;
    if (h.looping) {
      h.turn = 0;
      h.throttle = 1;
      return;
    }
    if (h.mode === "leave") {
      h.leaving = true;
      h.turn = 0;
      h.throttle = 0.6;
      return;
    }
    if (h.follow) {
      const f = h.follow, dx = wrapDx(f.x - h.x), dy = wrapDy(f.y - h.y);
      steer(h, Math.atan2(dy, dx), 2);
      h.throttle = 1;
      if (dx * Math.cos(f.psi) + dy * Math.sin(f.psi) <= 0) {
        h.follow = null;
        if (h.v > 100) Object.assign(h, { looping: true, th: 0 });
      } else if (s.t > f.until) h.follow = null;
      return;
    }
    const c = Math.cos(h.psi), sn = Math.sin(h.psi);
    const ahead = (g, near) => {
      const a = objectAim(h, g), along = a.x * c + a.y * sn, across = Math.abs(a.y * c - a.x * sn);
      return along > near && along < FIRE_RANGE && across < along * 0.4;
    };
    if (h.obj && (h.obj.broken || s.t > h.objUntil || !ahead(h.obj, 40))) h.obj = null;
    if (!h.obj && s.t > h.objNext && h.cool < 0.3 && inBox(h, 0)) {
      h.objNext = s.t + rand(6, 12);
      const targets = s.glass.filter((g) => g.target && !g.broken && ahead(g, 100));
      if (targets.length) {
        h.obj = targets[Math.floor(Math.random() * targets.length)];
        h.objUntil = s.t + 3.5;
      }
    }
    const aim = h.obj ? objectAim(h, h.obj) : lead(h, p);
    h.track = angle(h.track + angle(Math.atan2(aim.y, aim.x) - h.track) * Math.min(1, dt / LAG));
    steer(h, h.track, 2.5);
    h.throttle = h.obj ? 0.5 : clamp((aim.dist - 120) / 200, 0.02, 1);
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
    const clear = inBox(h, 0) && (h.obj || (!p.smoke && inBox(p, 70) && Math.abs(p.h - h.h) < 30 && Math.hypot(p.x - h.x, p.y - h.y) < FIRE_RANGE));
    if (h.cool <= 0 && s.t > s.calm && clear && aim.dist < FIRE_RANGE && off < FIRE_CONE) {
      h.burst = BURST;
      h.shotAt = 0;
      h.cool = BURST + rand(0.8, 1.8);
    }
  }

  function shoot(s, h, aim) {
    if (s.bullets.length >= MAX_BULLETS) return;
    let dx = Math.cos(h.psi), dy = Math.sin(h.psi);
    const aimLen = Math.hypot(aim.x, aim.y) || 1;
    if (Math.acos(clamp((dx * aim.x + dy * aim.y) / aimLen, -1, 1)) < LOCK_CONE) {
      dx = aim.x / aimLen;
      dy = aim.y / aimLen;
    }
    const a = Math.atan2(dy, dx) + rand(-SPREAD, SPREAD), hv = velocity(h);
    h.gun = -h.gun;
    const side = 6 * h.gun * h.size, front = 14 * h.size;
    s.bullets.push({
      x: h.x + Math.cos(h.psi) * front - Math.sin(h.psi) * side,
      y: h.y + Math.sin(h.psi) * front + Math.cos(h.psi) * side,
      vx: hv.x + Math.cos(a) * MUZZLE,
      vy: hv.y + Math.sin(a) * MUZZLE,
      life: BULLET_LIFE,
    });
  }

  function hits(p, x, y) {
    const dx = wrapDx(x - p.x), dy = wrapDy(y - p.y), c = Math.cos(p.psi), sn = Math.sin(p.psi);
    const along = dx * c + dy * sn, across = dy * c - dx * sn;
    return (along / (15 * p.size)) ** 2 + (across / (10 * p.size)) ** 2 < 1;
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
    Object.assign(p, { falling: true, looping: false, th: angle(p.th), smoke: 0.001, smokeAt: 0, spin: 0, sink: 0, spinDir: p.phi < 0 ? -1 : 1, leaving: true, wrap: false, mode: "fall" });
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
      if (b.x < -EDGE || b.x > W + EDGE || b.y < -EDGE || b.y > H + EDGE) b.life = 0;
      if (!p.smoke && Math.abs(p.h - h.h) < 30) {
        for (let k = 1; k <= 5; k++) {
          const x = x0 + (b.vx * dt * k) / 5, y = y0 + (b.vy * dt * k) / 5;
          if (!hits(p, x, y)) continue;
          s.sparks.push({ x, y, age: 0, spin: rand(0, 1) });
          puff(s, x, y, 2.4, 8.4, 0.6, "hit");
          p.hits++;
          if (p.mode === "cruise" && p.timer > 1.5) p.timer = rand(0.8, 1.5);
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
      const taker = [p, h].find((q) => !q.falling && Math.abs(q.h - CRUISE_H) < 40 && Math.hypot(wrapDx(q.x - st.x), wrapDy(q.y - st.y)) < STAR_REACH);
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
      if (!p.crashed && p.h <= 0) {
        p.crashed = true;
        s.endAt = s.t + 3;
        if (inBox(p, -20)) {
          for (let k = 0; k < 3; k++) s.sparks.push({ x: p.x + rand(-6, 6), y: p.y + rand(-6, 6), age: rand(-0.1, 0), spin: rand(0, 1) });
          puff(s, p.x, p.y, 6, 22, 0.9, "hit");
          for (let k = 0; k < 4; k++) puff(s, p.x + rand(-10, 10), p.y - k * 4, 6, 20, 2.2, "dark");
        }
      }
      if (p.crashed && s.t > s.endAt) s.fade = h.gone ? 0 : s.fade - dt / 0.6;
    } else if (s.t - s.started > 45 && p.mode === "cruise") {
      p.mode = h.mode = "leave";
      h.follow = null;
    }
    if (p.mode === "leave") s.exitTime += dt;
    for (const q of [p, h]) if (q.leaving && !inBox(q, -EDGE)) q.gone = true;
    if (s.exitTime > 12) s.fade -= dt / 0.6;
    if ((!p.falling && p.gone && h.gone) || s.fade <= 0) reset(s);
  }

  window.spitfire = { fly, steer, angle, rand, bankLimit, perspective, G, STALL, CRUISE, SHADOW_X, SHADOW_Y, DT };

  const scene = document.getElementById("scene");
  if (!scene || !window.requestAnimationFrame) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const NS = "http://www.w3.org/2000/svg";
  const sprites = { prey: scene.querySelector(".flyer.prey"), hunter: scene.querySelector(".flyer.hunter") };
  const shadows = { prey: scene.querySelector(".flyer-shadow.prey"), hunter: scene.querySelector(".flyer-shadow.hunter") };
  const poses = new Map([...Object.values(sprites), ...Object.values(shadows)].map((el) => [el, el.getAttribute("transform")]));
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

  let state = null, running = false, onScreen = true, last = 0, acc = 0, pending = 0, hunterOnTop = false;

  const n = (v) => v.toFixed(1);
  const pose = (x, y, p, k) => {
    const along = Math.cos(p.th), across = Math.max(Math.cos(p.phi), 0.25);
    const sx = (along < 0 ? -1 : 1) * Math.max(Math.abs(along), 0.15) * k;
    return `translate(${n(x)} ${n(y)}) rotate(${n((p.psi * 180) / Math.PI)}) scale(${sx.toFixed(3)} ${(across * k).toFixed(3)})`;
  };
  function draw(s) {
    for (const key of ["prey", "hunter"]) {
      const p = s[key], h = Math.max(0, p.h);
      const fade = p.crashed ? 0 : Math.max(0, Math.min(1, s.fade));
      sprites[key].setAttribute("transform", pose(p.x, p.y, p, SPRITE * perspective(h)));
      sprites[key].style.opacity = fade < 1 ? fade.toFixed(2) : "";
      shadows[key].setAttribute("transform", pose(p.x + h * SHADOW_X, p.y + h * SHADOW_Y, p, SPRITE * perspective(0)));
      shadows[key].style.opacity = (0.16 * fade * clamp(1.4 - h / 300, 0.3, 1)).toFixed(3);
    }
    const top = s.hunter.h > s.prey.h + 4;
    if (top !== hunterOnTop) {
      hunterOnTop = top;
      scene.insertBefore(sprites.hunter, top ? sprites.prey.nextSibling : sprites.prey);
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
      for (const [el, transform] of poses) {
        el.setAttribute("transform", transform);
        el.style.opacity = "";
      }
      hunterOnTop = false;
      scene.insertBefore(sprites.hunter, sprites.prey);
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
