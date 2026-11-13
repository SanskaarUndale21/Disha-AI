import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../api.dart';
import '../main.dart';
import '../notifications.dart';
import '../places.dart';
import '../realtime.dart';
import '../theme.dart';
import '../widgets.dart';

const _zoneRed = Color(0xFFD92D20);
const _zoneYellow = Color(0xFFF2B705);
const _zoneGreen = Color(0xFF2E9A57);

Color _zoneColor(String? level) => switch (level) { 'red' => _zoneRed, 'yellow' => _zoneYellow, _ => _zoneGreen };

enum _Show { areas, pins, both }

LatLng? _pt(Map<String, dynamic> m) {
  final a = m['lat'], b = m['lon'];
  return a is num && b is num ? LatLng(a.toDouble(), b.toDouble()) : null;
}

DateTime? _parseUtc(Object? v) {
  if (v == null) return null;
  final s = '$v';
  return DateTime.tryParse(RegExp(r'Z|[+-]\d\d:?\d\d$').hasMatch(s) ? s : '${s}Z')?.toLocal();
}

/// Every known defect in the city, no login needed and no personal data.
class PublicMapScreen extends StatefulWidget {
  const PublicMapScreen({super.key});
  @override
  State<PublicMapScreen> createState() => _PublicMapScreenState();
}

class _PublicMapScreenState extends State<PublicMapScreen> {
  final _map = MapController();
  final _sheet = DraggableScrollableController();
  final _from = TextEditingController();
  final _to = TextEditingController();

  List<Map<String, dynamic>>? _items;
  Map<String, dynamic>? _zones, _summary;
  List<Map<String, dynamic>>? _reports;
  String? _error;
  bool _ready = false;
  _Show _show = _Show.both;
  int _tab = 0;

  Map<String, dynamic>? _pickedCell;
  final Set<String> _fresh = {};
  final Set<String> _seen = {};
  LatLng? _pulse;
  Timer? _pulseTimer, _debounce, _poll;
  StreamSubscription? _sub;

  // route planner
  Map<String, dynamic>? _plan;
  int _sel = 0;
  bool _planning = false, _locating = false;
  String? _routeMsg;
  bool _routeErr = false;
  String? _banner;
  LatLng? _fromPt, _toPt;
  String? _lastO, _lastD, _anKey;
  int _planVer = 0;
  bool _stepsOpen = false;
  _RouteInfo? _an;

  @override
  void initState() {
    super.initState();
    _load(first: true);
    _sub = Realtime.feed.stream.listen((e) {
      final t = e.$1;
      if (t == 'map.defect' || t == 'map.repair' || t == 'map.report') {
        final p = _pt(e.$2);
        if (p != null) _pulseAt(p);
        _debounce?.cancel();
        _debounce = Timer(const Duration(milliseconds: 900), () {
          _load();
          if (_plan != null) _runPlan(quiet: true);
        });
      }
    });
    _poll = Timer.periodic(const Duration(seconds: 45), (_) => _load());
  }

  @override
  void dispose() {
    _sub?.cancel();
    _pulseTimer?.cancel();
    _debounce?.cancel();
    _poll?.cancel();
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  void _pulseAt(LatLng p) {
    setState(() => _pulse = p);
    _pulseTimer?.cancel();
    _pulseTimer = Timer(const Duration(seconds: 5), () {
      if (mounted) setState(() => _pulse = null);
    });
  }

  Future<void> _load({bool first = false}) async {
    try {
      final r = await Future.wait<Object?>([
        api.publicDefects(),
        api.publicZones(),
        api.publicComplaints(),
        api.publicSummary(),
      ]);
      if (!mounted) return;
      final reports = r[2] as List<Map<String, dynamic>>;
      final newOnes = <String>{};
      for (final c in reports) {
        final n = '${c['number']}';
        if (!first && _reports != null && !_seen.contains(n)) newOnes.add(n);
        _seen.add(n);
      }
      setState(() {
        _items = r[0] as List<Map<String, dynamic>>;
        _zones = r[1] as Map<String, dynamic>?;
        _reports = reports;
        _summary = r[3] as Map<String, dynamic>?;
        _error = null;
        _fresh.addAll(newOnes);
      });
      if (newOnes.isNotEmpty) {
        Timer(const Duration(seconds: 6), () {
          if (mounted) setState(() => _fresh.removeAll(newOnes));
        });
      }
      if (first) _fit();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  void _fit() {
    final pts = [for (final d in _items ?? <Map<String, dynamic>>[]) ?_pt(d)];
    if (!_ready || pts.isEmpty) return;
    if (pts.length == 1) {
      _map.move(pts.first, 15);
    } else {
      _map.fitCamera(CameraFit.bounds(bounds: LatLngBounds.fromPoints(pts), padding: const EdgeInsets.all(60)));
    }
  }

  List<Map<String, dynamic>> get _cells =>
      [for (final c in (_zones?['cells'] as List? ?? [])) Map<String, dynamic>.from(c as Map)];

  List<LatLng> _square(Map<String, dynamic> c) {
    final lat = (c['lat'] as num).toDouble(), lon = (c['lon'] as num).toDouble();
    final half = ((c['size_m'] as num?) ?? 300).toDouble() / 2;
    final dLat = half / 111320;
    final dLon = half / (111320 * _cosDeg(lat));
    return [LatLng(lat - dLat, lon - dLon), LatLng(lat - dLat, lon + dLon), LatLng(lat + dLat, lon + dLon), LatLng(lat + dLat, lon - dLon)];
  }

  static double _cosDeg(double d) => math.cos(d * math.pi / 180);

  void _focus(LatLng p, {double zoom = 16}) {
    _map.move(p, zoom);
    _pulseAt(p);
    _sheet.animateTo(0.16, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
  }

  void _onMapTap(LatLng p) {
    if (_show == _Show.pins) return;
    for (final c in _cells) {
      final sq = _square(c);
      if (p.latitude >= sq[0].latitude && p.latitude <= sq[2].latitude && p.longitude >= sq[0].longitude && p.longitude <= sq[2].longitude) {
        setState(() => _pickedCell = c);
        return;
      }
    }
    if (_pickedCell != null) setState(() => _pickedCell = null);
  }

  void _details(Map<String, dynamic> d) {
    final repaired = d['status'] == 'repaired';
    showCupertinoModalPopup<void>(
      context: context,
      builder: (ctx) => CupertinoActionSheet(
        title: Text('#${d['number']}  ${'${d['class'] ?? 'defect'}'.replaceAll('_', ' ')}'),
        message: Text('Severity: ${d['severity'] ?? 'unknown'}\n'
            'Reported ${d['reports'] ?? 1} ${(d['reports'] ?? 1) == 1 ? 'time' : 'times'}\n'
            'Status: ${repaired ? 'repaired' : 'open'}'),
        cancelButton: CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx), child: const Text('Close')),
      ),
    );
  }

  // ---------- route planner ----------
  Future<void> _useMyLocation() async {
    setState(() => _locating = true);
    final s = await locator.locate(force: true);
    if (!mounted) return;
    setState(() => _locating = false);
    if (s == null) {
      setState(() {
        _routeMsg = locator.error ?? 'Could not find your location. Type your start place instead.';
        _routeErr = true;
      });
      return;
    }
    _fromPt = LatLng(s.lat, s.lon);
    _from.text = 'My location';
    setState(() => _routeMsg = null);
  }

  String _friendly(Object e) {
    final m = '$e';
    final l = m.toLowerCase();
    if (l.contains('not found') || l.contains('geocode') || l.contains('could not find') || l.contains('no place')) {
      return "We couldn't find one of those places. Pick a suggestion, try a nearby landmark, or type latitude, longitude.";
    }
    if (l.contains('busy') || l.contains('timeout') || l.contains('503') || l.contains('502') || l.contains('504') || l.contains('unavailable') || l.contains('(5')) {
      return 'The routing service is busy right now. Please try again in a moment.';
    }
    return m;
  }

  Future<LatLng> _resolve(String text, LatLng? picked) async {
    if (picked != null) return picked;
    final c = Places.parseCoords(text);
    if (c != null) return c;
    final r = await Places.search(text, limit: 1);
    if (r.isEmpty) throw ApiException("We couldn't find \"$text\". Pick a suggestion or try a nearby landmark.");
    return r.first.point;
  }

  Future<void> _compare() async {
    final o = _from.text.trim(), d = _to.text.trim();
    if (o.isEmpty || d.isEmpty) {
      setState(() {
        _routeMsg = 'Enter where you start and where you are going.';
        _routeErr = true;
      });
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() => (_planning = true, _routeMsg = null, _banner = null));
    try {
      final a = await _resolve(o, _fromPt);
      final b = await _resolve(d, _toPt);
      _lastO = '${a.latitude.toStringAsFixed(6)},${a.longitude.toStringAsFixed(6)}';
      _lastD = '${b.latitude.toStringAsFixed(6)},${b.longitude.toStringAsFixed(6)}';
      await _runPlan(quiet: false);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _planning = false;
        _routeErr = true;
        _routeMsg = _friendly(e);
      });
    }
  }

  /// Fetches the plan for the last resolved start and end. [quiet] refreshes in place after a live map event.
  Future<void> _runPlan({required bool quiet}) async {
    final o = _lastO, d = _lastD;
    if (o == null || d == null) return;
    try {
      final j = await api.routePlan(o, d);
      if (!mounted) return;
      final before = _plan?['recommended'];
      final oldRoutes = (_plan?['routes'] as List? ?? []);
      final oldCount = (before is num && before.toInt() < oldRoutes.length)
          ? (oldRoutes[before.toInt()] as Map)['defect_count']
          : null;
      final routes = (j['routes'] as List? ?? []);
      if (routes.isEmpty) throw ApiException('No drivable route found between those places.');
      final rec = (j['recommended'] as num?)?.toInt() ?? 0;
      final recRoute = Map<String, dynamic>.from(routes[rec.clamp(0, routes.length - 1)] as Map);
      setState(() {
        _plan = j;
        _planVer++;
        _planning = false;
        _routeErr = false;
        _routeMsg = null;
        if (quiet) {
          if (before != null && before != j['recommended']) {
            _banner = 'A new report changed the best route';
            _sel = rec;
          } else if (_sel >= routes.length) {
            _sel = 0;
          }
        } else {
          _sel = rec;
          _stepsOpen = false;
        }
      });
      if (quiet && before != null) {
        final nowCount = recRoute['defect_count'];
        if (before != j['recommended']) {
          notifs.routeChanged('The best route is now Route ${rec + 1}: ${recRoute['duration_min']} min, '
              '${recRoute['defect_count'] ?? 0} reported potholes.');
        } else if (oldCount != null && oldCount != nowCount) {
          notifs.routeChanged('Road damage on your recommended route changed: now ${nowCount ?? 0} reported potholes.');
        }
      }
      if (!quiet) _fitRoute();
    } catch (e) {
      if (!mounted || quiet) return;
      setState(() {
        _planning = false;
        _routeErr = true;
        _routeMsg = _friendly(e);
      });
    }
  }

  List<LatLng> _geom(Map r) =>
      [for (final p in (r['geometry'] as List? ?? [])) LatLng((p[0] as num).toDouble(), (p[1] as num).toDouble())];

  Map<String, dynamic>? get _selRoute {
    final rs = _plan?['routes'] as List?;
    if (rs == null || rs.isEmpty) return null;
    return Map<String, dynamic>.from(rs[_sel.clamp(0, rs.length - 1)] as Map);
  }

  _RouteInfo? get _info {
    final r = _selRoute;
    if (r == null) return null;
    final key = '$_planVer:$_sel';
    if (_anKey != key) {
      _an = _RouteInfo.of(_geom(r), [for (final h in (r['defects'] as List? ?? [])) Map<String, dynamic>.from(h as Map)]);
      _anKey = key;
    }
    return _an;
  }

  void _fitRoute() {
    final r = _selRoute;
    if (r == null || !_ready) return;
    final g = _geom(r);
    if (g.length < 2) return;
    _map.fitCamera(CameraFit.bounds(bounds: LatLngBounds.fromPoints(g), padding: const EdgeInsets.fromLTRB(40, 150, 40, 200)));
    _sheet.animateTo(0.3, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
  }

  // ---------- build ----------
  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final items = _items ?? [];
    final cells = _cells;
    final showAreas = _show != _Show.pins, showPins = _show != _Show.areas;
    final route = _selRoute;
    final routes = (_plan?['routes'] as List? ?? []);

    return Scaffold(
      body: Stack(children: [
        FlutterMap(
          mapController: _map,
          options: MapOptions(
            initialCenter: const LatLng(12.9716, 77.5946),
            initialZoom: 12,
            onMapReady: () {
              _ready = true;
              _fit();
            },
            onTap: (_, p) => _onMapTap(p),
            interactionOptions: const InteractionOptions(flags: InteractiveFlag.all & ~InteractiveFlag.rotate),
          ),
          children: [
            const MapTiles(),
            if (showAreas)
              PolygonLayer(polygons: [
                for (final cell in cells)
                  Polygon(
                    points: _square(cell),
                    color: _zoneColor('${cell['level']}').withValues(alpha: (_pickedCell != null && _pickedCell!['lat'] == cell['lat'] && _pickedCell!['lon'] == cell['lon']) ? 0.55 : 0.35),
                    borderColor: _zoneColor('${cell['level']}'),
                    borderStrokeWidth: 1.5,
                  ),
              ]),
            if (showAreas)
              MarkerLayer(markers: [
                for (final cell in cells)
                  Marker(
                    point: LatLng((cell['lat'] as num).toDouble(), (cell['lon'] as num).toDouble()),
                    width: 44,
                    height: 44,
                    child: GestureDetector(
                      onTap: () => setState(() => _pickedCell = cell),
                      child: Semantics(
                        label: 'Area with ${cell['label']}',
                        child: Center(
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: _zoneColor('${cell['level']}'),
                              borderRadius: BorderRadius.circular(99),
                              border: Border.all(color: Colors.white, width: 2),
                            ),
                            child: Text('${cell['count']}',
                                style: TextStyle(
                                    color: cell['level'] == 'yellow' ? Colors.black : Colors.white,
                                    fontSize: 13,
                                    fontWeight: FontWeight.w800)),
                          ),
                        ),
                      ),
                    ),
                  ),
              ]),
            if (plannerHasRoute(routes))
              PolylineLayer(polylines: [
                for (var i = 0; i < routes.length; i++)
                  if (i != _sel)
                    Polyline(points: _geom(routes[i] as Map), color: const Color(0x998A9097), strokeWidth: 6, borderColor: Colors.white, borderStrokeWidth: 1),
                if (route != null) ...[
                  Polyline(points: _geom(route), color: Colors.white, strokeWidth: 11),
                  if (_info != null)
                    for (var k = 0; k < _info!.runs.length; k++)
                      Polyline(points: _info!.runs[k], color: _info!.colors[k], strokeWidth: 7),
                ],
              ]),
            if (plannerHasRoute(routes))
              MarkerLayer(markers: [
                for (var i = 0; i < routes.length; i++)
                  if (i != _sel)
                    // invisible wide tap target at the midpoint of other routes
                    Marker(
                      point: _geom(routes[i] as Map)[_geom(routes[i] as Map).length ~/ 2],
                      width: 44,
                      height: 44,
                      child: GestureDetector(
                        onTap: () => setState(() => _sel = i),
                        child: Semantics(
                          label: 'Select route ${i + 1}',
                          child: Container(
                            decoration: BoxDecoration(color: Colors.white, shape: BoxShape.circle, border: Border.all(color: Colors.grey)),
                            alignment: Alignment.center,
                            child: Text('${i + 1}', style: const TextStyle(fontWeight: FontWeight.w800)),
                          ),
                        ),
                      ),
                    ),
                if (route != null)
                  for (final h in (route['defects'] as List? ?? []))
                    if (_pt(Map<String, dynamic>.from(h as Map)) != null)
                      Marker(
                        point: _pt(Map<String, dynamic>.from(h))!,
                        width: 28,
                        height: 28,
                        child: Container(
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: ((h['risk'] as num?) ?? 0) >= 70 ? _zoneRed : const Color(0xFFE08A00),
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 2),
                          ),
                          child: Text('${h['number']}',
                              style: const TextStyle(color: Colors.white, fontSize: 9.5, fontWeight: FontWeight.w800)),
                        ),
                      ),
                if (_plan != null && _pt(Map<String, dynamic>.from(_plan!['origin'] as Map)) != null)
                  Marker(
                      point: _pt(Map<String, dynamic>.from(_plan!['origin'] as Map))!,
                      width: 34,
                      height: 34,
                      child: const MapPin(color: AppColors.blue, icon: CupertinoIcons.circle_fill, size: 30)),
                if (_plan != null && _pt(Map<String, dynamic>.from(_plan!['destination'] as Map)) != null)
                  Marker(
                      point: _pt(Map<String, dynamic>.from(_plan!['destination'] as Map))!,
                      width: 34,
                      height: 34,
                      child: const MapPin(color: AppColors.red, icon: CupertinoIcons.flag_fill, size: 30)),
              ]),
            if (showPins)
              MarkerLayer(markers: [
                for (final d in items)
                  if (_pt(d) != null)
                    Marker(
                      point: _pt(d)!,
                      width: 64,
                      height: 46,
                      child: GestureDetector(onTap: () => _details(d), child: _Label(d)),
                    ),
              ]),
            if (_pulse != null)
              MarkerLayer(markers: [
                Marker(point: _pulse!, width: 90, height: 90, child: const IgnorePointer(child: _Pulse())),
              ]),
            const MapCredit(),
          ],
        ),
        // top overlay
        Positioned(
          left: 12,
          right: 12,
          top: MediaQuery.paddingOf(context).top + 6,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              Pressable(
                onTap: () => Navigator.pop(context),
                child: Semantics(
                  label: 'Back',
                  child: Glass(
                    radius: 99,
                    opacity: 0.88,
                    child: SizedBox(width: 44, height: 44, child: Icon(CupertinoIcons.chevron_left, size: 20, color: c.text)),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Glass(
                  radius: 14,
                  opacity: 0.9,
                  child: Padding(
                    padding: const EdgeInsets.all(3),
                    child: Row(children: [
                      for (final (m, label) in [(_Show.areas, 'Areas'), (_Show.pins, 'Pins'), (_Show.both, 'Both')])
                        Expanded(
                          child: Semantics(
                            button: true,
                            selected: _show == m,
                            label: 'Show $label',
                            child: GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onTap: () => setState(() => (_show = m, _pickedCell = null)),
                              child: AnimatedContainer(
                                duration: const Duration(milliseconds: 150),
                                height: 38,
                                alignment: Alignment.center,
                                decoration: BoxDecoration(
                                    color: _show == m ? AppColors.blue : Colors.transparent, borderRadius: BorderRadius.circular(11)),
                                child: Text(label,
                                    style: TextStyle(
                                        fontSize: 14, fontWeight: FontWeight.w700, color: _show == m ? Colors.white : c.text)),
                              ),
                            ),
                          ),
                        ),
                    ]),
                  ),
                ),
              ),
            ]),
            const SizedBox(height: 8),
            _summaryStrip(context),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Glass(
                  radius: 12,
                  opacity: 0.9,
                  child: Padding(padding: const EdgeInsets.all(10), child: Text(_error!, style: const TextStyle(fontSize: 13))),
                ),
              ),
            if (_show != _Show.pins) ...[const SizedBox(height: 6), _legend(context)],
            if (_pickedCell != null && _show != _Show.pins) ...[const SizedBox(height: 6), _cellTip(context)],
            if (_banner != null) ...[const SizedBox(height: 6), _bannerBox()],
          ]),
        ),
        _sheetView(context),
      ]),
    );
  }

  bool plannerHasRoute(List routes) => routes.isNotEmpty;

  Widget _bannerBox() => Material(
        color: const Color(0xFF17191D),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
          child: Row(children: [
            const Icon(CupertinoIcons.arrow_2_circlepath, size: 16, color: _zoneYellow),
            const SizedBox(width: 8),
            Expanded(child: Text(_banner!, style: const TextStyle(color: Colors.white, fontSize: 13.5, fontWeight: FontWeight.w600))),
            IconButton(
                tooltip: 'Dismiss',
                onPressed: () => setState(() => _banner = null),
                icon: const Icon(Icons.close, size: 18, color: Colors.white)),
          ]),
        ),
      );

  Widget _cellTip(BuildContext context) {
    final c = _pickedCell!;
    return Glass(
      radius: 12,
      opacity: 0.94,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 4, 10),
        child: Row(children: [
          Container(width: 14, height: 14, decoration: BoxDecoration(color: _zoneColor('${c['level']}'), borderRadius: BorderRadius.circular(3))),
          const SizedBox(width: 10),
          Expanded(child: Text('${c['label']}', style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700))),
          IconButton(
              tooltip: 'Close', onPressed: () => setState(() => _pickedCell = null), icon: const Icon(Icons.close, size: 18)),
        ]),
      ),
    );
  }

  Widget _legend(BuildContext context) {
    Widget chip(Color col, String t) => Row(mainAxisSize: MainAxisSize.min, children: [
          Container(width: 12, height: 12, decoration: BoxDecoration(color: col, borderRadius: BorderRadius.circular(3))),
          const SizedBox(width: 5),
          Text(t, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        ]);
    return Semantics(
      label: 'Legend. Green 1 to 2 defects, yellow 3 to 5, red 6 or more or 3 or more serious',
      child: Glass(
        radius: 12,
        opacity: 0.9,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Wrap(spacing: 12, runSpacing: 4, children: [
            chip(_zoneGreen, '1 to 2 defects'),
            chip(_zoneYellow, '3 to 5'),
            chip(_zoneRed, '6+ or 3+ serious'),
          ]),
        ),
      ),
    );
  }

  Widget _summaryStrip(BuildContext context) {
    final s = _summary;
    final items = <(String, String, Color?)>[
      ('Open defects', '${s?['open_defects'] ?? (_items?.where((d) => d['status'] != 'repaired').length ?? '-')}', null),
      ('Complaints', '${s?['complaints_total'] ?? '-'}', null),
      ('Still open', '${s?['complaints_open'] ?? '-'}', AppColors.orange),
      ('Red zones', '${s?['red_zones'] ?? '-'}', _zoneRed),
      ('Most affected', '${s?['most_affected_area'] ?? '-'}', null),
    ];
    return SizedBox(
      height: 58,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: items.length,
        separatorBuilder: (_, _) => const SizedBox(width: 6),
        itemBuilder: (_, i) {
          final it = items[i];
          return Semantics(
            label: '${it.$1}: ${it.$2}',
            child: Glass(
              radius: 12,
              opacity: 0.92,
              child: ConstrainedBox(
                constraints: BoxConstraints(minWidth: 84, maxWidth: i == items.length - 1 ? 190 : 120),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
                    Text(it.$2,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: i == items.length - 1 ? 13.5 : 20, fontWeight: FontWeight.w800, color: it.$3)),
                    Text(it.$1, style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600, color: Color(0xFF6E6E73))),
                  ]),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _sheetView(BuildContext context) {
    final c = AppColors.of(context);
    return DraggableScrollableSheet(
      controller: _sheet,
      initialChildSize: 0.16,
      minChildSize: 0.09,
      maxChildSize: 0.88,
      snap: true,
      snapSizes: const [0.16, 0.5, 0.88],
      builder: (ctx, scroll) => Container(
        decoration: BoxDecoration(
          color: c.card,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(22)),
          boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 18)],
        ),
        child: ListView(
          controller: scroll,
          padding: EdgeInsets.fromLTRB(14, 0, 14, 24 + MediaQuery.viewInsetsOf(context).bottom),
          children: [
            Semantics(
              label: 'Drag to expand or collapse the panel',
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Container(width: 40, height: 5, decoration: BoxDecoration(color: c.separator, borderRadius: BorderRadius.circular(3))),
                ),
              ),
            ),
            Row(children: [
              for (final (i, label) in [(0, 'Recent reports'), (1, 'Plan a route')])
                Expanded(
                  child: Semantics(
                    button: true,
                    selected: _tab == i,
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () {
                        setState(() => _tab = i);
                        if (_sheet.size < 0.4) _sheet.animateTo(0.5, duration: const Duration(milliseconds: 220), curve: Curves.easeOut);
                      },
                      child: Container(
                        height: 44,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                            border: Border(bottom: BorderSide(color: _tab == i ? _zoneYellow : c.separator, width: 3))),
                        child: Text(label, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: _tab == i ? c.text : c.textSecondary)),
                      ),
                    ),
                  ),
                ),
            ]),
            const SizedBox(height: 10),
            if (_tab == 0) ..._reportsList(context) else ..._plannerView(context),
            const SizedBox(height: 10),
            Text(
                'Privacy: no names, phone numbers or photos are shown. Only the place, type and status of each report.',
                style: T.caption(context)),
          ],
        ),
      ),
    );
  }

  List<Widget> _reportsList(BuildContext context) {
    final c = AppColors.of(context);
    final list = _reports;
    if (list == null) {
      return [const Padding(padding: EdgeInsets.all(24), child: Center(child: CupertinoActivityIndicator()))];
    }
    if (list.isEmpty) {
      return [Padding(padding: const EdgeInsets.all(20), child: Center(child: Text('No reports yet. Be the first to report a road problem.', textAlign: TextAlign.center, style: T.sub(context))))];
    }
    return [
      for (final r in list)
        Builder(builder: (_) {
          final fresh = _fresh.contains('${r['number']}');
          final p = _pt(r);
          final t = _parseUtc(r['created_at']);
          final cat = categoryOf('${r['category']}');
          return Semantics(
            button: p != null,
            label: '${r['number']}, ${cat.label}, ${r['area'] ?? 'unknown area'}, ${statusStyle('${r['status']}').label}',
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: p == null ? null : () => _focus(p),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 500),
                margin: const EdgeInsets.only(bottom: 6),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                constraints: const BoxConstraints(minHeight: 56),
                decoration: BoxDecoration(
                  color: fresh ? _zoneYellow.withValues(alpha: 0.22) : c.cardAlt,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Row(children: [
                  IconBadge(cat.icon, cat.color, size: 38),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${cat.label}  ${r['number']}', style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700)),
                      Text('${r['area'] ?? 'Location not shared'}${t == null ? '' : ', ${timeAgo(t)}'}',
                          maxLines: 2, overflow: TextOverflow.ellipsis, style: T.sub(context).copyWith(fontSize: 13)),
                    ]),
                  ),
                  const SizedBox(width: 8),
                  StatusPill('${r['status']}'),
                ]),
              ),
            ),
          );
        }),
    ];
  }

  static String _eta(num min) {
    final t = DateTime.now().add(Duration(minutes: min.round()));
    final h = t.hour % 12 == 0 ? 12 : t.hour % 12;
    return '$h:${t.minute.toString().padLeft(2, '0')} ${t.hour < 12 ? 'AM' : 'PM'}';
  }

  static String _meters(num m) => m >= 1000 ? '${(m / 1000).toStringAsFixed(1)} km' : '${m.round()} m';

  List<Widget> _plannerView(BuildContext context) {
    final c = AppColors.of(context);
    final routes = (_plan?['routes'] as List? ?? []);
    final route = _selRoute;
    final info = _info;
    final advice = '${_plan?['advice'] ?? ''}'.trim();
    return [
      PlaceField(
        controller: _from,
        hint: 'From (place or latitude, longitude)',
        icon: CupertinoIcons.circle_fill,
        onPicked: (p) => _fromPt = p.point,
        onEdited: () => _fromPt = null,
      ),
      const SizedBox(height: 8),
      PlaceField(
        controller: _to,
        hint: 'To (place or latitude, longitude)',
        icon: CupertinoIcons.flag_fill,
        action: TextInputAction.go,
        onSubmit: _compare,
        onPicked: (p) => _toPt = p.point,
        onEdited: () => _toPt = null,
      ),
      const SizedBox(height: 8),
      Row(children: [
        Expanded(
          child: OutlinedButton.icon(
            style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
            onPressed: _locating ? null : _useMyLocation,
            icon: _locating
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(CupertinoIcons.location_fill, size: 16),
            label: const Text('My location'),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48), backgroundColor: _zoneYellow, foregroundColor: Colors.black),
            onPressed: _planning ? null : _compare,
            child: _planning
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Get directions', style: TextStyle(fontWeight: FontWeight.w800)),
          ),
        ),
      ]),
      if (_routeMsg != null && _routeMsg!.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Semantics(
            liveRegion: true,
            child: Text(_routeMsg!, style: TextStyle(fontSize: 14, color: _routeErr ? _zoneRed : c.textSecondary, fontWeight: FontWeight.w600)),
          ),
        )
      else if (_plan == null)
        Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Text('Routes are compared by driving time and by the road damage reported along them, updated live.', style: T.sub(context)),
        ),
      if (_plan != null && advice.isNotEmpty)
        Container(
          margin: const EdgeInsets.only(top: 12),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: _zoneGreen.withValues(alpha: 0.16),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: _zoneGreen, width: 1.5),
          ),
          child: Semantics(
            liveRegion: true,
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Icon(CupertinoIcons.checkmark_shield_fill, color: _zoneGreen, size: 22),
              const SizedBox(width: 10),
              Expanded(child: Text(advice, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700))),
            ]),
          ),
        ),
      const SizedBox(height: 10),
      for (var i = 0; i < routes.length; i++) _routeCard(context, Map<String, dynamic>.from(routes[i] as Map), i),
      if (route != null && info != null) ...[
        const SizedBox(height: 4),
        Text('Road damage on this route', style: T.title(context).copyWith(fontSize: 17)),
        const SizedBox(height: 8),
        if (info.hits.isEmpty)
          Text('No reported road damage on this route.', style: T.sub(context))
        else
          for (final h in info.hits) _hitTile(context, h),
        const SizedBox(height: 10),
        _stepsView(context, route),
      ],
    ];
  }

  Widget _hitTile(BuildContext context, _Hit h) {
    final c = AppColors.of(context);
    final cls = '${h.d['class'] ?? 'pothole'}'.replaceAll('_', ' ');
    final severe = h.risk >= 70;
    final p = _pt(h.d);
    return Semantics(
      button: p != null,
      label: '$cls number ${h.d['number']}, ${_meters(h.along)} from the start, risk ${h.risk.round()}',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: p == null ? null : () => _focus(p),
        child: Container(
          margin: const EdgeInsets.only(bottom: 6),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
          constraints: const BoxConstraints(minHeight: 48),
          decoration: BoxDecoration(color: c.cardAlt, borderRadius: BorderRadius.circular(12)),
          child: Row(children: [
            Container(
              width: 30,
              height: 30,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: severe ? _zoneRed : _routeAmber, shape: BoxShape.circle),
              child: Text('${h.d['number'] ?? ''}', style: const TextStyle(color: Colors.white, fontSize: 10.5, fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(cls.isEmpty ? 'Pothole' : '${cls[0].toUpperCase()}${cls.substring(1)}',
                    style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700)),
                Text('${_meters(h.along)} from start${severe ? ', serious' : ''}',
                    style: TextStyle(fontSize: 12.5, color: severe ? _zoneRed : c.textSecondary, fontWeight: FontWeight.w600)),
              ]),
            ),
          ]),
        ),
      ),
    );
  }

  Widget _stepsView(BuildContext context, Map<String, dynamic> route) {
    final c = AppColors.of(context);
    final steps = [for (final s in (route['steps'] as List? ?? [])) Map<String, dynamic>.from(s as Map)];
    if (steps.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Semantics(
        button: true,
        expanded: _stepsOpen,
        label: 'Step by step directions, ${steps.length} steps',
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => setState(() => _stepsOpen = !_stepsOpen),
          child: Container(
            constraints: const BoxConstraints(minHeight: 48),
            child: Row(children: [
              Expanded(child: Text('Step by step (${steps.length})', style: T.title(context).copyWith(fontSize: 17))),
              Icon(_stepsOpen ? CupertinoIcons.chevron_up : CupertinoIcons.chevron_down, size: 18, color: c.textSecondary),
            ]),
          ),
        ),
      ),
      if (_stepsOpen)
        for (var i = 0; i < steps.length; i++)
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              final p = _pt(steps[i]);
              if (p != null) _focus(p, zoom: 17);
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 7),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(width: 26, child: Text('${i + 1}.', style: TextStyle(fontWeight: FontWeight.w800, color: c.textSecondary))),
                Expanded(child: Text('${steps[i]['text'] ?? ''}', style: const TextStyle(fontSize: 14.5))),
                const SizedBox(width: 8),
                if (steps[i]['distance_m'] is num && (steps[i]['distance_m'] as num) > 0)
                  Text(_meters(steps[i]['distance_m'] as num), style: TextStyle(fontSize: 13, color: c.textSecondary, fontWeight: FontWeight.w600)),
              ]),
            ),
          ),
    ]);
  }

  Widget _routeCard(BuildContext context, Map<String, dynamic> r, int i) {
    final c = AppColors.of(context);
    final labels = [for (final l in (r['labels'] as List? ?? [])) '$l'];
    final defects = (r['defect_count'] as num?)?.toInt() ?? 0;
    final severe = (r['severe_count'] as num?)?.toInt() ?? 0;
    final mins = (r['duration_min'] as num?) ?? 0;
    final sel = i == _sel;
    Widget chip(String l) => Container(
          margin: const EdgeInsets.only(left: 6),
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(color: l == 'recommended' ? _zoneGreen : c.fill, borderRadius: BorderRadius.circular(7)),
          child: Text(l, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: l == 'recommended' ? Colors.white : c.text)),
        );
    return Semantics(
      button: true,
      selected: sel,
      label: 'Route ${i + 1}, ${r['duration_min']} minutes, arrive ${_eta(mins)}, ${r['distance_km']} kilometres, $defects reported potholes, ${labels.join(', ')}',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          setState(() => _sel = i);
          _fitRoute();
        },
        child: Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          constraints: const BoxConstraints(minHeight: 64),
          decoration: BoxDecoration(
            color: c.cardAlt,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: sel ? _zoneYellow : Colors.transparent, width: 2),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(crossAxisAlignment: WrapCrossAlignment.center, runSpacing: 4, children: [
              Text('${r['duration_min']} min', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
              const SizedBox(width: 8),
              Text('${r['distance_km']} km, arrive ${_eta(mins)}', style: T.sub(context)),
              for (final l in labels) chip(l),
              if (r['detour'] == true) chip('detour'),
            ]),
            const SizedBox(height: 4),
            Text(defects == 0 ? 'No reported potholes on this route' : '$defects reported ${defects == 1 ? 'pothole' : 'potholes'}, $severe serious',
                style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: severe > 0 ? _zoneRed : c.textSecondary)),
          ]),
        ),
      ),
    );
  }
}

/// A reported defect near the route and how far along the route it is.
class _Hit {
  final Map<String, dynamic> d;
  final double along, risk;
  _Hit(this.d, this.along, this.risk);
}

const _hitMeters = 28.0;
const _routeBlue = Color(0xFF1F5FBF);
const _routeAmber = Color(0xFFE08A00);

/// Route split into coloured runs: blue, amber near any defect, red near a defect with risk of 70 or more.
class _RouteInfo {
  final List<List<LatLng>> runs;
  final List<Color> colors;
  final List<_Hit> hits;
  _RouteInfo(this.runs, this.colors, this.hits);

  static double _m(LatLng a, LatLng b) {
    const r = 6371000.0;
    double rad(double d) => d * math.pi / 180;
    final h = math.pow(math.sin(rad(b.latitude - a.latitude) / 2), 2) +
        math.cos(rad(a.latitude)) * math.cos(rad(b.latitude)) * math.pow(math.sin(rad(b.longitude - a.longitude) / 2), 2);
    return 2 * r * math.asin(math.sqrt(h));
  }

  /// Distance in metres from p to segment a-b, and the fraction along the segment of the closest point.
  static (double, double) _seg(LatLng p, LatLng a, LatLng b) {
    final k = math.cos(p.latitude * math.pi / 180) * 111320, ky = 110574.0;
    final ax = (a.longitude - p.longitude) * k, ay = (a.latitude - p.latitude) * ky;
    final bx = (b.longitude - p.longitude) * k, by = (b.latitude - p.latitude) * ky;
    final dx = bx - ax, dy = by - ay;
    final len2 = dx * dx + dy * dy;
    final t = len2 == 0 ? 0.0 : ((-ax * dx - ay * dy) / len2).clamp(0.0, 1.0);
    final px = ax + t * dx, py = ay + t * dy;
    return (math.sqrt(px * px + py * py), t);
  }

  static _RouteInfo of(List<LatLng> g, List<Map<String, dynamic>> defects) {
    if (g.length < 2) return _RouteInfo([g], [_routeBlue], []);
    final cum = <double>[0];
    for (var i = 1; i < g.length; i++) {
      cum.add(cum.last + _m(g[i - 1], g[i]));
    }
    final lvl = List<int>.filled(g.length - 1, 0);
    final hits = <_Hit>[];
    for (final d in defects) {
      final p = _pt(d);
      if (p == null) continue;
      final risk = ((d['risk'] as num?) ?? 0).toDouble();
      var best = double.infinity, along = 0.0;
      for (var i = 0; i < g.length - 1; i++) {
        final (dist, t) = _seg(p, g[i], g[i + 1]);
        if (dist <= _hitMeters) lvl[i] = math.max(lvl[i], risk >= 70 ? 2 : 1);
        if (dist < best) {
          best = dist;
          along = cum[i] + t * (cum[i + 1] - cum[i]);
        }
      }
      hits.add(_Hit(d, along, risk));
    }
    hits.sort((a, b) => a.along.compareTo(b.along));
    final runs = <List<LatLng>>[], colors = <Color>[];
    var start = 0;
    for (var i = 1; i <= lvl.length; i++) {
      if (i == lvl.length || lvl[i] != lvl[start]) {
        runs.add(g.sublist(start, i + 1));
        colors.add(switch (lvl[start]) { 2 => _zoneRed, 1 => _routeAmber, _ => _routeBlue });
        start = i;
      }
    }
    return _RouteInfo(runs, colors, hits);
  }
}

class _Pulse extends StatelessWidget {
  const _Pulse();
  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        tween: Tween(begin: 0.2, end: 1),
        duration: const Duration(milliseconds: 1400),
        curve: Curves.easeOut,
        builder: (_, v, __) => Center(
          child: Container(
            width: 80 * v,
            height: 80 * v,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: _zoneRed.withValues(alpha: 1 - v * 0.8), width: 4),
            ),
          ),
        ),
      );
}

/// Marker: the defect's canonical number on a coloured disc, with the report count beneath.
class _Label extends StatelessWidget {
  const _Label(this.d);
  final Map<String, dynamic> d;
  @override
  Widget build(BuildContext context) {
    final repaired = d['status'] == 'repaired';
    final color = repaired ? AppColors.green : riskColor('${d['severity']}');
    final reports = (d['reports'] as num?)?.toInt() ?? 1;
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(99),
          border: Border.all(color: Colors.white, width: 2),
          boxShadow: const [BoxShadow(color: Color(0x40000000), blurRadius: 4, offset: Offset(0, 1))],
        ),
        child: Text('#${d['number']}', style: const TextStyle(color: Colors.white, fontSize: 11.5, fontWeight: FontWeight.w800)),
      ),
      const SizedBox(height: 2),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
        decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.9), borderRadius: BorderRadius.circular(6)),
        child: Text('$reports ${reports == 1 ? 'report' : 'reports'}',
            style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: Color(0xFF333333))),
      ),
    ]);
  }
}
