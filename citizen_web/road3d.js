/* Disha AI: a soft 3D road behind the website. It drives forward on its own, bends as you move the pointer or drag
   (or tilt a phone), and speeds up while you press and hold. Palette: charcoal, sage, peach, ivory. */
(function () {
  var cv = document.getElementById("bg3d");
  if (!cv || !cv.getContext) return;
  var ctx = cv.getContext("2d");
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var W = 0, H = 0, S = 0.5; // render at half resolution: smooth, cool and cheap
  var z = 0, speed = 0.9, target = 0.9, bend = 0, bendTarget = 0, tilt = 0, sway = 0, last = 0, acc = 0;
  var down = false, dragX = null;

  function resize() {
    W = Math.max(320, Math.round(innerWidth * S)); H = Math.max(240, Math.round(innerHeight * S));
    cv.width = W; cv.height = H;
  }
  resize(); addEventListener("resize", resize);

  function setBend(clientX) { bendTarget = Math.max(-1, Math.min(1, (clientX / innerWidth - 0.5) * 2)); }
  addEventListener("pointermove", function (e) { if (down && dragX != null) { bendTarget = Math.max(-1, Math.min(1, bendTarget + (e.clientX - dragX) / innerWidth * 3)); dragX = e.clientX; } else if (e.pointerType === "mouse") { setBend(e.clientX); } }, { passive: true });
  addEventListener("pointerdown", function (e) { down = true; dragX = e.clientX; target = 2.4; }, { passive: true });
  addEventListener("pointerup", function () { down = false; dragX = null; target = 0.9; }, { passive: true });
  addEventListener("pointercancel", function () { down = false; dragX = null; target = 0.9; }, { passive: true });
  addEventListener("wheel", function (e) { target = Math.min(3, 0.9 + Math.abs(e.deltaY) / 120); setTimeout(function () { if (!down) target = 0.9; }, 350); }, { passive: true });
  addEventListener("deviceorientation", function (e) { if (e.gamma != null) tilt = Math.max(-1, Math.min(1, e.gamma / 30)); }, { passive: true });

  function lerp(a, b, t) { return a + (b - a) * t; }
  var LIGHT = { sky0: "#F4F1DE", sky1: "#F6E9CB", sky2: "#F2CC8F", sun0: "rgba(255,247,226,.95)", sun1: "rgba(242,204,143,.55)", sun2: "rgba(242,204,143,0)", h1: "#BCD5C5", h2: "#9DC4AE", g0: "#A9CDB6", g1: "#81B29A", vA: "rgba(129,178,154,.55)", vB: "rgba(111,163,138,.55)", kA: "#F4F1DE", kB: "#F2CC8F", aA: "#5F6384", aB: "#585C7C", dash: "#F2CC8F", haze0: "rgba(246,233,203,.95)", haze1: "rgba(246,233,203,0)" };
  var DARK = { sky0: "#1F2133", sky1: "#2A2D47", sky2: "#5B4E55", sun0: "rgba(242,204,143,.55)", sun1: "rgba(242,204,143,.22)", sun2: "rgba(242,204,143,0)", h1: "#2B3A4A", h2: "#27423F", g0: "#25403B", g1: "#1A2D2D", vA: "rgba(60,100,86,.55)", vB: "rgba(48,84,72,.55)", kA: "#8A8CA3", kB: "#F2CC8F", aA: "#2A2C40", aB: "#242638", dash: "#F2CC8F", haze0: "rgba(60,56,70,.9)", haze1: "rgba(60,56,70,0)" };
  var P = LIGHT;

  var lastTheme = "";
  function frame(t) {
    if (!document.body.classList.contains("on-home")) { lastTheme = ""; return; }
    var th = document.documentElement.getAttribute("data-theme");
    if (reduce && th === lastTheme) return; lastTheme = th;
    var dt = Math.min(0.05, (t - last) / 1000 || 0.016); last = t;
    speed = lerp(speed, target, 0.06);
    z += speed * dt * 3.2;
    sway = Math.sin(t / 3800) * 0.35 + Math.sin(t / 1900) * 0.12;
    bend = lerp(bend, bendTarget * 0.9 + tilt * 0.9 + sway, 0.04);
    draw(t);
  }

  function draw(t) {
    P = document.documentElement.getAttribute("data-theme") === "dark" ? DARK : LIGHT;
    var hz = Math.round(H * 0.46); // horizon line
    // sky: ivory fading to a warm peach glow at the horizon
    var g = ctx.createLinearGradient(0, 0, 0, hz);
    g.addColorStop(0, P.sky0); g.addColorStop(0.7, P.sky1); g.addColorStop(1, P.sky2);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, hz + 1);
    // sun
    var sx = W * (0.5 - bend * 0.12), sr = H * 0.1;
    var sg = ctx.createRadialGradient(sx, hz - sr * 0.4, sr * 0.2, sx, hz - sr * 0.4, sr * 2.2);
    sg.addColorStop(0, P.sun0); sg.addColorStop(0.4, P.sun1); sg.addColorStop(1, P.sun2);
    ctx.fillStyle = sg; ctx.fillRect(0, 0, W, hz + 1);
    // far hills drift sideways as the road bends (parallax)
    hills(hz, P.h1, 0.10, 0.075, 1.3, -bend * 40);
    hills(hz, P.h2, 0.065, 0.1, 2.1, -bend * 70);
    // ground
    var gg = ctx.createLinearGradient(0, hz, 0, H);
    gg.addColorStop(0, P.g0); gg.addColorStop(1, P.g1);
    ctx.fillStyle = gg; ctx.fillRect(0, hz, W, H - hz);

    // road: draw strips from the horizon down; each strip has its own depth, so curves bend toward the viewer
    var half0 = W * 0.012, half1 = W * 0.46, x = 0, dx = 0;
    var cx = W * 0.5;
    for (var y = hz; y < H; y += 1) {
      var p = (y - hz) / (H - hz);           // 0 at horizon, 1 at the bottom of the screen
      var depth = 1 / (p + 0.02);            // perspective: far strips are deeper
      var curve = bend * Math.pow(1 - p, 2.2) * W * 0.55; // the road bends far away, straight near the viewer
      var half = lerp(half0, half1, p * p * 0.85 + p * 0.15);
      var c = cx + curve;
      var band = Math.floor((depth * 0.9 + z * 6) ) % 2 === 0;
      // verge stripes in two greens give the sense of speed
      ctx.fillStyle = band ? P.vA : P.vB;
      ctx.fillRect(0, y, W, 1);
      // kerb
      ctx.fillStyle = band ? P.kA : P.kB;
      ctx.fillRect(c - half * 1.08, y, half * 2.16, 1);
      // asphalt
      ctx.fillStyle = band ? P.aA : P.aB;
      ctx.fillRect(c - half, y, half * 2, 1);
      // centre dashes (peach) race toward the viewer
      if (Math.floor(depth * 0.55 + z * 3.2) % 2 === 0) {
        ctx.fillStyle = P.dash;
        var dw = Math.max(1, half * 0.035);
        ctx.fillRect(c - dw, y, dw * 2, 1);
      }
    }
    // soft haze at the horizon to melt road into sky
    var hg = ctx.createLinearGradient(0, hz - 6, 0, hz + H * 0.12);
    hg.addColorStop(0, P.haze0); hg.addColorStop(1, P.haze1);
    ctx.fillStyle = hg; ctx.fillRect(0, hz - 6, W, H * 0.12 + 6);
  }

  function hills(hz, color, amp, freq, scale, shift) {
    ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(0, hz + 1);
    for (var x = 0; x <= W; x += 6) {
      var u = (x + shift) / W * 6.28 * scale;
      var y = hz - H * amp * (0.55 + 0.45 * Math.sin(u * 1.1 + 1.3) * Math.cos(u * 0.5 + freq * 30));
      ctx.lineTo(x, y);
    }
    ctx.lineTo(W, hz + 1); ctx.closePath(); ctx.fill();
  }

  if (reduce) { draw(0); new MutationObserver(function () { draw(0); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] }); new MutationObserver(function () { draw(0); }).observe(document.body, { attributes: true, attributeFilter: ["class"] }); return; }
  var running = true, interval = 1000 / 30;
  document.addEventListener("visibilitychange", function () { running = !document.hidden; if (running) requestAnimationFrame(loop); });
  function loop(t) {
    if (!running) return;
    acc += t - (loop.prev || t); loop.prev = t;
    if (acc >= interval) { acc = 0; frame(t); }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();
