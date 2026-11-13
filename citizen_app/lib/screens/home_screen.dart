import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';

import '../api.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';
import 'detail_screen.dart';
import 'report_screen.dart';
import 'reports_screen.dart';

/// Bengaluru, where the helpline number is based. Used until we know where the citizen is.
const _defaultCenter = LatLng(12.9716, 77.5946);

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.onSeeAll});
  final VoidCallback onSeeAll;
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _map = MapController();
  List<Complaint>? _items;
  List<Map<String, dynamic>> _defects = [];
  String? _error;
  bool _mapReady = false;

  @override
  void initState() {
    super.initState();
    _load();
    refreshTick.addListener(_load);
    prefs.addListener(_rebuild);
    locator.addListener(_onLocation);
    locator.locate();
  }

  @override
  void dispose() {
    refreshTick.removeListener(_load);
    prefs.removeListener(_rebuild);
    locator.removeListener(_onLocation);
    super.dispose();
  }

  void _rebuild() => mounted ? setState(() {}) : null;

  void _onLocation() {
    final s = locator.spot;
    if (s != null && _mapReady) _map.move(LatLng(s.lat, s.lon), 15);
    _rebuild();
  }

  Future<void> _load() async {
    final defects = api.defects();
    try {
      final r = await api.myComplaints();
      if (mounted) setState(() => (_items = r, _error = null));
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
    final d = await defects;
    if (mounted) setState(() => _defects = d);
  }

  void _report([String? category]) => Navigator.of(context).push(
        CupertinoPageRoute(fullscreenDialog: true, builder: (_) => ReportScreen(initialCategory: category)),
      );

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final top = MediaQuery.paddingOf(context).top;
    final spot = locator.spot;
    final items = _items ?? [];
    return Stack(children: [
      Positioned.fill(
        bottom: MediaQuery.sizeOf(context).height * 0.36,
        child: FlutterMap(
          mapController: _map,
          options: MapOptions(
            initialCenter: spot != null ? LatLng(spot.lat, spot.lon) : _defaultCenter,
            initialZoom: spot != null ? 15 : 12,
            onMapReady: () => _mapReady = true,
            interactionOptions: const InteractionOptions(flags: InteractiveFlag.all & ~InteractiveFlag.rotate),
          ),
          children: [
            const MapTiles(),
            MarkerLayer(markers: [
              for (final d in _defects)
                Marker(
                  point: LatLng((d['lat'] as num).toDouble(), (d['lon'] as num).toDouble()),
                  width: 14,
                  height: 14,
                  child: _DefectDot(risk: d['risk_level'] as String?),
                ),
              for (final x in items)
                if (x.lat != null)
                  Marker(
                    point: LatLng(x.lat!, x.lon!),
                    width: 32,
                    height: 32,
                    child: GestureDetector(
                      onTap: () => Navigator.of(context)
                          .push(CupertinoPageRoute(builder: (_) => DetailScreen(id: x.id, initial: x))),
                      child: ReportPin(color: x.status == 'resolved' ? const Color(0xFF7FD3A8) : Palette.yellow),
                    ),
                  ),
              if (spot != null) Marker(point: LatLng(spot.lat, spot.lon), width: 44, height: 44, child: const YouAreHere()),
            ]),
            const MapCredit(),
          ],
        ),
      ),
      // wordmark plate + locate control
      Positioned(
        top: top + 12,
        left: 16,
        child: const SignPlate(
          face: Palette.asphalt,
          legend: Colors.white,
          radius: 10,
          padding: EdgeInsets.symmetric(horizontal: 12, vertical: 5),
          child: Text('RoadWatch',
              style: TextStyle(fontFamily: fontDisplay, fontSize: 22, fontWeight: FontWeight.w800, color: Colors.white)),
        ),
      ),
      Positioned(
        top: top + 12,
        right: 16,
        child: Pressable(
          onTap: () async {
            final s = await locator.locate(force: true);
            if (s == null && context.mounted && locator.error != null) toast(context, locator.error!, error: true);
          },
          child: Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: c.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: c.line),
            ),
            child: locator.busy
                ? const CupertinoActivityIndicator()
                : Icon(PhosphorIconsBold.crosshair, color: c.ink, size: 22),
          ),
        ),
      ),
      DraggableScrollableSheet(
        initialChildSize: 0.56,
        minChildSize: 0.40,
        maxChildSize: 0.94,
        snap: true,
        snapSizes: const [0.56],
        builder: (context, scroll) => Container(
          decoration: BoxDecoration(
            color: c.bg,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
            boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 24, offset: Offset(0, -2))],
          ),
          child: RefreshIndicator(
            onRefresh: _load,
            color: Palette.asphalt,
            backgroundColor: Palette.yellow,
            child: ListView(
              controller: scroll,
              physics: const AlwaysScrollableScrollPhysics(parent: ClampingScrollPhysics()),
              padding: const EdgeInsets.fromLTRB(20, 10, 20, 32),
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 5,
                    decoration: BoxDecoration(color: c.line, borderRadius: BorderRadius.circular(3)),
                  ),
                ),
                const SizedBox(height: 18),
                if (spot?.area?.isNotEmpty == true)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(children: [
                      Icon(PhosphorIconsFill.mapPin, size: 16, color: c.inkSoft),
                      const SizedBox(width: 5),
                      Expanded(child: Text(spot!.area!, style: T.small(context).copyWith(color: c.inkSoft))),
                    ]),
                  ),
                Text('Seen a bad road?', style: T.display(context)),
                const SizedBox(height: 8),
                Text('Send a photo. The repair team gets it with the exact spot on the map.', style: T.sub(context)),
                const SizedBox(height: 18),
                YellowButton(label: 'Report damage', icon: PhosphorIconsBold.camera, onTap: _report),
                const SizedBox(height: 12),
                HelplinePlate(number: prefs.helpline),
                SectionTitle(
                  'Your reports',
                  trailing: items.length > 3
                      ? CupertinoButton(
                          padding: EdgeInsets.zero,
                          minimumSize: Size.zero,
                          onPressed: widget.onSeeAll,
                          child: Text('See all ${items.length}',
                              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: c.ink,
                                  decoration: TextDecoration.underline, decorationColor: Palette.yellow, decorationThickness: 2.5)),
                        )
                      : null,
                ),
                if (_items == null && _error == null)
                  const Padding(padding: EdgeInsets.all(24), child: CupertinoActivityIndicator())
                else if (_error != null && items.isEmpty)
                  _Notice(
                    icon: PhosphorIconsBold.wifiSlash,
                    title: 'Can\'t reach RoadWatch',
                    text: _error!,
                  )
                else if (items.isEmpty)
                  const _FirstReport()
                else ...[
                  for (final x in items.take(3)) ComplaintRow(x),
                ],
              ],
            ),
          ),
        ),
      ),
    ]);
  }
}

/// Green highway sign with white legend: the helpline.
class HelplinePlate extends StatelessWidget {
  const HelplinePlate({super.key, required this.number, this.subtitle});
  final String number;
  final String? subtitle;
  @override
  Widget build(BuildContext context) => SignPlate(
        face: Palette.green,
        legend: Colors.white,
        onTap: () => callAgent(context, number),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        child: Row(children: [
          const Icon(PhosphorIconsFill.phoneCall, size: 28),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Call the helpline',
                  style: TextStyle(fontFamily: fontDisplay, fontSize: 22, fontWeight: FontWeight.w800, color: Colors.white)),
              Text(subtitle ?? '${prettyPhone(number)}, in Hindi or English',
                  style: const TextStyle(fontSize: 14.5, color: Color(0xE6FFFFFF), fontWeight: FontWeight.w500)),
            ]),
          ),
          const Icon(PhosphorIconsBold.arrowUpRight, size: 22),
        ]),
      );
}

class _DefectDot extends StatelessWidget {
  const _DefectDot({this.risk});
  final String? risk;
  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: switch (risk) {
            'High' => Palette.red,
            'Medium' => const Color(0xFFF08A24),
            _ => const Color(0xFF8A9299),
          },
          border: Border.all(color: Colors.white, width: 2),
        ),
      );
}

class _FirstReport extends StatelessWidget {
  const _FirstReport();
  @override
  Widget build(BuildContext context) => Surface(
        padding: const EdgeInsets.all(12),
        child: Row(children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: Image.asset('assets/photos/pothole_sq.jpg', width: 72, height: 72, fit: BoxFit.cover),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Text('Nothing reported yet. Your first report shows up here, with its repair status.',
                style: T.sub(context)),
          ),
        ]),
      );
}

class _Notice extends StatelessWidget {
  const _Notice({required this.icon, required this.title, required this.text});
  final IconData icon;
  final String title, text;
  @override
  Widget build(BuildContext context) => Surface(
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 24, color: AppColors.of(context).inkSoft),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: T.bodyStrong(context)),
              const SizedBox(height: 2),
              Text(text, style: T.sub(context)),
            ]),
          ),
        ]),
      );
}
