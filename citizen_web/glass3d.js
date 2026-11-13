/* Disha AI citizen website: depth layer. Pointer tilt, parallax, device tilt on touch, video lifecycle.
   Transform and opacity only, rAF throttled, no libraries. Disabled for prefers-reduced-motion. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");
  var vid = document.getElementById("bgvid");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- video: fade in over the poster, keep playing on iOS, pause while hidden ---- */
  function on() { root.classList.add("vid-on"); }
  if (vid && !reduce) {
    vid.muted = true; vid.defaultMuted = true; vid.setAttribute("muted", ""); vid.setAttribute("playsinline", ""); vid.setAttribute("webkit-playsinline", "");
    vid.addEventListener("playing", on); vid.addEventListener("loadeddata", function () { if (!vid.paused) on(); });
    setTimeout(on, 2500);
    var tryPlay = function () { var p = vid.play(); if (p && p.catch) p.catch(function () {}); };
    tryPlay();
    var unlock = function () { if (vid.paused && document.visibilityState === "visible") tryPlay(); };
    ["touchstart", "pointerdown", "keydown", "scroll"].forEach(function (ev) { window.addEventListener(ev, unlock, { once: true, passive: true, capture: true }); });
    document.addEventListener("visibilitychange", function () { if (document.hidden) vid.pause(); else tryPlay(); });
  } else on();
  if (reduce) return;

  var fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var main = document.getElementById("main");
  var SEL = ".statstrip, .mapcard, .callcard, .tripcard, .rtile, .al, .checkcard";
  var mx = 0, my = 0, px = 0, py = 0, sy = 0, raf = 0, active = null, hh = null, lastTarget = null, ptrX = 0, ptrY = 0;

  function frame() {
    raf = 0;
    if (!hh || !hh.isConnected) hh = document.querySelector(".hh");
    if (hh) { hh.style.setProperty("--px", px.toFixed(3)); hh.style.setProperty("--py", py.toFixed(3)); hh.style.setProperty("--sy", Math.min(sy, 900)); }
    if (vid) { vid.style.setProperty("--vx", px.toFixed(3)); vid.style.setProperty("--vy", py.toFixed(3)); }
    if (active && active.isConnected) {
      var r = active.getBoundingClientRect();
      var big = active.classList.contains("statstrip") || active.classList.contains("mapcard");
      var max = big ? 5 : 7;
      var nx = Math.max(0, Math.min(1, (ptrX - r.left) / (r.width || 1))), ny = Math.max(0, Math.min(1, (ptrY - r.top) / (r.height || 1)));
      active.style.setProperty("--ry", ((nx - .5) * 2 * max).toFixed(2) + "deg");
      active.style.setProperty("--rx", ((.5 - ny) * 2 * max).toFixed(2) + "deg");
      active.style.setProperty("--mx", (nx * 100).toFixed(1) + "%");
      active.style.setProperty("--my", (ny * 100).toFixed(1) + "%");
    }
  }
  function sched() { if (!raf) raf = requestAnimationFrame(frame); }
  function release(el) {
    if (!el) return;
    el.classList.remove("is-tilt");
    ["--rx", "--ry", "--mx", "--my"].forEach(function (k) { el.style.removeProperty(k); });
  }

  if (fine) {
    root.classList.add("fx");
    window.addEventListener("pointermove", function (e) {
      if (e.pointerType && e.pointerType !== "mouse" && e.pointerType !== "pen") return;
      ptrX = e.clientX; ptrY = e.clientY;
      px = (e.clientX / window.innerWidth - .5) * 2; py = (e.clientY / window.innerHeight - .5) * 2;
      var t = e.target && e.target.closest ? e.target.closest(SEL) : null;
      if (t !== active) { release(active); active = t; if (active) active.classList.add("is-tilt"); }
      sched();
    }, { passive: true });
    document.addEventListener("pointerleave", function () { release(active); active = null; px = 0; py = 0; sched(); });
    window.addEventListener("blur", function () { release(active); active = null; });
  } else if (window.DeviceOrientationEvent && typeof DeviceOrientationEvent.requestPermission !== "function") {
    /* touch devices: gentle parallax from device tilt where no permission prompt is needed; otherwise no effect */
    root.classList.add("fx");
    window.addEventListener("deviceorientation", function (e) {
      if (e.gamma == null || e.beta == null) return;
      px = Math.max(-1, Math.min(1, e.gamma / 25)); py = Math.max(-1, Math.min(1, (e.beta - 50) / 25));
      sched();
    }, { passive: true });
  }
  if (main) main.addEventListener("scroll", function () { sy = main.scrollTop; sched(); }, { passive: true });

  /* siren banner and shell: keep the header below the emergency banner instead of hidden under it */
  var em = document.getElementById("emergency");
  function syncEm() { root.style.setProperty("--em-h", em && !em.hidden ? em.offsetHeight + "px" : "0px"); }
  if (em) {
    new MutationObserver(syncEm).observe(em, { attributes: true, attributeFilter: ["hidden"] });
    if (window.ResizeObserver) new ResizeObserver(syncEm).observe(em);
    window.addEventListener("resize", syncEm);
    syncEm();
  }
})();
