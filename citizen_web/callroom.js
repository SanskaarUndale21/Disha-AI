/* Disha AI call room: in-browser voice call with the road assistant.
   Standalone. Usage: DishaCall.open() / DishaCall.close() */
(function () {
  "use strict";
  if (window.DishaCall) return;

  /* ---------- storage + config ---------- */
  var mem = {};
  function lsGet(k, d) { try { var v = localStorage.getItem(k); return v == null ? (k in mem ? mem[k] : d) : v; } catch (e) { return k in mem ? mem[k] : d; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { mem[k] = v; } }
  function apiBase() {
    var b = window.RW_API_BASE || lsGet("rw-api", "") || (location.protocol + "//" + location.hostname + ":8000");
    return String(b).replace(/\/+$/, "");
  }
  function deviceId() {
    var d = lsGet("rw-device", "");
    if (!d) { d = "web-" + Math.random().toString(36).slice(2, 12) + Date.now().toString(36); lsSet("rw-device", d); }
    return d;
  }

  var LANGS = [
    { code: "en", label: "English", native: "English", sr: "en-IN" },
    { code: "hi", label: "Hindi", native: "हिन्दी", sr: "hi-IN" },
    { code: "kn", label: "Kannada", native: "ಕನ್ನಡ", sr: "kn-IN" },
    { code: "mr", label: "Marathi", native: "मराठी", sr: "mr-IN" }
  ];
  function langOf(c) { for (var i = 0; i < LANGS.length; i++) if (LANGS[i].code === c) return LANGS[i]; return LANGS[0]; }

  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var synth = window.speechSynthesis;
  var reduceMotion = false;
  try { reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}

  var COLORS = { sage: "129,178,154", peach: "242,204,143", ivory: "244,241,222", danger: "224,122,95" };
  var ICON = {
    mic: '<svg viewBox="0 0 24 24"><path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3"/></svg>',
    micoff: '<svg viewBox="0 0 24 24"><path d="M15 9.3V6a3 3 0 0 0-5.9-.8M9 9v3a3 3 0 0 0 4.7 2.5M19 11a7 7 0 0 1-1.1 3.8M5 11a7 7 0 0 0 10.2 6.2M12 18v3M3 3l18 18"/></svg>',
    cam: '<svg viewBox="0 0 24 24"><path d="M3 8.5A2.5 2.5 0 0 1 5.5 6h8A2.5 2.5 0 0 1 16 8.5v7a2.5 2.5 0 0 1-2.5 2.5h-8A2.5 2.5 0 0 1 3 15.5v-7ZM16 10.5l5-3v9l-5-3"/></svg>',
    camoff: '<svg viewBox="0 0 24 24"><path d="M16 10.5l5-3v9l-3.2-1.9M16 15.5a2.5 2.5 0 0 1-2.5 2.5h-8A2.5 2.5 0 0 1 3 15.5v-7A2.5 2.5 0 0 1 5.5 6H9M3 3l18 18"/></svg>',
    flip: '<svg viewBox="0 0 24 24"><path d="M4 8h12l-3-3M20 16H8l3 3"/></svg>',
    end: '<svg viewBox="0 0 24 24"><path d="M3.5 14.6c4.7-4.2 12.3-4.2 17 0l-1.6 2.7-3-1.2.2-2.6c-2.2-.7-4.6-.7-6.8 0l.2 2.6-3 1.2-1-2.7Z"/></svg>',
    pin: '<svg viewBox="0 0 24 24"><path d="M12 21s7-6.2 7-11.5a7 7 0 0 0-14 0C5 14.8 12 21 12 21Z"/><circle cx="12" cy="9.5" r="2.5"/></svg>',
    gallery: '<svg viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="m4 17 5-4.5 4 3.5 3-2.5 4 3.5"/></svg>',
    clip: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3" fill="currentColor"/></svg>',
    send: '<svg viewBox="0 0 24 24"><path d="M4 12h15M13 6l6 6-6 6"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    x: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    vid: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7L8 5Z"/></svg>'
  };
  function ic(n) { return '<span class="dc-ic" aria-hidden="true">' + ICON[n] + "</span>"; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }

  /* ---------- the call ---------- */
  var S = null; // state of the open call, null when closed

  function el(sel) { return S.root.querySelector(sel); }
  function on(node, ev, fn) { node.addEventListener(ev, fn); S.unbind.push(function () { node.removeEventListener(ev, fn); }); }
  function later(fn, ms) { var id = setTimeout(function () { if (S) fn(); }, ms); S.timers.push(id); return id; }

  function open() {
    if (S) return;
    S = {
      lang: lsGet("rw-call-lang", "en"), state: "lobby", expect: "none", sid: null, fields: {}, stage: "",
      timers: [], unbind: [], media: [], mseq: 0, facing: "environment", muted: false, camOn: false, camDenied: false,
      micDenied: false, micStream: null, camStream: null, ac: null, analyser: null, level: 0, target: 0,
      recog: null, srFail: 0, speaking: false, busy: false, gen: 0, startedAt: 0, ticket: null, pos: null,
      raf: 0, rot: 0, prevOverflow: "", filing: null, rec: null, lastFocus: document.activeElement
    };
    if (!langOf(S.lang)) S.lang = "en";
    build();
    S.prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    try { if (synth) { synth.getVoices(); } } catch (e) {}
    on(document, "keydown", function (e) { if (e.key === "Escape") { e.preventDefault(); close(); } });
    var loop = function (ts) { if (!S) return; S.raf = requestAnimationFrame(loop); drawOrb(ts / 1000); };
    S.raf = requestAnimationFrame(loop);
    setState("lobby");
  }

  function close() {
    if (!S) return;
    var s = S; S = null;
    s.gen++;
    try { cancelAnimationFrame(s.raf); } catch (e) {}
    s.timers.forEach(clearTimeout);
    try { if (s.timerIv) clearInterval(s.timerIv); } catch (e) {}
    s.unbind.forEach(function (f) { try { f(); } catch (e) {} });
    try { if (s.recog) { s.recog.onend = s.recog.onresult = s.recog.onerror = null; s.recog.abort(); } } catch (e) {}
    try { if (synth) synth.cancel(); } catch (e) {}
    try { if (s.rec && s.rec.state !== "inactive") { s.rec.onstop = null; s.rec.stop(); } } catch (e) {}
    [s.micStream, s.camStream].forEach(function (st) { if (st) try { st.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {} });
    try { if (s.ac) s.ac.close(); } catch (e) {}
    s.media.forEach(function (m) { try { URL.revokeObjectURL(m.url); } catch (e) {} });
    try { s.root.remove(); } catch (e) {}
    document.body.style.overflow = s.prevOverflow;
    try { if (s.lastFocus && s.lastFocus.focus) s.lastFocus.focus(); } catch (e) {}
  }

  /* ---------- DOM ---------- */
  function build() {
    var root = document.createElement("div");
    root.className = "dc-root";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", "Voice call with Disha");
    var langs = LANGS.map(function (l) {
      return '<button type="button" class="dc-lang" role="radio" data-lang="' + l.code + '" aria-checked="' + (l.code === S.lang) + '"><b>' + esc(l.native) + "</b><i>" + esc(l.label) + "</i></button>";
    }).join("");
    root.innerHTML =
      '<div class="dc-bg"></div>' +
      '<header class="dc-top"><div class="dc-brand"><span class="dc-dot"></span>DISHA AI</div>' +
      '<div class="dc-chips"><span class="dc-chip dc-timer" aria-label="Call time">00:00</span>' +
      '<span class="dc-chip dc-loc" hidden>' + ic("pin") + '<span class="dc-loc-t">LOCATING</span></span></div></header>' +
      '<main class="dc-stage">' +
      '<video class="dc-video" playsinline muted autoplay></video>' +
      '<div class="dc-scan" aria-hidden="true"><i class="dc-c1"></i><i class="dc-c2"></i><i class="dc-c3"></i><i class="dc-c4"></i><b class="dc-sweep"></b></div>' +
      '<div class="dc-orbwrap"><canvas class="dc-orb" aria-hidden="true"></canvas></div>' +
      '<div class="dc-thumbs" aria-live="polite"></div>' +
      '<div class="dc-state" aria-hidden="true">READY</div>' +
      '<div class="dc-notice" role="status" hidden></div>' +
      '<section class="dc-result" hidden></section>' +
      "</main>" +
      '<section class="dc-lobby"><div class="dc-lobby-in">' +
      '<div class="dc-lobby-orb" aria-hidden="true"></div>' +
      '<h2 class="dc-h">Talk to Disha</h2>' +
      '<p class="dc-p">Describe the road problem out loud and show it on camera. Disha files the complaint for you.</p>' +
      '<div class="dc-langs" role="radiogroup" aria-label="Language">' + langs + "</div>" +
      '<button type="button" class="dc-go">' + ic("mic") + 'Start call</button>' +
      '<p class="dc-fine">Uses your microphone, camera and location during the call.</p>' +
      '<button type="button" class="dc-x" aria-label="Close">' + ic("x") + "</button>" +
      "</div></section>" +
      '<section class="dc-dock">' +
      '<div class="dc-caps" aria-live="polite"><p class="dc-say"></p><p class="dc-you"></p></div>' +
      '<div class="dc-camtools" hidden>' +
      '<button type="button" class="dc-tool dc-gal">' + ic("gallery") + '<span>Gallery</span></button>' +
      '<button type="button" class="dc-shutter" aria-label="Take photo"><i></i></button>' +
      '<button type="button" class="dc-tool dc-clip">' + ic("clip") + '<span>5s clip</span></button>' +
      "</div>" +
      '<div class="dc-sugs"></div>' +
      '<form class="dc-form" autocomplete="off"><input class="dc-input" type="text" inputmode="text" aria-label="Type to Disha" placeholder="Type your reply" maxlength="300"><button type="submit" class="dc-send" aria-label="Send">' + ic("send") + "</button></form>" +
      '<div class="dc-ctrl">' +
      '<button type="button" class="dc-btn dc-mute" aria-pressed="false" aria-label="Mute microphone">' + ic("mic") + "</button>" +
      '<button type="button" class="dc-btn dc-camb" aria-pressed="false" aria-label="Camera">' + ic("camoff") + "</button>" +
      '<button type="button" class="dc-btn dc-flip" aria-label="Flip camera" hidden>' + ic("flip") + "</button>" +
      '<button type="button" class="dc-btn dc-end" aria-label="End call">' + ic("end") + "</button>" +
      "</div></section>" +
      '<input type="file" class="dc-file" accept="image/*,video/*" multiple hidden>';
    document.body.appendChild(root);
    S.root = root;

    on(el(".dc-x"), "click", close);
    on(el(".dc-end"), "click", close);
    on(el(".dc-go"), "click", startCall);
    root.querySelectorAll(".dc-lang").forEach(function (b) {
      on(b, "click", function () {
        S.lang = b.getAttribute("data-lang"); lsSet("rw-call-lang", S.lang);
        root.querySelectorAll(".dc-lang").forEach(function (o) { o.setAttribute("aria-checked", String(o === b)); });
      });
    });
    on(el(".dc-form"), "submit", function (e) {
      e.preventDefault();
      var inp = el(".dc-input"), v = inp.value.trim();
      if (!v || !S.sid) return;
      inp.value = ""; userSays(v);
    });
    on(el(".dc-mute"), "click", toggleMute);
    on(el(".dc-camb"), "click", function () { if (S.camOn) stopCam(); else startCam(); });
    on(el(".dc-flip"), "click", function () { S.facing = S.facing === "environment" ? "user" : "environment"; startCam(); });
    on(el(".dc-shutter"), "click", snap);
    on(el(".dc-clip"), "click", recordClip);
    on(el(".dc-gal"), "click", function () { el(".dc-file").click(); });
    on(el(".dc-file"), "change", function (e) {
      var fl = Array.prototype.slice.call(e.target.files || []); e.target.value = "";
      fl.slice(0, 4).forEach(ingest);
    });
    on(el(".dc-sugs"), "click", function (e) {
      var b = e.target.closest ? e.target.closest(".dc-sug") : null;
      if (b) userSays(b.getAttribute("data-t"));
    });
    var wrap = el(".dc-orbwrap");
    if (window.ResizeObserver) { var ro = new ResizeObserver(sizeCanvas); ro.observe(wrap); S.unbind.push(function () { ro.disconnect(); }); }
    else on(window, "resize", sizeCanvas);
    sizeCanvas();
    try { el(".dc-go").focus(); } catch (e) {}
  }

  var STATE_LABEL = { lobby: "READY", connecting: "CONNECTING", listening: "LISTENING", typing: "YOUR TURN", thinking: "THINKING", speaking: "SPEAKING", camera: "SCANNING ROAD", filing: "FILING COMPLAINT", finished: "CALL COMPLETE" };

  function setState(st) {
    if (!S) return;
    S.state = st;
    var label = st === "listening" && (!SR || S.micDenied || S.muted || S.srBroken) ? STATE_LABEL.typing : STATE_LABEL[st];
    S.root.setAttribute("data-state", st);
    el(".dc-state").textContent = label;
    var cam = S.camOn;
    S.root.classList.toggle("dc-cam", cam);
    S.root.setAttribute("data-expect", S.expect);
    el(".dc-camtools").hidden = !(S.expect === "camera" && st !== "finished" && st !== "filing" && st !== "lobby");
    sizeCanvas();
  }

  function notice(msg) {
    if (!S) return;
    var n = el(".dc-notice");
    n.textContent = msg || ""; n.hidden = !msg;
  }

  /* ---------- network ---------- */
  function jfetch(path, body, timeout) {
    var ctl = window.AbortController ? new AbortController() : null;
    var to = ctl ? setTimeout(function () { ctl.abort(); }, timeout || 30000) : 0;
    return fetch(apiBase() + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctl ? ctl.signal : undefined })
      .then(function (r) {
        clearTimeout(to);
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (!r.ok) { var e = new Error((j && (j.detail || j.message)) || ("Request failed (" + r.status + ")")); e.status = r.status; throw e; }
          return j;
        });
      }, function (e) { clearTimeout(to); var x = new Error("No connection to the server."); x.status = 0; throw x; });
  }

  /* ---------- call flow ---------- */
  function getPosition() {
    return new Promise(function (res) {
      if (!navigator.geolocation) return res(null);
      var done = false, t = setTimeout(function () { if (!done) { done = true; res(null); } }, 11000);
      navigator.geolocation.getCurrentPosition(function (p) { if (!done) { done = true; clearTimeout(t); res(p.coords); } },
        function () { if (!done) { done = true; clearTimeout(t); res(null); } }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
    });
  }

  function startMic() {
    if (!SR || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return Promise.resolve();
    return navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }).then(function (st) {
      if (!S) { st.getTracks().forEach(function (t) { t.stop(); }); return; }
      S.micStream = st;
      try {
        var AC = window.AudioContext || window.webkitAudioContext;
        S.ac = new AC(); var src = S.ac.createMediaStreamSource(st);
        S.analyser = S.ac.createAnalyser(); S.analyser.fftSize = 512; src.connect(S.analyser);
        S.buf = new Uint8Array(S.analyser.fftSize);
      } catch (e) {}
    }, function () { if (S) { S.micDenied = true; } });
  }

  function startCall() {
    if (S.state !== "lobby") return;
    S.root.classList.add("dc-live");
    setState("connecting");
    el(".dc-say").textContent = "Connecting to Disha...";
    el(".dc-loc").hidden = false;
    S.startedAt = Date.now();
    S.timerIv = setInterval(tickTimer, 1000);
    if (!SR) notice("Voice input is not supported in this browser. Use Chrome or Edge to talk, or type and tap the suggestions below.");
    Promise.all([getPosition(), startMic()]).then(function (r) {
      if (!S) return;
      var c = r[0];
      if (c) { S.pos = { lat: c.latitude, lon: c.longitude }; }
      else { el(".dc-loc-t").textContent = "LOCATION OFF"; }
      if (S.micDenied) notice("Microphone is blocked. Allow it in your browser settings to talk, or type and tap the suggestions.");
      beginSession();
    });
  }

  function beginSession() {
    var body = { lang: S.lang, lat: S.pos ? S.pos.lat : null, lon: S.pos ? S.pos.lon : null, device_id: deviceId() };
    jfetch("/api/call/start", body, 25000).then(function (r) {
      if (!S) return;
      S.sid = r.session_id;
      handle(r);
    }, function (e) {
      if (!S) return;
      setState("lobby"); S.root.classList.remove("dc-live");
      try { clearInterval(S.timerIv); } catch (x) {}
      notice((e.status === 0 ? "Could not reach the Disha server. Check your connection and try again." : e.message) );
      el(".dc-go").lastChild.textContent = "Try again";
    });
  }

  function tickTimer() {
    if (!S) return;
    var s = Math.floor((Date.now() - S.startedAt) / 1000);
    el(".dc-timer").textContent = ("0" + Math.floor(s / 60)).slice(-2) + ":" + ("0" + (s % 60)).slice(-2);
  }

  function userSays(text, hidden) {
    if (!S || !S.sid || S.busy) return;
    stopListening(); cancelSpeech();
    if (!hidden) { el(".dc-you").textContent = text; }
    S.busy = true; setState("thinking");
    var g = ++S.gen;
    jfetch("/api/call/turn", { session_id: S.sid, text: text }, 30000).then(function (r) {
      if (!S || g !== S.gen) return;
      S.busy = false; handle(r);
    }, function (e) {
      if (!S || g !== S.gen) return;
      S.busy = false;
      if (e.status === 404) { notice("This call has ended. Close and start a new one."); setState("finished"); showResult({ lost: true }); return; }
      notice(e.status === 0 ? "Connection lost. Try again." : e.message);
      later(function () { notice(""); }, 4000);
      afterSpeech();
    });
  }

  function handle(r) {
    S.fields = r.fields || {}; S.expect = r.expect || "none"; S.stage = r.stage || "";
    S.done = !!r.done;
    paintLoc();
    paintSugs(r.suggest || []);
    el(".dc-say").textContent = r.say || "";
    el(".dc-you").textContent = "";
    if (S.expect === "camera" && !S.camOn && !S.camDenied) startCam();
    if (r.done && r.stage === "done" && S.fields.category) S.filing = fileComplaint();
    speak(r.say || "", afterSpeech);
  }

  function afterSpeech() {
    if (!S) return;
    if (S.done) {
      if (S.stage === "done" && S.filing) {
        setState("filing");
        S.filing.then(function (res) { if (S) showResult(res); });
      } else { setState("finished"); showResult({ cancelled: true }); }
      return;
    }
    if (S.expect === "camera") setState("camera"); else setState("listening");
    listen();
  }

  function paintLoc() {
    var f = S.fields, t = el(".dc-loc-t");
    if (f.place) t.textContent = String(f.place).split(",").slice(0, 2).join(",").toUpperCase();
    else if (S.pos) t.textContent = "GPS " + S.pos.lat.toFixed(3) + ", " + S.pos.lon.toFixed(3);
    el(".dc-loc").title = f.place || "";
  }

  function paintSugs(list) {
    el(".dc-sugs").innerHTML = list.map(function (s) { return '<button type="button" class="dc-sug" data-t="' + esc(s) + '">' + esc(s) + "</button>"; }).join("");
  }

  /* ---------- speech out ---------- */
  var voiceCache = {};
  function pickVoice(code) {
    if (voiceCache[code]) return voiceCache[code];
    var vs = [];
    try { vs = synth ? synth.getVoices() : []; } catch (e) {}
    var l = langOf(code), pre = l.code, best = null, bs = -1;
    vs.forEach(function (v) {
      var vl = (v.lang || "").replace("_", "-").toLowerCase(), sc = 0;
      if (vl === l.sr.toLowerCase()) sc += 10; else if (vl.indexOf(pre) === 0) sc += 6; else return;
      if (/female|woman|heera|zira|samantha|neerja|swara|lekha|veena|kalpana|aditi|priya|sapna|shruti|google/i.test(v.name)) sc += 4;
      if (/male$|\bmale\b|hemant|ravi|prabhat|madhur/i.test(v.name) && !/female/i.test(v.name)) sc -= 3;
      if (/natural|online/i.test(v.name)) sc += 2;
      if (sc > bs) { bs = sc; best = v; }
    });
    if (best && vs.length) voiceCache[code] = best;
    return best;
  }
  if (synth && synth.addEventListener) { try { synth.addEventListener("voiceschanged", function () { voiceCache = {}; }); } catch (e) {} }

  function cancelSpeech() { try { if (synth) synth.cancel(); } catch (e) {} if (S) { S.speaking = false; S.speakDone = null; } }

  function speak(text, cb) {
    stopListening(); cancelSpeech();
    if (!text) return cb();
    setState("speaking"); S.speaking = true;
    var fin = false, my = ++S.gen;
    var finish = function () { if (fin) return; fin = true; if (!S || my !== S.gen) return; S.speaking = false; cb(); };
    S.speakDone = finish;
    var ms = Math.max(1800, text.length * 85) + 3500;
    later(finish, ms);
    try {
      if (!synth || !window.SpeechSynthesisUtterance) { later(finish, Math.min(ms, text.length * 40 + 600)); return; }
      var u = new SpeechSynthesisUtterance(text), v = pickVoice(S.lang);
      u.lang = langOf(S.lang).sr; if (v) { u.voice = v; u.lang = v.lang; }
      u.rate = 0.95; u.pitch = 1.05;
      u.onend = finish; u.onerror = finish;
      S.utter = u;
      synth.speak(u);
    } catch (e) { later(finish, 800); }
  }

  /* ---------- speech in ---------- */
  function listen() {
    if (!S || !SR || S.micDenied || S.muted || S.srBroken) { setState(S.state); return; }
    if (S.state !== "listening" && S.state !== "camera") return;
    if (S.recog) return;
    var rc;
    try { rc = new SR(); } catch (e) { S.srBroken = true; setState(S.state); return; }
    rc.lang = langOf(S.lang).sr; rc.continuous = false; rc.interimResults = true; rc.maxAlternatives = 1;
    var got = false, my = S.gen;
    rc.onresult = function (e) {
      if (!S || my !== S.gen) return;
      var interim = "", fin = "";
      for (var i = e.resultIndex; i < e.results.length; i++) {
        var t = e.results[i][0].transcript;
        if (e.results[i].isFinal) fin += t; else interim += t;
      }
      S.srFail = 0;
      if (fin.trim()) { got = true; userSays(fin.trim()); }
      else if (interim) { el(".dc-you").textContent = interim; }
    };
    rc.onerror = function (e) {
      if (!S) return;
      var er = e && e.error;
      if (er === "not-allowed" || er === "service-not-allowed") { S.micDenied = true; notice("Microphone is blocked. Allow it in your browser settings, or type and tap the suggestions."); setState(S.state); }
      else if (er === "network" || er === "audio-capture") { S.srFail++; if (S.srFail >= 3) { S.srBroken = true; notice("Voice recognition is not available right now. Type or tap a suggestion."); setState(S.state); } }
    };
    rc.onend = function () {
      if (!S) return;
      if (S.recog === rc) S.recog = null;
      if (!got && !S.busy && !S.speaking && (S.state === "listening" || S.state === "camera") && !S.muted && !S.micDenied && !S.srBroken) later(listen, 350);
    };
    S.recog = rc;
    try { rc.start(); } catch (e) { S.recog = null; later(listen, 800); }
  }

  function stopListening() {
    if (!S || !S.recog) return;
    var rc = S.recog; S.recog = null;
    try { rc.onend = rc.onresult = rc.onerror = null; rc.abort(); } catch (e) {}
  }

  function toggleMute() {
    S.muted = !S.muted;
    var b = el(".dc-mute");
    b.setAttribute("aria-pressed", String(S.muted));
    b.classList.toggle("is-off", S.muted);
    b.innerHTML = ic(S.muted ? "micoff" : "mic");
    if (S.micStream) S.micStream.getTracks().forEach(function (t) { t.enabled = !S.muted; });
    if (S.muted) stopListening(); else if (S.state === "listening" || S.state === "camera") listen();
    setState(S.state);
  }

  /* ---------- camera ---------- */
  function startCam() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { S.camDenied = true; notice("Camera is not available here. Use Gallery to add a photo."); return; }
    if (S.camStream) { S.camStream.getTracks().forEach(function (t) { t.stop(); }); S.camStream = null; }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: S.facing }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false }).then(function (st) {
      if (!S) { st.getTracks().forEach(function (t) { t.stop(); }); return; }
      S.camStream = st; S.camOn = true;
      var v = el(".dc-video"); v.srcObject = st; var p = v.play(); if (p && p.catch) p.catch(function () {});
      var b = el(".dc-camb"); b.setAttribute("aria-pressed", "true"); b.classList.add("is-on"); b.innerHTML = ic("cam");
      v.classList.toggle("dc-mirror", S.facing === "user");
      if (navigator.mediaDevices.enumerateDevices) navigator.mediaDevices.enumerateDevices().then(function (ds) {
        if (S) el(".dc-flip").hidden = ds.filter(function (d) { return d.kind === "videoinput"; }).length < 2;
      }, function () {});
      setState(S.state);
    }, function () {
      if (!S) return;
      S.camDenied = true; S.camOn = false;
      notice("Camera is blocked. Allow it in your browser settings, or use Gallery to add a photo.");
      setState(S.state);
    });
  }

  function stopCam() {
    if (S.camStream) S.camStream.getTracks().forEach(function (t) { t.stop(); });
    S.camStream = null; S.camOn = false; S.camDenied = false;
    var v = el(".dc-video"); v.srcObject = null;
    var b = el(".dc-camb"); b.setAttribute("aria-pressed", "false"); b.classList.remove("is-on"); b.innerHTML = ic("camoff");
    el(".dc-flip").hidden = true;
    setState(S.state);
  }

  function snap() {
    var v = el(".dc-video");
    if (!S.camOn || !v.videoWidth) { el(".dc-file").click(); return; }
    var c = document.createElement("canvas"); c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    var fl = el(".dc-stage"); fl.classList.add("dc-flash"); later(function () { fl.classList.remove("dc-flash"); }, 220);
    c.toBlob(function (b) { if (b && S) ingest(new File([b], "disha-" + Date.now() + ".jpg", { type: "image/jpeg" })); }, "image/jpeg", 0.9);
  }

  function recordClip() {
    if (!S.camOn || !S.camStream || !window.MediaRecorder) { notice(window.MediaRecorder ? "Turn the camera on to record a clip." : "Clip recording is not supported here. Take a photo instead."); later(function () { notice(""); }, 3500); return; }
    if (S.rec && S.rec.state === "recording") return;
    var mt = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm", "video/mp4"].filter(function (m) { try { return MediaRecorder.isTypeSupported(m); } catch (e) { return false; } })[0];
    var chunks = [], rec;
    try { rec = new MediaRecorder(S.camStream, mt ? { mimeType: mt } : undefined); } catch (e) { notice("Clip recording failed. Take a photo instead."); return; }
    S.rec = rec;
    rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
    var btn = el(".dc-clip"), n = 5;
    btn.classList.add("is-rec"); btn.querySelector("span").textContent = "REC " + n + "s";
    var iv = setInterval(function () { if (!S) return clearInterval(iv); n--; btn.querySelector("span").textContent = "REC " + Math.max(n, 0) + "s"; }, 1000);
    S.timers.push(iv);
    rec.onstop = function () {
      clearInterval(iv);
      if (!S) return;
      btn.classList.remove("is-rec"); btn.querySelector("span").textContent = "5s clip";
      var type = (rec.mimeType || mt || "video/webm").split(";")[0];
      var blob = new Blob(chunks, { type: type });
      if (blob.size) ingest(new File([blob], "disha-clip-" + Date.now() + (type.indexOf("mp4") >= 0 ? ".mp4" : ".webm"), { type: type }));
    };
    rec.start();
    later(function () { try { if (rec.state === "recording") rec.stop(); } catch (e) {} }, 5000);
  }

  /* ---------- media check ---------- */
  function ingest(file) {
    if (!S || !S.sid) return;
    var isVid = /^video\//.test(file.type || "");
    var it = { id: ++S.mseq, file: file, url: URL.createObjectURL(file), video: isVid, state: "checking", token: "", label: "CHECKING" };
    S.media.push(it); paintThumbs();
    var fd = new FormData(); fd.append("file", file, file.name); fd.append("device_id", deviceId());
    var ctl = window.AbortController ? new AbortController() : null;
    var to = setTimeout(function () { if (ctl) ctl.abort(); }, 150000);
    fetch(apiBase() + "/api/screening/check", { method: "POST", body: fd, signal: ctl ? ctl.signal : undefined }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error("check failed"); return j; });
    }).then(function (j) {
      clearTimeout(to); if (!S) return;
      var pass = j.verdict === "pass";
      it.state = pass ? "pass" : "fail"; it.token = pass && j.token ? j.token : "";
      var top = (j.damage || [])[0];
      it.label = pass ? (top && top["class"] ? String(top["class"]).replace(/_/g, " ").toUpperCase() : "ROAD DAMAGE") : "NO DAMAGE SEEN";
      paintThumbs(); reportMedia(pass);
    }, function () {
      clearTimeout(to); if (!S) return;
      it.state = "unchecked"; it.label = "NOT CHECKED";
      paintThumbs(); reportMedia(true);
    });
  }

  function reportMedia(pass) {
    if (!S || S.expect !== "camera" || S.busy) return;
    userSays("__media__:" + S.media.length + ":" + (pass ? "pass" : "fail"), true);
  }

  function paintThumbs() {
    el(".dc-thumbs").innerHTML = S.media.slice(-4).map(function (m) {
      var body = m.video ? '<video src="' + m.url + '" muted playsinline></video>' : '<img alt="Captured road photo" src="' + m.url + '">';
      return '<figure class="dc-thumb is-' + m.state + '">' + body + '<figcaption>' + (m.state === "checking" ? '<span class="dc-spin"></span>' : m.state === "pass" ? ic("check") : "") + esc(m.label) + "</figcaption></figure>";
    }).join("");
  }

  /* ---------- filing ---------- */
  function fileComplaint() {
    var f = S.fields, cat = f.category === "manhole" ? "other" : f.category;
    var good = S.media.filter(function (m) { return m.state === "pass" || m.state === "unchecked"; });
    var addr = f.address || f.place || "";
    var run = function () {
      var fd = new FormData();
      fd.append("category", cat);
      fd.append("description", f.description || "Road problem reported by voice call");
      if (f.name) fd.append("citizen_name", f.name);
      fd.append("device_id", deviceId());
      if (f.lat != null) fd.append("lat", f.lat);
      if (f.lon != null) fd.append("lon", f.lon);
      if (addr) fd.append("address", addr);
      good.forEach(function (m) { fd.append("files", m.file, m.file.name); });
      var toks = good.map(function (m) { return m.token; }).filter(Boolean);
      if (toks.length) fd.append("screening_tokens", toks.join(","));
      return fetch(apiBase() + "/api/complaints", { method: "POST", body: fd }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (!r.ok) throw new Error((j && (j.detail || j.message)) || ("Could not file (" + r.status + ")"));
          return { ticket: j.ticket || j.ticket_number || j.id, category: cat, place: addr };
        });
      });
    };
    S.refile = run;
    return run().then(function (x) { return x; }, function (e) { return { error: e && e.message ? e.message : "Could not file the complaint." }; });
  }

  function showResult(res) {
    if (!S) return;
    setState("finished");
    stopListening();
    var box = el(".dc-result"); box.hidden = false;
    var h;
    if (res.ticket) {
      h = '<div class="dc-card"><div class="dc-seal">' + ic("check") + '</div><h3>Complaint filed</h3><p>Thank you. Disha has sent it to the road team.</p>' +
        '<div class="dc-ticket"><span>TICKET</span><b>' + esc(res.ticket) + "</b></div>" +
        (res.place ? '<p class="dc-sm">' + esc(res.place) + "</p>" : "") +
        '<button type="button" class="dc-go dc-done">Done</button></div>';
    } else if (res.error) {
      h = '<div class="dc-card is-err"><div class="dc-seal">' + ic("x") + '</div><h3>Could not file it</h3><p>' + esc(res.error) + '</p><button type="button" class="dc-go dc-retry">Try again</button><button type="button" class="dc-link dc-done">Close</button></div>';
    } else if (res.lost) {
      h = '<div class="dc-card is-err"><div class="dc-seal">' + ic("x") + '</div><h3>Call ended</h3><p>The session expired. Start a new call.</p><button type="button" class="dc-go dc-done">Close</button></div>';
    } else {
      h = '<div class="dc-card"><div class="dc-seal is-mute">' + ic("x") + '</div><h3>No complaint filed</h3><p>Nothing was registered. You can call Disha again any time.</p><button type="button" class="dc-go dc-done">Done</button></div>';
    }
    box.innerHTML = h;
    var d = box.querySelector(".dc-done"); if (d) { on(d, "click", close); try { d.focus(); } catch (e) {} }
    var rt = box.querySelector(".dc-retry");
    if (rt) on(rt, "click", function () {
      setState("filing"); box.hidden = true;
      S.refile().then(function (x) { if (S) showResult(x); }, function (e) { if (S) showResult({ error: e.message }); });
    });
  }

  /* ---------- orb canvas ---------- */
  function sizeCanvas() {
    if (!S) return;
    var c = el(".dc-orb"), r = c.parentNode.getBoundingClientRect(), d = Math.min(window.devicePixelRatio || 1, 2);
    var w = Math.max(40, Math.round(r.width * d)), h = Math.max(40, Math.round(r.height * d));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    S.cw = w; S.ch = h;
  }

  function userLevel() {
    if (!S.analyser || !S.buf) return 0;
    S.analyser.getByteTimeDomainData(S.buf);
    var sum = 0; for (var i = 0; i < S.buf.length; i++) { var v = (S.buf[i] - 128) / 128; sum += v * v; }
    return Math.min(1, Math.sqrt(sum / S.buf.length) * 4.5);
  }

  function drawOrb(t) {
    if (!S) return;
    var c = el(".dc-orb"), ctx = c.getContext("2d"), w = S.cw || c.width, h = S.ch || c.height;
    if (!ctx) return;
    var st = S.state, ts = reduceMotion ? 0 : t;
    var accent = (st === "speaking" || st === "filing") ? COLORS.peach : COLORS.sage;
    var tgt;
    if (st === "speaking") tgt = 0.3 + 0.45 * Math.abs(Math.sin(ts * 7.3)) * (0.55 + 0.45 * Math.abs(Math.sin(ts * 2.1 + 1)));
    else if (st === "listening" || st === "camera") tgt = Math.max(0.1, userLevel() * (S.muted ? 0 : 1)) + (S.analyser ? 0 : 0.1 + 0.06 * Math.sin(ts * 2));
    else if (st === "thinking" || st === "filing" || st === "connecting") tgt = 0.16 + 0.1 * Math.sin(ts * 4);
    else tgt = 0.12 + 0.05 * Math.sin(ts * 1.4);
    if (reduceMotion) tgt = 0.22;
    S.level += (tgt - S.level) * 0.22;
    var L = S.level;

    ctx.clearRect(0, 0, w, h);
    var cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 2, lw = Math.max(1, R * 0.008);
    // glow
    var g = ctx.createRadialGradient(cx, cy, R * 0.05, cx, cy, R);
    g.addColorStop(0, "rgba(" + accent + "," + (0.2 + L * 0.3) + ")");
    g.addColorStop(0.55, "rgba(" + accent + "," + (0.06 + L * 0.06) + ")");
    g.addColorStop(1, "rgba(" + accent + ",0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R, 0, 6.2832); ctx.fill();
    // concentric rings
    for (var i = 0; i < 5; i++) {
      var rr = R * (0.30 + i * 0.065) + L * R * 0.02 * (i + 1) + Math.sin(ts * 1.3 + i) * R * 0.004;
      ctx.strokeStyle = "rgba(" + COLORS.ivory + "," + (0.20 - i * 0.027) + ")"; ctx.lineWidth = lw;
      ctx.beginPath(); ctx.arc(cx, cy, rr, 0, 6.2832); ctx.stroke();
    }
    // HUD arcs
    var arcs = [[0.64, 1.0, 1.7, 0.9], [0.74, -0.7, 1.1, 1.3], [0.84, 0.45, 0.6, 2.2], [0.92, -0.25, 0.35, 3.1]];
    for (var a = 0; a < arcs.length; a++) {
      var ar = arcs[a], base = ts * ar[1] * 0.6 + ar[3];
      ctx.strokeStyle = "rgba(" + (a % 2 ? COLORS.ivory : accent) + "," + (a % 2 ? 0.22 : 0.5) + ")"; ctx.lineWidth = lw * (a === 0 ? 1.8 : 1);
      ctx.lineCap = "round";
      ctx.beginPath(); ctx.arc(cx, cy, R * ar[0], base, base + ar[2]); ctx.stroke();
      ctx.beginPath(); ctx.arc(cx, cy, R * ar[0], base + 3.4, base + 3.4 + ar[2] * 0.45); ctx.stroke();
    }
    if (st === "thinking" || st === "connecting" || st === "filing") {
      ctx.strokeStyle = "rgba(" + COLORS.peach + ",0.85)"; ctx.lineWidth = lw * 2;
      var sp = ts * 3.2; ctx.beginPath(); ctx.arc(cx, cy, R * 0.54, sp, sp + 1.1); ctx.stroke();
    }
    // tick ring
    ctx.strokeStyle = "rgba(" + COLORS.ivory + ",0.16)"; ctx.lineWidth = lw;
    var tr = ts * 0.12;
    for (var k = 0; k < 72; k++) {
      var an = k / 72 * 6.2832 + tr, long = k % 6 === 0, r1 = R * 0.955, r2 = R * (long ? 0.995 : 0.975);
      ctx.beginPath(); ctx.moveTo(cx + Math.cos(an) * r1, cy + Math.sin(an) * r1); ctx.lineTo(cx + Math.cos(an) * r2, cy + Math.sin(an) * r2); ctx.stroke();
    }
    // radial waveform
    var N = 96, r0 = R * 0.36, rot = ts * 0.25;
    ctx.strokeStyle = "rgba(" + accent + ",0.9)"; ctx.lineWidth = Math.max(1.2, R * 0.014); ctx.lineCap = "round";
    ctx.beginPath();
    for (var n = 0; n < N; n++) {
      var ang = n / N * 6.2832 + rot;
      var nz = (Math.sin(n * 0.7 + ts * 3.1) + Math.sin(n * 1.9 - ts * 2.3) + Math.sin(n * 0.31 + ts) + 3) / 6;
      var len = R * (0.012 + 0.26 * L * (0.25 + 0.75 * nz));
      ctx.moveTo(cx + Math.cos(ang) * r0, cy + Math.sin(ang) * r0);
      ctx.lineTo(cx + Math.cos(ang) * (r0 + len), cy + Math.sin(ang) * (r0 + len));
    }
    ctx.stroke();
    // core
    var cr = r0 * (0.8 + L * 0.12), cg = ctx.createRadialGradient(cx - cr * 0.25, cy - cr * 0.3, cr * 0.1, cx, cy, cr);
    cg.addColorStop(0, "rgba(" + COLORS.ivory + ",0.9)");
    cg.addColorStop(0.35, "rgba(" + accent + ",0.75)");
    cg.addColorStop(1, "rgba(" + accent + ",0.12)");
    ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(cx, cy, cr, 0, 6.2832); ctx.fill();
  }

  window.DishaCall = { open: open, close: close };
})();
