import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:video_player/video_player.dart';

import '../api.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';
import 'home_screen.dart' show CallCard;

class DetailScreen extends StatefulWidget {
  const DetailScreen({super.key, required this.id, this.initial});
  final int id;
  final Complaint? initial;
  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  late Complaint? _c = widget.initial;
  Timer? _poll;
  bool _showAi = true;

  @override
  void initState() {
    super.initState();
    _load();
    refreshTick.addListener(_load);
  }

  @override
  void dispose() {
    refreshTick.removeListener(_load);
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final c = await api.complaint(widget.id);
      if (!mounted) return;
      setState(() => _c = c);
      _poll?.cancel();
      if (c.media.any((m) => m.processing)) _poll = Timer(const Duration(seconds: 4), _load);
    } catch (e) {
      if (mounted && _c == null) toast(context, '$e', error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = _c;
    if (c == null) return const Scaffold(body: Center(child: CupertinoActivityIndicator()));
    final cat = categoryOf(c.category);
    final photo = c.media.where((m) => !m.isVideo).firstOrNull;
    final hero = photo == null ? null : (_showAi ? (photo.annotatedUrl ?? photo.mediaUrl) : photo.mediaUrl);
    final top = MediaQuery.paddingOf(context).top;
    final where = latLng(c.lat, c.lon);
    return Scaffold(
      body: Stack(children: [
        CustomScrollView(
          physics: const BouncingScrollPhysics(parent: AlwaysScrollableScrollPhysics()),
          slivers: [
            SliverToBoxAdapter(
              child: SizedBox(
                height: 300 + top,
                child: Stack(fit: StackFit.expand, children: [
                  if (hero != null)
                    Image.network(api.url(hero),
                        fit: BoxFit.cover, errorBuilder: (_, _, _) => Image.asset(cat.image, fit: BoxFit.cover))
                  else
                    Image.asset(cat.image, fit: BoxFit.cover),
                  const DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [Color(0x66000000), Color(0x00000000), Color(0xB3000000)],
                        stops: [0, 0.4, 1],
                      ),
                    ),
                  ),
                  Positioned(
                    left: 20,
                    right: 20,
                    bottom: 22,
                    child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(c.ticket,
                              style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.8), fontWeight: FontWeight.w600, fontSize: 13)),
                          const SizedBox(height: 2),
                          Text(cat.label,
                              style: const TextStyle(
                                  color: Colors.white, fontSize: 32, fontWeight: FontWeight.w800, letterSpacing: -1)),
                          const SizedBox(height: 4),
                          Text('Reported ${timeAgo(c.createdAt)}',
                              style: TextStyle(color: Colors.white.withValues(alpha: 0.85), fontSize: 14)),
                        ]),
                      ),
                      if (photo?.annotatedUrl != null)
                        Pressable(
                          onTap: () => setState(() => _showAi = !_showAi),
                          child: Glass(
                            radius: 99,
                            opacity: 0.55,
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                              child: Row(mainAxisSize: MainAxisSize.min, children: [
                                Icon(_showAi ? CupertinoIcons.eye_slash_fill : CupertinoIcons.viewfinder,
                                    size: 14, color: AppColors.of(context).text),
                                const SizedBox(width: 5),
                                Text(_showAi ? 'Original' : 'AI view',
                                    style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                              ]),
                            ),
                          ),
                        ),
                    ]),
                  ),
                ]),
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 60),
              sliver: SliverList.list(children: [
                _Timeline(status: c.status),
                if (c.adminNote?.isNotEmpty == true) ...[
                  const SizedBox(height: 12),
                  CardBox(
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const IconBadge(CupertinoIcons.bubble_left_fill, AppColors.indigo, size: 34),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('Update from the city', style: T.headline(context).copyWith(fontSize: 15)),
                          const SizedBox(height: 3),
                          Text(c.adminNote!, style: T.sub(context)),
                        ]),
                      ),
                    ]),
                  ),
                ],
                _aiSection(c),
                if (c.media.isNotEmpty) ...[
                  const SectionLabel('Evidence'),
                  GridView.count(
                    crossAxisCount: 3,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    mainAxisSpacing: 8,
                    crossAxisSpacing: 8,
                    children: [for (final m in c.media) _mediaCell(m)],
                  ),
                ],
                const SectionLabel('Location'),
                CardBox(
                  padding: EdgeInsets.zero,
                  child: Column(children: [
                    if (where != null)
                      ClipRRect(
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(22)),
                        child: SizedBox(
                          height: 160,
                          child: FlutterMap(
                            options: MapOptions(
                              initialCenter: where,
                              initialZoom: 16.5,
                              interactionOptions: const InteractionOptions(flags: InteractiveFlag.none),
                            ),
                            children: [
                              const MapTiles(),
                              MarkerLayer(markers: [
                                Marker(point: where, width: 34, height: 34, child: MapPin(color: cat.color, size: 34)),
                              ]),
                              const MapCredit(),
                            ],
                          ),
                        ),
                      ),
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        if (c.description.isNotEmpty) ...[
                          Text(c.description, style: T.body(context)),
                          const SizedBox(height: 14),
                        ],
                        _info(
                            CupertinoIcons.location_solid,
                            c.address?.isNotEmpty == true
                                ? c.address!
                                : (where != null
                                    ? '${c.lat!.toStringAsFixed(5)}, ${c.lon!.toStringAsFixed(5)}'
                                    : 'No location')),
                        const SizedBox(height: 10),
                        _info(CupertinoIcons.clock_fill, 'Updated ${timeAgo(c.updatedAt)}'),
                      ]),
                    ),
                  ]),
                ),
                const SizedBox(height: 16),
                CallCard(number: prefs.helpline, subtitle: 'Questions? Quote ${c.ticket}'),
              ]),
            ),
          ],
        ),
        Positioned(
          top: top + 8,
          left: 14,
          child: Pressable(
            onTap: () => Navigator.pop(context),
            child: Glass(
              radius: 99,
              opacity: 0.55,
              child: SizedBox(
                width: 40,
                height: 40,
                child: Icon(CupertinoIcons.chevron_left, size: 20, color: AppColors.of(context).text),
              ),
            ),
          ),
        ),
      ]),
    );
  }

  Widget _info(IconData icon, String text) => Row(children: [
        Icon(icon, size: 16, color: AppColors.of(context).textTertiary),
        const SizedBox(width: 10),
        Expanded(child: Text(text, style: T.sub(context))),
      ]);

  Widget _aiSection(Complaint c) {
    if (c.media.isEmpty) return const SizedBox.shrink();
    final processing = c.media.any((m) => m.processing);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SectionLabel('AI inspection'),
      CardBox(
        child: processing && c.findings.isEmpty
            ? Row(children: [
                const CupertinoActivityIndicator(),
                const SizedBox(width: 12),
                Expanded(child: Text('Scanning your video frame by frame...', style: T.sub(context))),
              ])
            : c.findings.isEmpty
                ? Row(children: [
                    const IconBadge(CupertinoIcons.person_2_fill, AppColors.blue, size: 34),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text('No damage auto-detected. An inspector will review your media.', style: T.sub(context)),
                    ),
                  ])
                : Column(children: [
                    for (var i = 0; i < c.findings.length; i++) ...[
                      if (i > 0) Divider(height: 20, thickness: 0.5, color: AppColors.of(context).separator),
                      _finding(c.findings[i]),
                    ],
                  ]),
      ),
    ]);
  }

  Widget _finding(Finding f) {
    final color = riskColor(f.riskLevel ?? f.severity);
    return Row(children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: SizedBox(
          width: 44,
          height: 44,
          child: f.cropUrl != null
              ? Image.network(api.url(f.cropUrl),
                  fit: BoxFit.cover, errorBuilder: (_, _, _) => Container(color: color.withValues(alpha: 0.15)))
              : Container(color: color.withValues(alpha: 0.15)),
        ),
      ),
      const SizedBox(width: 12),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(f.label[0].toUpperCase() + f.label.substring(1), style: T.headline(context).copyWith(fontSize: 15.5)),
          Text('${(f.confidence * 100).round()}% confidence${f.defectUid != null ? '  ·  ${f.defectUid}' : ''}',
              style: T.sub(context).copyWith(fontSize: 12.5)),
        ]),
      ),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(99)),
        child: Text('${f.riskLevel ?? f.severity} risk',
            style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700)),
      ),
    ]);
  }

  Widget _mediaCell(MediaItem m) {
    final src = m.isVideo ? m.mediaUrl : (m.annotatedUrl ?? m.mediaUrl);
    return Pressable(
      onTap: src == null
          ? null
          : () => Navigator.of(context).push(PageRouteBuilder(
                opaque: false,
                barrierColor: Colors.black,
                pageBuilder: (_, _, _) =>
                    _Viewer(url: api.url(m.isVideo ? (m.annotatedUrl ?? src) : src), video: m.isVideo),
                transitionsBuilder: (_, a, _, child) => FadeTransition(opacity: a, child: child),
              )),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Stack(fit: StackFit.expand, children: [
          if (!m.isVideo && src != null)
            Image.network(api.url(src), fit: BoxFit.cover, errorBuilder: (_, _, _) => Container(color: Colors.black12))
          else
            Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(colors: [Color(0xFF2C2C2E), Color(0xFF0B0B0F)]),
              ),
            ),
          if (m.isVideo)
            Center(
              child: m.processing
                  ? Column(mainAxisSize: MainAxisSize.min, children: [
                      const CupertinoActivityIndicator(color: Colors.white),
                      const SizedBox(height: 6),
                      Text('${(m.progress * 100).round()}%',
                          style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
                    ])
                  : const Icon(CupertinoIcons.play_circle_fill, color: Colors.white, size: 36),
            ),
        ]),
      ),
    );
  }
}

class _Timeline extends StatelessWidget {
  const _Timeline({required this.status});
  final String status;
  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    if (status == 'rejected') {
      return CardBox(
        child: Row(children: [
          const IconBadge(CupertinoIcons.xmark, AppColors.red, size: 36),
          const SizedBox(width: 12),
          Expanded(child: Text('This report was closed by the city.', style: T.headline(context).copyWith(fontSize: 15.5))),
        ]),
      );
    }
    final idx = statusOrder.indexOf(status).clamp(0, statusOrder.length - 1);
    return CardBox(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text('Status', style: T.caption(context)),
          const Spacer(),
          StatusPill(status),
        ]),
        const SizedBox(height: 18),
        Row(children: [
          for (var i = 0; i < statusOrder.length; i++) ...[
            _dot(i <= idx, statusStyle(statusOrder[i]).color, i == idx),
            if (i < statusOrder.length - 1)
              Expanded(
                child: Container(
                  height: 3,
                  margin: const EdgeInsets.symmetric(horizontal: 4),
                  decoration: BoxDecoration(
                    color: i < idx ? AppColors.blue : c.fill,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
          ],
        ]),
        const SizedBox(height: 8),
        Row(children: [
          for (var i = 0; i < statusOrder.length; i++)
            Expanded(
              child: Text(
                const ['Submitted', 'Review', 'Repair', 'Fixed'][i],
                textAlign: i == 0 ? TextAlign.left : (i == statusOrder.length - 1 ? TextAlign.right : TextAlign.center),
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: i == idx ? FontWeight.w700 : FontWeight.w500,
                  color: i <= idx ? c.text : c.textTertiary,
                ),
              ),
            ),
        ]),
      ]),
    );
  }

  Widget _dot(bool done, Color color, bool current) => AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        width: current ? 22 : 16,
        height: current ? 22 : 16,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: done ? (current ? color : AppColors.blue) : Colors.transparent,
          border: Border.all(color: done ? Colors.transparent : const Color(0x33888888), width: 2),
          boxShadow: current ? [BoxShadow(color: color.withValues(alpha: 0.45), blurRadius: 10)] : null,
        ),
        child: done ? Icon(CupertinoIcons.checkmark, size: current ? 13 : 10, color: Colors.white) : null,
      );
}

class _Viewer extends StatefulWidget {
  const _Viewer({required this.url, required this.video});
  final String url;
  final bool video;
  @override
  State<_Viewer> createState() => _ViewerState();
}

class _ViewerState extends State<_Viewer> {
  VideoPlayerController? _vc;

  @override
  void initState() {
    super.initState();
    if (widget.video) {
      _vc = VideoPlayerController.networkUrl(Uri.parse(widget.url))
        ..initialize().then((_) {
          if (mounted) setState(() {});
          _vc!
            ..setLooping(true)
            ..play();
        });
    }
  }

  @override
  void dispose() {
    _vc?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final vc = _vc;
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(children: [
        Center(
          child: widget.video
              ? (vc != null && vc.value.isInitialized
                  ? GestureDetector(
                      onTap: () => setState(() => vc.value.isPlaying ? vc.pause() : vc.play()),
                      child: AspectRatio(aspectRatio: vc.value.aspectRatio, child: VideoPlayer(vc)),
                    )
                  : const CupertinoActivityIndicator(color: Colors.white))
              : InteractiveViewer(maxScale: 5, child: Image.network(widget.url)),
        ),
        Positioned(
          top: MediaQuery.paddingOf(context).top + 8,
          right: 14,
          child: Pressable(
            onTap: () => Navigator.pop(context),
            child: Container(
              width: 38,
              height: 38,
              decoration: const BoxDecoration(color: Color(0x33FFFFFF), shape: BoxShape.circle),
              child: const Icon(CupertinoIcons.xmark, color: Colors.white, size: 18),
            ),
          ),
        ),
      ]),
    );
  }
}
