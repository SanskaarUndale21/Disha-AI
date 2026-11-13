/* Detection Studio logic */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  var API = (window.RW_API_BASE || lsGet("rw-api") || (location.protocol + "//" + location.hostname + ":8000")).replace(/\/+$/, "");
  function U(u) { return !u ? "" : /^(https?:|blob:|data:)/.test(u) ? u : API + (u.charAt(0) === "/" ? "" : "/") + u; }
  function device() { var d = lsGet("rw-device"); if (!d) { d = "dev-" + Math.random().toString(36).slice(2, 12); lsSet("rw-device", d); } return d; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function label(c) { return String(c || "unknown").replace(/_/g, " ").replace(/^./, function (m) { return m.toUpperCase(); }); }
  function setStatus(t) { $("status").textContent = t; }
  function show(id) { var e = $(id); e.hidden = false; return e; }

  var state = { file: null, insp: null, ticket: null, cid: null, pollT: null, mode: "oa", then: null };

  /* animated number */
  function countTo(el, from, to, ms, done) {
    if (reduce || from === to) { el.textContent = to; if (done) done(); return; }
    var t0 = performance.now();
    (function step(t) {
      var k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(step); else if (done) done();
    })(t0);
  }

  /* ---------- 1. upload + scan ---------- */
  var drop = $("drop"), fileIn = $("file");
  drop.addEventListener("click", function (e) { if (e.target.id !== "sample") fileIn.click(); });
  drop.addEventListener("keydown", function (e) { if ((e.key === "Enter" || e.key === " ") && e.target === drop) { e.preventDefault(); fileIn.click(); } });
  ["dragenter", "dragover"].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.add("over"); }); });
  ["dragleave", "drop"].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.remove("over"); }); });
  drop.addEventListener("drop", function (e) { var f = e.dataTransfer && e.dataTransfer.files[0]; if (f) start(f); });
  fileIn.addEventListener("change", function () { if (fileIn.files[0]) start(fileIn.files[0]); });
  $("sample").addEventListener("click", function (e) {
    e.stopPropagation();
    setStatus("FETCHING SAMPLE...");
    fetch(API + "/media/samples/pothole_drive.mp4").then(function (r) { if (!r.ok) throw new Error(r.status); return r.blob(); })
      .then(function (b) { start(new File([b], "pothole_drive.mp4", { type: "video/mp4" })); })
      .catch(function () { setStatus("SAMPLE NOT AVAILABLE, PLEASE UPLOAD A FILE"); });
  });

  function isVideo(f) { return /^video\//.test(f.type) || /\.(mp4|mov|m4v|avi|webm|mkv)$/i.test(f.name); }

  function start(file) {
    state.file = file; state.insp = null;
    ["dedupe", "compare", "ticket"].forEach(function (i) { $(i).hidden = true; });
    var url = URL.createObjectURL(file), vid = isVideo(file);
    $("prevEmpty").hidden = true;
    var pv = $("pvVid"), pi = $("pvImg");
    pv.hidden = !vid; pi.hidden = vid;
    if (vid) { pv.src = url; pv.play().catch(function () {}); } else { pi.src = url; }
    $("scanfx").hidden = false; $("rawCount").textContent = "0"; $("scanBar").style.width = "0%";
    setStatus("UPLOADING " + file.name.toUpperCase() + "...");
    var fd = new FormData();
    fd.append("file", file); fd.append("quality", "2k");
    var geo = loc();
    if (geo.real) { fd.append("lat", geo.lat); fd.append("lon", geo.lon); }
    fetch(API + "/api/inspections", { method: "POST", body: fd })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || r.status); return j; }); })
      .then(function (j) {
        if (j.job_id) poll(j.job_id); else finish(j.inspection || j);
      })
      .catch(function (e) { $("scanfx").hidden = true; setStatus("UPLOAD FAILED: " + String(e.message || e).toUpperCase()); });
  }

  var shown = 0;
  function poll(id) {
    shown = 0;
    (function tick() {
      fetch(API + "/api/jobs/" + id).then(function (r) { return r.json(); }).then(function (j) {
        var p = Math.max(0, Math.min(1, j.progress || 0));
        $("scanBar").style.width = Math.round(p * 100) + "%";
        var target = Math.round(p * p * 360 + p * 40);
        if (target > shown) { countTo($("rawCount"), shown, target, 500); shown = target; }
        setStatus("SCANNING FRAMES " + Math.round(p * 100) + "%");
        if (j.status === "done") finish(j.inspection);
        else if (j.status === "error") { $("scanfx").hidden = true; setStatus("ERROR: " + String(j.error || "failed").toUpperCase()); }
        else setTimeout(tick, 900);
      }).catch(function () { setTimeout(tick, 1500); });
    })();
  }

  function finish(insp) {
    state.insp = insp;
    var sm = insp.summary || {}, dets = insp.detections || [];
    var uniq = sm.unique_tracks != null ? sm.unique_tracks : (sm.new_defects != null ? sm.new_defects : dets.length);
    var rawS = Array.isArray(sm.raw_track_ids) ? sm.raw_track_ids.length : (sm.raw_track_ids || 0);
    var raw = rawS > uniq ? rawS : Math.max(dets.length, sm.total || 0);
    if (raw < uniq) raw = uniq;
    $("scanBar").style.width = "100%";
    countTo($("rawCount"), shown, raw, 700);
    setStatus("DONE. " + uniq + " UNIQUE DEFECTS FOUND");
    setTimeout(function () { $("scanfx").hidden = true; }, 900);
    renderDedupe(raw, uniq, sm, dets);
    renderCompare(insp);
    renderTicket(insp, uniq, sm);
    setTimeout(function () { $("dedupe").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" }); }, 1000);
  }

  /* ---------- 2. raw vs unique ---------- */
  function renderDedupe(raw, uniq, sm, dets) {
    show("dedupe");
    var fr = $("fnRaw"), fu = $("fnUniq"), bar = $("fnBar");
    fr.textContent = raw; fu.textContent = raw; bar.style.width = "100%"; $("dupPct").textContent = ""; $("chips").innerHTML = "";
    var pct = raw > 0 ? Math.round((1 - uniq / raw) * 100) : 0;
    setTimeout(function () {
      bar.style.width = Math.max(4, Math.round(uniq / Math.max(raw, 1) * 100)) + "%";
      countTo(fr, raw, uniq, 1600);
      countTo(fu, raw, uniq, 1600, function () {
        $("dupPct").textContent = pct + "% duplicates merged (" + raw + " sightings, " + uniq + " real defects)";
      });
    }, 500);
    var by = sm.by_class;
    if (!by || !Object.keys(by).length) { by = {}; dets.forEach(function (d) { var c = d.final_class || "defect"; by[c] = (by[c] || 0) + 1; }); }
    var h = "", i = 0;
    Object.keys(by).forEach(function (k) { h += '<span class="chip" style="animation-delay:' + (i++ * 80 + 300) + 'ms">' + esc(label(k)) + "<b>" + esc(by[k]) + "</b></span>"; });
    var bs = sm.by_severity || {};
    Object.keys(bs).forEach(function (k) { h += '<span class="chip" style="animation-delay:' + (i++ * 80 + 300) + 'ms;background:rgba(242,204,143,.18);border-color:rgba(242,204,143,.5)">' + esc(label(k)) + "<b>" + esc(bs[k]) + "</b></span>"; });
    $("chips").innerHTML = h;
  }

  /* ---------- 3. before / after ---------- */
  var cmp = $("cmp"), under = cmp.querySelector(".under"), over = cmp.querySelector(".over"), cmpVids = [];
  function setP(p) { p = Math.max(0, Math.min(100, p)); cmp.style.setProperty("--p", p + "%"); cmp.setAttribute("aria-valuenow", Math.round(p)); }
  var drag = false;
  function fromEvt(e) { var r = cmp.getBoundingClientRect(); setP((e.clientX - r.left) / r.width * 100); }
  cmp.addEventListener("pointerdown", function (e) { drag = true; try { cmp.setPointerCapture(e.pointerId); } catch (x) {} fromEvt(e); });
  cmp.addEventListener("pointermove", function (e) { if (drag) fromEvt(e); });
  cmp.addEventListener("pointerup", function () { drag = false; });
  cmp.addEventListener("pointercancel", function () { drag = false; });
  cmp.addEventListener("keydown", function (e) {
    var v = +cmp.getAttribute("aria-valuenow");
    if (e.key === "ArrowLeft") { setP(v - 5); e.preventDefault(); } else if (e.key === "ArrowRight") { setP(v + 5); e.preventDefault(); }
    else if (e.key === "Home") { setP(0); e.preventDefault(); } else if (e.key === "End") { setP(100); e.preventDefault(); }
  });

  function media(url, video, alt) {
    if (video) return '<video src="' + esc(url) + '" muted loop playsinline preload="auto" aria-label="' + esc(alt) + '"></video>';
    return '<img src="' + esc(url) + '" alt="' + esc(alt) + '">';
  }
  function setCompare(aUrl, bUrl, video, tl, tr) {
    under.innerHTML = media(aUrl, video, tl); over.innerHTML = media(bUrl, video, tr);
    $("tagL").textContent = tl; $("tagR").textContent = tr;
    cmpVids = Array.prototype.slice.call(cmp.querySelectorAll("video"));
    $("cmpPlay").hidden = !video; $("cmpPlay").textContent = "Play both";
    if (video && cmpVids.length === 2) {
      cmpVids[0].addEventListener("timeupdate", function () { if (Math.abs(cmpVids[0].currentTime - cmpVids[1].currentTime) > 0.25) cmpVids[1].currentTime = cmpVids[0].currentTime; });
    }
    setP(50);
  }
  $("cmpPlay").addEventListener("click", function () {
    if (!cmpVids.length) return;
    var play = cmpVids[0].paused;
    cmpVids.forEach(function (v) { if (play) v.play().catch(function () {}); else v.pause(); });
    this.textContent = play ? "Pause both" : "Play both";
  });

  function renderCompare(insp) {
    show("compare");
    state.mode = "oa"; $("tabOA").setAttribute("aria-pressed", "true"); $("tabTN").setAttribute("aria-pressed", "false");
    $("verdict").hidden = true;
    var video = (insp.media_type || "") === "video" || (state.file && isVideo(state.file));
    var orig = U(insp.media_url) || (state.file ? URL.createObjectURL(state.file) : "");
    setCompare(orig, U(insp.annotated_url), video, "ORIGINAL", "DETECTED");
    state.oa = { a: orig, b: U(insp.annotated_url), video: video };
    var g = loc();
    $("tabTN").hidden = true; state.then = null;
    fetch(API + "/api/progress?lat=" + g.lat + "&lon=" + g.lon + "&radius_m=50").then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j || !j.snapshots || j.snapshots.length < 2) return;
      var s = j.snapshots, a = s[0].annotated_url, b = s[s.length - 1].annotated_url;
      if (!a || !b) return;
      state.then = { a: U(a), b: U(b), verdict: j.verdict };
      $("tabTN").hidden = false;
    }).catch(function () {});
  }
  $("tabOA").addEventListener("click", function () {
    if (!state.oa) return;
    state.mode = "oa"; this.setAttribute("aria-pressed", "true"); $("tabTN").setAttribute("aria-pressed", "false");
    $("verdict").hidden = true; setCompare(state.oa.a, state.oa.b, state.oa.video, "ORIGINAL", "DETECTED");
  });
  $("tabTN").addEventListener("click", function () {
    if (!state.then) return;
    state.mode = "tn"; this.setAttribute("aria-pressed", "true"); $("tabOA").setAttribute("aria-pressed", "false");
    setCompare(state.then.a, state.then.b, false, "THEN", "NOW");
    var v = state.then.verdict, map = { worsening: "Worsening", improving: "Improved", improved: "Improved", repaired: "Repaired" };
    var ve = $("verdict");
    if (map[v]) { ve.textContent = map[v]; ve.hidden = false; } else ve.hidden = true;
  });

  /* ---------- 4. ticket, QR, letter, PDF ---------- */
  function loc() {
    var i = state.insp;
    if (i && i.lat != null && i.lon != null) return { lat: i.lat, lon: i.lon, real: true };
    if (state.geo) return { lat: state.geo.lat, lon: state.geo.lon, real: true };
    return { lat: 15.85, lon: 74.50, real: false };
  }
  try { if (navigator.geolocation) navigator.geolocation.getCurrentPosition(function (p) { state.geo = { lat: p.coords.latitude, lon: p.coords.longitude }; }, function () {}, { timeout: 4000 }); } catch (e) {}

  function summaryText(uniq, sm) {
    var by = sm.by_class || {}, parts = Object.keys(by).map(function (k) { return by[k] + " " + label(k).toLowerCase(); });
    return uniq + " unique road defect" + (uniq === 1 ? "" : "s") + " detected" + (parts.length ? " (" + parts.join(", ") + ")" : "") + ".";
  }
  function renderTicket(insp, uniq, sm) {
    show("ticket");
    var txt = summaryText(uniq, sm);
    state.desc = "Detected by Disha AI: " + txt;
    $("mSub").textContent = "Road damage report: " + uniq + " defect" + (uniq === 1 ? "" : "s") + " near Belagavi";
    $("mBody").textContent = "Respected Sir or Madam,\nAutomated road inspection found the following.\n" + txt + "\nKindly arrange inspection and repair. Photo evidence and map location are attached.";
    var th = insp.annotated_url ? U(insp.annotated_url) : "";
    var im = $("mImg"); im.hidden = true;
    if (th && !state.oa.video) { im.src = th; im.hidden = false; }
    else if (insp.detections && insp.detections[0] && insp.detections[0].crop_url) { im.src = U(insp.detections[0].crop_url); im.hidden = false; }
    $("mailState").textContent = "DRAFT"; $("mail").classList.remove("sent");
    $("mTicket").textContent = "pending"; $("qr").innerHTML = ""; $("qr").classList.remove("has"); $("qrHint").hidden = false; $("qrLink").textContent = "";
    $("fileC").disabled = false; $("tkMsg").textContent = "";
    setStep(-1);
  }
  function setStep(n) {
    var lis = $("stepper").querySelectorAll("li");
    Array.prototype.forEach.call(lis, function (li, i) { li.classList.toggle("on", i <= n); li.classList.toggle("cur", i === n); });
  }
  var STEP = { submitted: 0, in_review: 1, in_progress: 2, resolved: 3 };

  $("fileC").addEventListener("click", function () {
    var btn = this; btn.disabled = true; $("tkMsg").textContent = "FILING...";
    var g = loc(), fd = new FormData();
    fd.append("category", "pothole"); fd.append("description", state.desc || "Road damage detected");
    fd.append("lat", g.lat); fd.append("lon", g.lon); fd.append("device_id", device());
    if (state.file) fd.append("files", state.file, state.file.name);
    fetch(API + "/api/complaints", { method: "POST", body: fd })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || r.status); return j; }); })
      .then(function (j) {
        state.ticket = j.ticket; state.cid = j.id;
        $("tkMsg").textContent = "FILED " + j.ticket;
        $("mTicket").textContent = j.ticket;
        setStep(0);
        drawQR(j.ticket);
        sendMail();
        pollTicket();
      })
      .catch(function (e) { btn.disabled = false; $("tkMsg").textContent = "COULD NOT FILE: " + String(e.message || e).toUpperCase(); });
  });
  function drawQR(ticket) {
    var link = API + "/upload/" + ticket, q = $("qr");
    q.innerHTML = "";
    if (window.QRCode) { new QRCode(q, { text: link, width: 150, height: 150, colorDark: "#2B2D40", colorLight: "#ffffff" }); q.classList.add("has"); $("qrHint").hidden = true; }
    else $("qrHint").textContent = "QR library offline";
    var a = $("qrLink"); a.textContent = link; a.href = link;
  }
  function sendMail() {
    var st = $("mailState"), m = $("mail");
    st.textContent = "SENDING...";
    setTimeout(function () { st.textContent = "SENT"; m.classList.add("sent"); }, reduce ? 0 : 1600);
  }
  function pollTicket() {
    clearTimeout(state.pollT);
    if (state.cid == null) return;
    fetch(API + "/api/complaints/" + state.cid + "?device_id=" + encodeURIComponent(device()))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (c) { if (c && STEP[c.status] != null) setStep(STEP[c.status]); })
      .catch(function () {})
      .then(function () { state.pollT = setTimeout(pollTicket, 6000); });
  }

  /* PDF modal */
  var lastFocus = null;
  function openPdf() {
    if (!state.insp) return;
    var u = API + "/api/reports/analysis/" + state.insp.id + ".pdf";
    lastFocus = document.activeElement;
    $("pdfFrame").src = u; $("pdfDl").href = u; $("modal").hidden = false; $("pdfX").focus();
  }
  function closePdf() { $("modal").hidden = true; $("pdfFrame").src = "about:blank"; if (lastFocus) lastFocus.focus(); }
  $("pdfBtn").addEventListener("click", openPdf);
  $("pdfX").addEventListener("click", closePdf);
  $("modal").addEventListener("click", function (e) { if (e.target === this) closePdf(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("modal").hidden) closePdf(); });

  /* ---------- 5. robustness ---------- */
  fetch(API + "/api/model/metrics").then(function (r) { return r.json(); }).then(function (m) {
    var box = $("metrics"), c = m && m.conditions;
    if (!c || !c.models) { box.innerHTML = '<p class="sub">Metrics not available on this server.</p>'; return; }
    var names = Object.keys(c.models), key = names.filter(function (n) { return /wx/.test(n); }).pop() || names[0];
    var per = c.models[key] || {}, order = ["Day", "Night", "Fog", "Smoke", "Dust", "Rain"], h = "";
    order.forEach(function (k) {
      if (!per[k]) return;
      var v = per[k].map50 != null ? per[k].map50 : per[k].map;
      if (v == null) return;
      h += '<div class="mrow"><span class="mono">' + k + '</span><div class="track" role="img" aria-label="' + k + ' mAP50 ' + (v * 100).toFixed(1) + ' percent"><div class="fill" data-w="' + Math.round(v * 100) + '"></div></div><b>' + (v * 100).toFixed(1) + "</b></div>";
    });
    box.innerHTML = h ? h + '<p class="sub mono">mAP50 per condition, model ' + esc(key) + "</p>" : '<p class="sub">No per-condition metrics.</p>';
    var fills = box.querySelectorAll(".fill");
    function grow() { Array.prototype.forEach.call(fills, function (f) { f.style.width = f.getAttribute("data-w") + "%"; }); }
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) { if (es[0].isIntersecting) { grow(); io.disconnect(); } }, { threshold: 0.2 });
      io.observe(box);
    } else grow();
  }).catch(function () { $("metrics").innerHTML = '<p class="sub">Metrics unavailable (server offline).</p>'; });
})();
