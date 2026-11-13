import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';
import 'package:video_player/video_player.dart';

import '../api.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';
import 'home_screen.dart' show HelplinePlate;

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
    final colors = AppColors.of(context);
    if (c == null) return const Scaffold(body: Center(child: CupertinoActivityIndicator()));
    final cat = categoryOf(c.category);
    final photo = c.media.where((m) => !m.isVideo).firstOrNull;
    final heroUrl = photo == null ? null : (_showAi ? (photo.annotatedUrl ?? photo.mediaUrl) : photo.mediaUrl);
    final top = MediaQuery.paddingOf(context).top;
    final where = latLng(c.lat, c.lon);

    return Scaffold(
      body: Stack(children: [
        ListView(
          physics: const BouncingScrollPhysics(),
          padding: EdgeInsets.zero,
          children: [
            SizedBox(
              height: 320 + top,
              child: Stack(fit: StackFit.expand, children: [
                heroUrl != null
                    ? Image.network(api.url(heroUrl),
                        fit: BoxFit.cover, errorBuilder: (_, _, _) => Image.asset(cat.thumb, fit: BoxFit.cover))
                    : Image.asset('assets/photos/${cat.photo}.jpg', fit: BoxFit.cover),
                if (photo?.annotatedUrl != null)
                  Positioned(
                    right: 14,
                    bottom: 14,
                    child: Pressable(
                      onTap: () => setState(() => _showAi = !_showAi),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                        decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(8)),
                        child: Row(mainAxisSize: MainAxisSize.min, children: [
                          Icon(_showAi ? PhosphorIconsBold.eyeSlash : PhosphorIconsBold.scan,
                              size: 16, color: Palette.yellow),
                          const SizedBox(width: 6),
                          Text(_showAi ? 'Show original' : 'Show damage boxes',
                              style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600)),
                        ]),
                      ),
                    ),
                  ),
              ]),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(c.ticket, style: T.small(context)),
                const SizedBox(height: 2),
                Text(cat.label, style: T.display(context)),
                const SizedBox(height: 6),
                Text('Reported ${timeAgo(c.createdAt)}', style: T.sub(context)),
                const SizedBox(height: 22),
                _RoadProgress(status: c.status),
                if (c.adminNote?.isNotEmpty == true) ...[
                  const SizedBox(height: 16),
                  SignPlate(
                    face: Palette.blue,
                    legend: Colors.white,
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Icon(PhosphorIconsFill.chatCenteredText, size: 22),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          const Text('From the city',
                              style: TextStyle(fontFamily: fontDisplay, fontSize: 19, fontWeight: FontWeight.w700)),
                          const SizedBox(height: 2),
                          Text(c.adminNote!, style: const TextStyle(fontSize: 15.5, height: 1.4, color: Colors.white)),
                        ]),
                      ),
                    ]),
                  ),
                ],
                ..._aiSection(c),
                if (c.media.length > 1 || c.media.any((m) => m.isVideo)) ...[
                  const SectionTitle('Your photos and videos'),
                  GridView.count(
                    crossAxisCount: 3,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    mainAxisSpacing: 6,
                    crossAxisSpacing: 6,
                    children: [for (final m in c.media) _mediaCell(m)],
                  ),
                ],
                if (c.description.isNotEmpty) ...[
                  const SectionTitle('What you told us'),
                  Text(c.description, style: T.body(context)),
                ],
                const SectionTitle('Location'),
                if (where != null)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(14),
                    child: SizedBox(
                      height: 170,
                      child: FlutterMap(
                        options: MapOptions(
                          initialCenter: where,
                          initialZoom: 16.5,
                          interactionOptions: const InteractionOptions(flags: InteractiveFlag.none),
                        ),
                        children: [
                          const MapTiles(),
                          MarkerLayer(markers: [Marker(point: where, width: 34, height: 34, child: const ReportPin(size: 32))]),
                          const MapCredit(),
                        ],
                      ),
                    ),
                  ),
                const SizedBox(height: 10),
                Row(children: [
                  Icon(PhosphorIconsFill.mapPin, size: 18, color: colors.inkSoft),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      c.address?.isNotEmpty == true
                          ? c.address!
                          : (where != null
                              ? '${c.lat!.toStringAsFixed(5)}, ${c.lon!.toStringAsFixed(5)}'
                              : 'No location was attached'),
                      style: T.sub(context),
                    ),
                  ),
                ]),
                const SizedBox(height: 28),
                HelplinePlate(number: prefs.helpline, subtitle: 'Quote ${c.ticket} when you call'),
              ]),
            ),
          ],
        ),
        Positioned(
          top: top + 10,
          left: 14,
          child: Pressable(
            onTap: () => Navigator.pop(context),
            child: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(12)),
              child: const Icon(PhosphorIconsBold.arrowLeft, size: 22, color: Colors.white, semanticLabel: 'Back'),
            ),
          ),
        ),
      ]),
    );
  }

  List<Widget> _aiSection(Complaint c) {
    if (c.media.isEmpty) return [];
    final processing = c.media.any((m) => m.processing);
    final colors = AppColors.of(context);
    return [
      const SectionTitle('What the camera check found'),
      if (processing && c.findings.isEmpty)
        Row(children: [
          const CupertinoActivityIndicator(),
          const SizedBox(width: 12),
          Expanded(child: Text('Going through your video frame by frame. This takes a minute.', style: T.sub(context))),
        ])
      else if (c.findings.isEmpty)
        Text('Nothing clear enough to measure automatically. An inspector will review your photos.', style: T.sub(context))
      else
        for (final f in c.findings)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: colors.line))),
            child: Row(children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: SizedBox(
                  width: 52,
                  height: 52,
                  child: f.cropUrl != null
                      ? Image.network(api.url(f.cropUrl),
                          fit: BoxFit.cover, errorBuilder: (_, _, _) => Container(color: colors.fill))
                      : Container(color: colors.fill),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(f.label[0].toUpperCase() + f.label.substring(1), style: T.bodyStrong(context)),
                  Text('${(f.confidence * 100).round()}% sure${f.severity.isNotEmpty ? ', ${f.severity.toLowerCase()} severity' : ''}',
                      style: T.small(context)),
                ]),
              ),
              _RiskTag(f.riskLevel ?? f.severity),
            ]),
          ),
    ];
  }

  Widget _mediaCell(MediaItem m) {
    final src = m.mediaUrl;
    return Pressable(
      onTap: src == null
          ? null
          : () => Navigator.of(context).push(PageRouteBuilder(
                opaque: false,
                barrierColor: Colors.black,
                pageBuilder: (_, _, _) => _Viewer(
                  url: api.url(m.isVideo ? (m.annotatedUrl ?? src) : src),
                  video: m.isVideo,
                ),
                transitionsBuilder: (_, a, _, child) => FadeTransition(opacity: a, child: child),
              )),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: Stack(fit: StackFit.expand, children: [
          if (!m.isVideo && src != null)
            Image.network(api.url(src), fit: BoxFit.cover, errorBuilder: (_, _, _) => Container(color: Palette.asphalt))
          else
            Container(color: Palette.asphalt),
          if (m.isVideo)
            Center(
              child: m.processing
                  ? Column(mainAxisSize: MainAxisSize.min, children: [
                      const CupertinoActivityIndicator(color: Colors.white),
                      const SizedBox(height: 6),
                      Text('${(m.progress * 100).round()}%',
                          style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600)),
                    ])
                  : const Icon(PhosphorIconsFill.playCircle, color: Colors.white, size: 38),
            ),
        ]),
      ),
    );
  }
}

class _RiskTag extends StatelessWidget {
  const _RiskTag(this.level);
  final String level;
  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (level) {
      'High' => (Palette.red, Colors.white),
      'Medium' => (Palette.yellow, Palette.asphalt),
      _ => (AppColors.of(context).fill, AppColors.of(context).ink),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(6)),
      child: Text('$level risk', style: TextStyle(color: fg, fontSize: 13, fontWeight: FontWeight.w700)),
    );
  }
}

/// Repair progress drawn as a stretch of road: the finished part is fresh asphalt with lane dashes,
/// the part still ahead is unpaved grey. Stops are the four stages.
class _RoadProgress extends StatelessWidget {
  const _RoadProgress({required this.status});
  final String status;
  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    if (status == 'rejected') {
      return SignPlate(
        face: Palette.red,
        legend: Colors.white,
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        child: const Row(children: [
          Icon(PhosphorIconsBold.prohibit, size: 22),
          SizedBox(width: 12),
          Expanded(
            child: Text('The city closed this report without a repair.',
                style: TextStyle(fontSize: 15.5, fontWeight: FontWeight.w600, color: Colors.white)),
          ),
        ]),
      );
    }
    final idx = statusOrder.indexOf(status).clamp(0, statusOrder.length - 1);
    final st = statusStyle(status);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(st.label, style: T.h2(context).copyWith(color: idx == 0 ? colors.ink : st.color)),
      const SizedBox(height: 4),
      Text(
        const [
          'We have it. An officer will look at it soon.',
          'An officer is checking your photos and the spot.',
          'A crew has been assigned to fix it.',
          'The road has been repaired. Thanks for reporting it.',
        ][idx],
        style: T.sub(context),
      ),
      const SizedBox(height: 16),
      LayoutBuilder(builder: (context, box) {
        final w = box.maxWidth;
        const stopW = 30.0;
        final step = (w - stopW) / (statusOrder.length - 1);
        return SizedBox(
          height: 30,
          child: Stack(clipBehavior: Clip.none, children: [
            Positioned(
              left: 0,
              right: 0,
              top: 7,
              child: CustomPaint(size: Size(w, 16), painter: _RoadPainter(progress: idx / (statusOrder.length - 1), ahead: colors.fill)),
            ),
            for (var i = 0; i < statusOrder.length; i++)
              Positioned(
                left: i * step,
                top: 0,
                child: Container(
                  width: stopW,
                  height: stopW,
                  decoration: BoxDecoration(
                    color: i < idx ? Palette.asphalt : (i == idx ? Palette.yellow : colors.surface),
                    borderRadius: BorderRadius.circular(7),
                    border: Border.all(color: i <= idx ? Palette.asphalt : colors.line, width: 2.5),
                  ),
                  child: Icon(
                    i < idx ? PhosphorIconsBold.check : statusStyle(statusOrder[i]).icon,
                    size: 15,
                    color: i < idx ? Palette.yellow : (i == idx ? Palette.asphalt : colors.inkFaint),
                  ),
                ),
              ),
          ]),
        );
      }),
      const SizedBox(height: 8),
      Row(children: [
        for (var i = 0; i < statusOrder.length; i++)
          Expanded(
            child: Text(
              statusStyle(statusOrder[i]).step,
              textAlign: i == 0 ? TextAlign.left : (i == statusOrder.length - 1 ? TextAlign.right : TextAlign.center),
              style: TextStyle(
                fontSize: 13,
                fontWeight: i == idx ? FontWeight.w700 : FontWeight.w500,
                color: i <= idx ? colors.ink : colors.inkFaint,
              ),
            ),
          ),
      ]),
    ]);
  }
}

class _RoadPainter extends CustomPainter {
  _RoadPainter({required this.progress, required this.ahead});
  final double progress;
  final Color ahead;
  @override
  void paint(Canvas canvas, Size s) {
    final r = RRect.fromRectAndRadius(Offset.zero & s, const Radius.circular(3));
    canvas.drawRRect(r, Paint()..color = ahead);
    final doneW = (s.width * progress).clamp(0.0, s.width);
    if (doneW > 0) {
      canvas.save();
      canvas.clipRect(Rect.fromLTWH(0, 0, doneW, s.height));
      canvas.drawRRect(r, Paint()..color = Palette.asphalt);
      final dash = Paint()..color = Palette.yellow;
      for (double x = 6; x < doneW; x += 18) {
        canvas.drawRect(Rect.fromLTWH(x, s.height / 2 - 1.25, 9, 2.5), dash);
      }
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(covariant _RoadPainter old) => old.progress != progress || old.ahead != ahead;
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
          top: MediaQuery.paddingOf(context).top + 10,
          right: 14,
          child: Pressable(
            onTap: () => Navigator.pop(context),
            child: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(12)),
              child: const Icon(PhosphorIconsBold.x, color: Colors.white, size: 20, semanticLabel: 'Close'),
            ),
          ),
        ),
      ]),
    );
  }
}
