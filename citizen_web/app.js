(function () {
  var API = (function () {
    try { var o = localStorage.getItem("rw-api"); if (o) return o; } catch (e) {}
    return location.protocol + "//" + location.hostname + ":8000";
  })();
  var $ = function (id) { return document.getElementById(id); };
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var device = (function () {
    try {
      var d = localStorage.getItem("rw-device");
      if (!d) { d = "web-" + Math.random().toString(36).slice(2, 12) + Date.now().toString(36); localStorage.setItem("rw-device", d); }
      return d;
    } catch (e) { return "web-session"; }
  })();
  var pos = null, checks = [];

  function toast(t) {
    var e = document.createElement("div"); e.className = "toast"; e.textContent = t;
    $("toasts").appendChild(e); setTimeout(function () { e.remove(); }, 6000);
  }
  function show(tab) {
    document.querySelectorAll("#tabs button").forEach(function (b) { b.classList.toggle("on", b.dataset.tab === tab); });
    document.querySelectorAll(".pane").forEach(function (p) { p.className = "pane" + (p.id === "tab-" + tab ? " on" : ""); });
    if (tab === "mine") loadMine();
    if (tab === "alerts") { unread = 0; alerts.forEach(function (a) { a.read = true; }); renderAlerts(); }
    window.scrollTo(0, 0);
    if (tab === "map" && !$("mapframe").getAttribute("src")) $("mapframe").setAttribute("src", API + "/map");
  }
  document.querySelectorAll("#tabs button").forEach(function (b) { b.onclick = function () { show(b.dataset.tab); }; });

  $("gps").onclick = function () {
    if (!navigator.geolocation) { $("gps-note").textContent = "Location is not available here. Type the street instead."; return; }
    $("gps-note").textContent = "Finding you...";
    navigator.geolocation.getCurrentPosition(function (p) {
      pos = { lat: p.coords.latitude, lon: p.coords.longitude };
      $("gps-note").textContent = "Location set (" + pos.lat.toFixed(5) + ", " + pos.lon.toFixed(5) + ", accuracy about " + Math.round(p.coords.accuracy) + " m).";
    }, function () { $("gps-note").textContent = "Location permission denied. Type the street instead."; }, { enableHighAccuracy: true, timeout: 15000 });
  };

  function checkRow(f) {
    var row = document.createElement("div"); row.className = "chk";
    var img = document.createElement("img");
    if (f.type.indexOf("image") === 0) img.src = URL.createObjectURL(f);
    var t = document.createElement("div"); t.className = "t"; t.textContent = f.name;
    var pill = document.createElement("span"); pill.className = "pill wait"; pill.textContent = "Checking";
    row.appendChild(img); row.appendChild(t); row.appendChild(pill);
    $("checks").appendChild(row);
    var fd = new FormData(); fd.append("file", f); fd.append("device_id", device);
    var rec = { file: f, token: null, verdict: "wait" };
    rec.done = fetch(API + "/api/screening/check", { method: "POST", body: fd }).then(function (r) { return r.json(); }).then(function (j) {
      rec.verdict = j.verdict; rec.token = j.token;
      pill.className = "pill " + j.verdict;
      pill.textContent = j.verdict === "pass" ? "Road damage found" : j.verdict === "rate_limited" ? "Too many failed checks" : "No road damage seen";
      t.textContent = f.name + (j.reason ? " - " + j.reason : "");
      if (j.preview_url) img.src = API + j.preview_url;
      rec.info = j; renderScreen();
    }).catch(function () { rec.verdict = "fail"; pill.className = "pill fail"; pill.textContent = "Check failed"; });
    return rec;
  }
  function renderScreen() {
    var box = $("screen"), done = checks.filter(function (c) { return c.info; });
    if (!done.length) { box.classList.add("hidden"); return; }
    box.classList.remove("hidden");
    box.innerHTML = done.map(function (c) {
      var j = c.info, ok = j.verdict === "pass";
      var found = j.damage_found || j.damages || j.findings || j.detections || [];
      var names = (Array.isArray(found) ? found : []).map(function (d) { return typeof d === "string" ? d : (d.class_name || d.label || ""); }).filter(Boolean);
      var title = ok ? "Road damage found" : j.verdict === "rate_limited" ? "Too many failed checks, try later" : "No road damage seen";
      return "<div class=\"screen " + esc(j.verdict) + "\"><div class=\"sc\">" + (j.preview_url ? "<img alt=\"preview\" src=\"" + esc(API + j.preview_url) + "\">" : "") +
        "<div><h3>" + esc(title) + "</h3><div class=\"note\">" + esc(c.file.name) + (j.reason ? ": " + esc(j.reason) : "") + "</div>" +
        (names.length ? "<div class=\"cnts\">" + names.map(function (n) { return "<span>" + esc(String(n).replace(/_/g, " ")) + "</span>"; }).join("") + "</div>" : "") +
        "</div></div></div>";
    }).join("");
  }
  $("files").onchange = function () {
    $("screen").classList.add("hidden");
    $("checks").innerHTML = ""; checks = [];
    Array.prototype.forEach.call($("files").files, function (f) { checks.push(checkRow(f)); });
  };

  $("form").onsubmit = function (e) {
    e.preventDefault();
    var msg = $("msg"); msg.className = "note"; msg.textContent = "";
    if (!checks.length && !$("desc").value.trim()) { msg.className = "note err"; msg.textContent = "Add a photo or video, or describe the problem."; return; }
    if (!pos && !$("addr").value.trim()) { msg.className = "note err"; msg.textContent = "Tell us where it is: use your location or type the street."; return; }
    $("submit").disabled = true; msg.textContent = "Checking your media...";
    Promise.all(checks.map(function (c) { return c.done; })).then(function () {
      var bad = checks.filter(function (c) { return c.verdict !== "pass"; });
      if (bad.length) { throw new Error("Remove the files that do not show road damage, then submit again."); }
      var fd = new FormData();
      fd.append("category", $("category").value); fd.append("description", $("desc").value);
      fd.append("device_id", device);
      if ($("name").value) fd.append("citizen_name", $("name").value);
      if ($("phone").value) fd.append("citizen_phone", $("phone").value);
      if ($("addr").value) fd.append("address", $("addr").value);
      if (pos) { fd.append("lat", pos.lat); fd.append("lon", pos.lon); }
      fd.append("screening_tokens", checks.map(function (c) { return c.token; }).join(","));
      checks.forEach(function (c) { fd.append("files", c.file); });
      msg.textContent = "Sending...";
      return fetch(API + "/api/complaints", { method: "POST", body: fd });
    }).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Could not file the report"); return j; });
    }).then(function (j) {
      $("form").classList.add("hidden");
      var d = $("done"); d.classList.remove("hidden");
      d.innerHTML = "<h2>Report filed</h2><p>Your ticket is <b>" + esc(j.ticket) + "</b>. Follow it under My reports. Thank you for helping fix the road.</p><button class=\"primary\" id=\"again\">Report another</button>";
      $("again").onclick = function () { location.reload(); };
    }).catch(function (err) { msg.className = "note err"; msg.textContent = err.message; })
      .then(function () { $("submit").disabled = false; });
  };

  var ICON_PATH = { doc: "<rect x=\"5\" y=\"3\" width=\"14\" height=\"18\" rx=\"2\"/><path d=\"M9 8h6M9 12h6M9 16h4\"/>", bell: "<path d=\"M6 16V11a6 6 0 1112 0v5l2 2H4z\"/><path d=\"M10 21h4\"/>" };
  function emptyState(t, d, ic) { return "<div class=\"empty\"><svg viewBox=\"0 0 24 24\">" + ICON_PATH[ic || "doc"] + "</svg><b>" + esc(t) + "</b><span>" + esc(d) + "</span></div>"; }
  function loadMine() {
    var box = $("mine"); box.innerHTML = "<div class=\"skel\"></div><div class=\"skel\"></div>";
    fetch(API + "/api/complaints?device_id=" + encodeURIComponent(device)).then(function (r) { return r.json(); }).then(function (list) {
      if (!Array.isArray(list) || !list.length) { box.innerHTML = emptyState("No reports yet", "Reports you file from this browser show up here with live status."); return; }
      box.innerHTML = list.map(function (c) {
        var imgs = (c.media || []).filter(function (m) { return m.media_type !== "video" && (m.annotated_url || m.media_url); }).slice(0, 3).map(function (m) {
          return "<img alt=\"report photo\" src=\"" + esc(API + (m.annotated_url || m.media_url)) + "\">";
        }).join("");
        var f = (c.findings || []).length ? (c.findings.length + " damage found by the AI check") : "";
        var where = c.address || (c.lat != null ? c.lat.toFixed(4) + ", " + c.lon.toFixed(4) : "no location");
        return "<article class=\"rep\"><h3>" + esc(c.ticket) + "<span class=\"st " + esc(c.status) + "\">" + esc(String(c.status).replace("_", " ")) + "</span></h3>" +
          "<div class=\"sub\">" + esc(c.category) + ", " + esc(where) + " " + esc(f) + "</div>" +
          (c.admin_note ? "<p><b>Note from the team:</b> " + esc(c.admin_note) + "</p>" : "") + imgs + "</article>";
      }).join("");
    }).catch(function () { box.innerHTML = "<p class=\"note err\">Could not load your reports. Is the server running?</p>"; });
  }

  // ---- 3D tilt on cards
  document.querySelectorAll(".tilt").forEach(function (el) {
    el.addEventListener("mousemove", function (e) {
      var r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      el.style.transform = "rotateY(" + (x * 5).toFixed(2) + "deg) rotateX(" + (-y * 4).toFixed(2) + "deg)";
    });
    el.addEventListener("mouseleave", function () { el.style.transform = ""; });
  });

  // ---- video / photo analysis with boxed output
  var vq = "2k";
  document.querySelectorAll(".seg button").forEach(function (b) {
    b.onclick = function () { vq = b.dataset.q; document.querySelectorAll(".seg button").forEach(function (x) { x.className = x === b ? "on" : ""; }); };
  });
  $("vgps").onclick = function () {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(function (p) { $("vlat").value = p.coords.latitude.toFixed(6); $("vlon").value = p.coords.longitude.toFixed(6); });
  };
  function vmsg(t, err) { $("vmsg").className = "note" + (err ? " err" : ""); $("vmsg").textContent = t; }
  $("vgo").onclick = function () {
    var f = $("vfile").files[0];
    if (!f) { vmsg("Choose a video or photo first.", true); return; }
    var isVid = f.type.indexOf("video") === 0 || /\.(mp4|mov|avi|mkv|webm)$/i.test(f.name);
    var fd = new FormData(); fd.append("file", f);
    if (isVid) fd.append("quality", vq);
    var cls = Array.prototype.map.call(document.querySelectorAll("#classes input:checked"), function (x) { return x.value; });
    if (!cls.length) { vmsg("Pick at least one thing to look for.", true); return; }
    fd.append("classes", cls.join(","));
    if ($("vlat").value && $("vlon").value) { fd.append("lat", $("vlat").value); fd.append("lon", $("vlon").value); }
    fd.append("inspector", "citizen-web");
    $("vgo").disabled = true; $("vout").classList.add("hidden"); $("vprog").classList.remove("hidden"); $("vbar").style.width = "6%";
    vmsg(isVid ? "Uploading and analyzing in " + vq.toUpperCase() + " mode..." : "Analyzing photo...");
    fetch(API + "/api/inspections", { method: "POST", body: fd }).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Upload failed"); return j; });
    }).then(function (j) {
      if (j.job_id) return pollJob(j.job_id);
      return j;
    }).then(function (insp) { renderResult(insp, isVid); vmsg(""); })
      .catch(function (e) { vmsg(e.message, true); })
      .then(function () { $("vgo").disabled = false; $("vprog").classList.add("hidden"); });
  };
  function pollJob(id) {
    return new Promise(function (resolve, reject) {
      (function tick() {
        fetch(API + "/api/jobs/" + id).then(function (r) { return r.json(); }).then(function (j) {
          var pct = Math.max(6, Math.round((j.progress || 0) * (j.progress > 1 ? 1 : 100)));
          $("vbar").style.width = Math.min(pct, 98) + "%";
          if (j.status === "done") return resolve(j.inspection);
          if (j.status === "error" || j.status === "failed") return reject(new Error(j.error || "Analysis failed"));
          setTimeout(tick, 1200);
        }).catch(reject);
      })();
    });
  }
  var lastInsp = null, lastVid = false, showPossible = false;
  function isHigh(d) { return d.tier === "high" || (d.confidence || 0) >= 0.40; }
  function renderResult(i, isVid) {
    var fresh = !!i;
    if (i) { lastInsp = i; lastVid = isVid; showPossible = false; } else { i = lastInsp; isVid = lastVid; }
    var s = i.summary || {}, all = (i.detections || []).filter(function (d) { return d.verification !== "rejected"; });
    var seen = {};
    all = all.filter(function (d) { var k = d.track_id != null ? "t" + d.track_id : "d" + d.id; if (seen[k]) return false; seen[k] = 1; return true; });
    var high = all.filter(isHigh), poss = all.length - high.length;
    var rows = showPossible ? all : high;
    var byc = {};
    rows.forEach(function (d) { var k = String(d.final_class || d.class_name || "other").replace(/_/g, " "); byc[k] = (byc[k] || 0) + 1; });
    var cnts = Object.keys(byc).map(function (k) { return "<span>" + esc(k) + " " + byc[k] + "</span>"; }).join("") || "<span>none</span>";
    var media = i.annotated_url ? (isVid
      ? "<video controls autoplay muted loop playsinline src=\"" + esc(API + i.annotated_url) + "\"></video>"
      : "<img alt=\"annotated photo\" src=\"" + esc(API + i.annotated_url) + "\">") : "<p class=\"note\">No annotated output.</p>";
    rows = rows.slice().sort(function (a, b) { return (b.risk_score || 0) - (a.risk_score || 0); });
    var list = rows.slice(0, 80).map(function (d) {
      return "<div class=\"trow\">" + (d.crop_url ? "<img alt=\"\" src=\"" + esc(API + d.crop_url) + "\">" : "") +
        "<span class=\"id\">" + (d.track_id != null ? "ID " + d.track_id : "#" + d.id) + "</span><span>" + esc(String(d.final_class || d.class_name).replace(/_/g, " ")) + " " + Math.round((d.confidence || 0) * 100) + "%</span>" +
        (isHigh(d) ? "" : "<span class=\"tier\">possible</span>") +
        "<span class=\"sev " + esc(d.final_severity || d.severity) + "\">" + esc(d.final_severity || d.severity || "") + "</span></div>";
    }).join("") || emptyState(poss ? "No high-confidence damage" : "No road damage found", poss ? "Turn on Show possible too to review weaker detections." : "The road in this clip looks clear.");
    var o = $("vout"); o.classList.remove("hidden");
    o.innerHTML = "<div class=\"vgrid\"><div class=\"vbox tilt\">" + media + "</div><div class=\"card tilt\">" +
      "<div class=\"stats\"><div class=\"stat\"><b>" + rows.length + "</b><span>" + (showPossible ? "defects shown" : "high-confidence") + "</span></div>" +
      "<div class=\"stat\"><b>" + poss + "</b><span>possible more</span></div>" +
      "<div class=\"stat\"><b>" + (s.max_risk != null ? Math.round(s.max_risk) : "-") + "</b><span>top risk</span></div></div>" +
      "<div class=\"cnts\">" + cnts + "</div>" +
      "<div class=\"vtog\"><label><input type=\"checkbox\" id=\"vposs\"" + (showPossible ? " checked" : "") + "> Show possible too</label><span class=\"note\">" + (s.quality ? String(s.quality).toUpperCase() + " mode" : "") + "</span></div>" +
      "<p class=\"note\">AI estimate, verified by officers. Weak detections are hidden by default.</p>" +
      "<div class=\"tlist\">" + list + "</div>" +
      "<a class=\"btn3d primary\" style=\"text-align:center;text-decoration:none\" target=\"_blank\" href=\"" + API + "/api/reports/analysis/" + i.id + ".pdf\">Download PDF report</a>" +
      "</div></div>";
    $("vposs").onchange = function () { showPossible = this.checked; renderResult(null); };
    if (fresh) o.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---- alarm siren (WebAudio) and alerts
  var alerts = [], unread = 0, seenIds = {}, actx = null, siren = null, soundOn = false, curAlarm = null;
  try { soundOn = localStorage.getItem("rw-sound") === "1"; } catch (e) {}
  function ctx() { try { if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)(); if (actx.state === "suspended") actx.resume(); } catch (e) {} return actx; }
  function setSnd() { var b = $("sound"); b.classList.toggle("on", soundOn); b.textContent = soundOn ? "Alarm sound on" : "Enable alarm sound"; }
  function beep() {
    var c = ctx(); if (!c) return;
    var o = c.createOscillator(), g = c.createGain(); o.type = "square"; o.frequency.value = 880; g.gain.value = 0.2;
    o.connect(g); g.connect(c.destination); o.start(); o.stop(c.currentTime + 0.25);
  }
  function startSiren() {
    if (siren) return; var c = ctx(); if (!c) return;
    var o = c.createOscillator(), g = c.createGain(), lfo = c.createOscillator(), lg = c.createGain();
    o.type = "sawtooth"; o.frequency.value = 900; lfo.type = "triangle"; lfo.frequency.value = 1.6; lg.gain.value = 350; g.gain.value = 0.5;
    lfo.connect(lg); lg.connect(o.frequency); o.connect(g); g.connect(c.destination); o.start(); lfo.start();
    siren = { stop: function () { try { o.stop(); lfo.stop(); } catch (e) {} } };
  }
  function stopSiren() { if (siren) { siren.stop(); siren = null; } }
  $("sound").onclick = function () { soundOn = !soundOn; try { localStorage.setItem("rw-sound", soundOn ? "1" : "0"); } catch (e) {} setSnd(); if (soundOn) beep(); };
  setSnd();
  function showAlarm(d) {
    curAlarm = d;
    $("a-msg").textContent = d.message || "A person has fallen near a road defect.";
    $("a-loc").textContent = d.lat != null ? "Location: " + Number(d.lat).toFixed(5) + ", " + Number(d.lon).toFixed(5) : "";
    var im = $("a-img"); if (d.snapshot_url) { im.src = API + d.snapshot_url; im.classList.remove("hidden"); } else im.classList.add("hidden");
    $("a-map").classList.toggle("hidden", false);
    $("alarm").classList.remove("hidden");
    if (soundOn) startSiren(); else toast("Enable alarm sound in the header to hear emergency sirens");
    if (navigator.vibrate) { try { navigator.vibrate([400, 200, 400, 200, 400]); } catch (e) {} }
  }
  $("a-off").onclick = function () { stopSiren(); $("alarm").classList.add("hidden"); };
  $("a-map").onclick = function () { stopSiren(); openMap(curAlarm); };
  function openMap(d) {
    show("map");
    if (d && d.lat != null) $("mapframe").setAttribute("src", API + "/map#" + d.lat + "," + d.lon);
  }
  $("al-test").onclick = function () {
    if (!soundOn) { soundOn = true; try { localStorage.setItem("rw-sound", "1"); } catch (e) {} setSnd(); }
    showAlarm({ message: "This is a test alarm. No one is hurt." }); setTimeout(stopSiren, 3000);
  };
  $("al-clear").onclick = function () { unread = 0; alerts.forEach(function (a) { a.read = true; }); renderAlerts(); };
  function addAlert(kind, title, text, d, key) {
    if (key) { if (seenIds[key]) return; seenIds[key] = 1; }
    var onTab = $("tab-alerts").classList.contains("on");
    alerts.unshift({ kind: kind, title: title, text: text, d: d || {}, at: (d && d.created_at) ? new Date(d.created_at) : new Date(), read: onTab });
    alerts.length = Math.min(alerts.length, 30);
    if (!onTab) unread++;
    renderAlerts();
  }
  function renderAlerts() {
    var b = $("badge"); b.textContent = unread > 9 ? "9+" : unread; b.classList.toggle("hidden", !unread);
    $("alerts").innerHTML = alerts.length ? alerts.map(function (a, n) {
      return "<div class=\"al " + a.kind + (a.read ? "" : " unread") + "\">" + (a.d.snapshot_url ? "<img alt=\"\" src=\"" + esc(API + a.d.snapshot_url) + "\">" : "") +
        "<div class=\"grow\"><b>" + esc(a.title) + "</b><div class=\"note\">" + esc(a.text) + "</div><small>" + a.at.toLocaleTimeString() + "</small></div>" +
        (a.d.lat != null ? "<button class=\"btn3d\" data-n=\"" + n + "\">Map</button>" : "") + "</div>";
    }).join("") : emptyState("All quiet", "Safety alerts and repair news will appear here as they happen.", "bell");
    document.querySelectorAll("#alerts button[data-n]").forEach(function (x) {
      x.onclick = function () { openMap(alerts[+x.dataset.n].d); };
    });
  }
  function handle(m, live) {
    var t = m.type || "", d = m.data || {};
    if (t === "emergency.fall") {
      addAlert("safety", "Person down", d.message || "Emergency near a road defect", d, "f" + (d.id || d.created_at));
      if (live) showAlarm(d);
    } else if (/^map\./.test(t)) {
      var cls = d["class"] ? String(d["class"]).replace(/_/g, " ") : "road damage";
      var tag = d.number != null ? " #" + d.number : "";
      if (t === "map.repair") addAlert("repair", "Road defect repaired", "A defect" + tag + " was fixed and verified.", d, "r" + (d.uid || d.number) + "-" + d.lat);
      else if (t === "map.defect") addAlert("info", d["new"] ? "New road damage" : "Road damage updated", cls + tag + (d.severity ? ", severity " + d.severity : "") + (d.reports > 1 ? ", " + d.reports + " reports" : ""), d, null);
      else if (t === "map.report") addAlert("info", "New citizen report", (d.category || "Road issue") + " reported nearby.", d, null);
    }
  }
  renderAlerts();

  var retry = 1000;
  function connect() {
    var ws = new WebSocket(API.replace("http", "ws") + "/ws/events");
    ws.onopen = function () { retry = 1000; $("live").className = "live on"; $("live").lastChild.textContent = "Live"; };
    ws.onmessage = function (e) {
      var m; try { m = JSON.parse(e.data); } catch (_) { return; }
      if (m.type === "hello") { (m.recent || []).forEach(function (r) { handle(r, false); }); return; }
      handle(m, true);
      if (m.type === "map.repair") toast("A road defect was marked repaired");
      if (m.type === "map.defect") toast("New road damage reported on the map");
      if (/complaint/.test(m.type || "") && $("tab-mine").classList.contains("on")) loadMine();
    };
    ws.onclose = function () { $("live").className = "live"; $("live").lastChild.textContent = "Reconnecting"; setTimeout(connect, retry = Math.min(retry * 2, 15000)); };
  }
  connect();
})();
