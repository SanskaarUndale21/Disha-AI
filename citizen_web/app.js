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
    document.querySelectorAll("#tabs button").forEach(function (b) { b.className = b.dataset.tab === tab ? "on" : ""; });
    document.querySelectorAll(".pane").forEach(function (p) { p.className = "pane" + (p.id === "tab-" + tab ? " on" : ""); });
    if (tab === "mine") loadMine();
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
    }).catch(function () { rec.verdict = "fail"; pill.className = "pill fail"; pill.textContent = "Check failed"; });
    return rec;
  }
  $("files").onchange = function () {
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

  function loadMine() {
    var box = $("mine"); box.textContent = "Loading...";
    fetch(API + "/api/complaints?device_id=" + encodeURIComponent(device)).then(function (r) { return r.json(); }).then(function (list) {
      if (!Array.isArray(list) || !list.length) { box.innerHTML = "<p class=\"note\">No reports from this browser yet. Use Report damage to file one.</p>"; return; }
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

  var retry = 1000;
  function connect() {
    var ws = new WebSocket(API.replace("http", "ws") + "/ws/events");
    ws.onopen = function () { retry = 1000; $("live").className = "live on"; $("live").lastChild.textContent = "Live"; };
    ws.onmessage = function (e) {
      var m; try { m = JSON.parse(e.data); } catch (_) { return; }
      if (m.type === "map.repair") toast("A road defect was marked repaired");
      if (m.type === "map.defect") toast("New road damage reported on the map");
      if (/complaint/.test(m.type || "") && $("tab-mine").classList.contains("on")) loadMine();
    };
    ws.onclose = function () { $("live").className = "live"; $("live").lastChild.textContent = "Reconnecting"; setTimeout(connect, retry = Math.min(retry * 2, 15000)); };
  }
  connect();
})();
