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
  var COLORS = { pothole: "#ff3b30", alligator_crack: "#ff9500", transverse_crack: "#0a84ff", longitudinal_crack: "#bf5af2", manhole: "#1f8cc7", speed_breaker: "#f2b705", debris: "#8c7a3c", barricade: "#c8c8c8" };
  var PREFIX = { pothole: "PH", alligator_crack: "AC", transverse_crack: "TC", longitudinal_crack: "LC", manhole: "MH", speed_breaker: "SB", debris: "DB", barricade: "BR" };
  var CLASSES = Object.keys(COLORS);
  var nice = function (s) { return String(s || "").replace(/_/g, " "); };

  // tilt effect
  document.querySelectorAll(".tilt").forEach(function (el) {
    el.addEventListener("mousemove", function (e) {
      var r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      el.style.transform = "rotateY(" + (x * 2.2) + "deg) rotateX(" + (-y * 2.2) + "deg)";
    });
    el.addEventListener("mouseleave", function () { el.style.transform = ""; });
  });

  // tabs
  var curTab = "cam";
  document.querySelectorAll("[data-tab]").forEach(function (b) {
    b.onclick = function () {
      curTab = b.dataset.tab;
      document.querySelectorAll("[data-tab]").forEach(function (x) { x.classList.toggle("on", x === b); });
      document.querySelectorAll(".pane").forEach(function (p) { p.classList.toggle("on", p.id === "tab-" + curTab); });
    };
  });

  // options
  $("clsList").innerHTML = CLASSES.map(function (c) {
    return "<label><input type=\"checkbox\" value=\"" + c + "\" checked><i style=\"background:" + COLORS[c] + "\"></i>" + nice(c) + "</label>";
  }).join("");
  function selected() { return Array.prototype.map.call($("clsList").querySelectorAll("input:checked"), function (i) { return i.value; }); }
  $("selAll").onclick = function () { $("clsList").querySelectorAll("input").forEach(function (i) { i.checked = true; }); sendConfig(); };
  $("selNone").onclick = function () { $("clsList").querySelectorAll("input").forEach(function (i) { i.checked = false; }); sendConfig(); };
  document.querySelectorAll("#clsList input,#optPeople,#optHaz,#optCracks").forEach(function (i) { i.addEventListener("change", sendConfig); });
  var quality = "2k";
  document.querySelectorAll("#qseg button").forEach(function (b) {
    b.onclick = function () { quality = b.dataset.q; document.querySelectorAll("#qseg button").forEach(function (x) { x.className = x === b ? "on" : ""; }); };
  });
  function getLoc() { var a = parseFloat($("lat").value), b = parseFloat($("lon").value); return isFinite(a) && isFinite(b) ? [a, b] : null; }
  $("gps").onclick = function () {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(function (p) {
      $("lat").value = p.coords.latitude.toFixed(6); $("lon").value = p.coords.longitude.toFixed(6); sendGps();
    }, function () {});
  };
  $("lat").addEventListener("change", sendGps); $("lon").addEventListener("change", sendGps);

  // ---------- alarm
  var actx = null, siren = null, alarmOn = false;
  try { alarmOn = localStorage.getItem("rw-alarm") === "1"; } catch (e) {}
  function refreshAlarmBtn() { $("alarmEnable").textContent = alarmOn ? "Alarm sound enabled" : "Enable alarm sound"; $("alarmEnable").classList.toggle("on", alarmOn); }
  refreshAlarmBtn();
  function ctx() {
    var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return null;
    if (!actx) actx = new AC();
    if (actx.state === "suspended") actx.resume().catch(function () {});
    return actx;
  }
  function beep() {
    var c = ctx(); if (!c) return;
    var o = c.createOscillator(), g = c.createGain(), t = c.currentTime;
    o.type = "sine"; o.frequency.value = 880;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.3, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.3);
    o.connect(g).connect(c.destination); o.start(t); o.stop(t + 0.32);
  }
  $("alarmEnable").onclick = function () {
    alarmOn = true; try { localStorage.setItem("rw-alarm", "1"); } catch (e) {}
    refreshAlarmBtn(); beep();
  };
  function startSiren() {
    if (siren) return;
    var c = ctx(); if (!c) return;
    var o = c.createOscillator(), g = c.createGain();
    o.type = "sawtooth"; g.gain.value = 0.35;
    o.connect(g).connect(c.destination); o.start();
    var t0 = performance.now();
    var timer = setInterval(function () {
      var ph = ((performance.now() - t0) % 1200) / 1200;
      var f = 600 + 500 * (ph < 0.5 ? ph * 2 : (1 - ph) * 2);
      o.frequency.setValueAtTime(f, c.currentTime);
    }, 30);
    siren = { o: o, g: g, timer: timer };
  }
  function stopSiren() {
    if (!siren) return;
    clearInterval(siren.timer);
    try { siren.g.gain.setTargetAtTime(0.0001, siren.o.context.currentTime, 0.03); siren.o.stop(siren.o.context.currentTime + 0.15); } catch (e) {}
    siren = null;
  }
  var lastAlarmId = null;
  function raiseAlarm(em) {
    em = em || {};
    var key = em.id != null ? em.id : "x";
    if ($("alarm").classList.contains("show") && lastAlarmId === key) return;
    lastAlarmId = key;
    $("almsg").textContent = em.message || "A person has fallen. Check on them now.";
    var l = getLoc();
    $("alloc").textContent = em.lat != null && em.lon != null ? "Location: " + Number(em.lat).toFixed(5) + ", " + Number(em.lon).toFixed(5) : (l ? "Location: " + l[0] + ", " + l[1] : "Location unknown");
    var im = $("alsnap");
    if (em.snapshot_url) { im.src = API + em.snapshot_url; im.classList.remove("hidden"); } else im.classList.add("hidden");
    $("alarm").classList.add("show");
    startSiren();
  }
  $("aldis").onclick = function () { $("alarm").classList.remove("show"); stopSiren(); };
  $("alarmTest").onclick = function () {
    raiseAlarm({ id: "test" + Date.now(), message: "Test alarm: simulated person down.", lat: null, lon: null });
  };

  // ---------- status + events socket
  var retry = 1000;
  function setStatus(txt, cls) { $("status").className = "chip " + (cls || ""); $("status").lastChild.textContent = txt; }
  function connectEvents() {
    var ws;
    try { ws = new WebSocket(API.replace("http", "ws") + "/ws/events"); } catch (e) { return; }
    ws.onopen = function () { retry = 1000; setStatus("Live", "on"); };
    ws.onmessage = function (e) {
      var m; try { m = JSON.parse(e.data); } catch (_) { return; }
      if (m.type === "emergency.fall") raiseAlarm(m.data || m.payload || m);
      if (m.type === "inspection.created" || m.type === "live.saved") loadRecent();
    };
    ws.onclose = function () { setStatus("Reconnecting", "bad"); setTimeout(connectEvents, retry = Math.min(retry * 2, 15000)); };
  }
  connectEvents();

  // ---------- recent
  function loadRecent() {
    fetch(API + "/api/inspections?limit=10").then(function (r) { return r.json(); }).then(function (j) {
      var arr = Array.isArray(j) ? j : (j.items || j.inspections || []);
      $("recent").innerHTML = arr.map(function (i) {
        return "<div class=\"up\"><b>#" + i.id + "</b><span>" + esc(i.media_type || "") + " " + esc(i.original_name || "") + "</span><a target=\"_blank\" href=\"" + API + "/api/reports/analysis/" + i.id + ".pdf\">PDF</a></div>";
      }).join("") || "<p class=\"note\">No uploads yet.</p>";
    }).catch(function () {});
  }
  loadRecent();

  // ---------- upload (video / photo)
  function form(f, isVid) {
    var fd = new FormData(); fd.append("file", f);
    if (isVid) fd.append("quality", quality);
    fd.append("classes", selected().join(","));
    var l = getLoc(); if (l) { fd.append("lat", l[0]); fd.append("lon", l[1]); }
    fd.append("inspector", $("insp").value || "operator");
    return fd;
  }
  function post(fd) {
    return fetch(API + "/api/inspections", { method: "POST", body: fd }).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Upload failed"); return j; });
    });
  }
  function pollJob(id, bar) {
    return new Promise(function (resolve, reject) {
      (function tick() {
        fetch(API + "/api/jobs/" + id).then(function (r) { return r.json(); }).then(function (j) {
          var p = Math.max(6, Math.round((j.progress || 0) * (j.progress > 1 ? 1 : 100)));
          if (bar) bar.style.width = Math.min(p, 98) + "%";
          if (j.status === "done") return resolve(j.inspection);
          if (j.status === "error" || j.status === "failed") return reject(new Error(j.error || "Analysis failed"));
          setTimeout(tick, 1200);
        }).catch(reject);
      })();
    });
  }
  function resultHtml(i, isVid) {
    var s = i.summary || {}, dets = (i.detections || []).filter(function (d) { return d.verification !== "rejected"; });
    var byc = s.by_class || {}, classes = Object.keys(byc).map(function (k) { return nice(k) + " " + byc[k]; }).join(", ");
    var media = i.annotated_url ? (isVid
      ? "<video controls autoplay muted loop playsinline src=\"" + esc(API + i.annotated_url) + "\"></video>"
      : "<img alt=\"annotated\" src=\"" + esc(API + i.annotated_url) + "\">") : "<p class=\"note\">No annotated output.</p>";
    var seen = {}, rows = dets.filter(function (d) { var k = d.track_id != null ? "t" + d.track_id : "d" + d.id; if (seen[k]) return false; seen[k] = 1; return true; });
    rows.sort(function (a, b) { return (b.risk_score || 0) - (a.risk_score || 0); });
    var list = rows.slice(0, 80).map(function (d) {
      return "<div class=\"trow\">" + (d.crop_url ? "<img alt=\"\" src=\"" + esc(API + d.crop_url) + "\">" : "") +
        "<span class=\"id\">" + (d.track_id != null ? "ID " + d.track_id : "#" + d.id) + "</span><span>" + esc(nice(d.final_class || d.class_name)) + " " + Math.round((d.confidence || 0) * 100) + "%</span>" +
        "<span class=\"sev " + esc(d.final_severity || d.severity) + "\">" + esc(d.final_severity || d.severity || "") + "</span></div>";
    }).join("") || "<p class=\"note\">No road damage found.</p>";
    return "<div class=\"vgrid\"><div class=\"vbox\">" + media + "</div><div class=\"card\">" +
      "<div class=\"stats\"><div class=\"stat\"><b>" + (s.total != null ? s.total : rows.length) + "</b><span>defects</span></div>" +
      "<div class=\"stat\"><b>" + (s.unique_tracks != null ? s.unique_tracks : rows.length) + "</b><span>tracked IDs</span></div>" +
      "<div class=\"stat\"><b>" + (s.max_risk != null ? Math.round(s.max_risk) : "-") + "</b><span>top risk</span></div></div>" +
      "<p class=\"note\">" + esc(classes || "No classes") + "</p><div class=\"tlist\">" + list + "</div>" +
      "<a class=\"btn3d primary\" style=\"text-align:center;text-decoration:none\" target=\"_blank\" href=\"" + API + "/api/reports/analysis/" + i.id + ".pdf\">Download PDF report</a></div></div>";
  }
  $("vgo").onclick = function () {
    var f = $("vfile").files[0];
    if (!f) { $("vmsg").textContent = "Choose a video first."; return; }
    $("vgo").disabled = true; $("vout").innerHTML = ""; $("vprog").classList.remove("hidden"); $("vbar").style.width = "6%";
    $("vmsg").className = "note"; $("vmsg").textContent = "Uploading and analyzing in " + quality.toUpperCase() + " mode...";
    post(form(f, true)).then(function (j) { return j.job_id ? pollJob(j.job_id, $("vbar")) : j; })
      .then(function (i) { $("vout").innerHTML = resultHtml(i, true); $("vmsg").textContent = ""; loadRecent(); })
      .catch(function (e) { $("vmsg").className = "note err"; $("vmsg").textContent = e.message; })
      .then(function () { $("vgo").disabled = false; $("vprog").classList.add("hidden"); });
  };
  $("pgo").onclick = function () {
    var fs = Array.prototype.slice.call($("pfile").files);
    if (!fs.length) { $("pmsg").textContent = "Choose photo(s) first."; return; }
    $("pgo").disabled = true; $("pout").innerHTML = ""; var n = 0;
    fs.reduce(function (p, f) {
      return p.then(function () {
        $("pmsg").className = "note"; $("pmsg").textContent = "Analyzing " + (++n) + " of " + fs.length + "...";
        return post(form(f, false)).then(function (j) { return j.job_id ? pollJob(j.job_id) : j; })
          .then(function (i) { $("pout").insertAdjacentHTML("beforeend", resultHtml(i, false)); })
          .catch(function (e) { $("pout").insertAdjacentHTML("beforeend", "<p class=\"note err\">" + esc(f.name) + ": " + esc(e.message) + "</p>"); });
      });
    }, Promise.resolve()).then(function () { $("pmsg").textContent = "Done."; $("pgo").disabled = false; loadRecent(); });
  };

  // ---------- live camera
  var lv = $("lv"), lc = $("lc"), grab = document.createElement("canvas");
  var ws = null, running = false, inflight = 0, sentQ = [], shown = null, last = null, SEND_W = 640;
  function wsSend(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }
  function sendConfig() { wsSend({ type: "config", cracks: $("optCracks").checked, classes: selected(), people: $("optPeople").checked, hazards: $("optHaz").checked }); }
  function sendGps() { var l = getLoc(); if (l) wsSend({ type: "gps", lat: l[0], lon: l[1] }); }
  function cmsg(t, err) { $("cmsg").className = "note" + (err ? " err" : ""); $("cmsg").textContent = t; }

  function connectLive() {
    return new Promise(function (ok, bad) {
      var s = new WebSocket(API.replace("http", "ws") + "/ws/live");
      s.binaryType = "arraybuffer";
      s.onopen = function () { ws = s; sendConfig(); sendGps(); ok(s); };
      s.onerror = function () { bad(new Error("Cannot reach the detection server")); };
      s.onclose = function () { if (ws === s) { running = false; $("lhud").textContent = "disconnected"; } };
      s.onmessage = function (e) {
        if (ws !== s) return;
        var m = JSON.parse(e.data);
        if (m.type === "frame") {
          inflight = Math.max(0, inflight - 1);
          var pend = sentQ.shift();
          if (pend) pend.then(function (bm) { shown = bm; last = m; }); else last = m;
          $("lhud").textContent = "frame " + m.frame + " | unique " + m.unique + " | " + m.infer_ms + " ms";
          if (m.emergency) raiseAlarm(m.emergency);
          pump();
        } else if (m.type === "error") { inflight = Math.max(0, inflight - 1); sentQ.shift(); pump(); }
        else if (m.type === "saved") {
          running = false;
          $("cres").innerHTML = m.inspection_id
            ? "<div class=\"card ok\"><b>Saved as inspection #" + m.inspection_id + "</b><p class=\"note\">" + m.defects.length + " defects, " + m.defects.filter(function (d) { return d.duplicate; }).length + " matched existing records.</p><a class=\"btn3d primary\" style=\"text-decoration:none;text-align:center\" target=\"_blank\" href=\"" + API + "/api/reports/analysis/" + m.inspection_id + ".pdf\">Download PDF report</a></div>"
            : "<p class=\"note\">Nothing confirmed to save.</p>";
          cmsg(""); loadRecent();
        }
      };
    });
  }
  function sendOne() {
    if (!running || !ws || ws.readyState !== 1 || !lv.videoWidth || lv.paused || lv.ended) return false;
    var sc = Math.min(1, SEND_W / lv.videoWidth);
    grab.width = Math.round(lv.videoWidth * sc); grab.height = Math.round(lv.videoHeight * sc);
    grab.getContext("2d").drawImage(lv, 0, 0, grab.width, grab.height);
    inflight++;
    sentQ.push(createImageBitmap(grab));
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
  function stopLive() {
    stopStream();
    running = false;
    if (ws) { var s = ws; ws = null; try { s.close(); } catch (e) {} }
    if (lv.srcObject) { lv.srcObject.getTracks().forEach(function (t) { t.stop(); }); lv.srcObject = null; }
    lv.pause(); last = null; shown = null; sentQ = []; inflight = 0;
    $("lhud").textContent = "stopped";
  }
  function beginLive() {
    last = null; shown = null; sentQ = []; inflight = 0; $("cres").innerHTML = "";
    return connectLive().then(function () { running = true; $("lhud").textContent = "live"; pump(); });
  }
  $("camStart").onclick = function () {
    stopLive(); cmsg("Starting camera...");
    navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false })
      .then(function (st) { lv.removeAttribute("src"); lv.srcObject = st; return lv.play(); })
      .then(beginLive).then(function () { cmsg(""); })
      .catch(function (e) { cmsg("Camera unavailable: " + e.message, true); });
  };
  $("camFile").onchange = function () {
    var f = $("camFile").files[0]; if (!f) return;
    stopLive(); lv.srcObject = null; lv.src = URL.createObjectURL(f); lv.loop = true; lv.playbackRate = 0.6;
    lv.play().then(beginLive).then(function () { cmsg(""); }).catch(function (e) { cmsg("Cannot play this video: " + e.message, true); });
  };
  $("camStop").onclick = stopLive;
  $("camFinish").onclick = function () {
    if (!ws || ws.readyState !== 1) { cmsg("Start a source first.", true); return; }
    running = false; lv.pause(); cmsg("Saving...");
    var l = getLoc();
    wsSend({ type: "finish", road_name: "", road_type: "unknown", traffic_level: "unknown", inspector: $("insp").value || "operator", lat: l ? l[0] : null, lon: l ? l[1] : null, location_source: l ? "gps" : null });
  };

  // stream URL source (server pulls the stream and returns annotated frames)
  var sws = null, streamMode = false;
  function stopStream() {
    if (sws) { var s = sws; sws = null; try { s.send(JSON.stringify({ type: "stop" })); s.close(); } catch (e) {} }
    streamMode = false; lv.style.display = ""; $("lv").parentNode.style.aspectRatio = "";
  }
  $("camUrlGo").onclick = function () {
    var url = $("camUrl").value.trim();
    if (!url) { cmsg("Enter a stream address first.", true); return; }
    stopLive(); stopStream(); cmsg("Connecting to stream...");
    var s = new WebSocket(API.replace("http", "ws") + "/ws/livestream");
    sws = s; streamMode = true; lv.style.display = "none";
    s.onopen = function () {
      var l = getLoc();
      s.send(JSON.stringify({ type: "start", url: url, classes: selected(), people: $("optPeople").checked, hazards: $("optHaz").checked, cracks: $("optCracks").checked, lat: l ? l[0] : null, lon: l ? l[1] : null }));
    };
    s.onerror = function () { cmsg("Cannot reach the detection server", true); };
    s.onclose = function () { if (sws === s) { cmsg("Stream closed.", true); stopStream(); } };
    s.onmessage = function (e) {
      if (sws !== s) return;
      var m; try { m = JSON.parse(e.data); } catch (_) { return; }
      if (m.type === "started") { cmsg("Stream connected."); $("lhud").textContent = "stream live"; }
      else if (m.type === "error") { cmsg("Stream error: " + m.error, true); }
      else if (m.type === "frame" || m.image) {
        $("lc").parentNode.style.aspectRatio = m.w + " / " + m.h;
        if (m.emergency) raiseAlarm(m.emergency);
        $("lhud").textContent = "stream | frame " + (m.frame || "") + " | unique " + (m.unique || 0);
        if (m.image) {
          var img = new Image();
          img.onload = function () { createImageBitmap(img).then(function (bm) { shown = bm; last = m; }); };
          img.src = "data:image/jpeg;base64," + m.image;
        } else last = m;
      }
    };
  };
  var _stopLive = stopLive;
  $("camStop").onclick = function () { stopStream(); _stopLive(); last = null; shown = null; };

  function draw() {
    var host = lc.parentNode.getBoundingClientRect();
    var r = streamMode ? host : lv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    var W = Math.round(r.width * dpr), H = Math.round(r.height * dpr);
    if (lc.width !== W || lc.height !== H) { lc.width = W; lc.height = H; }
    var c = lc.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, r.width, r.height);
    if (last && (lv.videoWidth || streamMode)) {
      var m = last, s = Math.min(r.width / m.w, r.height / m.h), ox = (r.width - m.w * s) / 2, oy = (r.height - m.h * s) / 2;
      if (shown) c.drawImage(shown, ox, oy, m.w * s, m.h * s);
      var tag = function (x, y, txt, col, fg) {
        c.font = "700 13px sans-serif"; var w = c.measureText(txt).width + 12;
        c.fillStyle = col; c.fillRect(x, y - 20, w, 20); c.fillStyle = fg || "#000"; c.fillText(txt, x + 6, y - 6);
      };
      (m.hazards || []).forEach(function (h) {
        var col = h.kind === "animal" ? "#ff9500" : "#32d2ff";
        c.strokeStyle = col; c.lineWidth = h.kind === "animal" ? 3 : 2;
        c.strokeRect(ox + h.box[0] * s, oy + h.box[1] * s, (h.box[2] - h.box[0]) * s, (h.box[3] - h.box[1]) * s);
        tag(ox + h.box[0] * s, oy + h.box[1] * s, h.label, col);
      });
      (m.people || []).forEach(function (p) {
        var X = ox + p.box[0] * s, Y = oy + p.box[1] * s;
        c.strokeStyle = p.fallen ? "#ff3b30" : "#fff"; c.lineWidth = p.fallen ? 3 : 1.5; c.setLineDash(p.fallen ? [] : [6, 4]);
        c.strokeRect(X, Y, (p.box[2] - p.box[0]) * s, (p.box[3] - p.box[1]) * s); c.setLineDash([]);
        if (p.fallen) tag(X, Y, "Fallen", "#ff3b30", "#fff");
      });
      (m.tracks || []).forEach(function (t) {
        var X = ox + t.box[0] * s, Y = oy + t.box[1] * s, w = (t.box[2] - t.box[0]) * s, h = (t.box[3] - t.box[1]) * s, col = COLORS[t.cls] || "#fff";
        if (!t.confirmed) { c.setLineDash([4, 4]); c.strokeStyle = col + "88"; c.lineWidth = 1.5; c.strokeRect(X, Y, w, h); c.setLineDash([]); return; }
        (t.poly || []).forEach(function (poly) {
          if (poly.length < 3) return; c.beginPath();
          poly.forEach(function (q, k) { var px = ox + q[0] * s, py = oy + q[1] * s; k ? c.lineTo(px, py) : c.moveTo(px, py); });
          c.closePath(); c.fillStyle = col + "40"; c.fill(); c.strokeStyle = col; c.lineWidth = 1.5; c.stroke();
        });
        c.strokeStyle = col; c.lineWidth = 2.5; c.strokeRect(X, Y, w, h);
        tag(X, Y < 22 ? Y + 20 : Y, (PREFIX[t.cls] || "RD") + " " + t.id + " " + nice(t.cls) + " " + Math.round(t.conf * 100) + "% " + (t.tier === "high" ? "" : "(possible)"), col);
      });
    }
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();
