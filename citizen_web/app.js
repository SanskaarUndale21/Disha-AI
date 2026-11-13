/* Disha AI citizen web app. Mirrors the Flutter citizen app screens, with PWA, notifications and an offline queue. */
(function () {
  "use strict";

  /* ================= storage and config ================= */
  var mem = {};
  function lsGet(k, d) { try { var v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return mem[k] != null ? mem[k] : d; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { mem[k] = v; } }
  function lsJson(k, d) { try { var v = JSON.parse(lsGet(k, "")); return v == null ? d : v; } catch (e) { return d; } }
  function lsSetJson(k, v) { lsSet(k, JSON.stringify(v)); }

  var DEFAULT_HELPLINE = "+918064270577";
  var API = (function () {
    var o = lsGet("rw-api", "") || window.RW_API_BASE || "";
    if (o) return o.replace(/\/+$/, "");
    return location.protocol + "//" + location.hostname + ":8000";
  })();
  var device = (function () {
    var d = lsGet("rw-device", "");
    if (!d) { d = "web-" + Math.random().toString(36).slice(2, 12) + Date.now().toString(36); lsSet("rw-device", d); }
    return d;
  })();
  var helpline = lsGet("rw-helpline", DEFAULT_HELPLINE);
  var MAX_FILES = 8;

  var CATS = [
    { key: "pothole", label: "Pothole", hint: "Holes or craters", icon: "hex", color: "orange", photo: "pothole" },
    { key: "crack", label: "Cracks", hint: "Surface cracking", icon: "bolt", color: "yellow", photo: "crack" },
    { key: "waterlogging", label: "Waterlogging", hint: "Flooded stretch", icon: "drop", color: "teal", photo: "waterlogging" },
    { key: "broken_road", label: "Broken road", hint: "Caved or washed out", icon: "warn", color: "red", photo: "broken_road" },
    { key: "other", label: "Other", hint: "Open manhole, debris", icon: "dots", color: "purple", photo: "other" }
  ];
  CATS.forEach(function (c) { Object.defineProperty(c, "label", { get: function () { return T("c_" + c.key); }, enumerable: true }); Object.defineProperty(c, "hint", { get: function () { return T("h_" + c.key); }, enumerable: true }); });
  function catOf(k) { for (var i = 0; i < CATS.length; i++) if (CATS[i].key === k) return CATS[i]; return CATS[4]; }
  var STATUS = {
    submitted: { label: "Submitted", icon: "paper", color: "blue" },
    in_review: { label: "In review", icon: "eye", color: "indigo" },
    in_progress: { label: "Repair underway", icon: "hammer", color: "orange" },
    resolved: { label: "Resolved", icon: "seal", color: "green" },
    rejected: { label: "Closed", icon: "xcircle", color: "red" }
  };
  Object.keys(STATUS).forEach(function (k) { Object.defineProperty(STATUS[k], "label", { get: function () { return T("st_" + k); }, enumerable: true }); });
  var STATUS_ORDER = ["submitted", "in_review", "in_progress", "resolved"];
  function statusOf(s) { return STATUS[s] || STATUS.submitted; }
  var DEFAULT_CLASSES = { longitudinal_crack: "Longitudinal crack", transverse_crack: "Transverse crack", alligator_crack: "Alligator crack", pothole: "Pothole", manhole: "Manhole or drain cover", speed_breaker: "Speed breaker", debris: "Debris or loose gravel", barricade: "Barricade or work zone" };

  /* ================= helpers ================= */
  function $(id) { return document.getElementById(id); }
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function icon(n, cls) { return '<svg class="ic ' + (cls || "") + '" aria-hidden="true"><use href="#i-' + n + '"/></svg>'; }
  function badgeIcon(n, color, size) { return '<span class="iconbadge c-' + color + '" style="--s:' + (size || 40) + 'px">' + icon(n) + "</span>"; }
  function pill(st) { var s = statusOf(st); return '<span class="pill st-' + esc(st in STATUS ? st : "submitted") + '">' + icon(s.icon) + esc(s.label) + "</span>"; }
  function skel(h, extra) { return '<div class="skel" style="height:' + h + "px;" + (extra || "") + '" aria-hidden="true"></div>'; }
  function cap(s) { s = String(s || ""); return s.charAt(0).toUpperCase() + s.slice(1); }
  function nice(s) { return String(s || "").replace(/_/g, " "); }
  function timeAgo(t) {
    var d = t instanceof Date ? t : new Date(t); if (isNaN(d)) return "";
    var s = (Date.now() - d.getTime()) / 1000;
    if (s < 60) return "Just now"; if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago"; if (s < 604800) return Math.floor(s / 86400) + "d ago";
    return d.getDate() + " " + ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getMonth()] + " " + d.getFullYear();
  }
  function prettyPhone(n) {
    var d = String(n).replace(/\D/g, "");
    if (d.length === 12 && d.indexOf("91") === 0) { var l = "0" + d.slice(2); return l.slice(0, 3) + " " + l.slice(3, 7) + " " + l.slice(7); }
    return n;
  }
  function fmtSize(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB"; }
  function url(p) { return !p ? "" : (/^https?:/.test(p) ? p : API + p); }
  function isVideoFile(f) { return (f.type || "").indexOf("video") === 0 || /\.(mp4|mov|avi|mkv|webm|m4v|3gp)$/i.test(f.name || ""); }
  function isImageFile(f) { return (f.type || "").indexOf("image") === 0 || /\.(jpe?g|png|webp|bmp|heic|heif)$/i.test(f.name || ""); }

  /* ================= network ================= */
  function ApiError(msg, status, body) { this.message = msg; this.status = status; this.body = body; }
  ApiError.prototype = Object.create(Error.prototype);
  function netMsg() { return "Can't reach the Disha AI server at " + API + ". Check your internet, or set the right address under Profile."; }
  function errText(j, status) {
    var d = j && (j.detail || j.message || j.error);
    if (Array.isArray(d)) d = d.map(function (x) { return x && x.msg ? x.msg : String(x); }).join(". ");
    if (d && typeof d === "object") d = JSON.stringify(d);
    if (d) return String(d);
    if (status === 413) return "That file is too large. Try a shorter video or a smaller photo.";
    if (status === 429) return "Too many requests. Please wait a minute and try again.";
    if (status === 401 || status === 403) return "You are not allowed to do that.";
    if (status === 404) return "We could not find that.";
    if (status >= 500) return "The server had a problem. Please try again in a moment.";
    return "Something went wrong (code " + status + ").";
  }
  function api(path, o) {
    o = o || {};
    var ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, o.timeout || 20000);
    return fetch(API + path, { method: o.method || "GET", body: o.body, headers: o.headers, signal: ctl ? ctl.signal : undefined }).then(function (r) {
      clearTimeout(timer);
      return r.text().then(function (t) {
        var j = null; try { j = t ? JSON.parse(t) : null; } catch (e) {}
        if (!r.ok) throw new ApiError(errText(j, r.status), r.status, j);
        return j;
      });
    }, function (e) {
      clearTimeout(timer);
      throw new ApiError(e && e.name === "AbortError" ? "The server is slow to answer. Check your connection and try again." : netMsg(), 0);
    });
  }
  function upload(path, fd, o) {
    o = o || {};
    return new Promise(function (resolve, reject) {
      var x = new XMLHttpRequest();
      x.open("POST", API + path); x.timeout = o.timeout || 300000;
      if (x.upload) x.upload.onprogress = function (e) { if (o.onProgress && e.lengthComputable) o.onProgress(e.loaded / e.total); };
      x.onload = function () {
        var j = null; try { j = JSON.parse(x.responseText); } catch (e) {}
        if (j && o.acceptBody && o.acceptBody(j)) return resolve(j);
        if (x.status >= 200 && x.status < 300) return resolve(j || {});
        reject(new ApiError(errText(j, x.status), x.status, j));
      };
      x.onerror = function () { reject(new ApiError(netMsg(), 0)); };
      x.ontimeout = function () { reject(new ApiError("The server took too long to answer. Check your connection and try again.", -1)); };
      x.send(fd);
    });
  }
  function reach() { // true when the API answers at all
    var ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var t = setTimeout(function () { if (ctl) ctl.abort(); }, 8000);
    return fetch(API + "/api/citizen/config", { signal: ctl ? ctl.signal : undefined, cache: "no-store" }).then(function (r) { clearTimeout(t); return r.ok ? r.json() : true; }, function () { clearTimeout(t); return false; });
  }

  /* ================= toasts ================= */
  function toast(msg, o) {
    o = o || {};
    var e = document.createElement("div"); e.className = "toast" + (o.error ? " error" : "");
    e.innerHTML = (o.icon ? badgeIcon(o.icon, o.color || "blue") : "") + '<div class="tx">' + (o.title ? "<b>" + esc(o.title) + "</b><span>" + esc(msg) + "</span>" : esc(msg)) + "</div>" + (o.action ? '<button type="button" class="btn">' + esc(o.action.label) + "</button>" : "");
    if (o.action) e.querySelector("button").onclick = function () { e.remove(); o.action.fn(); };
    var box = $("toasts"); box.appendChild(e);
    while (box.children.length > 3) box.removeChild(box.firstChild);
    setTimeout(function () { if (e.parentNode) e.remove(); }, o.ms || 6000);
  }

  /* ================= profile prefs ================= */
  var prefs = {
    get name() { return lsGet("rw-name", ""); }, set name(v) { lsSet("rw-name", String(v || "").trim()); },
    get phone() { return lsGet("rw-phone", ""); }, set phone(v) { lsSet("rw-phone", String(v || "").trim()); }
  };
  function greeting() {
    var h = new Date().getHours(), part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
    var first = prefs.name.split(" ")[0];
    return first ? part + ", " + first : part;
  }

  /* ================= audio siren ================= */
  var actx = null, siren = null, sirenTimer = null;
  var soundOn = lsGet("rw-sound", "0") === "1";
  function audio() {
    try { if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)(); if (actx.state === "suspended") actx.resume(); } catch (e) {}
    return actx;
  }
  function audioReady() { return !!actx && actx.state === "running"; }
  function beep() {
    var c = audio(); if (!c) return;
    var o = c.createOscillator(), g = c.createGain(); o.type = "square"; o.frequency.value = 880; g.gain.value = 0.15;
    o.connect(g); g.connect(c.destination); o.start(); o.stop(c.currentTime + 0.25);
  }
  function startSiren() {
    if (siren) return; var c = audio(); if (!c) return;
    var o = c.createOscillator(), g = c.createGain(), lfo = c.createOscillator(), lg = c.createGain();
    o.type = "sawtooth"; o.frequency.value = 900; lfo.type = "triangle"; lfo.frequency.value = 1.6; lg.gain.value = 350; g.gain.value = 0.4;
    lfo.connect(lg); lg.connect(o.frequency); o.connect(g); g.connect(c.destination); o.start(); lfo.start();
    siren = { stop: function () { try { o.stop(); lfo.stop(); } catch (e) {} } };
    clearTimeout(sirenTimer); sirenTimer = setTimeout(stopSiren, 120000);
  }
  function stopSiren() { clearTimeout(sirenTimer); if (siren) { siren.stop(); siren = null; } }
  // Browsers only allow sound after a tap. If the citizen turned the siren on, unlock audio on the first tap anywhere.
  document.addEventListener("pointerdown", function () { if (soundOn && !audioReady()) audio(); }, { passive: true });
  document.addEventListener("keydown", function () { if (soundOn && !audioReady()) audio(); });

  /* ================= system notifications ================= */
  var swReg = null;
  function notifSupported() { return "Notification" in window; }
  function notifPerm() { return notifSupported() ? Notification.permission : "unsupported"; }
  function notifWanted() { return lsGet("rw-notify", "0") === "1" && notifPerm() === "granted"; }
  function askNotifPermission() {
    if (!notifSupported()) { toast("This browser cannot show notifications. In-app alerts still work.", { error: true }); return Promise.resolve("unsupported"); }
    if (!window.isSecureContext) { toast("Notifications need a secure address (https). In-app alerts still work.", { error: true }); return Promise.resolve("insecure"); }
    lsSet("rw-notif-asked", "1");
    var p;
    try { p = Notification.requestPermission(); } catch (e) { return Promise.resolve("default"); }
    return Promise.resolve(p).then(function (r) {
      if (r === "granted") { lsSet("rw-notify", "1"); toast("You will get alerts even when this tab is in the background.", { title: "Notifications on", icon: "bell", color: "green" }); }
      else if (r === "denied") toast("Notifications are blocked. Click the lock icon in the address bar and allow notifications.", { error: true, ms: 9000 });
      renderRoute(true); return r;
    });
  }
  function systemNotify(title, body, data, urgent) {
    if (!notifWanted()) return;
    if (!urgent && document.visibilityState === "visible" && document.hasFocus()) return; // in-app toast is enough
    var opts = { body: body, icon: "icons/icon-192.png", badge: "icons/icon-192.png", tag: (data && data.tag) || undefined, data: { url: (data && data.url) || "./#/alerts" }, requireInteraction: !!urgent };
    try {
      if (swReg && swReg.showNotification) swReg.showNotification(title, opts);
      else { var n = new Notification(title, opts); n.onclick = function () { window.focus(); location.hash = "#/alerts"; n.close(); }; }
    } catch (e) {}
  }
  function offerNotifPrompt() {
    if (!notifSupported() || notifPerm() !== "default" || lsGet("rw-notif-asked", "0") === "1" || !window.isSecureContext) return;
    lsSet("rw-notif-asked", "1");
    toast("Get a notice when a road near you is repaired or a report of yours changes.", { title: "Turn on notifications?", icon: "bell", color: "blue", ms: 12000, action: { label: "Turn on", fn: askNotifPermission } });
  }

  /* ================= notification center ================= */
  var notifs = lsJson("rw-notifs", []);
  if (!Array.isArray(notifs)) notifs = [];
  var KIND = { safety: { icon: "warn", color: "red", label: "Safety" }, repair: { icon: "seal", color: "green", label: "Repair" }, defect: { icon: "hex", color: "orange", label: "Road damage" }, report: { icon: "doc", color: "blue", label: "Citizen report" }, status: { icon: "paper", color: "indigo", label: "Your report" }, system: { icon: "info", color: "blue", label: "Disha AI" } };
  function saveNotifs() { notifs = notifs.slice(0, 100); lsSetJson("rw-notifs", notifs); }
  function unreadCount() { var n = 0; notifs.forEach(function (a) { if (!a.read) n++; }); return n; }
  function refreshBadge() {
    var n = unreadCount(), b = $("bell-badge");
    b.hidden = !n; b.textContent = n > 9 ? "9+" : n;
    $("bell").setAttribute("aria-label", n ? "Notifications, " + n + " unread" : "Notifications");
    document.title = (n ? "(" + n + ") " : "") + "Disha AI";
    try { if (navigator.setAppBadge) { n ? navigator.setAppBadge(n) : navigator.clearAppBadge(); } } catch (e) {}
  }
  function addNotif(kind, title, text, data, key, opts) {
    opts = opts || {};
    if (key) { for (var i = 0; i < notifs.length; i++) if (notifs[i].key === key) return null; }
    var onAlerts = current === "alerts";
    var n = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), key: key || "", kind: kind, title: title, text: text, data: data || {}, at: (data && data.created_at && !isNaN(new Date(data.created_at))) ? new Date(data.created_at).toISOString() : new Date().toISOString(), read: !!opts.silent || onAlerts };
    notifs.unshift(n); saveNotifs(); refreshBadge();
    if (!opts.silent) {
      var bell = $("bell"); bell.classList.remove("ring"); void bell.offsetWidth; bell.classList.add("ring");
      var k = KIND[kind] || KIND.system;
      if (opts.toast !== false && kind !== "safety") toast(text, { title: title, icon: k.icon, color: k.color });
      systemNotify(title, text, { tag: key || n.id }, kind === "safety");
      offerNotifPrompt();
    }
    if (current === "alerts") renderRoute(true);
    return n;
  }
  $("bell").onclick = function () { location.hash = "#/alerts"; };

  /* ================= emergency banner ================= */
  var emData = null;
  function showEmergency(d) {
    emData = d || {};
    $("em-msg").textContent = emData.message || "A person has fallen near a road defect.";
    $("em-loc").textContent = emData.lat != null ? "Location: " + Number(emData.lat).toFixed(5) + ", " + Number(emData.lon).toFixed(5) : "";
    var im = $("em-img"); if (emData.snapshot_url) { im.src = url(emData.snapshot_url); im.hidden = false; } else im.hidden = true;
    $("em-map").hidden = emData.lat == null;
    $("emergency").hidden = false;
    if (soundOn) { audio(); if (audioReady()) { startSiren(); $("em-sound").hidden = true; } else { $("em-sound").hidden = false; } }
    else { $("em-sound").hidden = false; }
    if (navigator.vibrate) { try { navigator.vibrate([400, 200, 400, 200, 400]); } catch (e) {} }
    $("em-off").focus({ preventScroll: true });
  }
  $("em-sound").onclick = function () { soundOn = true; lsSet("rw-sound", "1"); audio(); startSiren(); this.hidden = true; };
  $("em-off").onclick = function () { stopSiren(); $("emergency").hidden = true; };
  $("em-map").onclick = function () { stopSiren(); $("emergency").hidden = true; var d = emData || {}; location.hash = "#/map?lat=" + d.lat + "&lon=" + d.lon; };

  /* ================= live events (websocket) ================= */
  var ws = null, wsOk = false, wsRetry = 1000, wsPing = null, lastSystem = 0;
  function setLive(on) { wsOk = on; var e = $("live-pill"); if (e) { e.className = "pill " + (on ? "st-resolved" : "st-in_progress"); e.lastChild.textContent = on ? "Live" : "Reconnecting"; } }
  function connectWs() {
    clearTimeout(connectWs.t);
    try { ws = new WebSocket(API.replace(/^http/, "ws") + "/ws/events"); } catch (e) { return; }
    ws.onopen = function () { wsRetry = 1000; setLive(true); clearInterval(wsPing); wsPing = setInterval(function () { try { ws.send("ping"); } catch (e) {} }, 25000); };
    ws.onmessage = function (e) {
      var m; try { m = JSON.parse(e.data); } catch (_) { return; }
      if (!m || !m.type) return;
      if (m.type === "hello") { (m.recent || []).forEach(function (r) { handleEvent(r, false); }); return; }
      handleEvent(m, true);
    };
    ws.onclose = function () { clearInterval(wsPing); setLive(false); connectWs.t = setTimeout(connectWs, wsRetry = Math.min(wsRetry * 2, 15000)); };
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  }
  function handleEvent(m, live) {
    var t = m.type || "", d = m.data || {};
    var silent = !live;
    if (t === "emergency.fall") {
      var fkey = (d.id || d.created_at) ? "f" + (d.id || d.created_at) : null;
      var n = addNotif("safety", "Person down near a road defect", d.message || "An emergency was detected near a road defect.", d, fkey, { silent: silent });
      if (live && (n || !fkey)) showEmergency(d);
    } else if (t === "map.repair") {
      addNotif("repair", "Road defect repaired", "A defect" + (d.number != null ? " #" + d.number : "") + " was fixed and verified.", d, "r" + (d.uid || d.number) + "-" + d.lat, { silent: silent });
    } else if (t === "map.defect") {
      var cls = d["class"] ? nice(d["class"]) : "road damage";
      addNotif("defect", d["new"] ? "New road damage on the map" : "Road damage updated", cap(cls) + (d.number != null ? " #" + d.number : "") + (d.severity ? ", severity " + d.severity : "") + (d.reports > 1 ? ", " + d.reports + " reports" : ""), d, "d" + (d.uid || d.number || "") + ":" + (d.reports || "") + ":" + (d.severity || "") + ":" + (d["new"] ? 1 : 0), { silent: silent, toast: false });
    } else if (t === "map.report") {
      addNotif("report", "New citizen report nearby", (d.category ? cap(nice(d.category)) : "A road issue") + " was reported.", d, "p" + d.category + ":" + d.lat + ":" + d.lon, { silent: silent, toast: false });
    } else if (t.indexOf("complaint.") === 0 && live) {
      pollComplaints(true);
    }
  }

  /* ================= my complaints, status polling ================= */
  var complaints = null, complaintsErr = null;
  function fetchComplaints() {
    return api("/api/complaints?device_id=" + encodeURIComponent(device)).then(function (l) { complaints = Array.isArray(l) ? l : []; complaintsErr = null; return complaints; }, function (e) { complaintsErr = e.message; throw e; });
  }
  function pollComplaints(fast) {
    if (!navigator.onLine) return Promise.resolve();
    return fetchComplaints().then(function (list) {
      var snap = lsJson("rw-snap", null), next = {};
      list.forEach(function (c) { next[c.id] = c.status; });
      if (snap) {
        list.forEach(function (c) {
          if (snap[c.id] != null && snap[c.id] !== c.status) {
            var s = statusOf(c.status);
            addNotif("status", c.ticket + " is now " + s.label.toLowerCase(), c.admin_note || "Status updated by the city.", { id: c.id, tag: "c" + c.id }, "s" + c.id + ":" + c.status);
          }
        });
      }
      lsSetJson("rw-snap", next);
      if (current === "home" || current === "reports") renderRoute(true);
    }, function () {});
  }

  /* ================= offline queue ================= */
  function getQueue() { var q = lsJson("rw-queue", []); return Array.isArray(q) ? q : []; }
  function setQueue(q) { try { localStorage.setItem("rw-queue", JSON.stringify(q)); return true; } catch (e) { return false; } }
  function fileToData(f) {
    return new Promise(function (res) {
      if (isImageFile(f) && f.size > 700 * 1024 && window.createImageBitmap) { // shrink big photos so the queue fits in storage
        createImageBitmap(f).then(function (bm) {
          var s = Math.min(1, 1600 / Math.max(bm.width, bm.height)), c = document.createElement("canvas");
          c.width = Math.round(bm.width * s); c.height = Math.round(bm.height * s); c.getContext("2d").drawImage(bm, 0, 0, c.width, c.height);
          res({ name: f.name.replace(/\.\w+$/, "") + ".jpg", type: "image/jpeg", data: c.toDataURL("image/jpeg", 0.8) });
        }, function () { read(); });
      } else read();
      function read() { var r = new FileReader(); r.onload = function () { res({ name: f.name, type: f.type, data: r.result }); }; r.onerror = function () { res(null); }; r.readAsDataURL(f); }
    });
  }
  function dataToFile(o) {
    var parts = o.data.split(","), bin = atob(parts[1]), arr = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return new File([arr], o.name, { type: o.type });
  }
  function enqueueReport(fields, files) {
    var usable = files.filter(function (f) { return f.size <= 8 * 1024 * 1024; }), dropped = files.length - usable.length;
    return Promise.all(usable.map(fileToData)).then(function (list) {
      list = list.filter(Boolean);
      var item = { id: "q" + Date.now(), at: new Date().toISOString(), fields: fields, files: list };
      var q = getQueue(); q.push(item);
      if (!setQueue(q)) { // too big: keep the text and location only
        item.files = []; dropped = files.length; q[q.length - 1] = item;
        if (!setQueue(q)) return { ok: false };
      }
      return { ok: true, dropped: dropped };
    });
  }
  var flushing = false;
  function flushQueue(manual) {
    var q = getQueue();
    if (flushing || !q.length) return Promise.resolve();
    if (!navigator.onLine) { if (manual) toast("You are offline. Your report will be sent when you are back online.", { error: true }); return Promise.resolve(); }
    flushing = true;
    var chain = Promise.resolve();
    q.slice().forEach(function (item) {
      chain = chain.then(function () {
        var fd = new FormData();
        Object.keys(item.fields).forEach(function (k) { fd.append(k, item.fields[k]); });
        item.files.forEach(function (o) { try { fd.append("files", dataToFile(o)); } catch (e) {} });
        return upload("/api/complaints", fd, { timeout: 300000 }).then(function (c) {
          setQueue(getQueue().filter(function (x) { return x.id !== item.id; }));
          addNotif("status", "Queued report sent", "Your saved report is filed as " + (c.ticket || "a new ticket") + ".", { id: c.id }, "q" + item.id);
        }, function (e) {
          if (e.status >= 400 && e.status < 500 && e.status !== 408 && e.status !== 429) { // server refuses it for good
            setQueue(getQueue().filter(function (x) { return x.id !== item.id; }));
            addNotif("system", "A saved report was not accepted", e.message, {}, "qx" + item.id);
          }
          throw e;
        });
      }).catch(function () {});
    });
    return chain.then(function () { flushing = false; fetchComplaints().then(function () { renderRoute(true); }, function () { renderRoute(true); }); });
  }

  /* ================= network status bar ================= */
  var netTimer = null;
  function netBar(text, cls, ms) {
    var b = $("netbar"); clearTimeout(netTimer);
    if (!text) { b.hidden = true; return; }
    b.className = "netbar " + (cls || ""); b.textContent = text; b.hidden = false;
    if (ms) netTimer = setTimeout(function () { b.hidden = true; }, ms);
  }
  window.addEventListener("offline", function () { netBar("You are offline. Reports are saved and sent later.", "warn"); });
  window.addEventListener("online", function () { netBar("Back online", "ok", 3000); flushQueue(); pollComplaints(); if (!wsOk) connectWs(); });

  /* ================= install prompt ================= */
  var installEvt = null;
  window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); installEvt = e; if (current === "home" || current === "profile") renderRoute(true); });
  window.addEventListener("appinstalled", function () { installEvt = null; toast("Disha AI is installed on this device.", { icon: "check", color: "green" }); renderRoute(true); });
  function doInstall() { if (!installEvt) return; installEvt.prompt(); installEvt.userChoice.then(function () { installEvt = null; renderRoute(true); }); }
  function isStandalone() { return (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true; }

  /* ================= geolocation ================= */
  var spot = null, locBusy = false, locErr = "";
  function describe(lat, lon) {
    return fetch(API + "/api/nav/reverse?lat=" + lat + "&lon=" + lon, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : Promise.reject(); }).then(function (j) {
      var a = (j && (j.address || j.name)) || ""; if (!a) return Promise.reject(); return a;
    }).catch(function () { return describeOsm(lat, lon); });
  }
  function describeOsm(lat, lon) {
    var ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var t = setTimeout(function () { if (ctl) ctl.abort(); }, 6000);
    return fetch("https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18&lat=" + lat + "&lon=" + lon, { signal: ctl ? ctl.signal : undefined }).then(function (r) { clearTimeout(t); return r.json(); }).then(function (j) {
      var a = j.address || {}, parts = [a.road, a.neighbourhood || a.suburb, a.city || a.town || a.village].filter(Boolean);
      return parts.length ? parts.join(", ") : (j.display_name || "");
    }).catch(function () { clearTimeout(t); return ""; });
  }
  function locate(force) {
    if (!navigator.geolocation) { locErr = T("e_gps_time"); return Promise.resolve(null); }
    if (spot && !force) return Promise.resolve(spot);
    locBusy = true; locErr = "";
    return new Promise(function (res) {
      navigator.geolocation.getCurrentPosition(function (p) {
        spot = { lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy, address: "" }; locBusy = false; res(spot);
        describe(spot.lat, spot.lon).then(function (a) { if (spot) { spot.address = a; if (onSpot) onSpot(); } });
      }, function (e) {
        locBusy = false;
        locErr = e && e.code === 1 ? T("e_gps") : e && e.code === 3 ? T("e_gps_time") : "We could not find your location. Type the street below instead.";
        res(null);
      }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 });
    });
  }
  var onSpot = null;

  /* ================= router ================= */
  var current = "", cleanup = null, view = $("view");
  var TABS = { home: "home", reports: "reports", report: "report", c: "reports", map: "map", alerts: "", profile: "profile", drive: "home" };
  function parseHash() {
    var h = location.hash.replace(/^#\/?/, ""), q = {}, i = h.indexOf("?");
    if (i >= 0) { h.slice(i + 1).split("&").forEach(function (kv) { var p = kv.split("="); if (p[0]) q[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || ""); }); h = h.slice(0, i); }
    var parts = h.split("/").filter(Boolean);
    return { name: parts[0] || "home", parts: parts, q: q };
  }
  var routeState = null;
  var enterT = 0;
  function renderRoute(soft) {
    var p = routeState || parseHash();
    var name = TABS.hasOwnProperty(p.name) ? p.name : "home";
    if (soft && (name !== current || name === "map")) return;
    if (!soft && cleanup) { try { cleanup(); } catch (e) {} cleanup = null; }
    current = name;
    document.body.className = "on-" + (name === "c" ? "detail" : name);
    var t = TABS[name];
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (a) { if (a.dataset.tab === t) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    var nlKey = { home: "home", report: "report", drive: "drive", map: "map", reports: "reports", c: "reports", alerts: "alerts", profile: "profile" }[name];
    Array.prototype.forEach.call(document.querySelectorAll("[data-nl]"), function (a) { if (a.dataset.nl === nlKey) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    var main = $("main");
    if (name === "map") { main.hidden = true; $("mapview").hidden = false; viewMap(p); refreshBadge(); return; }
    main.hidden = false; $("mapview").hidden = true;
    var scroll = soft ? main.scrollTop : 0;
    if (!soft) { view.classList.remove("enter"); void view.offsetWidth; view.classList.add("enter"); clearTimeout(enterT); enterT = setTimeout(function () { view.classList.remove("enter"); }, 500); }
    var fn = { home: viewHome, reports: viewReports, report: viewReport, c: viewDetail, alerts: viewAlerts, profile: viewProfile, drive: viewDrive }[name];
    var cl = fn(p, !!soft);
    if (!soft) { cleanup = typeof cl === "function" ? cl : null; main.scrollTop = 0; main.focus({ preventScroll: true }); document.title = (unreadCount() ? "(" + unreadCount() + ") " : "") + "Disha AI"; }
    else if (typeof cl === "function") cleanup = cl;
    if (soft) main.scrollTop = scroll;
  }
  window.addEventListener("hashchange", function () { routeState = null; renderRoute(); });
  function go(h) { if (location.hash === h) { routeState = null; renderRoute(); } else location.hash = h; }

  /* ================= shared fragments ================= */
  function sectionHead(t, trailing) { return '<div class="section"><h2>' + esc(t) + "</h2>" + (trailing || "") + "</div>"; }
  function emptyBlock(o) {
    return '<div class="empty card">' + (o.img ? '<img src="assets/photos/' + o.img + '" alt="">' : icon(o.icon || "doc", "ic-big")) + "<h3>" + esc(o.title) + "</h3><p>" + esc(o.text) + "</p>" + (o.btn ? '<button type="button" class="btn primary" id="' + o.btn.id + '">' + esc(o.btn.label) + "</button>" : "") + "</div>";
  }
  function errBlock(msg, id) {
    return '<div class="empty card">' + icon("wifi-off", "ic-big") + "<h3>Can't load this right now</h3><p>" + esc(msg) + '</p><button type="button" class="btn primary" id="' + (id || "retry") + '">Try again</button></div>';
  }
  function tileHtml(c) {
    var cat = catOf(c.category), photo = null;
    (c.media || []).forEach(function (m) { if (!photo && m.media_type !== "video" && m.media_url) photo = m.media_url; });
    var n = (c.media || []).length;
    return '<a class="card rtile pressable" href="#/c/' + c.id + '" aria-label="' + esc(cat.label + ", " + statusOf(c.status).label + ", ticket " + c.ticket) + '">' +
      '<img class="thumb" alt="" loading="lazy" src="' + esc(photo ? url(photo) : "assets/photos/" + cat.photo + "_sq.jpg") + '" onerror="this.onerror=null;this.src=\'assets/photos/' + cat.photo + '_sq.jpg\'">' +
      '<div class="body"><div class="row1"><span class="headline">' + esc(cat.label) + '</span><span class="when">' + esc(timeAgo(c.created_at)) + "</span></div>" +
      '<div class="desc">' + esc(c.description || c.address || c.ticket) + '</div><div class="row3">' + pill(c.status) + "<span>" + esc(c.ticket) + '</span><span class="sp"></span>' + (n ? icon("photo") + "<span>" + n + "</span>" : "") + "</div></div></a>";
  }
  function bindRetry(id, fn) { var b = $(id); if (b) b.onclick = fn; }

  /* ================= HOME ================= */
  var defectsCache = null, defectsErr = null;
  function loadDefects() {
    return api("/api/public/defects").catch(function () { return api("/api/defects?status=active"); }).then(function (l) { defectsCache = (Array.isArray(l) ? l : []).filter(function (d) { return d.lat != null; }); defectsErr = null; }, function (e) { defectsErr = e.message; });
  }
  function nearbyHtml() {
    if (defectsCache == null && !defectsErr) return skel(96);
    if (defectsErr) return '<div class="card sm" style="display:flex;gap:12px;align-items:center">' + badgeIcon("wifi-off", "orange", 38) + '<div style="flex:1"><b>Map data unavailable</b><div class="sub">' + esc(defectsErr) + '</div></div><button type="button" class="btn" id="retry-def">Retry</button></div>';
    var n = defectsCache.length, hi = 0, med = 0;
    defectsCache.forEach(function (d) { var r = d.risk_level || d.severity; if (r === "High" || r === "Critical" || r === "Severe") hi++; else if (r === "Medium" || r === "Moderate") med++; });
    return '<a class="card pressable rowlink" href="#/map">' + badgeIcon("map", "green", 44) + '<div class="grow"><div class="headline">' + (n ? n + " known damage spot" + (n === 1 ? "" : "s") : "No damage reported yet") + '</div><div class="sub">' + (n ? hi + " high risk, " + med + " medium. Open the city map." : "Open the city map to explore roads.") + "</div></div>" + icon("chev-r") + "</a>";
  }
  function paintNearby() { var n = $("nearby"); if (n && current === "home") { n.innerHTML = nearbyHtml(); bindRetry("retry-def", retryDefects); } }
  function retryDefects() { defectsErr = null; defectsCache = null; paintNearby(); loadDefects().then(paintNearby); }
  /* public numbers for the hero strip and the latest-reports feed (no personal data) */
  var pub = { stats: null, summary: null, feed: null, err: false };
  function loadPublic() {
    pub.err = false;
    var a = api("/api/public/stats").then(function (s) { pub.stats = s; }, function () { pub.err = true; });
    var b = api("/api/public/summary").then(function (s) { pub.summary = s; }, function () { pub.err = true; });
    var c = api("/api/public/complaints?limit=8").then(function (l) { pub.feed = Array.isArray(l) ? l : []; }, function () { pub.err = true; if (pub.feed == null) pub.feed = []; });
    return Promise.all([a, b, c]);
  }
  function num(n) { return n == null ? "--" : Number(n).toLocaleString("en-IN"); }
  function statStrip() {
    var s = pub.stats, m = pub.summary;
    var spots = m ? m.open_defects : s ? s.open : null, fixed = s ? s.repaired : m ? m.complaints_resolved : null, recent = s ? s.citizens_reports_last_30d : null;
    function cell(v, l, hint) { var big = v != null ? '<b class="bignum">' + num(v) + "</b>" : pub.err ? '<b class="bignum">N/A</b>' : '<b class="bignum sk" role="status" aria-label="Loading"></b>'; return '<div class="stat-c">' + big + '<span class="mono">' + l + "</span><small>" + (v == null && pub.err ? "Could not reach the server" : hint) + "</small></div>"; }
    return cell(spots, "KNOWN DAMAGE SPOTS", "On the city map right now") + cell(fixed, "FIXED SPOTS", "Marked repaired by crews") + cell(recent, "REPORTS, LAST 30 DAYS", "Sent in by citizens like you");
  }
  function miniMap() {
    var d = defectsCache;
    if (d == null) return '<div class="mm-skel">' + skel(300) + "</div>";
    if (!d.length) return '<div class="mm-empty">No damage mapped yet</div>';
    var minLa = 90, maxLa = -90, minLo = 180, maxLo = -180;
    var la = d.map(function (x) { return x.lat; }).sort(function (a, b) { return a - b; }), lo = d.map(function (x) { return x.lon; }).sort(function (a, b) { return a - b; });
    var mLa = la[la.length >> 1], mLo = lo[lo.length >> 1];
    var near = d.filter(function (x) { return Math.abs(x.lat - mLa) < 0.3 && Math.abs(x.lon - mLo) < 0.3; });
    if (near.length > 12) d = near;
    d.forEach(function (x) { minLa = Math.min(minLa, x.lat); maxLa = Math.max(maxLa, x.lat); minLo = Math.min(minLo, x.lon); maxLo = Math.max(maxLo, x.lon); });
    var W = 640, H = 380, pad = 36, kx = Math.cos(((minLa + maxLa) / 2) * Math.PI / 180);
    var sx = (W - pad * 2) / Math.max(0.002, (maxLo - minLo) * kx), sy = (H - pad * 2) / Math.max(0.002, maxLa - minLa), sc = Math.min(sx, sy);
    var ox = (W - (maxLo - minLo) * kx * sc) / 2, oy = (H - (maxLa - minLa) * sc) / 2;
    var out = "", i;
    for (i = 1; i < 8; i++) out += '<path d="M' + (i * 80) + ' 0V' + H + '" class="mm-g"/>';
    for (i = 1; i < 5; i++) out += '<path d="M0 ' + (i * 76) + 'H' + W + '" class="mm-g"/>';
    out += '<path class="mm-r" d="M-10 300C120 250 190 280 300 190S480 120 650 70"/><path class="mm-r" d="M90 -10C130 110 220 150 250 250S330 330 360 400"/><path class="mm-r" d="M-10 120C150 140 330 90 500 230S600 330 650 320"/>';
    d.forEach(function (x) {
      var r = x.risk_level || x.severity, c = (r === "High" || r === "Critical" || r === "Severe") ? "hi" : (r === "Medium" || r === "Moderate") ? "md" : "lo";
      out += '<circle class="mm-d ' + c + '" r="' + (c === "hi" ? 3.4 : 2.8) + '" cx="' + ((x.lon - minLo) * kx * sc + ox).toFixed(1) + '" cy="' + ((maxLa - x.lat) * sc + oy).toFixed(1) + '"/>';
    });
    return '<svg class="mm-svg" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Preview of mapped damage spots" preserveAspectRatio="xMidYMid slice">' + out + "</svg>";
  }
  function feedHtml() {
    var f = pub.feed;
    if (f == null) return skel(56) + skel(56, "margin-top:8px") + skel(56, "margin-top:8px");
    if (!f.length && pub.err) return '<div class="feed-empty"><b>Could not load reports</b><span>We could not reach the Disha AI server. Check your internet connection and try again in a moment.</span></div>';
    if (!f.length) return '<div class="feed-empty"><b>Nothing reported yet</b><span>Be the first to flag a bad stretch of road.</span></div>';
    return '<ul class="feed">' + f.slice(0, 6).map(function (c) {
      var cat = catOf(c.category);
      return '<li class="feed-r"><span class="mono tk">' + esc(c.number) + '</span><span class="fc"><b>' + esc(cat.label) + '</b><small>' + esc(c.area || "Location shared on the map") + '</small></span>' + pill(c.status) + '<span class="mono when">' + esc(timeAgo(c.created_at)) + "</span></li>";
    }).join("") + "</ul>";
  }
  function alertsHtml() {
    var items = notifs.slice(0, 3);
    if (!items.length) return '<div class="al-empty"><span class="mono">ALL QUIET</span><p>No safety alerts right now. We will show warnings and repair news here the moment they happen.</p></div>';
    return '<ul class="al-mini">' + items.map(function (a) {
      var k = KIND[a.kind] || KIND.system;
      return '<li class="' + (a.kind === "safety" ? "emerg" : "") + '"><span class="mono">' + esc(k.label.toUpperCase()) + "</span><b>" + esc(a.title) + "</b><small>" + esc(a.text) + " &middot; " + esc(timeAgo(a.at)) + "</small></li>";
    }).join("") + "</ul>";
  }
  function paintPublic() {
    if (current !== "home") return;
    var a = $("h-stats"), b = $("h-feed"), c = $("h-map");
    if (a) a.innerHTML = statStrip();
    if (b) b.innerHTML = feedHtml();
    if (c) c.innerHTML = miniMap();
    var n = $("h-nearby"); if (n) n.textContent = defectsCache ? defectsCache.length + " spots" : "";
  }
  function homeCtx() {
    var mine = complaints || [];
    if (complaints == null && lsGet("rw-last", "")) return '<div class="ctx card" aria-busy="true">' + skel(18, "width:45%") + skel(14, "width:70%;margin-top:10px") + skel(40, "margin-top:14px") + "</div>";
    if (!mine.length) {
      return '<div class="ctx card how3" aria-label="' + esc(T("how")) + '"><div class="ctx-k mono">' + esc(T("how")) + '</div><ol>' +
        [["camera", "how1", "how1d"], ["target", "how2", "how2d"], ["hammer", "how3", "how3d"]].map(function (x, i) { return "<li>" + badgeIcon(x[0], ["blue", "green", "orange"][i], 36) + "<b>" + esc(T(x[1])) + "</b><small>" + esc(T(x[2])) + "</small></li>"; }).join("") + "</ol></div>";
    }
    var c = mine[0], st = c.status, idx = Math.max(0, STATUS_ORDER.indexOf(st)), closed = st === "rejected";
    var days = Math.max(0, Math.floor((Date.now() - new Date(c.created_at).getTime()) / 864e5)), cat = catOf(c.category);
    var open = st === "resolved" ? T("st_resolved") : closed ? T("st_rejected") : days === 0 ? T("today") : days + " " + (days === 1 ? T("day_open") : T("days_open"));
    return '<a class="ctx card pressable" href="#/c/' + c.id + '" aria-label="' + esc(T("latest") + ": " + cat.label + ", " + statusOf(st).label) + '"><div class="ctx-top"><div><div class="ctx-k mono">' + esc(T("latest")) + '</div><div class="ctx-t">' + esc(cat.label) + ' <span>' + esc(c.ticket) + '</span></div></div><span class="ctx-d">' + esc(open) + '</span></div>' +
      '<ol class="stp" aria-hidden="true">' + STATUS_ORDER.map(function (k, i) { return '<li class="' + (closed ? "" : i < idx ? "done" : i === idx ? "cur" : "") + '"><i></i><span>' + esc(T("st_" + k)) + "</span></li>"; }).join("") + '</ol><div class="ctx-go">' + esc(T("view")) + " " + icon("arrow") + "</div></a>";
  }
  function viewHome(p, soft) {
    var q = getQueue(), mine = complaints || [];
    view.innerHTML =
      '<section class="hh"><div class="hh-in wrap">' +
      homeCtx() +
      '<span class="tagline mono"><i class="ldot"></i>LIVE <u></u> AI CHECKED <u></u> FREE TO USE</span>' +
      '<h1 class="display">' + esc(T("hero1")) + '<br><em>' + esc(T("hero2")) + '</em></h1>' +
      '<p class="lede">' + esc(T("lede")) + '</p>' +
      '<div class="cta-row"><a class="pbtn peach glow" href="#/report">' + esc(T("report_btn")) + ' ' + icon("arrow") + '</a></div>' +
      '<div class="qa" role="group" aria-label="' + esc(T("quick")) + '"><a class="qa-i" href="#/map?dir=1">' + icon("route") + '<span>' + esc(T("plan")) + '</span></a><button type="button" class="qa-i" data-talk="1">' + icon("wave") + '<span>' + esc(T("talk")) + '</span></button><a class="qa-i" href="#/alerts">' + icon("bell") + '<span>' + esc(T("alerts")) + '</span></a></div>' +
      '<div class="statstrip" id="h-stats" aria-live="polite">' + statStrip() + "</div>" +
      "</div></section>" +
      '<div class="below">' +
      (q.length ? '<div class="wrap"><div class="banner info" style="margin-top:22px">' + icon("wifi-off") + "<div><b>" + q.length + " report" + (q.length > 1 ? "s" : "") + " waiting to send</b>Saved on this device. We send it as soon as you are online.<div class=\"btnrow\"><button type=\"button\" class=\"btn\" id=\"q-send\">Send now</button></div></div></div></div>" : "") +
      '<section class="sec wrap"><div class="sec-h"><span class="mono kick">01 / HOW IT WORKS</span><h2 class="h2">From a photo to a <em>fixed</em> road in three steps.</h2></div>' +
      '<ol class="steps"><li><span class="stepn">01</span><h3>Snap it</h3><p>Take a photo or a short video of the damage. Location is picked up for you, or type the street.</p></li>' +
      '<li><span class="stepn">02</span><h3>AI checks it</h3><p>Our model confirms the damage, rates how risky it is and rejects blurry or unrelated pictures.</p></li>' +
      '<li><span class="stepn">03</span><h3>Crew fixes it</h3><p>It lands on the repair queue. You follow every status change under My reports, with alerts.</p></li></ol></section>' +
      '<section class="sec wrap mapsec"><div class="mapcard"><div class="mc-txt"><span class="mono kick">02 / LIVE MAP</span><h2 class="h2">Every known damage spot, <em>on one map.</em></h2><p class="lede sm">Red is high risk, peach is moderate, sage is minor. Plan a route that steers clear of the worst stretches.</p>' +
      '<div class="cta-row"><a class="pbtn sage" href="#/map">Open live map ' + icon("arrow") + '</a><a class="pbtn outline" href="#/map?dir=1">Plan a safe trip</a></div></div>' +
      '<a class="mc-vis pressable" href="#/map" aria-label="Open the live city map"><div id="h-map" class="mm">' + miniMap() + '</div><span class="mono chip live"><i class="ldot"></i>LIVE</span><span class="mono chip cnt" id="h-nearby">' + (defectsCache ? defectsCache.length + " spots" : "") + '</span><span class="mm-key mono"><i class="hi"></i>HIGH<i class="md"></i>MODERATE<i class="lo"></i>MINOR</span></a></div></section>' +
      '<section class="sec wrap"><div class="sec-h row"><div><span class="mono kick">03 / LATEST REPORTS</span><h2 class="h2">What neighbours are <em>flagging</em> now.</h2></div><a class="pbtn outline sm" href="#/reports">' + (mine.length ? "My reports (" + mine.length + ")" : "My reports") + '</a></div>' +
      '<div id="h-feed">' + feedHtml() + '</div>' +
      '<div class="quick-h mono">QUICK REPORT</div><div class="quick">' + CATS.map(function (c) { return '<a class="phototile pressable" href="#/report?cat=' + c.key + '" aria-label="Report ' + esc(c.label) + '"><img alt="" loading="lazy" src="assets/photos/' + c.photo + '_sq.jpg"><span class="lbl">' + esc(c.label) + "</span></a>"; }).join("") + "</div></section>" +
      '<section class="sec wrap"><div class="sec-h"><span class="mono kick">04 / SAFETY ALERTS</span><h2 class="h2">Warnings that <em>reach you</em> first.</h2></div>' +
      '<div class="safe"><div class="safe-a" id="h-alerts">' + alertsHtml() + '<a class="pbtn outline sm" href="#/alerts">All alerts</a></div>' +
      '<div class="safe-b"><a class="callcard pressable" href="tel:' + esc(helpline.replace(/\s/g, "")) + '" aria-label="Call the Disha AI agent on ' + esc(prettyPhone(helpline)) + '"><span class="ring">' + icon("wave") + '<i class="dot"></i></span><div class="grow"><span class="mono">VOICE HELPLINE</span><div class="headline">Call Disha AI agent</div><div class="sub">' + esc(prettyPhone(helpline)) + ' &middot; Hindi and English</div></div><span class="callbtn">' + icon("phone") + '</span></a>' +
      '<a class="tripcard pressable" href="#/drive"><span class="mono">VIDEO ANALYSIS</span><div class="headline">Scan a dashcam clip</div><div class="sub">Upload a drive video and every pothole is boxed and mapped.</div></a>' +
      (installEvt && !isStandalone() ? '<button type="button" class="tripcard pressable" id="install"><span class="mono">INSTALL</span><div class="headline">Add Disha AI to your phone</div><div class="sub">One tap from the home screen.</div></button>' : "") +
      '</div></div></section>' +
      '<footer class="foot wrap"><span class="mono">DISHA AI &middot; ROADS, REPORTED AND FIXED</span><span class="mono">CITIZEN PORTAL</span></footer></div>';
    bindRetry("q-send", function () { flushQueue(true); });
    bindRetry("install", doInstall);
    if (!soft) {
      if (complaints == null) fetchComplaints().then(function () { renderRoute(true); }, function () { renderRoute(true); });
      else pollComplaints();
      if (defectsCache == null) loadDefects().then(paintPublic);
      loadPublic().then(paintPublic);
    }
  }

  /* ================= MY REPORTS ================= */
  var repFilter = 0;
  function viewReports(p, soft) {
    var all = complaints || [], list = repFilter === 1 ? all.filter(function (x) { return x.status !== "resolved" && x.status !== "rejected"; }) : repFilter === 2 ? all.filter(function (x) { return x.status === "resolved" || x.status === "rejected"; }) : all;
    var body;
    if (complaints == null && !complaintsErr) body = skel(88) + skel(88, "margin-top:10px") + skel(88, "margin-top:10px");
    else if (complaintsErr && !all.length) body = errBlock(complaintsErr, "retry-rep");
    else if (!list.length) body = '<div class="empty"><img src="assets/photos/crack_sq.jpg" alt=""><h3>' + (repFilter === 2 ? "Nothing closed yet" : "Nothing here") + '</h3><p>Report a road issue from Home and track it here.</p><a class="btn primary" href="#/report">Report an issue</a></div>';
    else body = '<div class="list">' + list.map(tileHtml).join("") + "</div>";
    view.innerHTML = '<div class="page-head"><h1 class="large-title grow">My Reports</h1></div><div style="height:16px"></div>' +
      '<div class="segmented" role="group" aria-label="Filter reports">' + ["All", "Open", "Closed"].map(function (l, i) { return '<button type="button" data-f="' + i + '" aria-pressed="' + (repFilter === i) + '">' + l + "</button>"; }).join("") + '</div><div style="height:18px"></div><div id="replist" aria-live="polite">' + body + "</div>";
    Array.prototype.forEach.call(view.querySelectorAll("[data-f]"), function (b) { b.onclick = function () { repFilter = +b.dataset.f; renderRoute(true); }; });
    bindRetry("retry-rep", function () { complaintsErr = null; complaints = null; renderRoute(true); fetchComplaints().then(function () { renderRoute(true); }, function () { renderRoute(true); }); });
    if (!soft) fetchComplaints().then(function () { renderRoute(true); }, function () { renderRoute(true); });
  }

  /* ================= REPORT (new) ================= */
  var R = null;
  function newReportState(cat) {
    return { category: cat || "pothole", files: [], desc: "", name: prefs.name, phone: prefs.phone, addr: "", sending: false, progress: 0, blockedUntil: null, blockedReason: "", warning: "", seq: 0, done: null, queued: null, step: 0 };
  }
  function buzz(n) { try { if (navigator.vibrate) navigator.vibrate(n || 12); } catch (e) {} }
  function friendly(e) {
    if (!navigator.onLine || (e && e.status === 0 && !navigator.onLine)) return T("e_offline");
    if (e && (e.status === 0 || e.status === -1)) return T("e_server");
    return (e && e.message) || T("e_server");
  }
  var STEPS = ["s_issue", "s_photo", "s_loc", "s_send"];
  function viewReport(p, soft) {
    if (p.parts[1] === "done" && R && (R.done || R.queued)) return viewDone();
    if (!R || R.done || R.queued || !soft && !R.keep) R = newReportState(p.q.cat);
    else if (p.q.cat) R.category = p.q.cat;
    R.keep = false;
    view.innerHTML =
      '<div class="sheetbar wzbar"><button type="button" class="btn ghost" id="r-back"></button><h1 class="headline" id="r-title"></h1><button type="button" class="btn ghost" id="r-cancel">' + esc(T("cancel")) + '</button></div>' +
      '<ol class="wz-prog" aria-label="Progress">' + STEPS.map(function (k, i) { return '<li data-i="' + i + '"><i>' + (i + 1) + "</i><span>" + esc(T(k)) + "</span></li>"; }).join("") + "</ol>" +
      '<div class="wz-step" id="r-step" aria-live="polite"></div>' +
      '<div class="wz-bar"><p class="hint" id="r-hint" aria-live="polite"></p><button type="button" class="btn primary big block progress" id="r-next"><i id="r-prog"></i><span id="r-sub-t"></span></button></div>' +
      '<input id="in-photo" type="file" accept="image/*" capture="environment" hidden><input id="in-video" type="file" accept="video/*" capture="environment" hidden><input id="in-lib" type="file" accept="image/*,video/*" multiple hidden>';
    $("r-cancel").onclick = function () { if (R.sending) return; var dirty = R.files.length || R.desc; if (dirty && !confirm("Discard this report?")) return; R = null; go("#/home"); };
    $("r-back").onclick = function () { if (R.sending) return; if (R.step === 0) { $("r-cancel").onclick(); } else setStep(R.step - 1); };
    $("r-next").onclick = onNext;
    $("in-photo").onchange = function () { addFiles(this.files); this.value = ""; };
    $("in-video").onchange = function () { addFiles(this.files); this.value = ""; };
    $("in-lib").onchange = function () { addFiles(this.files); this.value = ""; };
    onSpot = function () { if (R && R.step === 2) paintStep(true); };
    paintStep(false);
    return function () { onSpot = null; R && (R.keep = false); };
  }
  function setStep(n, noFocus) {
    R.step = Math.max(0, Math.min(3, n)); buzz(10);
    var st = $("r-step"); if (st) { st.classList.remove("in"); void st.offsetWidth; st.classList.add("in"); }
    paintStep(false); $("main").scrollTop = 0;
    if (!noFocus) { var h = $("r-h"); if (h) h.focus({ preventScroll: true }); }
  }
  function stepOk() {
    if (!R) return false;
    if (R.step === 1) return !R.files.some(function (f) { return f.state === "checking" || f.state === "fail" || f.state === "error"; });
    if (R.step === 2) return !!spot || R.addr.trim().length >= 3;
    if (R.step === 3) return canSubmit();
    return true;
  }
  function stepHint() {
    if (!R || R.sending) return "";
    if (R.step === 1) { if (R.files.some(function (f) { return f.state === "checking"; })) return T("e_wait"); if (R.files.some(function (f) { return f.state === "fail" || f.state === "error"; })) return T("e_fail"); }
    if (R.step === 2 && !stepOk()) return T("e_place");
    if (R.step === 3 && !canSubmit()) return R.files.length ? T("e_fail") : T("e_need");
    return "";
  }
  function onNext() {
    if (!R || R.sending) return;
    if (!stepOk()) { buzz([30, 40, 30]); var h = stepHint(); if (h) toast(h, { error: true }); return; }
    if (R.step === 3) return submitReport();
    setStep(R.step + 1);
  }
  function paintBar() {
    var b = $("r-next"); if (!b || !R) return;
    var ok = stepOk(), last = R.step === 3;
    b.className = "btn big block progress " + (ok || R.sending ? "primary" : "");
    if (ok || R.sending) b.removeAttribute("aria-disabled"); else b.setAttribute("aria-disabled", "true");
    var label = last ? T("submit") : (R.step === 1 && !R.files.length ? T("skip_photo") : T("next"));
    $("r-sub-t").innerHTML = R.sending ? '<span class="spinner" style="color:#fff"></span>' + (R.progress < 0.5 ? T("sending") : T("sent_wait")) : esc(label) + (last ? "" : " " + icon("arrow"));
    $("r-prog").style.width = R.sending ? Math.round(Math.max(5, R.progress * 100)) + "%" : "0";
    $("r-hint").textContent = stepHint();
    $("r-back").innerHTML = icon("chev-l") + esc(R.step === 0 ? T("cancel") : T("back"));
    $("r-back").setAttribute("aria-label", R.step === 0 ? T("cancel") : T("back"));
    $("r-cancel").style.visibility = R.step === 0 ? "hidden" : "visible";
    Array.prototype.forEach.call(view.querySelectorAll(".wz-prog li"), function (li) { var i = +li.dataset.i; li.className = i < R.step ? "done" : i === R.step ? "cur" : ""; if (i === R.step) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current"); });
    $("r-title").textContent = T("step_of", { n: R.step + 1 });
  }
  function paintSubmit() { paintBar(); }
  function paintStep(keepFocus) {
    var st = $("r-step"); if (!st || !R) return;
    var fn = [stepIssue, stepPhoto, stepLoc, stepSend][R.step];
    var ae = document.activeElement, fid = keepFocus && ae && ae.id && st.contains(ae) ? ae.id : null, fs = fid && ae.selectionStart;
    st.innerHTML = fn();
    bindStep();
    if (fid && $(fid)) { try { $(fid).focus({ preventScroll: true }); if (fs != null && $(fid).setSelectionRange) $(fid).setSelectionRange(fs, fs); } catch (e) {} }
    paintBar();
  }
  function stepIssue() {
    return '<h2 class="wz-h" id="r-h" tabindex="-1">' + esc(T("q_issue")) + '</h2><div class="cats2" role="radiogroup" aria-label="' + esc(T("q_issue")) + '">' + CATS.map(function (c) {
      return '<button type="button" class="cat2" role="radio" data-cat="' + c.key + '" aria-checked="' + (R.category === c.key) + '">' + badgeIcon(c.icon, c.color, 44) + '<span class="tx"><b>' + esc(c.label) + "</b><small>" + esc(c.hint) + '</small></span><span class="tick">' + icon("check") + "</span></button>";
    }).join("") + "</div>";
  }
  function stepPhoto() {
    var chk = blocked() ? '<div class="banner err" style="margin-bottom:12px">' + icon("xcircle") + "<div><b>" + esc(hhmm(R.blockedUntil)) + "</b> " + esc(R.blockedReason || "") + "</div></div>" : "";
    var thumbs = R.files.map(function (it) {
      var r = it.res, cls, txt, ic;
      if (it.state === "checking") { cls = "chk"; txt = T("ai_check"); ic = "target"; }
      else if (it.state === "pass") { cls = "ok"; txt = headline(r); ic = "seal"; }
      else if (it.state === "fail") { cls = "bad"; txt = r && r.verdict === "rate_limited" ? "Paused" : T("ai_fail"); ic = "xcircle"; }
      else { cls = "warn"; txt = T("ai_err"); ic = "refresh"; }
      var base = it.video ? '<video src="' + esc(it.objUrl) + '#t=0.1" muted playsinline preload="metadata"></video>' : '<img alt="Photo ' + it.id + '" src="' + esc(it.objUrl) + '">';
      return '<div class="thumb2"><div class="pv">' + base + (it.state === "checking" ? '<span class="over"><span class="spinner" style="color:#fff"></span></span>' : "") + '</div>' +
        '<button type="button" class="chip2 ' + cls + '" ' + (it.state === "error" ? 'data-retry="' + it.id + '"' : it.state === "fail" && !(r && r.verdict === "rate_limited") ? 'data-retake="' + it.id + '"' : "") + ">" + icon(ic) + "<span>" + esc(txt) + "</span></button>" +
        '<button type="button" class="rm2" data-rm="' + it.id + '" aria-label="' + esc(T("remove")) + '">' + icon("trash") + "</button>" +
        (it.state === "fail" && r && r.reason ? '<p class="why">' + esc(r.reason) + "</p>" : "") + "</div>";
    }).join("");
    return '<h2 class="wz-h" id="r-h" tabindex="-1">' + esc(T("q_photo")) + "</h2>" + chk +
      '<div class="capt"><button type="button" class="cap big" data-pick="photo">' + icon("camera") + "<b>" + esc(T("take_photo")) + '</b></button>' +
      '<button type="button" class="cap" data-pick="video">' + icon("video") + "<b>" + esc(T("rec_video")) + '</b></button>' +
      '<button type="button" class="cap" data-pick="lib">' + icon("photo") + "<b>" + esc(T("library")) + "</b></button></div>" +
      (R.warning && !blocked() ? '<div class="banner" style="margin-top:12px">' + icon("warn") + "<div>" + esc(R.warning) + "</div></div>" : "") +
      (R.files.length ? '<div class="thumbs2">' + thumbs + '</div><p class="caption" style="margin-top:8px">' + R.files.length + "/" + MAX_FILES + "</p>" : '<p class="tip">' + icon("info") + "<span>" + esc(T("photo_tip")) + "</span></p>");
  }
  function stepLoc() {
    var has = !!spot;
    var title = locBusy && !spot ? T("finding") : spot ? (spot.address || T("loc_found")) : R.addr.trim() || "";
    var map = spot ? '<iframe title="Your location on a map" loading="lazy" tabindex="-1" src="https://www.openstreetmap.org/export/embed.html?bbox=' + [spot.lon - 0.003, spot.lat - 0.002, spot.lon + 0.003, spot.lat + 0.002].join("%2C") + "&layer=mapnik&marker=" + spot.lat + "%2C" + spot.lon + '"></iframe>' : "";
    return '<h2 class="wz-h" id="r-h" tabindex="-1">' + esc(T("q_loc")) + '</h2>' +
      '<button type="button" class="btn primary big block" id="r-locate"' + (locBusy ? " disabled" : "") + ">" + (locBusy ? '<span class="spinner" style="color:#fff"></span>' : icon("target")) + esc(locBusy ? T("finding") : T("use_loc")) + "</button>" +
      (locErr ? '<div class="banner err" style="margin-top:12px" role="alert">' + icon("warn") + "<div>" + esc(locErr) + "</div></div>" : "") +
      (has ? '<div class="card flush locc"><div class="locmap mini">' + map + '</div><div class="locrow">' + badgeIcon("pin", "green", 40) + '<div class="grow"><div class="caption">' + esc(T("loc_found")) + '</div><div class="headline">' + esc(title) + "</div></div></div></div>" : "") +
      '<label class="field wz-addr" for="r-addr">' + icon("pin") + '<input id="r-addr" autocomplete="street-address" placeholder="' + esc(T("loc_edit")) + '" value="' + esc(R.addr) + '"></label>';
  }
  function stepSend() {
    var c = catOf(R.category), addr = (spot && spot.address) || R.addr.trim() || (spot ? spot.lat.toFixed(4) + ", " + spot.lon.toFixed(4) : "");
    var th = R.files.slice(0, 4).map(function (it) { return it.video ? '<span class="mt">' + icon("video") + "</span>" : '<img alt="" src="' + esc(it.objUrl) + '">'; }).join("");
    return '<h2 class="wz-h" id="r-h" tabindex="-1">' + esc(T("q_send")) + '</h2><div class="card sumc">' +
      '<div class="kv"><span>' + esc(T("sum_issue")) + '</span><span class="v">' + esc(c.label) + '</span></div>' +
      '<div class="kv"><span>' + esc(T("sum_photos")) + '</span><span class="v">' + (th ? '<span class="mths">' + th + "</span>" : esc(T("none"))) + '</span></div>' +
      '<div class="kv"><span>' + esc(T("sum_place")) + '</span><span class="v">' + esc(addr) + "</span></div></div>" +
      '<div class="section"><h2>' + esc(R.files.length ? T("details") : T("details_req")) + '</h2></div><div class="card fieldgroup"><label class="field" style="display:block;padding:6px 16px 0"><textarea id="r-desc" class="formin" rows="3" maxlength="500" aria-label="' + esc(T("details_req")) + '" placeholder="' + esc(T("details_ph")) + '">' + esc(R.desc) + '</textarea></label><div class="cnt" id="r-cnt">' + R.desc.length + "/500</div></div>" +
      '<div class="card fieldgroup" style="margin-top:12px"><label class="field">' + icon("person-s") + '<input id="r-name" autocomplete="name" aria-label="' + esc(T("your_name")) + '" placeholder="' + esc(T("your_name")) + '" value="' + esc(R.name) + '"></label><label class="field">' + icon("phone") + '<input id="r-phone" type="tel" autocomplete="tel" inputmode="tel" aria-label="' + esc(T("your_phone")) + '" placeholder="' + esc(T("your_phone")) + '" value="' + esc(R.phone) + '"></label></div>';
  }
  function bindStep() {
    var st = $("r-step");
    Array.prototype.forEach.call(st.querySelectorAll("[data-cat]"), function (b) {
      b.onclick = function () { buzz(15); R.category = b.dataset.cat; Array.prototype.forEach.call(st.querySelectorAll("[data-cat]"), function (x) { x.setAttribute("aria-checked", x === b); }); };
    });
    Array.prototype.forEach.call(st.querySelectorAll("[data-pick]"), function (b) { b.onclick = function () { if (blocked()) return toast("Reporting is paused until " + hhmm(R.blockedUntil) + ".", { error: true }); $("in-" + b.dataset.pick).click(); }; });
    function findIt(id) { for (var i = 0; i < R.files.length; i++) if (R.files[i].id === +id) return R.files[i]; }
    Array.prototype.forEach.call(st.querySelectorAll("[data-rm]"), function (b) { b.onclick = function () { removeFile(findIt(b.dataset.rm)); }; });
    Array.prototype.forEach.call(st.querySelectorAll("[data-retake]"), function (b) { b.onclick = function () { var it = findIt(b.dataset.retake); removeFile(it, true); $(it.video ? "in-video" : "in-photo").click(); }; });
    Array.prototype.forEach.call(st.querySelectorAll("[data-retry]"), function (b) { b.onclick = function () { var it = findIt(b.dataset.retry); runCheck(it); paintStep(); }; });
    if ($("r-locate")) $("r-locate").onclick = function () { buzz(15); locBusy = true; paintStep(); locate(true).then(function () { locBusy = false; paintStep(); }); };
    if ($("r-addr")) $("r-addr").oninput = function () { R.addr = this.value; paintBar(); };
    if ($("r-desc")) $("r-desc").oninput = function () { R.desc = this.value; $("r-cnt").textContent = this.value.length + "/500"; paintBar(); };
    if ($("r-name")) $("r-name").oninput = function () { R.name = this.value; };
    if ($("r-phone")) $("r-phone").oninput = function () { R.phone = this.value; };
    Array.prototype.forEach.call(st.querySelectorAll("input, textarea"), function (i) { i.addEventListener("focus", function () { setTimeout(function () { try { i.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (e) {} }, 300); }); });
  }
  function blocked() { return R.blockedUntil && Date.now() < R.blockedUntil; }
  function hhmm(t) { var d = new Date(t); return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2); }
  function addFiles(list) {
    if (!R) return;
    if (blocked()) return toast("Reporting is paused until " + hhmm(R.blockedUntil) + ".", { error: true });
    var arr = Array.prototype.slice.call(list || []);
    if (!arr.length) return;
    var room = MAX_FILES - R.files.length;
    if (room <= 0) return toast("You can attach up to " + MAX_FILES + " files.");
    if (arr.length > room) { toast("Only the first " + room + " were added. The limit is " + MAX_FILES + " files."); arr = arr.slice(0, room); }
    arr.forEach(function (f) {
      if (!isImageFile(f) && !isVideoFile(f)) return toast(f.name + " is not a photo or video. Use JPG or PNG photos, or MP4 or MOV videos.", { error: true });
      if (f.size > 500 * 1024 * 1024) return toast(f.name + " is too large (" + fmtSize(f.size) + "). Try a shorter clip.", { error: true });
      var it = { id: ++R.seq, file: f, state: "checking", res: null, err: "", objUrl: URL.createObjectURL(f), video: isVideoFile(f) };
      R.files.push(it); runCheck(it);
    });
    buzz(20); paintStep();
  }
  function runCheck(it) {
    it.state = "checking"; it.err = "";
    var fd = new FormData(); fd.append("file", it.file, it.file.name); fd.append("device_id", device); if (prefs.phone) fd.append("phone", prefs.phone);
    upload("/api/screening/check", fd, { timeout: 180000, acceptBody: function (j) { return j && j.verdict != null; } }).then(function (j) {
      if (!R || R.files.indexOf(it) < 0) return;
      it.res = j; it.state = j.verdict === "pass" ? "pass" : "fail";
      if (j.warning && String(j.warning).trim()) R.warning = j.warning;
      if (j.verdict === "rate_limited") { R.blockedUntil = j.blocked_until ? new Date(j.blocked_until).getTime() : Date.now() + 3600000; R.blockedReason = j.reason || ""; }
      buzz(it.state === "pass" ? 25 : [30, 40, 30]); if (R.step === 1) paintStep(); else paintBar();
    }, function (e) {
      if (!R || R.files.indexOf(it) < 0) return;
      it.state = "error"; it.err = friendly(e); if (R.step === 1) { paintStep(); toast(it.err, { error: true }); } else paintBar();
    });
  }
  function headline(r) {
    var dm = r.damage || [];
    if (r.verdict !== "pass" || !dm.length) return r.reason || T("ai_ok");
    var top = dm.reduce(function (a, b) { return (b.confidence || 0) > (a.confidence || 0) ? b : a; });
    var name = nice(top["class"] || "damage"), pct = Math.round((top.confidence != null ? top.confidence : r.max_confidence || 0) * 100);
    return cap(name) + " " + pct + "%" + (dm.length > 1 ? " +" + (dm.length - 1) : "");
  }
  function removeFile(it, silent) {
    if (!it) return; var i = R.files.indexOf(it); if (i < 0) return; R.files.splice(i, 1); buzz(15);
    paintStep();
    if (silent) { try { URL.revokeObjectURL(it.objUrl); } catch (e) {} return; }
    toast(T("removed"), { ms: 6000, action: { label: T("undo"), fn: function () { if (!R) return; R.files.splice(Math.min(i, R.files.length), 0, it); buzz(10); if (R.step === 1) paintStep(); else paintBar(); } } });
  }
  function canSubmit() {
    if (!R || R.sending) return false;
    if (!R.files.length) return (R.desc || "").trim().length >= 5;
    return R.files.every(function (f) { return f.state === "pass"; });
  }
  function submitReport() {
    if (!R || R.sending) return;
    if (!canSubmit()) return toast(stepHint() || T("e_need"));
    prefs.name = R.name; prefs.phone = R.phone;
    var f = { category: R.category, description: R.desc.trim(), device_id: device };
    if (R.name.trim()) f.citizen_name = R.name.trim(); if (R.phone.trim()) f.citizen_phone = R.phone.trim();
    var addr = spot && spot.address ? spot.address : R.addr.trim();
    if (spot) { f.lat = spot.lat; f.lon = spot.lon; } if (addr) f.address = addr;
    var toks = R.files.map(function (x) { return x.res && x.res.token; }).filter(Boolean);
    if (toks.length) f.screening_tokens = toks.join(",");
    var fd = new FormData(); Object.keys(f).forEach(function (k) { fd.append(k, f[k]); });
    R.files.forEach(function (x) { fd.append("files", x.file, x.file.name); });
    R.sending = true; R.progress = 0.05; buzz(30); paintBar();
    if (!navigator.onLine) return queueIt(f);
    upload("/api/complaints", fd, { timeout: 600000, onProgress: function (p) { if (R) { R.progress = Math.max(R.progress, p * 0.5); paintBar(); } } }).then(function (c) {
      R.sending = false; R.done = c; lsSet("rw-last", c.ticket || "");
      if (Array.isArray(complaints)) complaints = [c].concat(complaints.filter(function (x) { return x.id !== c.id; })); else complaints = null;
      var snap = lsJson("rw-snap", {}) || {}; snap[c.id] = c.status || "submitted"; lsSetJson("rw-snap", snap);
      go("#/report/done");
    }, function (e) {
      if (e.status === 0 || e.status === -1) return queueIt(f, e);
      R.sending = false; paintBar(); toast(friendly(e), { error: true, ms: 9000 });
    });
    var tick = setInterval(function () { if (!R || !R.sending) return clearInterval(tick); if (R.progress >= 0.5 && R.progress < 0.95) { R.progress += 0.02; paintBar(); } }, 800);
  }
  function queueIt(fields, err) {
    var files = R.files.map(function (x) { return x.file; });
    delete fields.screening_tokens;
    enqueueReport(fields, files).then(function (r) {
      R.sending = false;
      if (!r.ok) { paintBar(); return toast(T("e_offline"), { error: true, ms: 9000 }); }
      R.queued = { dropped: r.dropped }; go("#/report/done");
    });
  }
  function copyText(t) {
    function fb() { var a = document.createElement("textarea"); a.value = t; a.style.position = "fixed"; a.style.opacity = "0"; document.body.appendChild(a); a.select(); try { document.execCommand("copy"); } catch (e) {} a.remove(); }
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(t).catch(fb);
    fb(); return Promise.resolve();
  }
  function a2hsHtml() {
    if (isStandalone() || lsGet("rw-a2hs", "") === "1") return "";
    var ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    return '<div class="a2hs" id="a2hs">' + icon("install") + '<div class="grow"><b>' + esc(T("a2hs")) + "</b>" + (installEvt ? "" : "<span>" + esc(T("a2hs_ios")) + "</span>") + '</div>' + (installEvt ? '<button type="button" class="btn primary" id="a2hs-go">' + esc(T("a2hs_btn")) + "</button>" : "") + '<button type="button" class="btn ghost" id="a2hs-x">' + esc(T("dismiss")) + "</button></div>";
  }
  function bindA2hs() {
    var x = $("a2hs-x"); if (x) x.onclick = function () { lsSet("rw-a2hs", "1"); $("a2hs").remove(); };
    var g = $("a2hs-go"); if (g) g.onclick = doInstall;
  }
  function viewDone() {
    var c = R.done, q = R.queued;
    if (q) {
      view.innerHTML = '<div class="success"><div class="seal" style="background:linear-gradient(135deg,#ff9f0a,#d97706);box-shadow:0 16px 40px rgba(255,159,10,.33)">' + icon("wifi-off") + '</div><h1 class="large-title" id="r-h" tabindex="-1" style="font-size:30px">' + esc(T("saved_title")) + '</h1><p class="sub" style="font-size:16px;margin:8px 0 24px">' + esc(T("saved_sub")) + (q.dropped ? " " + q.dropped + " large file" + (q.dropped > 1 ? "s were" : " was") + " too big to keep." : "") + '</p><a class="btn primary big block" href="#/home">OK</a></div>';
      var d0 = R; if ($("r-h")) $("r-h").focus({ preventScroll: true }); return function () { if (R === d0) R = null; };
    }
    var n = (c.findings || []).length, pending = (c.media || []).some(function (m) { return m.status === "running" || m.status === "processing"; });
    var dots = ""; for (var i = 0; i < 14; i++) dots += '<i style="--a:' + (i * 26) + "deg;--d:" + (60 + (i % 4) * 14) + "px;--c:" + ["#F2CC8F", "#81B29A", "#F4F1DE", "#E07A5F"][i % 4] + ';--t:' + (i % 5) * 40 + 'ms"></i>';
    view.innerHTML = '<div class="success"><div class="burst" aria-hidden="true">' + dots + '</div><div class="seal pop">' + icon("check") + '</div><h1 class="large-title" id="r-h" tabindex="-1" style="font-size:30px">' + esc(T("ok_title")) + '</h1><p class="sub" style="font-size:16px;margin:8px 0 20px">' + esc(T("ok_sub")) + "</p>" +
      '<div class="ticketbox"><span class="caption">' + esc(T("ticket")) + '</span><b class="tno" id="tno">' + esc(c.ticket) + '</b><div class="tact"><button type="button" class="btn" id="t-copy">' + esc(T("copy")) + '</button><button type="button" class="btn" id="t-share">' + esc(T("share")) + "</button></div></div>" +
      '<div class="card" style="text-align:left;margin-top:14px"><div class="kv"><span>' + esc(T("sum_issue")) + '</span><span>' + esc(catOf(c.category).label) + '</span></div><div class="kv"><span>AI</span><span>' + esc(pending ? "..." : n === 0 ? ((c.media || []).length ? "Manual review" : "-") : n + " defect" + (n === 1 ? "" : "s")) + "</span></div></div>" +
      '<div style="height:20px"></div><a class="btn primary big block" href="#/c/' + c.id + '">' + esc(T("track")) + '</a><div style="height:8px"></div><button type="button" class="btn big block" id="t-again">' + esc(T("another")) + "</button>" + a2hsHtml() + "</div>";
    buzz([40, 50, 80]);
    $("t-copy").onclick = function () { var b = this; copyText(c.ticket).then(function () { b.textContent = T("copied"); buzz(12); setTimeout(function () { b.textContent = T("copy"); }, 1800); }); };
    $("t-share").onclick = function () { var t = T("share_text", { t: c.ticket }); if (navigator.share) navigator.share({ title: "Disha AI", text: t, url: location.origin + location.pathname + "#/c/" + c.id }).catch(function () {}); else copyText(t).then(function () { toast(T("copied")); }); };
    $("t-again").onclick = function () { R = null; go("#/report"); };
    bindA2hs(); $("r-h").focus({ preventScroll: true });
    var done = R; return function () { if (R === done) R = null; };
  }

  /* ================= DETAIL ================= */
  function viewDetail(p, soft) {
    var id = +p.parts[1], timer = null, c = null;
    for (var i = 0; i < (complaints || []).length; i++) if (complaints[i].id === id) c = complaints[i];
    var showAi = true, dead = false;
    function paint() {
      if (!c) { view.innerHTML = '<div class="dhero" style="background:var(--fill)"><a class="back" href="#/reports" aria-label="Back to my reports">' + icon("chev-l") + "</a></div>" + skel(80, "margin-top:18px") + skel(160, "margin-top:12px"); return; }
      var cat = catOf(c.category), photo = null;
      (c.media || []).forEach(function (m) { if (!photo && m.media_type !== "video") photo = m; });
      var hero = photo ? (showAi ? (photo.annotated_url || photo.media_url) : photo.media_url) : null;
      var processing = (c.media || []).some(function (m) { return m.status === "running" || m.status === "processing"; });
      var rej = c.status === "rejected", cur = STATUS_ORDER.indexOf(c.status);
      var tl = (rej ? ["submitted", "rejected"] : STATUS_ORDER).map(function (s, i) {
        var st = statusOf(s), done = rej ? true : i <= cur;
        return '<div class="tl ' + (done ? "done " : "") + (i === (rej ? 1 : cur) ? "cur " : "") + 'c-' + st.color + '"><div class="dot">' + icon(st.icon) + "</div>" + esc(st.label) + "</div>";
      }).join("");
      var f = c.findings || [];
      var ai = !(c.media || []).length ? "" : sectionHead("AI inspection") + '<div class="card">' + (processing && !f.length ? '<div style="display:flex;gap:12px;align-items:center"><span class="spinner"></span><span class="sub">Scanning your video frame by frame...</span></div>' : !f.length ? '<div style="display:flex;gap:12px;align-items:center">' + badgeIcon("person-s", "blue", 34) + '<span class="sub">No damage auto-detected. An inspector will review your media.</span></div>' : f.map(function (x) { var rk = x.risk_level || x.severity || ""; return '<div class="finding">' + (x.crop_url ? '<img class="crop" alt="" src="' + esc(url(x.crop_url)) + '" onerror="this.style.visibility=\'hidden\'">' : '<span class="crop"></span>') + '<div class="grow"><div class="headline">' + esc(nice(x.class_name || "damage")) + '</div><div class="sub" style="font-size:12.5px">' + Math.round((x.confidence || 0) * 100) + "% confidence" + (x.defect_uid ? "  ·  " + esc(x.defect_uid) : "") + '</div></div><span class="pill rk-' + esc(cap(rk)) + '">' + esc(rk) + " risk</span></div>"; }).join("")) + "</div>";
      var hasEv = (c.media || []).some(function (m) { return m.media_url || m.annotated_url; });
      var ev = hasEv ? sectionHead("Evidence") + '<div class="evgrid">' + c.media.map(function (m, i) {
        var vid = m.media_type === "video", src = vid ? (m.annotated_url || m.media_url) : (m.annotated_url || m.media_url);
        if (!src) return ""; return '<button type="button" class="ev pressable" data-ev="' + i + '" aria-label="' + (vid ? "Play video " : "View photo ") + (i + 1) + '">' + (vid ? icon("play") : '<img alt="" loading="lazy" src="' + esc(url(src)) + '">') + "</button>";
      }).join("") + "</div>" : "";
      view.innerHTML =
        '<div class="dhero"><img alt="" src="' + esc(hero ? url(hero) : "assets/photos/" + cat.photo + ".jpg") + '" onerror="this.onerror=null;this.src=\'assets/photos/' + cat.photo + '.jpg\'"><a class="back" href="#/reports" aria-label="Back to my reports">' + icon("chev-l") + '</a><div class="tx"><div class="grow"><div class="tk">' + esc(c.ticket) + "</div><h1>" + esc(cat.label) + '</h1><div style="font-size:14px;opacity:.9">Reported ' + esc(timeAgo(c.created_at)) + "</div></div>" + (photo && photo.annotated_url ? '<button type="button" class="chipbtn tg" id="d-ai" style="background:var(--glass);color:var(--text)" aria-pressed="' + showAi + '">' + icon(showAi ? "eye" : "target") + (showAi ? "Original" : "AI view") + "</button>" : "") + "</div></div>" +
        '<div style="height:18px"></div><div class="card"><div class="timeline" role="list" aria-label="Report progress">' + tl + "</div></div>" +
        (c.admin_note ? '<div class="card" style="display:flex;gap:12px;margin-top:12px">' + badgeIcon("bubble", "indigo", 34) + '<div><div class="headline" style="font-size:15px">Update from the city</div><div class="sub" style="margin-top:3px">' + esc(c.admin_note) + "</div></div></div>" : "") +
        ai + ev + sectionHead("Location") +
        '<div class="card flush">' + (c.lat != null ? '<div class="locmap" style="height:160px"><iframe title="Where this was reported" loading="lazy" src="https://www.openstreetmap.org/export/embed.html?bbox=' + [c.lon - 0.003, c.lat - 0.002, c.lon + 0.003, c.lat + 0.002].join("%2C") + "&layer=mapnik&marker=" + c.lat + "%2C" + c.lon + '"></iframe></div>' : "") + '<div style="padding:16px">' + (c.description ? '<div style="font-size:16px;margin-bottom:6px">' + esc(c.description) + "</div>" : "") + '<div class="info-row">' + icon("pin") + "<span>" + esc(c.address || (c.lat != null ? c.lat.toFixed(5) + ", " + c.lon.toFixed(5) : "No location")) + '</span></div><div class="info-row">' + icon("check") + "<span>Updated " + esc(timeAgo(c.updated_at || c.created_at)) + "</span></div></div></div>" +
        '<button type="button" class="card pressable rowlink" id="d-mail" style="margin-top:16px;display:flex">' + badgeIcon("mail", "blue", 48) + '<div class="grow"><div class="headline">Email complaint</div><div class="sub" style="font-size:13px">Send it to the office responsible for this road</div></div>' + icon("chev-r") + "</button>" +
        '<a class="card callcard pressable" style="margin-top:12px" href="tel:' + esc(helpline.replace(/\s/g, "")) + '"><span class="ring">' + badgeIcon("wave", "indigo", 48) + '<i class="dot"></i></span><div class="grow"><div class="headline">Call Disha AI agent</div><div class="sub" style="font-size:13px">Questions? Quote ' + esc(c.ticket) + '</div></div><span class="callbtn">' + icon("phone") + "</span></a>";
      var ai2 = $("d-ai"); if (ai2) ai2.onclick = function () { showAi = !showAi; paint(); };
      Array.prototype.forEach.call(view.querySelectorAll("[data-ev]"), function (b) { b.onclick = function () { lightbox(c.media[+b.dataset.ev]); }; });
      $("d-mail").onclick = function () { emailComplaint(c, this); };
    }
    function load() {
      api("/api/complaints/" + id + "?device_id=" + encodeURIComponent(device)).then(function (x) {
        if (dead) return; c = x; paint(); clearTimeout(timer);
        if ((c.media || []).some(function (m) { return m.status === "running" || m.status === "processing"; })) timer = setTimeout(load, 4000);
      }, function (e) {
        if (dead) return;
        if (!c) view.innerHTML = '<div class="page-head"><a class="btn ghost" href="#/reports">' + icon("chev-l") + 'My Reports</a></div><div style="height:12px"></div>' + errBlock(e.status === 404 ? "We could not find this report. It may have been filed from another device." : e.message, "retry-d");
        bindRetry("retry-d", load);
      });
    }
    paint(); load();
    return function () { dead = true; clearTimeout(timer); };
  }
  function lightbox(m) {
    var vid = m.media_type === "video", src = url(m.annotated_url || m.media_url);
    var d = document.createElement("div"); d.className = "lightbox"; d.setAttribute("role", "dialog"); d.setAttribute("aria-label", "Evidence viewer");
    d.innerHTML = (vid ? '<video controls autoplay playsinline src="' + esc(src) + '"></video>' : '<img alt="Evidence photo" src="' + esc(src) + '">') + '<button type="button" class="btn" aria-label="Close viewer">' + icon("xcircle") + "Close</button>";
    function close() { d.remove(); document.removeEventListener("keydown", key); }
    function key(e) { if (e.key === "Escape") close(); }
    d.onclick = function (e) { if (e.target === d || e.target.closest("button")) close(); };
    document.addEventListener("keydown", key); document.body.appendChild(d); d.querySelector("button").focus();
  }
  function sheet(html, onMount) {
    var root = $("sheet-root"), bg = document.createElement("div"); bg.className = "sheet-bg";
    bg.innerHTML = '<div class="sheet" role="dialog" aria-modal="true">' + html + "</div>"; root.appendChild(bg);
    var prev = document.activeElement;
    function close() { bg.remove(); document.removeEventListener("keydown", key); try { prev && prev.focus(); } catch (e) {} }
    function key(e) { if (e.key === "Escape") close(); }
    bg.onclick = function (e) { if (e.target === bg) close(); };
    document.addEventListener("keydown", key);
    var first = bg.querySelector("button, a"); if (first) first.focus();
    if (onMount) onMount(bg, close);
    return close;
  }
  function emailComplaint(c, btn) {
    btn.style.opacity = ".6";
    api("/api/route/" + encodeURIComponent(c.ticket)).then(function (r) {
      btn.style.opacity = "";
      if (!r || r.applicable !== true) return sheet("<h2>Email is not available for this road</h2><p>" + esc((r && r.reason) || "No office is set up for this location yet.") + '</p><button type="button" class="btn primary" data-x>OK</button>', function (b, close) { b.querySelector("[data-x]").onclick = close; });
      var email = r.email || "", subject = r.subject || "Road damage complaint " + c.ticket, body = r.body || "";
      sheet("<h2>Send to " + esc(r.authority || "the road authority") + "</h2><p>" + esc(email) + (r.verified ? "" : "<br>This address is not yet verified by the admin.") + '</p><a class="btn primary" href="mailto:' + esc(email) + "?subject=" + encodeURIComponent(subject) + "&amp;body=" + encodeURIComponent(body) + '">Open email draft</a><button type="button" class="btn" data-copy>Copy the message</button><button type="button" class="btn" data-x>Cancel</button>', function (b, close) {
        b.querySelector("[data-x]").onclick = close;
        b.querySelector("[data-copy]").onclick = function () { var t = "To: " + email + "\nSubject: " + subject + "\n\n" + body; (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(function () { toast("Message copied. Paste it into your email app."); }, function () { toast("Could not copy. Use Open email draft instead.", { error: true }); }); };
      });
    }, function (e) { btn.style.opacity = ""; toast(e.message, { error: true }); });
  }

  /* ================= MAP ================= */
  var mapLoaded = false, coachDismissed = false;
  function viewMap(p) {
    var frame = $("mapframe"), err = $("map-err");
    var hash = p.q.lat && p.q.lon ? "#" + p.q.lat + "," + p.q.lon : "", ml = I18N.get() === "hi" ? "hi" : "en", mp = "/map?lang=" + ml;
    $("map-coach").hidden = !(p.q.dir === "1" && !coachDismissed);
    function load() {
      err.hidden = true;
      if (!navigator.onLine) { $("map-err-t").textContent = "You are offline. Connect to the internet to see the map."; err.hidden = false; return; }
      fetch(API + "/map", { mode: "no-cors", cache: "no-store" }).then(function () {
        if (!mapLoaded || frame.getAttribute("data-api") !== API + mp) { frame.src = API + mp + hash; frame.setAttribute("data-api", API + mp); mapLoaded = true; }
        else if (hash && frame.contentWindow) { try { frame.contentWindow.location.replace(API + mp + hash); } catch (e) { frame.src = API + mp + hash; } }
      }, function () { mapLoaded = false; $("map-err-t").textContent = "The Disha AI server at " + API + " is not answering. Check that it is running, or fix the address under Profile."; err.hidden = false; });
    }
    $("map-retry").onclick = load; $("coach-x").onclick = function () { coachDismissed = true; $("map-coach").hidden = true; };
    load();
  }

  /* ================= ALERTS ================= */
  function viewAlerts() {
    var perm = notifPerm(), items = notifs;
    var notice = "";
    if (perm === "default" && notifSupported() && window.isSecureContext) notice = '<div class="banner info" style="margin-bottom:12px">' + icon("bell") + '<div><b>Get alerts even when Disha AI is closed</b>Allow notifications to hear about repairs and safety alerts.<div class="btnrow"><button type="button" class="btn primary" id="al-perm">Turn on notifications</button></div></div></div>';
    else if (perm === "denied") notice = '<div class="banner" style="margin-bottom:12px">' + icon("warn") + "<div><b>Notifications are blocked</b>Allow them from the lock icon in the address bar to get alerts in the background.</div></div>";
    view.innerHTML = '<div class="page-head"><h1 class="large-title grow">Alerts</h1></div><div style="height:10px"></div><div class="btnrow" style="align-items:center;margin-bottom:14px"><span id="live-pill" class="pill ' + (wsOk ? "st-resolved" : "st-in_progress") + '">' + icon("target") + "<span>" + (wsOk ? "Live" : "Reconnecting") + '</span></span><span style="flex:1"></span>' + (items.length ? '<button type="button" class="btn" id="al-read"' + (unreadCount() ? "" : " disabled") + '>Mark all read</button><button type="button" class="btn danger" id="al-clear">Clear</button>' : "") + "</div>" + notice +
      (items.length ? '<div class="list" aria-live="polite">' + items.map(function (a, i) {
        var k = KIND[a.kind] || KIND.system, d = a.data || {};
        return '<div class="card al ' + (a.read ? "" : "unread ") + (a.kind === "safety" ? "emerg" : "") + '" data-n="' + i + '">' + (d.snapshot_url ? '<img class="snap" alt="Snapshot" src="' + esc(url(d.snapshot_url)) + '" onerror="this.remove()">' : badgeIcon(k.icon, k.color, 40)) + '<div class="grow"><div class="headline">' + esc(a.title) + '</div><div class="sub">' + esc(a.text) + "</div><small>" + esc(k.label) + " · " + esc(timeAgo(a.at)) + '</small><div class="btnrow">' + (d.lat != null ? '<a class="chipbtn" href="#/map?lat=' + esc(d.lat) + "&amp;lon=" + esc(d.lon) + '">' + icon("map") + "View on map</a>" : "") + (a.kind === "status" && d.id ? '<a class="chipbtn" href="#/c/' + esc(d.id) + '">' + icon("doc") + "Open report</a>" : "") + (!a.read ? '<button type="button" class="chipbtn neutral" data-read="' + i + '">Mark read</button>' : "") + "</div></div></div>";
      }).join("") + "</div>" : emptyBlock({ icon: "bell", title: "All quiet", text: "Safety alerts, repair news and updates on your reports will appear here as they happen." }));
    var pb = $("al-perm"); if (pb) pb.onclick = askNotifPermission;
    var ar = $("al-read"); if (ar) ar.onclick = function () { notifs.forEach(function (a) { a.read = true; }); saveNotifs(); refreshBadge(); renderRoute(true); };
    var ac = $("al-clear"); if (ac) ac.onclick = function () { if (!confirm("Clear all alerts?")) return; notifs = []; saveNotifs(); refreshBadge(); renderRoute(true); };
    Array.prototype.forEach.call(view.querySelectorAll("[data-read]"), function (b) { b.onclick = function () { notifs[+b.dataset.read].read = true; saveNotifs(); refreshBadge(); renderRoute(true); }; });
    // opening the screen marks what is visible as read after a moment so the unread dots can be seen
    var t = setTimeout(function () { if (unreadCount() && current === "alerts") { /* keep unread until the citizen acts, like a mail inbox */ } }, 0);
    return function () { clearTimeout(t); };
  }

  /* ================= PROFILE ================= */
  function setLang(c) {
    I18N.set(c); buzz(12); toast(I18N.langs.filter(function (l) { return l.code === c; })[0].native);
    if (current === "map") { mapLoaded = false; renderRoute(); } else renderRoute(true);
  }
  function viewProfile() {
    var init = prefs.name.trim() ? prefs.name.trim().split(/\s+/).slice(0, 2).map(function (w) { return w[0].toUpperCase(); }).join("") : "?";
    var perm = notifPerm(), nOn = notifWanted();
    var permNote = perm === "unsupported" ? "This browser cannot show notifications." : !window.isSecureContext ? "Notifications need a secure (https) address. In-app alerts still work." : perm === "denied" ? "Blocked in the browser. Allow it from the lock icon in the address bar." : nOn ? "On. You will get a notice for repairs, safety alerts and report updates." : "Off. Turn on to get alerts when this tab is in the background.";
    var q = getQueue();
    function row(ic, color, label, inner) { return '<div class="grow-row">' + badgeIcon(ic, color, 30) + '<div class="lbl">' + label + "</div>" + (inner || "") + "</div>"; }
    view.innerHTML = '<div class="page-head"><h1 class="large-title grow">Profile</h1></div>' +
      '<div class="avatar" aria-hidden="true">' + esc(init) + '</div><div style="text-align:center" class="title">' + esc(prefs.name || "Citizen") + '</div><div class="sub" style="text-align:center;margin-top:4px">Not signed in · reports linked to this device</div>' +
      '<div class="caption group-t">YOUR DETAILS</div><div class="card group">' +
      row("person-s", "blue", '<input class="formin" id="p-name" aria-label="Name" placeholder="Name" autocomplete="name" value="' + esc(prefs.name) + '">') +
      row("phone", "green", '<input class="formin" id="p-phone" aria-label="Mobile" placeholder="Mobile" type="tel" autocomplete="tel" value="' + esc(prefs.phone) + '">') + "</div>" +
      '<div class="caption group-t">' + esc(T("lang").toUpperCase()) + '</div><div class="card group langs" role="radiogroup" aria-label="' + esc(T("lang")) + '">' + I18N.langs.map(function (l) { return '<button type="button" class="langrow" role="radio" data-lg="' + l.code + '" aria-checked="' + (I18N.get() === l.code) + '"><b>' + esc(l.native) + "</b>" + icon("check") + "</button>"; }).join("") + "</div>" +
      '<div class="caption group-t">NOTIFICATIONS</div><div class="card group">' +
      row("bell", "red", '<label for="p-notif">Browser notifications</label>', '<span class="switch"><input id="p-notif" type="checkbox" role="switch"' + (nOn ? " checked" : "") + (perm === "unsupported" ? " disabled" : "") + '><i></i></span>') +
      row("speaker", "orange", '<label for="p-sound">Emergency siren sound</label>', '<span class="switch"><input id="p-sound" type="checkbox" role="switch"' + (soundOn ? " checked" : "") + '><i></i></span>') +
      '<div class="grow-row"><button type="button" class="btn danger" id="p-test" style="width:100%">Send a test emergency alert</button></div></div>' +
      '<p class="sub" style="padding:8px 6px 0;font-size:12.5px" id="p-nnote">' + esc(permNote) + " Browsers allow the siren only after you tap once on this page." + "</p>" +
      (installEvt && !isStandalone() ? '<div class="caption group-t">APP</div><div class="card group"><button type="button" class="grow-row" id="p-install" style="width:100%;border:0;background:none;text-align:left">' + badgeIcon("install", "blue", 30) + '<div class="lbl">Install Disha AI on this device</div>' + icon("chev-r") + "</button></div>" : "") +
      (q.length ? '<div class="caption group-t">WAITING TO SEND</div><div class="card group">' + row("wifi-off", "orange", q.length + " saved report" + (q.length > 1 ? "s" : ""), '<button type="button" class="btn" id="p-flush">Send now</button>') + "</div>" : "") +
      '<div class="caption group-t">HELP</div><div class="card group"><a class="grow-row" style="text-decoration:none;color:inherit" href="tel:' + esc(helpline.replace(/\s/g, "")) + '">' + badgeIcon("wave", "indigo", 30) + '<div class="lbl">Call Disha AI agent</div><span class="val">' + esc(prettyPhone(helpline)) + "</span>" + icon("chev-r") + "</a></div>" +
      '<div class="caption group-t">SERVER</div><div class="card group">' + row("route", "teal", '<input class="formin" id="p-api" aria-label="Server address" placeholder="http://192.168.x.x:8000" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false" value="' + esc(lsGet("rw-api", "")) + '">') + '</div><p class="sub" style="padding:8px 6px 0;font-size:12.5px">Leave empty to use ' + esc(location.protocol + "//" + location.hostname + ":8000") + ". Point this to the Disha AI backend. On a phone use your computer's network address.</p>" +
      '<div style="height:24px"></div><button type="button" class="btn primary big block" id="p-save">Save</button><p class="caption" style="text-align:center;margin-top:20px;font-weight:500">Disha AI Citizen 1.1 (web)</p>';
    Array.prototype.forEach.call(view.querySelectorAll("[data-lg]"), function (b) { b.onclick = function () { setLang(b.dataset.lg); }; });
    $("p-notif").onchange = function () {
      var el = this;
      if (el.checked) { askNotifPermission().then(function (r) { if (r !== "granted") { el.checked = false; lsSet("rw-notify", "0"); } }); }
      else { lsSet("rw-notify", "0"); renderRoute(true); }
    };
    $("p-sound").onchange = function () { soundOn = this.checked; lsSet("rw-sound", soundOn ? "1" : "0"); if (soundOn) { audio(); beep(); toast("Siren is on. It plays for emergency alerts while this page is open.", { icon: "speaker", color: "orange" }); } else stopSiren(); };
    $("p-test").onclick = function () { if (soundOn) audio(); showEmergency({ message: "This is a test alert. No one is hurt." }); setTimeout(function () { if (!$("emergency").hidden && /test alert/.test($("em-msg").textContent)) stopSiren(); }, 4000); systemNotify("Test emergency alert", "This is a test. No one is hurt.", { url: "./#/alerts" }, true); };
    bindRetry("p-install", doInstall); bindRetry("p-flush", function () { flushQueue(true); });
    $("p-save").onclick = function () {
      prefs.name = $("p-name").value; prefs.phone = $("p-phone").value;
      var s = $("p-api").value.trim(), bad = false;
      if (s) { if (!/^https?:\/\//i.test(s)) s = "http://" + s; s = s.replace(/\/+$/, ""); try { new URL(s); } catch (e) { bad = true; } }
      if (bad) return toast("That server address does not look right. Example: http://192.168.1.20:8000", { error: true });
      var changed = s !== lsGet("rw-api", "");
      if (s) lsSet("rw-api", s); else try { localStorage.removeItem("rw-api"); } catch (e) {}
      if (changed) { API = s || location.protocol + "//" + location.hostname + ":8000"; mapLoaded = false; complaints = null; defectsCache = null; try { ws.onclose = null; ws.close(); } catch (e) {} connectWs(); syncConfig(); }
      toast(changed ? "Saved. Now using " + API : "Saved", { icon: "check", color: "green" }); renderRoute(true);
    };
  }

  /* ================= DRIVE / IMPORT ================= */
  var D = { file: null, quality: "2k", classes: null, where: "none", gpx: null, lat: "", lon: "", busy: false, status: "", progress: 0, result: null, error: "", showPossible: false, locErr: "" };
  var classMap = null;
  function loadClasses() { if (classMap) return; api("/api/config").then(function (c) { classMap = c.class_labels || DEFAULT_CLASSES; if (current === "drive") renderRoute(true); }, function () { classMap = DEFAULT_CLASSES; }); }
  function viewDrive(p, soft) {
    loadClasses();
    var map = classMap || DEFAULT_CLASSES; if (!D.classes) D.classes = Object.keys(map);
    var isVid = D.file ? isVideoFile(D.file) : true;
    var ready = D.file && !D.busy && D.classes.length && (D.where !== "gpx" || D.gpx) && (D.where !== "here" || (D.lat && D.lon));
    view.innerHTML = '<div class="page-head"><a class="btn ghost" href="#/home" aria-label="Back to Home" style="margin-left:-8px">' + icon("chev-l") + 'Home</a><span class="grow"></span></div><h1 class="large-title" style="margin-top:4px;font-size:30px">Video analysis</h1>' +
      '<p class="sub" style="margin:8px 0 0">Upload a dashcam clip or a photo. Every pothole is boxed and tracked once, then added to the city map.</p>' +
      sectionHead("1. The video or photo") + '<div class="card dropzone">' + badgeIcon("film", D.file ? "green" : "blue", 42) + '<div class="grow"><div class="headline">' + esc(D.file ? D.file.name : "No file chosen") + '</div><div class="sub">' + (D.file ? esc(fmtSize(D.file.size)) : "MP4, MOV or JPG. Up to a few minutes works best.") + '</div></div><button type="button" class="btn" id="d-pick"' + (D.busy ? " disabled" : "") + ">" + (D.file ? "Change" : "Choose") + '</button><input id="d-file" type="file" accept="video/*,image/*" hidden></div>' +
      '<div id="d-ferr"></div>' +
      sectionHead("2. What to look for") + '<div class="checks" role="group" aria-label="Damage types">' + Object.keys(map).map(function (k) { return '<label class="check"><input type="checkbox" value="' + esc(k) + '"' + (D.classes.indexOf(k) >= 0 ? " checked" : "") + (D.busy ? " disabled" : "") + ">" + esc(map[k]) + "</label>"; }).join("") + "</div>" +
      (isVid ? sectionHead("3. Quality") + '<div class="segmented" role="group" aria-label="Quality"><button type="button" data-q="2k" aria-pressed="' + (D.quality === "2k") + '">2K (faster)</button><button type="button" data-q="4k" aria-pressed="' + (D.quality === "4k") + '">4K (sharper)</button></div>' : "") +
      sectionHead((isVid ? "4" : "3") + ". Where was it recorded?") + '<p class="sub" style="margin:0 0 10px">An old clip must not be stamped with where you are now, so pick carefully.</p><div class="list" role="radiogroup" aria-label="Location source">' +
      [["gpx", "map", "Use a GPX track", D.gpx ? D.gpx.name : "Most accurate. Each frame gets its own position."], ["here", "pin", "I am recording right now", D.lat && D.lon ? D.lat + ", " + D.lon : "Uses your current location."], ["none", "pin-off", "Send without a location", "Potholes are still detected, but marked as location unknown."]].map(function (o) {
        return '<button type="button" class="opt" role="radio" data-w="' + o[0] + '" aria-checked="' + (D.where === o[0]) + '"><span class="radio"></span>' + icon(o[1]) + '<span class="grow"><div class="headline" style="font-size:15.5px">' + o[2] + '</div><div class="sub" style="font-size:13px">' + esc(o[3]) + "</div></span>" + "</button>";
      }).join("") + '</div>' + (D.where === "gpx" ? '<div style="margin-top:10px"><button type="button" class="btn" id="d-gpx">' + (D.gpx ? "Change GPX file" : "Choose GPX file") + "</button></div>" : "") + '<input id="d-gpxf" type="file" accept=".gpx,application/gpx+xml,text/xml" hidden>' + (D.locErr ? '<p class="banner err" style="margin-top:10px">' + icon("warn") + "<span>" + esc(D.locErr) + "</span></p>" : "") +
      '<div style="height:20px"></div><div id="d-prog"></div><div id="d-err"></div><button type="button" class="btn primary big block" id="d-go" ' + (ready ? "" : 'aria-disabled="true"') + ">" + (D.busy ? '<span class="spinner" style="color:#fff"></span>Working...' : "Upload and scan") + '</button><div id="d-out" aria-live="polite"></div>';
    $("d-pick").onclick = function () { $("d-file").click(); };
    $("d-file").onchange = function () {
      var f = this.files[0]; this.value = ""; if (!f) return;
      if (!isVideoFile(f) && !isImageFile(f)) { D.error = ""; return setFerr("That is not a video or photo. Use MP4 or MOV videos, or JPG or PNG photos."); }
      if (f.size > 2 * 1024 * 1024 * 1024) return setFerr("That file is " + fmtSize(f.size) + ", which is too large. Trim the clip and try again.");
      D.file = f; D.result = null; D.error = ""; renderRoute(true);
    };
    function setFerr(t) { $("d-ferr").innerHTML = '<p class="banner err" style="margin-top:10px">' + icon("warn") + "<span>" + esc(t) + "</span></p>"; }
    Array.prototype.forEach.call(view.querySelectorAll(".check input"), function (c) { c.onchange = function () { D.classes = Array.prototype.map.call(view.querySelectorAll(".check input:checked"), function (x) { return x.value; }); }; });
    Array.prototype.forEach.call(view.querySelectorAll("[data-q]"), function (b) { b.onclick = function () { D.quality = b.dataset.q; renderRoute(true); }; });
    Array.prototype.forEach.call(view.querySelectorAll("[data-w]"), function (b) {
      b.onclick = function (e) {
        if (D.busy) return;
        D.where = b.dataset.w; D.locErr = "";
        if (D.where === "gpx" && !D.gpx) { renderRoute(true); var gi = $("d-gpxf"); if (gi) gi.click(); return; }
        if (D.where === "here" && !(D.lat && D.lon)) { renderRoute(true); locate(true).then(function (s) { if (s) { D.lat = s.lat.toFixed(6); D.lon = s.lon.toFixed(6); } else { D.locErr = locErr; D.where = "none"; } renderRoute(true); }); return; }
        renderRoute(true);
      };
    });
    if ($("d-gpx")) $("d-gpx").onclick = function () { $("d-gpxf").click(); };
    $("d-gpxf").onchange = function () { var f = this.files[0]; this.value = ""; if (!f) return; if (!/\.gpx$/i.test(f.name)) { D.locErr = "That is not a .gpx file."; return renderRoute(true); } D.gpx = f; D.where = "gpx"; D.locErr = ""; renderRoute(true); };
    $("d-go").onclick = function () { if (!ready) { var t = !D.file ? "Choose a video or photo first." : !D.classes.length ? "Pick at least one thing to look for." : D.where === "gpx" ? "Choose a GPX file, or pick another location option." : "Waiting for your location."; return toast(t); } runAnalysis(isVid); };
    paintDrive();
    return function () { };
  }
  function paintDrive() {
    if (current !== "drive") return;
    var pg = $("d-prog"), er = $("d-err"), out = $("d-out"); if (!pg) return;
    pg.innerHTML = D.busy ? '<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + Math.round(D.progress * 100) + '"><i style="width:' + Math.max(6, Math.round(D.progress * 100)) + '%"></i></div><p class="sub" style="margin:8px 0 14px">' + esc(D.status) + "</p>" : "";
    er.innerHTML = D.error ? '<div class="banner err" style="margin-bottom:12px">' + icon("xcircle") + "<div><b>That did not work</b>" + esc(D.error) + "</div></div>" : "";
    if (D.result) { out.innerHTML = resultHtml(D.result); bindResult(); } else out.innerHTML = "";
    var go = $("d-go"); if (go) { if (D.busy) { go.setAttribute("aria-disabled", "true"); go.className = "btn big block"; } }
  }
  function runAnalysis(isVid) {
    D.busy = true; D.error = ""; D.result = null; D.progress = 0.04; D.status = isVid ? "Uploading the clip..." : "Uploading the photo...";
    var fd = new FormData(); fd.append("file", D.file, D.file.name);
    if (isVid) fd.append("quality", D.quality);
    fd.append("classes", D.classes.join(","));
    if (D.where === "gpx" && D.gpx) fd.append("gpx_file", D.gpx, D.gpx.name);
    if (D.where === "here" && D.lat && D.lon) { fd.append("lat", D.lat); fd.append("lon", D.lon); }
    fd.append("inspector", "citizen: " + (prefs.name || "web import")); fd.append("notes", "Imported from the citizen web app");
    renderRoute(true);
    upload("/api/inspections", fd, { timeout: 900000, onProgress: function (p) { D.progress = 0.04 + p * 0.3; paintDrive(); } }).then(function (j) {
      if (!j.job_id) return j;
      D.status = isVid ? "Scanning the video frame by frame (" + D.quality.toUpperCase() + ")..." : "Analysing the photo..."; D.progress = 0.35; paintDrive();
      return pollJob(j.job_id);
    }).then(function (insp) { D.busy = false; D.result = insp; D.showPossible = false; D.isVid = isVid; renderRoute(true); if (current === "drive") { var o = $("d-out"); if (o) o.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }); } else addNotif("system", "Your video analysis is ready", "Open Drive / Import to see the boxed video and the report.", {}, "job" + Date.now()); },
      function (e) { D.busy = false; D.error = e.message; renderRoute(true); });
  }
  function pollJob(id) {
    return new Promise(function (resolve, reject) {
      var fails = 0;
      (function tick() {
        api("/api/jobs/" + id, { timeout: 15000 }).then(function (j) {
          fails = 0;
          var pr = j.progress || 0; pr = pr > 1 ? pr / 100 : pr; D.progress = Math.min(0.98, 0.35 + 0.63 * pr); paintDrive();
          if (j.status === "done") return resolve(j.inspection);
          if (j.status === "error" || j.status === "failed") return reject(new ApiError("The video could not be processed: " + (j.error || "unknown error") + ". Try a shorter clip or another format.", 500));
          setTimeout(tick, 1500);
        }, function (e) {
          if (++fails >= 6) return reject(new ApiError("We lost contact with the server while it was working. The analysis may still finish, so check the city map later. " + e.message, 0));
          setTimeout(tick, 3000);
        });
      })();
    });
  }
  function isHigh(d) { return d.tier === "high" || (d.confidence || 0) >= 0.40; }
  function resultHtml(i) {
    var s = i.summary || {}, all = (i.detections || []).filter(function (d) { return d.verification !== "rejected"; }), seen = {};
    all = all.filter(function (d) { var k = d.track_id != null ? "t" + d.track_id : "d" + d.id; if (seen[k]) return false; seen[k] = 1; return true; });
    var high = all.filter(isHigh), poss = all.length - high.length, rows = D.showPossible ? all : high, byc = {};
    rows.forEach(function (d) { var k = nice(d.final_class || d.class_name || "other"); byc[k] = (byc[k] || 0) + 1; });
    var cnts = Object.keys(byc).map(function (k) { return "<span>" + esc(k) + " " + byc[k] + "</span>"; }).join("") || "<span>none</span>";
    var media = i.annotated_url ? (D.isVid ? '<video controls autoplay muted loop playsinline aria-label="Video with damage boxed" src="' + esc(url(i.annotated_url)) + '"></video>' : '<img alt="Photo with damage boxed" src="' + esc(url(i.annotated_url)) + '">') : '<p class="sub" style="padding:16px;color:#fff">No annotated output was produced.</p>';
    rows = rows.slice().sort(function (a, b) { return (b.risk_score || 0) - (a.risk_score || 0); });
    var list = rows.slice(0, 80).map(function (d) {
      var sev = d.final_severity || d.severity || "";
      return '<div class="trow">' + (d.crop_url ? '<img alt="" loading="lazy" src="' + esc(url(d.crop_url)) + '" onerror="this.remove()">' : "") + '<span class="id">' + (d.track_id != null ? "ID " + d.track_id : "#" + d.id) + '</span><span class="nm">' + esc(nice(d.final_class || d.class_name)) + " " + Math.round((d.confidence || 0) * 100) + "%" + (isHigh(d) ? "" : ' <span class="caption">(possible)</span>') + '</span><span class="pill rk-' + esc(cap(sev)) + '">' + esc(sev) + "</span></div>";
    }).join("") || '<div class="empty" style="padding:16px"><h3>' + (poss ? "No high-confidence damage" : "No road damage found") + "</h3><p>" + (poss ? "Turn on Show possible too to review weaker detections." : "The road in this clip looks clear.") + "</p></div>";
    var falls = s.falls && s.falls.length ? '<div class="banner err" style="margin:10px 0">' + icon("warn") + "<div><b>Person down detected</b>At " + s.falls.map(function (f) { return f.time_s + " s"; }).join(", ") + " in this video.</div></div>" : "";
    return sectionHead("Result") + '<div class="vbox">' + media + '</div><div class="card" style="margin-top:12px"><div class="stats" style="margin:0 0 6px"><div class="stat s-blue"><b>' + rows.length + "</b><span>" + (D.showPossible ? "shown" : "confident") + '</span></div><div class="stat s-orange"><b>' + poss + '</b><span>possible more</span></div><div class="stat s-green"><b>' + (s.max_risk != null ? Math.round(s.max_risk) : "-") + "</b><span>top risk</span></div></div>" +
      '<div class="cnts">' + cnts + '</div><label class="check" style="margin:4px 0 10px"><input type="checkbox" id="d-poss"' + (D.showPossible ? " checked" : "") + ">Show possible too</label>" + (s.quality ? ' <span class="caption">' + esc(String(s.quality).toUpperCase()) + " mode</span>" : "") + '<p class="sub" style="font-size:12.5px">AI estimate, verified by officers. Weak detections are hidden by default.</p>' + falls + '<div class="tlist">' + list + '</div><div style="height:12px"></div><a class="btn primary big block" target="_blank" rel="noopener" href="' + esc(API + "/api/reports/analysis/" + i.id + ".pdf") + '">' + icon("download") + 'Download PDF report</a><div style="height:8px"></div><a class="btn block" href="#/map">' + icon("map") + "See it on the city map</a></div>";
  }
  function bindResult() { var c = $("d-poss"); if (c) c.onchange = function () { D.showPossible = this.checked; paintDrive(); }; }

  /* ================= sync config, boot ================= */
  function syncConfig() { api("/api/citizen/config").then(function (c) { if (c && typeof c.helpline === "string") { helpline = c.helpline; lsSet("rw-helpline", helpline); } if (current === "home") renderRoute(true); }, function () {}); }

  refreshBadge();
  if (!navigator.onLine) netBar("You are offline. Reports are saved and sent later.", "warn");
  window.addEventListener("error", function () {});
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    navigator.serviceWorker.register("sw.js").then(function (r) { swReg = r; }, function () {});
    navigator.serviceWorker.ready.then(function (r) { swReg = r; });
  }
  function applyTheme(t, save) {
    document.documentElement.setAttribute("data-theme", t);
    var m = document.getElementById("meta-theme"); if (m) m.setAttribute("content", t === "dark" ? "#1F2133" : "#F4F1DE");
    var b = $("theme-btn"); if (b) { b.setAttribute("aria-label", t === "dark" ? "Switch to light mode" : "Switch to dark mode"); b.setAttribute("aria-pressed", t === "dark" ? "true" : "false"); }
    if (save) lsSet("rw-theme", t);
  }
  applyTheme(document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark", false);
  $("theme-btn").onclick = function () { applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark", true); };
  $("lang-btn").onclick = function () {
    sheet('<h2 class="headline" style="margin:4px 0 12px">' + esc(T("lang")) + '</h2><div class="card group langs" role="radiogroup">' + I18N.langs.map(function (l) { return '<button type="button" class="langrow" role="radio" data-lg="' + l.code + '" aria-checked="' + (I18N.get() === l.code) + '"><b>' + esc(l.native) + "</b>" + icon("check") + "</button>"; }).join("") + "</div>", function (bg, close) {
      Array.prototype.forEach.call(bg.querySelectorAll("[data-lg]"), function (b) { b.onclick = function () { close(); setLang(b.dataset.lg); }; });
    });
  };
  I18N.apply();
  renderRoute();
  syncConfig();
  connectWs();
  flushQueue();
  setInterval(function () { pollComplaints(); flushQueue(); }, 30000);
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") { pollComplaints(); if (!wsOk) connectWs(); } });
  setTimeout(pollComplaints, 2500);
})();

/* Talk to Disha: opens the in-browser voice call from any button with data-talk or #talk-btn */
document.addEventListener("click", function (e) {
  var t = e.target.closest && e.target.closest("[data-talk], #talk-btn");
  if (t && window.DishaCall) { e.preventDefault(); window.RW_API_BASE = window.RW_API_BASE || (typeof API !== "undefined" ? API : undefined); window.DishaCall.open(); }
});
