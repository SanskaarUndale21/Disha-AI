(function () {
  "use strict";
  var API = (function () {
    try { var o = localStorage.getItem("rw-api"); if (o) return o.replace(/\/+$/, ""); } catch (e) {}
    if (window.RW_API_BASE) return window.RW_API_BASE;
    return location.protocol + "//" + location.hostname + ":8000";
  })();
  var $ = function (id) { return document.getElementById(id); };
  var vid = $("vid"), cv = $("cv"), cx = cv.getContext("2d"), grab = document.createElement("canvas");
  var ws = null, running = false, inflight = 0, sentQ = [], shown = null, last = null, SEND_W = 640;
  var seen = {}, sevSeen = {}, crackSeen = {}, raw = 0, risk = [], fpsT = [], beeped = {};
  var DPR = Math.min(2, window.devicePixelRatio || 1);
  var COL = { pothole: "#E07A5F", alligator_crack: "#F2CC8F", transverse_crack: "#F4F1DE", longitudinal_crack: "#81B29A" };

  function resize() { cv.width = Math.round(innerWidth * DPR); cv.height = Math.round(innerHeight * DPR); }
  addEventListener("resize", resize); resize();

  // ---------- audio
  var actx = null, siren = null;
  function ctx() {
    var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return null;
    if (!actx) actx = new AC();
    if (actx.state === "suspended") actx.resume().catch(function () {});
    return actx;
  }
  function beep(freq, dur) {
    var c = ctx(); if (!c) return;
    var o = c.createOscillator(), g = c.createGain(), t = c.currentTime;
    o.type = "sine"; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.3, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + dur + 0.02);
  }
  function startSiren() {
    if (siren) return;
    var c = ctx(); if (!c) return;
    var o = c.createOscillator(), g = c.createGain();
    o.type = "sawtooth"; g.gain.value = 0.3; o.connect(g); g.connect(c.destination); o.start();
    var t0 = performance.now();
    var timer = setInterval(function () {
      var ph = ((performance.now() - t0) % 1200) / 1200;
      o.frequency.setValueAtTime(600 + 500 * (ph < 0.5 ? ph * 2 : (1 - ph) * 2), c.currentTime);
    }, 30);
    siren = { o: o, g: g, timer: timer };
  }
  function stopSiren() {
    if (!siren) return;
    clearInterval(siren.timer);
    try { siren.g.gain.setTargetAtTime(0.0001, siren.o.context.currentTime, 0.03); siren.o.stop(siren.o.context.currentTime + 0.15); } catch (e) {}
    siren = null;
  }
  var alarmTimer = null;
  function raiseAlarm(em) {
    $("alMsg").textContent = (em && em.message) || "Emergency detected";
    $("alarm").classList.add("on"); startSiren();
    clearTimeout(alarmTimer);
    alarmTimer = setTimeout(function () { $("alarm").classList.remove("on"); stopSiren(); }, 6000);
  }

  // distance model: horizon at 40% of height, bottom edge about 5 m, y at 45% about 60 m
  function distM(y2, H) {
    var d = (3 * H) / Math.max(0.02 * H, y2 - 0.4 * H);
    return Math.max(4, Math.min(80, d));
  }

  // ---------- socket
  function wsSend(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }
  function connect() {
    return new Promise(function (ok, bad) {
      var s = new WebSocket(API.replace("http", "ws") + "/ws/live");
      s.binaryType = "arraybuffer";
      s.onopen = function () { ws = s; wsSend({ type: "config", cracks: true, people: true, hazards: true, sensitivity: "max" }); ok(s); };
      s.onerror = function () { bad(new Error("Cannot reach the detection server")); };
      s.onclose = function () { if (ws === s) { running = false; setLive(false, "OFFLINE"); } };
      s.onmessage = function (e) {
        if (ws !== s) return;
        var m; try { m = JSON.parse(e.data); } catch (x) { return; }
        if (m.type === "frame") {
          inflight = Math.max(0, inflight - 1);
          var pend = sentQ.shift();
          if (pend) pend.then(function (bm) { shown = bm; onFrame(m); }); else onFrame(m);
          pump();
        } else if (m.type === "error") { inflight = Math.max(0, inflight - 1); sentQ.shift(); pump(); }
      };
    });
  }
  function sendOne() {
    if (!running || !ws || ws.readyState !== 1 || !vid.videoWidth || vid.paused || vid.ended) return false;
    var sc = Math.min(1, SEND_W / vid.videoWidth);
    grab.width = Math.round(vid.videoWidth * sc); grab.height = Math.round(vid.videoHeight * sc);
    grab.getContext("2d").drawImage(vid, 0, 0, grab.width, grab.height);
    inflight++; sentQ.push(createImageBitmap(grab));
    var s = ws;
    grab.toBlob(function (b) {
      if (b && s.readyState === 1) b.arrayBuffer().then(function (buf) { s.send(buf); });
      else { inflight--; sentQ.pop(); }
    }, "image/jpeg", 0.72);
    return true;
  }
  function pump() {
    while (running && inflight < 2) { if (!sendOne()) { if (running) setTimeout(pump, 80); return; } }
  }

  // ---------- per-frame logic
  var near = null;
  function isSerious(t) { return /sever|high|serious|critical/i.test((t.severity || "") + " " + (t.risk || "")); }
  function onFrame(m) {
    last = m;
    var now = performance.now(); fpsT.push(now); while (fpsT.length && now - fpsT[0] > 2000) fpsT.shift();
    $("fps").textContent = Math.round(fpsT.length / 2);
    $("lat").textContent = Math.round(m.infer_ms || 0);
    $("frm").textContent = m.frame || 0;
    var H = m.h || 720, best = null, maxRisk = 0;
    (m.tracks || []).forEach(function (t) {
      raw++;
      if (!t.confirmed) return;
      if (/pothole/i.test(t.cls)) {
        seen[t.id] = 1;
        if (isSerious(t)) sevSeen[t.id] = 1;
        t._d = distM(t.box[3], H);
        if (t.box[3] > H * 0.45 && (!best || t._d < best._d)) best = t;
      } else crackSeen[t.id] = 1;
      maxRisk = Math.max(maxRisk, t.risk_score || (isSerious(t) ? 80 : 40));
    });
    risk.push(maxRisk); if (risk.length > 60) risk.shift();
    var u = Object.keys(seen).length, cr = Object.keys(crackSeen).length;
    $("cUniq").textContent = u;
    $("cSev").textContent = Object.keys(sevSeen).length;
    $("cCrack").textContent = cr;
    $("cRaw").textContent = raw;
    $("dedupe").textContent = "raw " + raw + " vs unique " + (u + cr);
    near = best; updateBanner();
    if (m.emergency) raiseAlarm(m.emergency);
    drawSpark();
  }

  var beepAt = 0;
  function updateBanner() {
    var b = $("banner");
    if (near && near._d <= 25) {
      var d = near._d < 10 ? Math.round(near._d) : Math.round(near._d / 5) * 5;
      var sev = isSerious(near);
      $("bTxt").textContent = sev ? "Serious pothole ahead, slow down" : "Pothole ahead, " + d + " m";
      $("bTag").textContent = sev ? "SERIOUS HAZARD, " + d + " M" : "HAZARD";
      b.classList.toggle("sev", sev); b.classList.add("on");
      var now = performance.now(), f = 520 + (25 - near._d) * 22;
      if (!beeped[near.id]) { beeped[near.id] = 1; beepAt = now; beep(f, 0.22); }
      else if (near._d < 10 && now - beepAt > 380) { beepAt = now; beep(f + 120, 0.12); }
    } else b.classList.remove("on");
  }

  function drawSpark() {
    var c = $("spark"), g = c.getContext("2d"), w = c.width, h = c.height;
    g.clearRect(0, 0, w, h);
    if (risk.length < 2) return;
    g.beginPath();
    risk.forEach(function (v, i) {
      var x = i / 59 * w, y = h - 4 - Math.min(100, v) / 100 * (h - 8);
      if (i) g.lineTo(x, y); else g.moveTo(x, y);
    });
    g.strokeStyle = "#F2CC8F"; g.lineWidth = 2; g.stroke();
    g.lineTo((risk.length - 1) / 59 * w, h); g.lineTo(0, h); g.closePath();
    g.fillStyle = "rgba(242,204,143,.18)"; g.fill();
  }

  // ---------- render loop
  function frame() {
    requestAnimationFrame(frame);
    var W = cv.width, H = cv.height;
    cx.fillStyle = "#14151f"; cx.fillRect(0, 0, W, H);
    var src = null, sw = 0, sh = 0;
    if (shown && last) { src = shown; sw = shown.width; sh = shown.height; }
    else if (vid.videoWidth) { src = vid; sw = vid.videoWidth; sh = vid.videoHeight; }
    if (!src) return;
    var s = Math.min(W / sw, H / sh);
    cx.drawImage(src, (W - sw * s) / 2, (H - sh * s) / 2, sw * s, sh * s);
    if (!last) return;
    var mw = last.w || sw, mh = last.h || sh, k = Math.min(W / mw, H / mh), px = (W - mw * k) / 2, py = (H - mh * k) / 2;
    var t = performance.now();
    if (last.lane && last.lane.segments) {
      cx.strokeStyle = "rgba(129,178,154,.8)"; cx.lineWidth = 2 * DPR; cx.beginPath();
      last.lane.segments.forEach(function (q) { cx.moveTo(px + q[0] * k, py + q[1] * k); cx.lineTo(px + q[2] * k, py + q[3] * k); });
      cx.stroke();
    }
    (last.tracks || []).forEach(function (tr) {
      var x1 = px + tr.box[0] * k, y1 = py + tr.box[1] * k, w = (tr.box[2] - tr.box[0]) * k, h = (tr.box[3] - tr.box[1]) * k;
      var col = COL[tr.cls] || "#F4F1DE";
      if (!tr.confirmed) { cx.setLineDash([5 * DPR, 5 * DPR]); cx.strokeStyle = col + "88"; cx.lineWidth = DPR; cx.strokeRect(x1, y1, w, h); cx.setLineDash([]); return; }
      var ser = isSerious(tr);
      cx.shadowColor = col; cx.shadowBlur = ser ? 14 + 8 * Math.sin(t / 150) : 6;
      cx.strokeStyle = col; cx.lineWidth = (ser ? 3 : 2) * DPR; cx.strokeRect(x1, y1, w, h);
      cx.shadowBlur = 0;
      cx.fillStyle = col + "22"; cx.fillRect(x1, y1, w, h);
      var c = Math.max(8 * DPR, Math.min(w, h) * 0.25); cx.lineWidth = 4 * DPR; cx.lineCap = "round"; cx.beginPath();
      cx.moveTo(x1, y1 + c); cx.lineTo(x1, y1); cx.lineTo(x1 + c, y1);
      cx.moveTo(x1 + w - c, y1 + h); cx.lineTo(x1 + w, y1 + h); cx.lineTo(x1 + w, y1 + h - c); cx.stroke();
      var lab = "#" + tr.id + " " + (tr.cls || "").replace(/_/g, " ");
      if (/pothole/i.test(tr.cls)) lab += "  " + Math.round(distM(tr.box[3], mh)) + " m";
      var fs = 12 * DPR; cx.font = "700 " + fs + "px JetBrains Mono,monospace";
      var tw = cx.measureText(lab).width + 12 * DPR, ly = y1 - fs - 8 > 0 ? y1 - fs - 8 : y1 + h;
      cx.fillStyle = "rgba(25,26,40,.8)"; cx.fillRect(x1, ly, tw, fs + 8);
      cx.fillStyle = col; cx.fillText(lab, x1 + 6 * DPR, ly + fs + 1);
    });
    var sy = py + ((t / 18) % mh) * k, gr = cx.createLinearGradient(0, sy - 40 * DPR, 0, sy);
    gr.addColorStop(0, "rgba(129,178,154,0)"); gr.addColorStop(1, "rgba(129,178,154,.18)");
    cx.fillStyle = gr; cx.fillRect(px, sy - 40 * DPR, mw * k, 40 * DPR);
  }
  requestAnimationFrame(frame);

  // ---------- control
  function setLive(on, txt) { $("chipLive").classList.toggle("live", on); $("liveTxt").textContent = txt || (on ? "LIVE" : "STANDBY"); }
  function msg(t) { $("msg").textContent = t || ""; }
  function reset() { seen = {}; sevSeen = {}; crackSeen = {}; raw = 0; risk = []; beeped = {}; last = null; shown = null; sentQ = []; inflight = 0; near = null; }
  function begin() {
    reset(); ctx();
    return connect().then(function () { running = true; setLive(true); $("start").classList.add("off"); pump(); });
  }
  $("btnDemo").onclick = function () {
    ctx(); beep(660, 0.12); msg("Loading demo drive...");
    vid.srcObject = null; vid.src = "assets/demo_drive.mp4"; vid.loop = true; vid.playbackRate = 0.6;
    vid.play().then(begin).catch(function (e) { msg("Could not start: " + e.message); });
  };
  $("btnCam").onclick = function () {
    ctx(); msg("Starting camera...");
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false })
      .then(function (st) { vid.removeAttribute("src"); vid.srcObject = st; return vid.play(); })
      .then(begin).catch(function (e) { msg("Camera unavailable: " + e.message); });
  };
  $("fsBtn").onclick = function () {
    if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(function () {});
  };
  addEventListener("keydown", function (e) {
    if (e.key === "Escape" && document.fullscreenElement) document.exitFullscreen();
  });
})();
