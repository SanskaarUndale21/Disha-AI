import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:image_picker/image_picker.dart';
import 'package:latlong2/latlong.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import 'theme.dart';

/// Opens the phone dialer with the helpline number filled in.
Future<void> callAgent(BuildContext context, String number) async {
  HapticFeedback.mediumImpact();
  final uri = Uri(scheme: 'tel', path: number.replaceAll(' ', ''));
  final ok = await launchUrl(uri, mode: LaunchMode.externalApplication).catchError((_) => false);
  if (!ok && context.mounted) toast(context, 'This device can\'t place calls. Dial $number from your phone.');
}

/// +918064270577 -> 080 6427 0577 (how Indians write landline numbers).
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
      content: Row(children: [
        Icon(error ? PhosphorIconsBold.warningCircle : PhosphorIconsBold.info,
            color: error ? Palette.yellow : Colors.white, size: 20),
        const SizedBox(width: 10),
        Expanded(child: Text(msg, style: const TextStyle(fontWeight: FontWeight.w500, fontSize: 15))),
      ]),
      behavior: SnackBarBehavior.floating,
      backgroundColor: Palette.asphalt,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 20),
    ));
}

/// Press feedback: quick scale-down, settles back. Answers the tap, nothing more.
class Pressable extends StatefulWidget {
  const Pressable({super.key, required this.child, this.onTap, this.scale = 0.97});
  final Widget child;
  final VoidCallback? onTap;
  final double scale;
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
                HapticFeedback.selectionClick();
                widget.onTap!();
              },
        child: AnimatedScale(
          scale: _down ? widget.scale : 1,
          duration: Duration(milliseconds: _down ? 80 : 180),
          curve: Curves.easeOut,
          child: widget.child,
        ),
      ),
    );
  }
}

/// A road sign plate: solid face, inset border in the legend colour. The app's one signature element.
class SignPlate extends StatelessWidget {
  const SignPlate({
    super.key,
    required this.face,
    required this.legend,
    required this.child,
    this.onTap,
    this.padding = const EdgeInsets.fromLTRB(18, 16, 18, 16),
    this.radius = 12,
  });
  final Color face, legend;
  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsets padding;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final plate = Container(
      decoration: BoxDecoration(color: face, borderRadius: BorderRadius.circular(radius)),
      padding: const EdgeInsets.all(5),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(radius - 4),
          border: Border.all(color: legend, width: 2.5),
        ),
        padding: padding,
        child: DefaultTextStyle.merge(style: TextStyle(color: legend), child: IconTheme.merge(data: IconThemeData(color: legend), child: child)),
      ),
    );
    return onTap == null ? plate : Pressable(onTap: onTap, scale: 0.98, child: plate);
  }
}

/// Primary action: yellow sign plate with a single line label.
class YellowButton extends StatelessWidget {
  const YellowButton({super.key, required this.label, this.icon, this.onTap, this.busy = false, this.enabled = true});
  final String label;
  final IconData? icon;
  final VoidCallback? onTap;
  final bool busy, enabled;
  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 150),
      opacity: enabled || busy ? 1 : 0.45,
      child: SignPlate(
        face: Palette.yellow,
        legend: Palette.asphalt,
        radius: 12,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        onTap: enabled && !busy ? onTap : null,
        child: SizedBox(
          width: double.infinity,
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            if (busy)
              const CupertinoActivityIndicator(color: Palette.asphalt)
            else if (icon != null)
              Icon(icon, size: 22),
            const SizedBox(width: 10),
            Text(label,
                style: const TextStyle(
                    fontFamily: fontDisplay, fontSize: 22, fontWeight: FontWeight.w800, color: Palette.asphalt)),
          ]),
        ),
      ),
    );
  }
}

/// Plain surface block. Flat, no shadow: hierarchy comes from spacing and type, not elevation.
class Surface extends StatelessWidget {
  const Surface({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.radius = 16, this.onTap});
  final Widget child;
  final EdgeInsets padding;
  final double radius;
  final VoidCallback? onTap;
  @override
  Widget build(BuildContext context) {
    final box = Container(
      padding: padding,
      decoration: BoxDecoration(color: AppColors.of(context).surface, borderRadius: BorderRadius.circular(radius)),
      child: child,
    );
    return onTap == null ? box : Pressable(onTap: onTap, child: box);
  }
}

class StatusTag extends StatelessWidget {
  const StatusTag(this.status, {super.key});
  final String status;
  @override
  Widget build(BuildContext context) {
    final s = statusStyle(status);
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(width: 8, height: 8, decoration: BoxDecoration(color: s.color, borderRadius: BorderRadius.circular(2))),
      const SizedBox(width: 6),
      Text(s.label, style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: s.color)),
    ]);
  }
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
        color: Palette.asphalt,
        child: const Center(child: Icon(PhosphorIconsFill.playCircle, color: Colors.white, size: 36)),
      );
    }
    return kIsWeb ? Image.network(file.path, fit: BoxFit.cover) : Image.file(File(file.path), fit: BoxFit.cover);
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.trailing, this.top = 28});
  final String text;
  final Widget? trailing;
  final double top;
  @override
  Widget build(BuildContext context) => Padding(
        padding: EdgeInsets.fromLTRB(2, top, 2, 12),
        child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Expanded(child: Text(text, style: T.h2(context))),
          ?trailing,
        ]),
      );
}

/// Base map tiles (CARTO, OpenStreetMap data). Light or dark to match the theme.
class MapTiles extends StatelessWidget {
  const MapTiles({super.key});
  @override
  Widget build(BuildContext context) {
    return TileLayer(
      urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      userAgentPackageName: 'com.roadwatch.roadwatch_citizen',
    );
  }
}

class MapCredit extends StatelessWidget {
  const MapCredit({super.key});
  @override
  Widget build(BuildContext context) => Align(
        alignment: Alignment.bottomLeft,
        child: Container(
          margin: const EdgeInsets.all(6),
          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
          color: Colors.white.withValues(alpha: 0.75),
          child: const Text('© OpenStreetMap contributors', style: TextStyle(fontSize: 9.5, color: Color(0xFF444444))),
        ),
      );
}

/// Report pin: yellow plate with black legend, like a hazard marker.
class ReportPin extends StatelessWidget {
  const ReportPin({super.key, this.size = 30, this.color = Palette.yellow});
  final double size;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(size * 0.22),
          border: Border.all(color: Palette.asphalt, width: 2.5),
        ),
        child: Icon(PhosphorIconsBold.warning, size: size * 0.55, color: Palette.asphalt),
      );
}

class YouAreHere extends StatelessWidget {
  const YouAreHere({super.key});
  @override
  Widget build(BuildContext context) => Container(
        width: 44,
        height: 44,
        alignment: Alignment.center,
        decoration: BoxDecoration(shape: BoxShape.circle, color: Palette.blue.withValues(alpha: 0.18)),
        child: Container(
          width: 16,
          height: 16,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: Palette.blue,
            border: Border.all(color: Colors.white, width: 3),
          ),
        ),
      );
}

LatLng? latLng(double? lat, double? lon) => lat == null || lon == null ? null : LatLng(lat, lon);

String timeAgo(DateTime t) {
  final d = DateTime.now().difference(t);
  if (d.inMinutes < 1) return 'just now';
  if (d.inMinutes < 60) return '${d.inMinutes} min ago';
  if (d.inHours < 24) return '${d.inHours} h ago';
  if (d.inDays == 1) return 'yesterday';
  if (d.inDays < 7) return '${d.inDays} days ago';
  return dateLabel(t);
}

String dateLabel(DateTime t) {
  const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${t.day} ${m[t.month - 1]} ${t.year}';
}
