import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:image_picker/image_picker.dart';
import 'package:latlong2/latlong.dart';

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

  Future<void> _addMedia() async {
    if (_files.length >= _maxFiles) return toast(context, 'You can attach up to $_maxFiles files');
    final choice = await showCupertinoModalPopup<int>(
      context: context,
      builder: (ctx) => CupertinoActionSheet(
        title: const Text('Add evidence'),
        message: const Text('Clear, close shots help the AI measure the damage'),
        actions: [
          CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx, 0), child: const Text('Take Photo')),
          CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx, 1), child: const Text('Record Video')),
          CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx, 2), child: const Text('Photo & Video Library')),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.pop(ctx),
          child: const Text('Cancel'),
        ),
      ),
    );
    if (choice != null) await _pick(choice);
  }

  Future<void> _pick(int choice) async {
    if (_files.length >= _maxFiles) return toast(context, 'You can attach up to $_maxFiles files');
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
      if (mounted) toast(context, 'Could not open camera or gallery', error: true);
    }
  }

  bool get _canSubmit => !_sending && (_files.isNotEmpty || _desc.text.trim().length >= 5);

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_canSubmit) return toast(context, 'Add a photo, a video or a short description');
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
        transitionDuration: const Duration(milliseconds: 380),
        pageBuilder: (_, _, _) => _SuccessScreen(complaint: c),
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
    final signedIn = Api.accessToken != null && prefs.name.isNotEmpty;
    return Scaffold(
      backgroundColor: c.bg,
      appBar: PreferredSize(
        preferredSize: const Size.fromHeight(52),
        child: Glass(
          child: SafeArea(
            bottom: false,
            child: SizedBox(
              height: 52,
              child: Stack(alignment: Alignment.center, children: [
                Text('New Report', style: T.headline(context)),
                Positioned(
                  left: 4,
                  child: CupertinoButton(
                    onPressed: _sending ? null : () => Navigator.pop(context),
                    child: const Text('Cancel'),
                  ),
                ),
              ]),
            ),
          ),
        ),
      ),
      body: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: ListView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 140),
          children: [
            _label('What\'s the issue?'),
            GridView.count(
              crossAxisCount: 3,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 10,
              crossAxisSpacing: 10,
              children: [for (final cat in categories) _categoryTile(cat)],
            ),
            _label('Photos & videos', trailing: '${_files.length}/$_maxFiles'),
            if (_files.isEmpty) _shotGuide() else _mediaStrip(),
            _label('Location'),
            _locationCard(),
            _label('Details'),
            CardBox(
              padding: const EdgeInsets.fromLTRB(16, 6, 16, 6),
              child: TextField(
                controller: _desc,
                onChanged: (_) => setState(() {}),
                minLines: 3,
                maxLines: 6,
                maxLength: 500,
                textCapitalization: TextCapitalization.sentences,
                style: T.body(context),
                decoration: InputDecoration(
                  border: InputBorder.none,
                  hintText: 'e.g. Deep pothole near the bus stop, two-wheelers swerving into traffic',
                  hintStyle: T.body(context).copyWith(color: c.textTertiary),
                  counterStyle: T.caption(context),
                ),
              ),
            ),
            if (signedIn)
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 16, 4, 0),
                child: Row(children: [
                  const Icon(CupertinoIcons.person_crop_circle_fill_badge_checkmark, size: 18, color: AppColors.green),
                  const SizedBox(width: 8),
                  Expanded(
                      child: Text('Filing as ${prefs.name}. You\'ll get live status updates.', style: T.sub(context))),
                ]),
              )
            else ...[
              _label('Your contact'),
              CardBox(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Column(children: [
                  _field(_name, 'Full name', CupertinoIcons.person_fill, TextInputType.name),
                  Divider(height: 1, thickness: 0.5, color: c.separator, indent: 34),
                  _field(_phone, 'Mobile number', CupertinoIcons.phone_fill, TextInputType.phone),
                ]),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 8, 4, 0),
                child: Text('Used only to send you repair updates. Optional.',
                    style: T.sub(context).copyWith(fontSize: 12.5)),
              ),
            ],
          ],
        ),
      ),
      bottomNavigationBar: Glass(
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
            child: Pressable(
              onTap: _sending ? null : _submit,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                height: 56,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  color: _canSubmit || _sending ? AppColors.blue : c.fill,
                  boxShadow: _canSubmit
                      ? const [BoxShadow(color: Color(0x550A84FF), blurRadius: 20, offset: Offset(0, 8))]
                      : null,
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(18),
                  child: Stack(children: [
                    if (_sending)
                      AnimatedFractionallySizedBox(
                        duration: const Duration(milliseconds: 400),
                        widthFactor: _progress.clamp(0.05, 1),
                        child: Container(color: Colors.white.withValues(alpha: 0.18)),
                      ),
                    Center(
                      child: _sending
                          ? Row(mainAxisSize: MainAxisSize.min, children: [
                              const CupertinoActivityIndicator(color: Colors.white),
                              const SizedBox(width: 10),
                              Text(_progress < 0.5 ? 'Uploading...' : 'AI is analysing...',
                                  style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
                            ])
                          : Text('Submit report',
                              style: TextStyle(
                                  color: _canSubmit ? Colors.white : c.textTertiary,
                                  fontSize: 17,
                                  fontWeight: FontWeight.w600)),
                    ),
                  ]),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _label(String t, {String? trailing}) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 24, 4, 10),
        child: Row(children: [
          Expanded(child: Text(t, style: T.headline(context).copyWith(fontSize: 18))),
          if (trailing != null) Text(trailing, style: T.caption(context)),
        ]),
      );

  Widget _categoryTile(Category cat) {
    final sel = _category == cat.key;
    return Pressable(
      onTap: () => setState(() => _category = cat.key),
      child: Semantics(
        selected: sel,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
          padding: EdgeInsets.all(sel ? 3 : 0),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: sel ? AppColors.blue : Colors.transparent, width: 2.5),
          ),
          child: Stack(fit: StackFit.expand, children: [
            PhotoTile(asset: cat.thumb, label: cat.label, radius: sel ? 16 : 20, labelSize: 13.5),
            Positioned(
              right: 6,
              top: 6,
              child: AnimatedScale(
                scale: sel ? 1 : 0,
                duration: const Duration(milliseconds: 260),
                curve: Curves.easeOutBack,
                child: Container(
                  decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                  child: const Icon(CupertinoIcons.checkmark_circle_fill, color: AppColors.blue, size: 22),
                ),
              ),
            ),
          ]),
        ),
      ),
    );
  }

  /// Empty state for evidence: a real example of a good shot, then the three ways to add one.
  Widget _shotGuide() {
    return CardBox(
      padding: EdgeInsets.zero,
      child: Column(children: [
        ClipRRect(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(22)),
          child: AspectRatio(
            aspectRatio: 16 / 9,
            child: Stack(fit: StackFit.expand, children: [
              Image.asset('assets/photos/goodshot.jpg', fit: BoxFit.cover),
              Positioned(
                left: 12,
                bottom: 12,
                child: Glass(
                  radius: 99,
                  opacity: 0.85,
                  child: const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      Icon(CupertinoIcons.checkmark_alt_circle_fill, size: 14, color: AppColors.green),
                      SizedBox(width: 5),
                      Text('Good shot', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                    ]),
                  ),
                ),
              ),
            ]),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Text('Step back about a metre so the whole pothole and a bit of road around it are in frame.',
              style: T.sub(context)),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
          child: Row(children: [
            Expanded(child: _pickButton(CupertinoIcons.camera_fill, 'Photo', () => _pick(0), primary: true)),
            const SizedBox(width: 8),
            Expanded(child: _pickButton(CupertinoIcons.videocam_fill, 'Video', () => _pick(1))),
            const SizedBox(width: 8),
            Expanded(child: _pickButton(CupertinoIcons.photo_on_rectangle, 'Library', () => _pick(2))),
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
        height: 60,
        decoration: BoxDecoration(
          color: primary ? AppColors.blue : c.fill,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(icon, size: 22, color: primary ? Colors.white : AppColors.blue),
          const SizedBox(height: 3),
          Text(label,
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: primary ? Colors.white : c.text)),
        ]),
      ),
    );
  }

  Widget _mediaStrip() => SizedBox(
        height: 112,
        child: ListView(
          scrollDirection: Axis.horizontal,
          clipBehavior: Clip.none,
          physics: const BouncingScrollPhysics(),
          children: [
            _addTile(),
            for (var i = 0; i < _files.length; i++) _mediaTile(i),
          ],
        ),
      );

  Widget _addTile() {
    final c = AppColors.of(context);
    return Pressable(
      onTap: _addMedia,
      child: Container(
        width: 112,
        margin: const EdgeInsets.only(right: 10),
        decoration: BoxDecoration(
          color: AppColors.blue.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppColors.blue.withValues(alpha: 0.35), width: 1.2),
        ),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          const Icon(CupertinoIcons.camera_fill, color: AppColors.blue, size: 28),
          const SizedBox(height: 6),
          const Text('Add', style: TextStyle(color: AppColors.blue, fontWeight: FontWeight.w600)),
          Text('photo / video', style: TextStyle(fontSize: 11, color: c.textSecondary)),
        ]),
      ),
    );
  }

  Widget _mediaTile(int i) {
    final f = _files[i];
    final video = Api.isVideo(f);
    return Padding(
      padding: const EdgeInsets.only(right: 10),
      child: Stack(children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(20),
          child: SizedBox(width: 112, height: 112, child: LocalThumb(f, isVideo: video)),
        ),
        if (video)
          Positioned(
            left: 8,
            bottom: 8,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
              decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(8)),
              child: const Row(children: [
                Icon(CupertinoIcons.videocam_fill, color: Colors.white, size: 12),
                SizedBox(width: 3),
                Text('Video', style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
              ]),
            ),
          ),
        Positioned(
          right: 6,
          top: 6,
          child: Pressable(
            onTap: () => setState(() => _files.removeAt(i)),
            child: Container(
              width: 26,
              height: 26,
              decoration: const BoxDecoration(color: Colors.black54, shape: BoxShape.circle),
              child: const Icon(CupertinoIcons.xmark, color: Colors.white, size: 14),
            ),
          ),
        ),
      ]),
    );
  }

  Widget _locationCard() {
    final s = _spot;
    final has = s != null;
    final color = has ? AppColors.green : (locator.error != null ? AppColors.orange : AppColors.blue);
    return CardBox(
      padding: EdgeInsets.zero,
      child: Column(children: [
        ClipRRect(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(22)),
          child: SizedBox(
            height: 170,
            child: FlutterMap(
              mapController: _map,
              options: MapOptions(
                initialCenter: has ? LatLng(s.lat, s.lon) : const LatLng(12.9716, 77.5946),
                initialZoom: has ? 17 : 12,
                onMapReady: () => _mapReady = true,
                onTap: (_, p) => _movePin(p),
                interactionOptions: const InteractionOptions(flags: InteractiveFlag.all & ~InteractiveFlag.rotate),
              ),
              children: [
                const MapTiles(),
                if (has)
                  MarkerLayer(markers: [
                    Marker(
                      point: LatLng(s.lat, s.lon),
                      width: 34,
                      height: 34,
                      child: MapPin(color: categoryOf(_category).color, size: 34),
                    ),
                  ]),
                const MapCredit(),
              ],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(14),
          child: Row(children: [
            IconBadge(has ? CupertinoIcons.location_fill : CupertinoIcons.location_slash_fill, color, size: 40),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(
                  locator.busy && !has
                      ? 'Finding your location...'
                      : has
                          ? (s.address?.isNotEmpty == true ? s.address! : 'Pinned on the map')
                          : 'Tap the map to place a pin',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: T.headline(context).copyWith(fontSize: 15.5),
                ),
                const SizedBox(height: 2),
                Text(
                  has
                      ? (_pinMoved ? 'Placed by you. Tap the map to adjust.' : '±${s.accuracy?.round() ?? '?'} m. Tap the map to adjust.')
                      : (locator.error ?? 'Pinning the exact spot helps crews find it'),
                  style: T.sub(context).copyWith(fontSize: 12.5),
                ),
              ]),
            ),
            locator.busy
                ? const Padding(padding: EdgeInsets.all(8), child: CupertinoActivityIndicator())
                : CupertinoButton(
                    padding: const EdgeInsets.all(8),
                    minimumSize: Size.zero,
                    onPressed: _useMyLocation,
                    child: const Icon(CupertinoIcons.location_circle, size: 24),
                  ),
          ]),
        ),
      ]),
    );
  }

  Widget _field(TextEditingController ctl, String hint, IconData icon, TextInputType type) {
    final c = AppColors.of(context);
    return Row(children: [
      Icon(icon, size: 18, color: c.textTertiary),
      const SizedBox(width: 14),
      Expanded(
        child: TextField(
          controller: ctl,
          keyboardType: type,
          style: T.body(context),
          decoration: InputDecoration(
            border: InputBorder.none,
            hintText: hint,
            hintStyle: T.body(context).copyWith(color: c.textTertiary),
            contentPadding: const EdgeInsets.symmetric(vertical: 15),
          ),
        ),
      ),
    ]);
  }
}

class _SuccessScreen extends StatefulWidget {
  const _SuccessScreen({required this.complaint});
  final Complaint complaint;
  @override
  State<_SuccessScreen> createState() => _SuccessScreenState();
}

class _SuccessScreenState extends State<_SuccessScreen> with SingleTickerProviderStateMixin {
  late final _ac = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..forward();

  @override
  void dispose() {
    _ac.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.complaint;
    final n = c.findings.length;
    final pending = c.media.any((m) => m.processing);
    final scale = CurvedAnimation(parent: _ac, curve: const Interval(0, 0.6, curve: Curves.elasticOut));
    final fade = CurvedAnimation(parent: _ac, curve: const Interval(0.35, 1, curve: Curves.easeOut));
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(children: [
            const Spacer(flex: 2),
            ScaleTransition(
              scale: scale,
              child: Container(
                width: 110,
                height: 110,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(colors: [Color(0xFF4CD964), Color(0xFF28B446)]),
                  boxShadow: [BoxShadow(color: Color(0x5530D158), blurRadius: 40, offset: Offset(0, 16))],
                ),
                child: const Icon(CupertinoIcons.checkmark_alt, color: Colors.white, size: 60),
              ),
            ),
            const SizedBox(height: 28),
            FadeTransition(
              opacity: fade,
              child: Column(children: [
                Text('Report submitted', style: T.largeTitle(context).copyWith(fontSize: 30)),
                const SizedBox(height: 8),
                Text('Thanks for making your streets safer.', style: T.sub(context).copyWith(fontSize: 16)),
                const SizedBox(height: 24),
                CardBox(
                  child: Column(children: [
                    _row(context, 'Ticket', c.ticket, bold: true),
                    _row(context, 'Category', categoryOf(c.category).label),
                    _row(
                      context,
                      'AI check',
                      pending
                          ? 'Analysing video...'
                          : (n == 0
                              ? (c.media.isEmpty ? 'No media' : 'Sent for manual review')
                              : '$n defect${n == 1 ? '' : 's'} detected'),
                    ),
                  ]),
                ),
              ]),
            ),
            const Spacer(flex: 3),
            Pressable(
              onTap: () => Navigator.of(context).pushReplacement(
                CupertinoPageRoute(builder: (_) => DetailScreen(id: c.id, initial: c)),
              ),
              child: Container(
                height: 56,
                alignment: Alignment.center,
                decoration: BoxDecoration(color: AppColors.blue, borderRadius: BorderRadius.circular(18)),
                child: const Text('Track this report',
                    style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
              ),
            ),
            CupertinoButton(onPressed: () => Navigator.pop(context), child: const Text('Done')),
          ]),
        ),
      ),
    );
  }

  Widget _row(BuildContext context, String k, String v, {bool bold = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(children: [
          Text(k, style: T.sub(context)),
          const Spacer(),
          Text(v, style: T.body(context).copyWith(fontWeight: bold ? FontWeight.w700 : FontWeight.w500)),
        ]),
      );
}
