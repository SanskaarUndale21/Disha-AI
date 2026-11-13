import 'dart:io';
import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:image_picker/image_picker.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import 'theme.dart';

/// Opens the phone dialer with the helpline number filled in.
Future<void> callAgent(BuildContext context, String number) async {
  HapticFeedback.mediumImpact();
  final uri = Uri(scheme: 'tel', path: number.replaceAll(' ', ''));
  final ok = await launchUrl(uri, mode: LaunchMode.externalApplication).catchError((_) => false);
  if (!ok && context.mounted) {
    toast(context, 'No dialer available. Call $number from your phone.');
  }
}

/// +918064270577 -> 080 6427 0577
String prettyPhone(String n) {
  final d = n.replaceAll(RegExp(r'[^0-9]'), '');
  if (d.length == 12 && d.startsWith('91')) {
    final l = '0${d.substring(2)}';
    return '${l.substring(0, 3)} ${l.substring(3, 7)} ${l.substring(7)}';
  }
  return n;
}

void toast(BuildContext context, String msg, {bool error = false}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text(msg, style: const TextStyle(fontWeight: FontWeight.w500)),
      behavior: SnackBarBehavior.floating,
      backgroundColor: error ? AppColors.red : const Color(0xE61C1C1E),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 24),
    ));
}

/// Springy scale-down on press, like iOS buttons and cards.
class Pressable extends StatefulWidget {
  const Pressable({super.key, required this.child, this.onTap, this.scale = 0.97, this.haptic = true});
  final Widget child;
  final VoidCallback? onTap;
  final double scale;
  final bool haptic;
  @override
  State<Pressable> createState() => _PressableState();
}

class _PressableState extends State<Pressable> {
  bool _down = false;
  void _set(bool v) => setState(() => _down = v);
  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: widget.onTap != null,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: widget.onTap == null ? null : (_) => _set(true),
        onTapCancel: () => _set(false),
        onTapUp: (_) => _set(false),
        onTap: widget.onTap == null
            ? null
            : () {
                if (widget.haptic) HapticFeedback.selectionClick();
                widget.onTap!();
              },
        child: AnimatedScale(
          scale: _down ? widget.scale : 1,
          duration: Duration(milliseconds: _down ? 90 : 260),
          curve: _down ? Curves.easeOut : Curves.elasticOut,
          child: AnimatedOpacity(
              opacity: _down ? 0.85 : 1, duration: const Duration(milliseconds: 120), child: widget.child),
        ),
      ),
    );
  }
}

class CardBox extends StatelessWidget {
  const CardBox({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.radius = 22});
  final Widget child;
  final EdgeInsets padding;
  final double radius;
  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: dark ? null : [const BoxShadow(color: Color(0x0F000000), blurRadius: 24, offset: Offset(0, 8))],
      ),
      child: child,
    );
  }
}

class Glass extends StatelessWidget {
  const Glass({super.key, required this.child, this.radius = 0, this.opacity = 0.72});
  final Widget child;
  final double radius, opacity;
  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: Container(color: c.card.withValues(alpha: opacity), child: child),
      ),
    );
  }
}

class StatusPill extends StatelessWidget {
  const StatusPill(this.status, {super.key});
  final String status;
  @override
  Widget build(BuildContext context) {
    final s = statusStyle(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(color: s.color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(99)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(s.icon, size: 12, color: s.color),
        const SizedBox(width: 5),
        Text(s.label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: s.color)),
      ]),
    );
  }
}

class IconBadge extends StatelessWidget {
  const IconBadge(this.icon, this.color, {super.key, this.size = 40});
  final IconData icon;
  final Color color;
  final double size;
  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(size * 0.3),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color.lerp(color, Colors.white, 0.18)!, color],
          ),
        ),
        child: Icon(icon, color: Colors.white, size: size * 0.5),
      );
}

/// Real photo tile with a soft scrim and a label, used for issue types.
class PhotoTile extends StatelessWidget {
  const PhotoTile(
      {super.key, required this.asset, required this.label, this.radius = 20, this.labelSize = 14, this.icon, this.color});
  final String asset, label;
  final double radius, labelSize;
  final IconData? icon;
  final Color? color;
  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(radius),
        child: Stack(fit: StackFit.expand, children: [
          Image.asset(asset, fit: BoxFit.cover),
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0x00000000), Color(0xB3000000)],
                stops: [0.4, 1],
              ),
            ),
          ),
          if (icon != null) Positioned(left: 8, top: 8, child: IconBadge(icon!, color ?? AppColors.blue, size: 30)),
          Positioned(
            left: 10,
            right: 10,
            bottom: 9,
            child: FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(label,
                  maxLines: 1,
                  style: TextStyle(
                      color: Colors.white, fontSize: labelSize, fontWeight: FontWeight.w700, letterSpacing: -0.2)),
            ),
          ),
        ]),
      );
}

/// Local preview of a picked image or video.
class LocalThumb extends StatelessWidget {
  const LocalThumb(this.file, {super.key, required this.isVideo});
  final XFile file;
  final bool isVideo;
  @override
  Widget build(BuildContext context) {
    if (isVideo) {
      return Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
              colors: [Color(0xFF2C2C2E), Color(0xFF0B0B0F)], begin: Alignment.topLeft, end: Alignment.bottomRight),
        ),
        child: const Center(child: Icon(CupertinoIcons.play_circle_fill, color: Colors.white, size: 34)),
      );
    }
    return kIsWeb ? Image.network(file.path, fit: BoxFit.cover) : Image.file(File(file.path), fit: BoxFit.cover);
  }
}

class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key, this.trailing});
  final String text;
  final Widget? trailing;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 26, 4, 10),
        child: Row(children: [
          Expanded(child: Text(text, style: T.title(context).copyWith(fontSize: 20))),
          ?trailing,
        ]),
      );
}

// ---------- maps (OpenStreetMap tiles) ----------

class MapTiles extends StatelessWidget {
  const MapTiles({super.key});
  @override
  Widget build(BuildContext context) => TileLayer(
        urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        userAgentPackageName: 'com.roadwatch.roadwatch_citizen',
      );
}

class MapCredit extends StatelessWidget {
  const MapCredit({super.key});
  @override
  Widget build(BuildContext context) => Align(
        alignment: Alignment.bottomRight,
        child: Container(
          margin: const EdgeInsets.all(6),
          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
          decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.8), borderRadius: BorderRadius.circular(4)),
          child: const Text('© OpenStreetMap', style: TextStyle(fontSize: 9.5, color: Color(0xFF444444))),
        ),
      );
}

/// iOS Maps style pin: coloured disc with a white ring and glyph.
class MapPin extends StatelessWidget {
  const MapPin({super.key, this.color = AppColors.orange, this.icon = CupertinoIcons.exclamationmark, this.size = 30});
  final Color color;
  final IconData icon;
  final double size;
  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: color,
          border: Border.all(color: Colors.white, width: 2.5),
          boxShadow: const [BoxShadow(color: Color(0x40000000), blurRadius: 6, offset: Offset(0, 2))],
        ),
        child: Icon(icon, color: Colors.white, size: size * 0.5),
      );
}

class YouAreHere extends StatelessWidget {
  const YouAreHere({super.key});
  @override
  Widget build(BuildContext context) => Container(
        width: 40,
        height: 40,
        alignment: Alignment.center,
        decoration: BoxDecoration(shape: BoxShape.circle, color: AppColors.blue.withValues(alpha: 0.18)),
        child: Container(
          width: 16,
          height: 16,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppColors.blue,
            border: Border.all(color: Colors.white, width: 3),
          ),
        ),
      );
}

LatLng? latLng(double? lat, double? lon) => lat == null || lon == null ? null : LatLng(lat, lon);

String timeAgo(DateTime t) {
  final d = DateTime.now().difference(t);
  if (d.inMinutes < 1) return 'Just now';
  if (d.inMinutes < 60) return '${d.inMinutes}m ago';
  if (d.inHours < 24) return '${d.inHours}h ago';
  if (d.inDays < 7) return '${d.inDays}d ago';
  const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${t.day} ${m[t.month - 1]} ${t.year}';
}

/// Pulsing placeholder shown while content loads.
class Skeleton extends StatefulWidget {
  const Skeleton({super.key, required this.height, this.radius = 16});
  final double height, radius;
  @override
  State<Skeleton> createState() => _SkeletonState();
}

class _SkeletonState extends State<Skeleton> with SingleTickerProviderStateMixin {
  late final _ac = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))
    ..repeat(reverse: true);
  @override
  void dispose() {
    _ac.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return AnimatedBuilder(
      animation: _ac,
      builder: (_, _) => Container(
        height: widget.height,
        decoration: BoxDecoration(
          color: Color.lerp(c.fill, c.separator, _ac.value),
          borderRadius: BorderRadius.circular(widget.radius),
        ),
      ),
    );
  }
}
