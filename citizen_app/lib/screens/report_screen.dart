import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:image_picker/image_picker.dart';
import 'package:latlong2/latlong.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';

import '../api.dart';
import '../location.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';
import 'detail_screen.dart';

const _maxFiles = 8;

class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key, this.initialCategory});
  final String? initialCategory;
  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  late String _category = widget.initialCategory ?? 'pothole';
  final _files = <XFile>[];
  final _desc = TextEditingController();
  late final _name = TextEditingController(text: prefs.name);
  late final _phone = TextEditingController(text: prefs.phone);
  final _picker = ImagePicker();
  final _map = MapController();
  bool _mapReady = false;

  Spot? _spot;
  bool _pinMoved = false;
  bool _sending = false;
  double _progress = 0;

  @override
  void initState() {
    super.initState();
    _spot = locator.spot;
    locator.addListener(_onLocation);
    locator.locate(force: true);
  }

  @override
  void dispose() {
    locator.removeListener(_onLocation);
    _desc.dispose();
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  void _onLocation() {
    if (!mounted) return;
    if (!_pinMoved && locator.spot != null) {
      _spot = locator.spot;
      if (_mapReady) _map.move(LatLng(_spot!.lat, _spot!.lon), 17);
    }
    setState(() {});
  }

  Future<void> _movePin(LatLng p) async {
    HapticFeedback.selectionClick();
    setState(() => (_pinMoved = true, _spot = Spot(p.latitude, p.longitude)));
    final s = await Locator.describe(p.latitude, p.longitude);
    if (mounted && _spot?.lat == p.latitude) setState(() => _spot = s);
  }

  void _useMyLocation() {
    _pinMoved = false;
    locator.locate(force: true);
  }

  Future<void> _pick(int choice) async {
    if (_files.length >= _maxFiles) return toast(context, 'You can attach up to $_maxFiles photos or videos.');
    try {
      final List<XFile> picked = switch (choice) {
        0 => [?await _picker.pickImage(source: ImageSource.camera, imageQuality: 85, maxWidth: 2560)],
        1 => [?await _picker.pickVideo(source: ImageSource.camera, maxDuration: const Duration(minutes: 2))],
        _ => await _picker.pickMultipleMedia(imageQuality: 85, maxWidth: 2560, limit: _maxFiles - _files.length),
      };
      if (picked.isEmpty) return;
      HapticFeedback.lightImpact();
      setState(() => _files.addAll(picked.take(_maxFiles - _files.length)));
    } catch (_) {
      if (mounted) toast(context, 'The camera or gallery didn\'t open. Check app permissions in Settings.', error: true);
    }
  }

  bool get _ready => _files.isNotEmpty || _desc.text.trim().length >= 5;

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_ready) return toast(context, 'Add a photo or video, or describe the problem in a few words.');
    await prefs.save(name: _name.text, phone: _phone.text);
    setState(() => (_sending = true, _progress = 0.05));
    try {
      final c = await api.submit(
        category: _category,
        description: _desc.text.trim(),
        files: _files,
        lat: _spot?.lat,
        lon: _spot?.lon,
        address: _spot?.address,
        onProgress: (p) => mounted ? setState(() => _progress = p) : null,
      );
      HapticFeedback.heavyImpact();
      refreshTick.value++;
      if (!mounted) return;
      Navigator.of(context).pushReplacement(PageRouteBuilder(
        transitionDuration: const Duration(milliseconds: 300),
        pageBuilder: (_, _, _) => _SentScreen(complaint: c),
        transitionsBuilder: (_, a, _, child) => FadeTransition(opacity: a, child: child),
      ));
    } catch (e) {
      if (mounted) {
        setState(() => _sending = false);
        toast(context, '$e', error: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final signedInName = prefs.name.isNotEmpty && Api.accessToken != null;
    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(
        backgroundColor: c.bg,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        automaticallyImplyLeading: false,
        titleSpacing: 20,
        title: Text('New report', style: T.h2(context)),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Pressable(
              onTap: _sending ? null : () => Navigator.pop(context),
              child: Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: c.fill, borderRadius: BorderRadius.circular(10)),
                child: Icon(PhosphorIconsBold.x, size: 20, color: c.ink, semanticLabel: 'Close'),
              ),
            ),
          ),
        ],
      ),
      body: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: ListView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 40),
          children: [
            _step(1, 'Show us the damage'),
            if (_files.isEmpty) _shotGuide() else _mediaStrip(),
            _step(2, 'What is it?'),
            _categoryGrid(),
            _step(3, 'Where is it?'),
            _locationBlock(),
            _step(4, 'Anything the crew should know?'),
            _textBox(
              controller: _desc,
              hint: 'Near the bus stop, two-wheelers swerve into traffic to avoid it.',
              lines: 3,
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 24),
            if (signedInName)
              Text('Sending as ${prefs.name}. You\'ll get status updates in the app.', style: T.sub(context))
            else ...[
              Text('Your name and number (optional)', style: T.bodyStrong(context)),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(child: _textBox(controller: _name, hint: 'Name', type: TextInputType.name)),
                const SizedBox(width: 10),
                Expanded(child: _textBox(controller: _phone, hint: 'Mobile', type: TextInputType.phone)),
              ]),
              const SizedBox(height: 6),
              Text('Only used if the crew needs to reach you.', style: T.small(context)),
            ],
          ],
        ),
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(color: c.surface, border: Border(top: BorderSide(color: c.line))),
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              if (_sending) ...[
                ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: LinearProgressIndicator(
                    value: _progress,
                    minHeight: 4,
                    backgroundColor: c.fill,
                    color: Palette.asphalt,
                  ),
                ),
                const SizedBox(height: 8),
                Text(_progress < 0.5 ? 'Uploading your photos' : 'Checking them for damage',
                    style: T.small(context)),
                const SizedBox(height: 8),
              ],
              YellowButton(
                label: _sending ? 'Sending' : 'Send report',
                icon: PhosphorIconsBold.paperPlaneRight,
                busy: _sending,
                enabled: _ready,
                onTap: _submit,
              ),
            ]),
          ),
        ),
      ),
    );
  }

  /// Steps really are a sequence here, so they're numbered.
  Widget _step(int n, String title) => Padding(
        padding: const EdgeInsets.fromLTRB(0, 26, 0, 12),
        child: Row(children: [
          Container(
            width: 26,
            height: 26,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(6)),
            child: Text('$n',
                style: const TextStyle(
                    fontFamily: fontDisplay, color: Palette.yellow, fontWeight: FontWeight.w800, fontSize: 17)),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(title, style: T.h3(context))),
        ]),
      );

  Widget _shotGuide() {
    final c = AppColors.of(context);
    return Container(
      decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(16)),
      clipBehavior: Clip.antiAlias,
      child: Column(children: [
        AspectRatio(
          aspectRatio: 16 / 9,
          child: Stack(fit: StackFit.expand, children: [
            Image.asset('assets/photos/goodshot.jpg', fit: BoxFit.cover),
            // framing guide, like a camera viewfinder
            Padding(
              padding: const EdgeInsets.all(18),
              child: CustomPaint(painter: _FramePainter()),
            ),
            Positioned(
              left: 12,
              bottom: 12,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(6)),
                child: const Text('A good shot',
                    style: TextStyle(color: Colors.white, fontSize: 12.5, fontWeight: FontWeight.w600)),
              ),
            ),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Text('Stand about a metre back so the whole pothole and some road around it are in the frame.',
              style: T.sub(context)),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
          child: Row(children: [
            Expanded(child: _pickButton(PhosphorIconsBold.camera, 'Take photo', () => _pick(0), primary: true)),
            const SizedBox(width: 8),
            Expanded(child: _pickButton(PhosphorIconsBold.videoCamera, 'Record video', () => _pick(1))),
            const SizedBox(width: 8),
            Expanded(child: _pickButton(PhosphorIconsBold.images, 'Gallery', () => _pick(2))),
          ]),
        ),
      ]),
    );
  }

  Widget _pickButton(IconData icon, String label, VoidCallback onTap, {bool primary = false}) {
    final c = AppColors.of(context);
    return Pressable(
      onTap: onTap,
      child: Container(
        height: 64,
        decoration: BoxDecoration(
          color: primary ? Palette.yellow : c.fill,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(icon, size: 22, color: primary ? Palette.asphalt : c.ink),
          const SizedBox(height: 4),
          Text(label,
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: primary ? Palette.asphalt : c.ink)),
        ]),
      ),
    );
  }

  Widget _mediaStrip() {
    final c = AppColors.of(context);
    return SizedBox(
      height: 120,
      child: ListView(
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        children: [
          for (var i = 0; i < _files.length; i++)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Stack(children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: SizedBox(width: 120, height: 120, child: LocalThumb(_files[i], isVideo: Api.isVideo(_files[i]))),
                ),
                Positioned(
                  right: 6,
                  top: 6,
                  child: Pressable(
                    onTap: () => setState(() => _files.removeAt(i)),
                    child: Container(
                      width: 28,
                      height: 28,
                      decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(8)),
                      child: const Icon(PhosphorIconsBold.x, color: Colors.white, size: 15, semanticLabel: 'Remove'),
                    ),
                  ),
                ),
              ]),
            ),
          if (_files.length < _maxFiles)
            Pressable(
              onTap: () => showCupertinoModalPopup(
                context: context,
                builder: (ctx) => CupertinoActionSheet(
                  actions: [
                    CupertinoActionSheetAction(onPressed: () { Navigator.pop(ctx); _pick(0); }, child: const Text('Take photo')),
                    CupertinoActionSheetAction(onPressed: () { Navigator.pop(ctx); _pick(1); }, child: const Text('Record video')),
                    CupertinoActionSheetAction(onPressed: () { Navigator.pop(ctx); _pick(2); }, child: const Text('Choose from gallery')),
                  ],
                  cancelButton: CupertinoActionSheetAction(
                      isDefaultAction: true, onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
                ),
              ),
              child: Container(
                width: 120,
                decoration: BoxDecoration(
                  color: c.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: c.line, width: 1.5),
                ),
                child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Icon(PhosphorIconsBold.plus, color: c.ink, size: 24),
                  const SizedBox(height: 4),
                  Text('Add more', style: TextStyle(fontWeight: FontWeight.w600, color: c.ink)),
                  Text('${_files.length} of $_maxFiles', style: T.small(context)),
                ]),
              ),
            ),
        ],
      ),
    );
  }

  Widget _categoryGrid() {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: 1.35,
      children: [for (final cat in categories) _categoryTile(cat)],
    );
  }

  Widget _categoryTile(Category cat) {
    final sel = _category == cat.key;
    return Pressable(
      onTap: () => setState(() => _category = cat.key),
      child: Semantics(
        selected: sel,
        label: cat.label,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: sel ? Palette.yellow : Colors.transparent, width: 4),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(sel ? 10 : 14),
            child: Stack(fit: StackFit.expand, children: [
              Image.asset(cat.thumb, fit: BoxFit.cover),
              const DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [Color(0x00000000), Color(0xCC000000)],
                    stops: [0.35, 1],
                  ),
                ),
              ),
              Positioned(
                left: 10,
                right: 10,
                bottom: 8,
                child: Text(cat.label,
                    style: const TextStyle(
                        fontFamily: fontDisplay, color: Colors.white, fontSize: 20, fontWeight: FontWeight.w700)),
              ),
              if (sel)
                Positioned(
                  right: 8,
                  top: 8,
                  child: Container(
                    width: 26,
                    height: 26,
                    decoration: BoxDecoration(color: Palette.yellow, borderRadius: BorderRadius.circular(7)),
                    child: const Icon(PhosphorIconsBold.check, size: 16, color: Palette.asphalt),
                  ),
                ),
            ]),
          ),
        ),
      ),
    );
  }

  Widget _locationBlock() {
    final c = AppColors.of(context);
    final s = _spot;
    final center = s != null ? LatLng(s.lat, s.lon) : const LatLng(12.9716, 77.5946);
    return Container(
      decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(16)),
      clipBehavior: Clip.antiAlias,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          height: 190,
          child: Stack(children: [
            FlutterMap(
              mapController: _map,
              options: MapOptions(
                initialCenter: center,
                initialZoom: s != null ? 17 : 12,
                onMapReady: () => _mapReady = true,
                onTap: (_, p) => _movePin(p),
                interactionOptions: const InteractionOptions(flags: InteractiveFlag.all & ~InteractiveFlag.rotate),
              ),
              children: [
                const MapTiles(),
                if (s != null)
                  MarkerLayer(markers: [
                    Marker(point: LatLng(s.lat, s.lon), width: 36, height: 36, child: const ReportPin(size: 34)),
                  ]),
                const MapCredit(),
              ],
            ),
            Positioned(
              right: 8,
              top: 8,
              child: Pressable(
                onTap: _useMyLocation,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                  decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(8)),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    locator.busy
                        ? const SizedBox(width: 16, height: 16, child: CupertinoActivityIndicator(color: Colors.white, radius: 7))
                        : const Icon(PhosphorIconsBold.crosshair, size: 16, color: Colors.white),
                    const SizedBox(width: 6),
                    const Text('My location',
                        style: TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600)),
                  ]),
                ),
              ),
            ),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(PhosphorIconsFill.mapPin, size: 20, color: s != null ? c.ink : c.inkFaint),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(
                  s == null
                      ? (locator.busy ? 'Finding where you are' : 'Tap the map to place the pin')
                      : (s.address?.isNotEmpty == true ? s.address! : 'Pinned on the map'),
                  style: T.bodyStrong(context),
                ),
                const SizedBox(height: 2),
                Text(
                  s == null
                      ? (locator.error ?? 'An exact spot gets the crew there faster.')
                      : (_pinMoved
                          ? 'Pin placed by you. Tap elsewhere to move it.'
                          : 'Accurate to about ${s.accuracy?.round() ?? '?'} m. Tap the map to adjust.'),
                  style: T.small(context),
                ),
              ]),
            ),
          ]),
        ),
      ]),
    );
  }

  Widget _textBox({
    required TextEditingController controller,
    required String hint,
    int lines = 1,
    TextInputType? type,
    ValueChanged<String>? onChanged,
  }) {
    final c = AppColors.of(context);
    return TextField(
      controller: controller,
      onChanged: onChanged,
      minLines: lines,
      maxLines: lines == 1 ? 1 : 6,
      keyboardType: type,
      textCapitalization: type == null ? TextCapitalization.sentences : TextCapitalization.words,
      style: T.body(context),
      decoration: InputDecoration(
        filled: true,
        fillColor: c.surface,
        hintText: hint,
        hintStyle: T.body(context).copyWith(color: c.inkFaint),
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: c.line)),
        focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: c.ink, width: 2)),
      ),
    );
  }
}

class _FramePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size s) {
    final p = Paint()
      ..color = Palette.yellow
      ..strokeWidth = 4
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.square;
    const l = 26.0;
    for (final (x, y, dx, dy) in [(0.0, 0.0, 1.0, 1.0), (s.width, 0.0, -1.0, 1.0), (0.0, s.height, 1.0, -1.0), (s.width, s.height, -1.0, -1.0)]) {
      canvas.drawLine(Offset(x, y), Offset(x + l * dx, y), p);
      canvas.drawLine(Offset(x, y), Offset(x, y + l * dy), p);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// Confirmation: the ticket number on a yellow plate, what happens next.
class _SentScreen extends StatelessWidget {
  const _SentScreen({required this.complaint});
  final Complaint complaint;

  @override
  Widget build(BuildContext context) {
    final c = complaint;
    final n = c.findings.length;
    final video = c.media.any((m) => m.processing);
    final aiLine = c.media.isEmpty
        ? 'No photos attached, so an inspector will check the spot.'
        : video
            ? 'Your video is being checked for damage now. Results appear in the report.'
            : n == 0
                ? 'The automatic check found nothing clear, so an inspector will look at your photos.'
                : 'The automatic check found $n ${n == 1 ? 'defect' : 'defects'} in your photos.';
    return Scaffold(
      backgroundColor: Palette.asphalt,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 32, 24, 16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(PhosphorIconsFill.checkCircle, color: Palette.yellow, size: 44),
            const SizedBox(height: 18),
            const Text('Report sent',
                style: TextStyle(
                    fontFamily: fontDisplay, fontSize: 44, height: 1, fontWeight: FontWeight.w800, color: Colors.white)),
            const SizedBox(height: 10),
            Text('Thanks. It\'s with the road maintenance team now.',
                style: TextStyle(fontSize: 17, height: 1.4, color: Colors.white.withValues(alpha: 0.8))),
            const SizedBox(height: 28),
            SignPlate(
              face: Palette.yellow,
              legend: Palette.asphalt,
              padding: const EdgeInsets.fromLTRB(18, 14, 18, 16),
              child: SizedBox(
                width: double.infinity,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('Your ticket', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                  Text(c.ticket,
                      style: const TextStyle(
                          fontFamily: fontDisplay, fontSize: 48, height: 1.05, fontWeight: FontWeight.w800)),
                  const Text('Quote this if you call the helpline.', style: TextStyle(fontSize: 14)),
                ]),
              ),
            ),
            const SizedBox(height: 22),
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(PhosphorIconsBold.scan, color: Colors.white.withValues(alpha: 0.8), size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(aiLine, style: TextStyle(fontSize: 15.5, height: 1.4, color: Colors.white.withValues(alpha: 0.8))),
              ),
            ]),
            const Spacer(),
            YellowButton(
              label: 'Track this report',
              icon: PhosphorIconsBold.path,
              onTap: () => Navigator.of(context).pushReplacement(
                CupertinoPageRoute(builder: (_) => DetailScreen(id: c.id, initial: c)),
              ),
            ),
            const SizedBox(height: 4),
            Center(
              child: CupertinoButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Back to map',
                    style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
              ),
            ),
          ]),
        ),
      ),
    );
  }
}
