import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../api.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';
import 'detail_screen.dart';
import 'report_screen.dart';
import 'reports_screen.dart';

/// Bengaluru (the helpline is an 080 number). Used until we know where the citizen is.
const _defaultCenter = LatLng(12.9716, 77.5946);

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.onSeeAll});
  final VoidCallback onSeeAll;
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _map = MapController();
  bool _mapReady = false;
  List<Complaint>? _items;
  List<Map<String, dynamic>> _defects = [];
  String? _error;

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
    if (s != null && _mapReady) _map.move(LatLng(s.lat, s.lon), 14.5);
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

  String get _greeting {
    final h = DateTime.now().hour;
    final part = h < 12 ? 'Good morning' : (h < 17 ? 'Good afternoon' : 'Good evening');
    final first = prefs.name.split(' ').first;
    return first.isEmpty ? part : '$part, $first';
  }

  void _report([String? category]) => Navigator.of(context).push(
        CupertinoPageRoute(fullscreenDialog: true, builder: (_) => ReportScreen(initialCategory: category)),
      );

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final items = _items ?? [];
    final open = items.where((x) => x.status != 'resolved' && x.status != 'rejected').length;
    final resolved = items.where((x) => x.status == 'resolved').length;
    return CustomScrollView(
      physics: const BouncingScrollPhysics(parent: AlwaysScrollableScrollPhysics()),
      slivers: [
        CupertinoSliverRefreshControl(onRefresh: _load),
        SliverSafeArea(
          bottom: false,
          sliver: SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
            sliver: SliverList.list(children: [
              Text(_greeting, style: T.sub(context).copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(height: 2),
              Row(children: [
                Expanded(child: Text('RoadWatch', style: T.largeTitle(context))),
                const IconBadge(CupertinoIcons.location_north_fill, AppColors.blue, size: 38),
              ]),
              const SizedBox(height: 20),
              _HeroCard(onTap: () => _report()),
              const SizedBox(height: 14),
              _CallCard(number: prefs.helpline),
              SectionLabel('Near you',
                  trailing: locator.spot?.area?.isNotEmpty == true
                      ? Flexible(
                          child: Text(locator.spot!.area!,
                              maxLines: 1, overflow: TextOverflow.ellipsis, style: T.sub(context)))
                      : null),
              _nearbyMap(items),
              const SectionLabel('Quick report'),
              SizedBox(
                height: 118,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  clipBehavior: Clip.none,
                  physics: const BouncingScrollPhysics(),
                  itemCount: categories.length,
                  separatorBuilder: (_, _) => const SizedBox(width: 10),
                  itemBuilder: (_, i) {
                    final cat = categories[i];
                    return Pressable(
                      onTap: () => _report(cat.key),
                      child: SizedBox(width: 118, child: PhotoTile(asset: cat.thumb, label: cat.label, icon: cat.icon, color: cat.color)),
                    );
                  },
                ),
              ),
              if (items.isNotEmpty) ...[
                const SizedBox(height: 14),
                Row(children: [
                  Expanded(child: _Stat(value: '${items.length}', label: 'Reported', color: AppColors.blue)),
                  const SizedBox(width: 10),
                  Expanded(child: _Stat(value: '$open', label: 'Open', color: AppColors.orange)),
                  const SizedBox(width: 10),
                  Expanded(child: _Stat(value: '$resolved', label: 'Fixed', color: AppColors.green)),
                ]),
              ],
              SectionLabel('Recent reports',
                  trailing: items.length > 3
                      ? CupertinoButton(
                          padding: EdgeInsets.zero,
                          minimumSize: Size.zero,
                          onPressed: widget.onSeeAll,
                          child: const Text('See all', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w500)),
                        )
                      : null),
              if (_items == null && _error == null)
                const Padding(padding: EdgeInsets.all(30), child: CupertinoActivityIndicator())
              else if (_error != null && items.isEmpty)
                _Empty(
                    icon: CupertinoIcons.wifi_exclamationmark,
                    title: 'Offline',
                    text: _error!,
                    color: c.textTertiary)
              else if (items.isEmpty)
                const _FirstReport()
              else
                for (final x in items.take(3))
                  Padding(padding: const EdgeInsets.only(bottom: 10), child: ComplaintTile(x)),
            ]),
          ),
        ),
      ],
    );
  }

  Widget _nearbyMap(List<Complaint> items) {
    final spot = locator.spot;
    final known = _defects.length;
    return CardBox(
      padding: EdgeInsets.zero,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(22),
        child: SizedBox(
          height: 210,
          child: Stack(children: [
            FlutterMap(
              mapController: _map,
              options: MapOptions(
                initialCenter: spot != null ? LatLng(spot.lat, spot.lon) : _defaultCenter,
                initialZoom: spot != null ? 14.5 : 12,
                onMapReady: () => _mapReady = true,
                interactionOptions: const InteractionOptions(flags: InteractiveFlag.all & ~InteractiveFlag.rotate),
              ),
              children: [
                const MapTiles(),
                MarkerLayer(markers: [
                  for (final d in _defects)
                    Marker(
                      point: LatLng((d['lat'] as num).toDouble(), (d['lon'] as num).toDouble()),
                      width: 22,
                      height: 22,
                      child: MapPin(
                        size: 22,
                        color: switch (d['risk_level']) {
                          'High' => AppColors.red,
                          'Medium' => AppColors.orange,
                          _ => AppColors.yellow,
                        },
                      ),
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
                          child: MapPin(
                            color: statusStyle(x.status).color,
                            icon: CupertinoIcons.person_fill,
                          ),
                        ),
                      ),
                  if (spot != null)
                    Marker(point: LatLng(spot.lat, spot.lon), width: 40, height: 40, child: const YouAreHere()),
                ]),
                const MapCredit(),
              ],
            ),
            Positioned(
              left: 10,
              top: 10,
              child: Glass(
                radius: 99,
                opacity: 0.85,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(CupertinoIcons.exclamationmark_circle_fill, size: 14, color: AppColors.orange),
                    const SizedBox(width: 5),
                    Text(known == 0 ? 'No damage reported nearby' : '$known known spots',
                        style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                  ]),
                ),
              ),
            ),
            Positioned(
              right: 10,
              top: 10,
              child: Pressable(
                onTap: () async {
                  final s = await locator.locate(force: true);
                  if (s == null && mounted && locator.error != null) toast(context, locator.error!, error: true);
                },
                child: Glass(
                  radius: 99,
                  opacity: 0.85,
                  child: SizedBox(
                    width: 36,
                    height: 36,
                    child: locator.busy
                        ? const CupertinoActivityIndicator(radius: 8)
                        : const Icon(CupertinoIcons.location_fill, size: 17, color: AppColors.blue),
                  ),
                ),
              ),
            ),
          ]),
        ),
      ),
    );
  }
}

class _HeroCard extends StatelessWidget {
  const _HeroCard({required this.onTap});
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: onTap,
      child: Container(
        height: 220,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(28),
          boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 30, offset: Offset(0, 14))],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(28),
          child: Stack(fit: StackFit.expand, children: [
            Image.asset('assets/photos/street.jpg', fit: BoxFit.cover),
            // tinted scrim keeps the old blue to indigo character, over a real street
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [Color(0x660A84FF), Color(0xCC1B1A4A)],
                ),
              ),
            ),
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Color(0x00000000), Color(0x99000000)],
                  stops: [0.35, 1],
                ),
              ),
            ),
            Positioned(
              right: 18,
              top: 18,
              child: Glass(
                radius: 14,
                opacity: 0.25,
                child: const Padding(
                  padding: EdgeInsets.all(10),
                  child: Icon(CupertinoIcons.camera_viewfinder, color: Colors.white, size: 28),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(22),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Spacer(),
                const Text('Spotted a bad road?',
                    style: TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -0.8)),
                const SizedBox(height: 4),
                Text('Snap a photo or video. AI checks it and routes it to the repair crew.',
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.88), fontSize: 14.5, height: 1.3)),
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(99)),
                  child: const Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(CupertinoIcons.plus, size: 16, color: AppColors.blue),
                    SizedBox(width: 6),
                    Text('Report an issue',
                        style: TextStyle(color: AppColors.blue, fontWeight: FontWeight.w700, fontSize: 14.5)),
                  ]),
                ),
              ]),
            ),
          ]),
        ),
      ),
    );
  }
}

class CallCard extends StatelessWidget {
  const CallCard({super.key, required this.number, this.subtitle});
  final String number;
  final String? subtitle;
  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: () => callAgent(context, number),
      child: CardBox(
        padding: const EdgeInsets.fromLTRB(16, 14, 14, 14),
        child: Row(children: [
          Stack(clipBehavior: Clip.none, children: [
            const IconBadge(CupertinoIcons.waveform, AppColors.indigo, size: 48),
            Positioned(
              right: -2,
              bottom: -2,
              child: Container(
                width: 14,
                height: 14,
                decoration: BoxDecoration(
                  color: AppColors.green,
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.of(context).card, width: 2.5),
                ),
              ),
            ),
          ]),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Call RoadWatch agent', style: T.headline(context)),
              const SizedBox(height: 2),
              Text(subtitle ?? '${prettyPhone(number)}  ·  Hindi & English',
                  style: T.sub(context).copyWith(fontSize: 13)),
            ]),
          ),
          Container(
            width: 50,
            height: 50,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(colors: [Color(0xFF4CD964), Color(0xFF28B446)]),
              boxShadow: [BoxShadow(color: Color(0x5530D158), blurRadius: 16, offset: Offset(0, 6))],
            ),
            child: const Icon(CupertinoIcons.phone_fill, color: Colors.white, size: 24),
          ),
        ]),
      ),
    );
  }
}

class _CallCard extends CallCard {
  const _CallCard({required super.number});
}

class _Stat extends StatelessWidget {
  const _Stat({required this.value, required this.label, required this.color});
  final String value, label;
  final Color color;
  @override
  Widget build(BuildContext context) => CardBox(
        radius: 18,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(value, style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -0.8, color: color)),
          Text(label, style: T.sub(context).copyWith(fontSize: 13)),
        ]),
      );
}

class _FirstReport extends StatelessWidget {
  const _FirstReport();
  @override
  Widget build(BuildContext context) => CardBox(
        padding: const EdgeInsets.all(12),
        child: Row(children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: Image.asset('assets/photos/pothole_sq.jpg', width: 72, height: 72, fit: BoxFit.cover),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('No reports yet', style: T.headline(context)),
              const SizedBox(height: 3),
              Text('Your complaints and their repair status will show up here.', style: T.sub(context)),
            ]),
          ),
        ]),
      );
}

class _Empty extends StatelessWidget {
  const _Empty({required this.icon, required this.title, required this.text, required this.color});
  final IconData icon;
  final String title, text;
  final Color color;
  @override
  Widget build(BuildContext context) => CardBox(
        padding: const EdgeInsets.symmetric(vertical: 30, horizontal: 24),
        child: Column(children: [
          Icon(icon, size: 36, color: color),
          const SizedBox(height: 10),
          Text(title, style: T.headline(context)),
          const SizedBox(height: 4),
          Text(text, textAlign: TextAlign.center, style: T.sub(context)),
        ]),
      );
}
