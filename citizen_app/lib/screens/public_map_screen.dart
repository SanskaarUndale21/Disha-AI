import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../main.dart';
import '../theme.dart';
import '../widgets.dart';

/// Every known defect in the city, no login needed and no personal data.
class PublicMapScreen extends StatefulWidget {
  const PublicMapScreen({super.key});
  @override
  State<PublicMapScreen> createState() => _PublicMapScreenState();
}

class _PublicMapScreenState extends State<PublicMapScreen> {
  final _map = MapController();
  List<Map<String, dynamic>>? _items;
  String? _error;
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await api.publicDefects();
      if (!mounted) return;
      setState(() => (_items = r, _error = null));
      _fit();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  void _fit() {
    final pts = [for (final d in _items ?? []) LatLng((d['lat'] as num).toDouble(), (d['lon'] as num).toDouble())];
    if (!_ready || pts.isEmpty) return;
    if (pts.length == 1) {
      _map.move(pts.first, 15);
    } else {
      _map.fitCamera(CameraFit.bounds(bounds: LatLngBounds.fromPoints(pts), padding: const EdgeInsets.all(60)));
    }
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

  @override
  Widget build(BuildContext context) {
    final items = _items ?? [];
    final open = items.where((d) => d['status'] != 'repaired').length;
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
            interactionOptions: const InteractionOptions(flags: InteractiveFlag.all & ~InteractiveFlag.rotate),
          ),
          children: [
            const MapTiles(),
            MarkerLayer(markers: [
              for (final d in items)
                Marker(
                  point: LatLng((d['lat'] as num).toDouble(), (d['lon'] as num).toDouble()),
                  width: 64,
                  height: 46,
                  child: GestureDetector(onTap: () => _details(d), child: _Label(d)),
                ),
            ]),
            const MapCredit(),
          ],
        ),
        Positioned(
          left: 14,
          right: 14,
          top: MediaQuery.paddingOf(context).top + 8,
          child: Row(children: [
            Pressable(
              onTap: () => Navigator.pop(context),
              child: Glass(
                radius: 99,
                opacity: 0.85,
                child: SizedBox(
                    width: 40, height: 40, child: Icon(CupertinoIcons.chevron_left, size: 20, color: AppColors.of(context).text)),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Glass(
                radius: 16,
                opacity: 0.88,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  child: Text(
                    _error != null
                        ? _error!
                        : _items == null
                            ? 'Loading the city map...'
                            : '$open open, ${items.length - open} repaired. Tap a marker for details.',
                    style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            ),
          ]),
        ),
      ]),
    );
  }
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
