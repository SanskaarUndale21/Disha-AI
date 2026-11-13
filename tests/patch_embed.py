"""One-off patch: add an interactive EMBED mode (?embed=1) to the shared map page, used by the admin dashboard card and
the citizen home page instead of their static map pictures."""
p = r"D:\coding\Hackvalley\backend\app\static\public_map.html"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


# 1) mode flag
rep('''  var APP = Q.get("app") === "1"; if (APP) document.body.classList.add("app");
  var CZ = APP || window.innerWidth < 700; if (CZ) document.body.classList.add("cz");''',
    '''  var EMBED = Q.get("embed") === "1"; if (EMBED) document.body.classList.add("embed");
  var APP = Q.get("app") === "1"; if (APP) document.body.classList.add("app");
  var CZ = (APP || window.innerWidth < 700) && !EMBED; if (CZ) document.body.classList.add("cz");''')

# 2) css: hide the side panel, keep map controls, style the embed bar
rep('body.cz{font-size:15.5px}', '''body.cz{font-size:15.5px}
body.embed #panel,body.embed .brand,body.embed #sheet,body.embed #toasts{display:none!important}
body.embed #pills{top:10px;left:10px}
body.embed #embedbar{display:flex}
#embedbar{display:none;position:absolute;left:10px;bottom:34px;z-index:6;gap:6px;flex-wrap:wrap;max-width:calc(100% - 90px)}
#embedbar button,#embedbar a{font:700 12.5px "Plus Jakarta Sans",system-ui,sans-serif;padding:7px 12px;border-radius:999px;border:1px solid rgba(61,64,91,.18);background:rgba(251,249,239,.94);color:#3D405B;cursor:pointer;text-decoration:none;box-shadow:0 2px 8px rgba(61,64,91,.14);backdrop-filter:blur(6px)}
#embedbar button.on{background:#81B29A;border-color:#81B29A;color:#2F3249}
#embedbar a.open{background:#3D405B;color:#F4F1DE;border-color:#3D405B}
.maplibregl-popup-content{font-family:"Plus Jakarta Sans",system-ui,sans-serif;border-radius:14px;padding:12px 14px;min-width:190px}
.ep h4{margin:0 0 4px;font-size:15px}.ep .m{color:#5E617A;font-size:12.5px;margin:2px 0}.ep .b{margin-top:8px;display:flex;gap:6px}
.ep .b a,.ep .b button{font:700 12px inherit;padding:6px 11px;border-radius:999px;border:1px solid #d9d4bd;background:#fff;color:#3D405B;cursor:pointer;text-decoration:none}
.ep .b a.p{background:#81B29A;border-color:#81B29A;color:#2F3249}''')

# 3) html: the filter bar, right after the pills block
rep('  <div id="pills">', '''  <div id="embedbar" role="group" aria-label="Map filters"><button class="on" data-f="all">All</button><button data-f="serious">Serious</button><button data-f="other">Moderate and minor</button><button data-f="fixed">Repaired</button><a class="open" href="/map" target="_top" id="embedopen">Open full map</a></div>
  <div id="pills">''')

# 4) behaviour: popup instead of the side sheet, and filters
rep('''  function showDefect(uid, fly) {
    var d = findDefect(uid); if (!d) return;''', '''  var embedPop = null;
  function embedShow(d) {
    if (embedPop) embedPop.remove();
    var rep_ = d.status === "repaired";
    var h = '<div class="ep"><h4>' + esc(nameOf(d["class"])) + " " + esc(d.number) + '</h4><div class="m">' + (rep_ ? "Repaired" : esc(d.severity || "Open")) +
      " &middot; " + esc(d.reports || 1) + ' report' + ((d.reports || 1) > 1 ? "s" : "") + '</div><div class="m">First seen ' + esc((d.first_seen || "").slice(0, 10)) + '</div>' +
      '<div class="b"><a class="p" target="_top" href="/map?dir=1&to=' + d.lat + "," + d.lon + "&name=" + encodeURIComponent(nameOf(d["class"]) + " " + d.number) + '">Directions here</a>' +
      (officerMode ? '<button id="epfix">' + (rep_ ? "Reopen" : "Mark repaired") + "</button>" : "") + "</div></div>";
    embedPop = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: "260px" }).setLngLat([d.lon, d.lat]).setHTML(h).addTo(map);
    var f = embedPop.getElement().querySelector("#epfix");
    if (f) f.onclick = function () { officerPatch([d.number], rep_ ? "active" : "repaired").then(function () { embedPop.remove(); }).catch(function (e) { alert(e.message); }); };
    try { parent.postMessage({ type: "rw-defect", id: d.number, uid: d.uid }, "*"); } catch (e) {}
  }
  function embedFilter(kind) {
    var T = CLR.terra, S_ = CLR.sage;
    var pf = kind === "serious" ? ["==", ["get", "c"], T] : kind === "fixed" ? ["==", ["get", "c"], S_] : kind === "other" ? ["==", ["get", "c"], CLR.amber] : null;
    var hf = kind === "serious" ? [">=", ["get", "w"], 1] : kind === "other" ? ["<", ["get", "w"], 1] : kind === "fixed" ? ["==", ["get", "w"], -1] : null;
    try { map.setFilter("pts", pf); map.setFilter("heat", hf); } catch (e) {}
  }
  function showDefect(uid, fly) {
    var d = findDefect(uid); if (!d) return;
    if (EMBED) { if (fly) map.flyTo({ center: [d.lon, d.lat], zoom: Math.max(map.getZoom(), 15.5) }); embedShow(d); return; }''')
rep('map.on("load", function () {', '''if (EMBED) {
    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("#embedbar button[data-f]"); if (!b) return;
      document.querySelectorAll("#embedbar button[data-f]").forEach(function (x) { x.classList.toggle("on", x === b); });
      embedFilter(b.dataset.f);
    });
  }
  map.on("load", function () {''')
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("embed patched")
