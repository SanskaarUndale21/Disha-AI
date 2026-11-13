import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:image_picker/image_picker.dart';
import 'package:latlong2/latlong.dart';
import 'package:share_plus/share_plus.dart';

import '../api.dart';
import '../i18n.dart';
import '../location.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';
import 'detail_screen.dart';
import 'home_screen.dart' show friendlyError;

const _maxFiles = 8;

enum _CheckState { checking, pass, fail, error }

/// AI damage check status for one attached photo or video.
class _Check {
  _CheckState state = _CheckState.checking;
  ScreenResult? result;
  String? error;
}

class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key, this.initialCategory});
  final String? initialCategory;
  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  late String _category = widget.initialCategory ?? 'pothole';
  final _files = <XFile>[];
  final _checks = <XFile, _Check>{};
  String? _warning;
  DateTime? _blockedUntil;
  String? _blockedReason;

  bool get _blocked => _blockedUntil != null && DateTime.now().isBefore(_blockedUntil!);

  String _hhmm(DateTime t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

  Future<void> _check(XFile f) async {
    final c = _Check();
    setState(() => _checks[f] = c);
    try {
      final r = await api.screen(f, _files.indexOf(f));
      if (!mounted || _checks[f] != c) return;
      setState(() {
        c.result = r;
        c.state = r.passed ? _CheckState.pass : _CheckState.fail;
        if (r.warning != null) _warning = r.warning;
        if (r.rateLimited) {
          _blockedUntil = r.blockedUntil ?? DateTime.now().add(const Duration(hours: 1));
          _blockedReason = r.reason;
        }
      });
      HapticFeedback.lightImpact();
    } on ApiException catch (e) {
      if (mounted && _checks[f] == c) setState(() => (c.state = _CheckState.error, c.error = e.message));
    } catch (_) {
      if (mounted && _checks[f] == c) {
        setState(() => (c.state = _CheckState.error, c.error = 'The check failed. Tap Retry.'));
      }
    }
  }

  void _remove(XFile f) => setState(() {
    _files.remove(f);
    _checks.remove(f);
  });

  Future<void> _retake(XFile f) async {
    _remove(f);
    await _addMedia();
  }

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
    if (_blocked) return toast(context, 'Reporting is paused until ${_hhmm(_blockedUntil!)}.', error: true);
    if (_files.length >= _maxFiles) return toast(context, 'You can attach up to $_maxFiles files');
    final choice = await showCupertinoModalPopup<int>(
      context: context,
      builder: (ctx) => CupertinoActionSheet(
        title: const Text('Add evidence'),
        message: const Text('Clear, close shots help the AI measure the damage'),
        actions: [
          CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx, 0), child: const Text('Take Photo')),
          CupertinoActionSheetAction(onPressed: () => Navigator.pop(ctx, 1), child: const Text('Record Video')),
          CupertinoActionSheetAction(
            onPressed: () => Navigator.pop(ctx, 2),
            child: const Text('Photo & Video Library'),
          ),
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
    if (_blocked) return toast(context, 'Reporting is paused until ${_hhmm(_blockedUntil!)}.', error: true);
    if (_files.length >= _maxFiles) return toast(context, 'You can attach up to $_maxFiles files');
    try {
      final List<XFile> picked = switch (choice) {
        0 => [?await _picker.pickImage(source: ImageSource.camera, imageQuality: 85, maxWidth: 2560)],
        1 => [?await _picker.pickVideo(source: ImageSource.camera, maxDuration: const Duration(minutes: 2))],
        _ => await _picker.pickMultipleMedia(imageQuality: 85, maxWidth: 2560, limit: _maxFiles - _files.length),
      };
      if (picked.isEmpty) return;
      HapticFeedback.lightImpact();
      final added = picked.take(_maxFiles - _files.length).toList();
      setState(() => _files.addAll(added));
      for (final f in added) {
        _check(f);
      }
    } catch (_) {
      if (mounted) toast(context, tr('err_generic'), error: true);
    }
  }

  bool get _allPassed => _files.every((f) => _checks[f]?.state == _CheckState.pass);
  bool get _anyChecking => _files.any((f) => _checks[f]?.state == _CheckState.checking);

  bool get _canSubmit => !_sending && (_files.isEmpty ? _desc.text.trim().length >= 5 : _allPassed);

  /// Why Submit is disabled, in plain words; null when it is enabled.
  String? get _submitHint {
    if (_sending || _canSubmit) return null;
    if (_files.isEmpty) return tr('hint_photo');
    if (_anyChecking) return tr('hint_checking');
    return tr('hint_fix');
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_canSubmit) return toast(context, _submitHint ?? 'Add a photo, a video or a short description');
    await prefs.save(name: _name.text, phone: _phone.text);
    setState(() => (_sending = true, _progress = 0.05));
    try {
      final c = await api.submit(
        category: _category,
        description: _desc.text.trim(),
        files: _files,
        screeningTokens: [for (final f in _files) ?_checks[f]?.result?.token],
        lat: _spot?.lat,
        lon: _spot?.lon,
        address: _spot?.address,
        onProgress: (p) => mounted ? setState(() => _progress = p) : null,
      );
      HapticFeedback.heavyImpact();
      refreshTick.value++;
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        PageRouteBuilder(
          transitionDuration: const Duration(milliseconds: 380),
          pageBuilder: (_, _, _) => _SuccessScreen(complaint: c),
          transitionsBuilder: (_, a, _, child) => FadeTransition(opacity: a, child: child),
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() => _sending = false);
        toast(context, e is ApiException ? e.message : friendlyError('$e'), error: true);
      }
    }
  }

  int _step = 0;
  bool _autoCam = false;

  bool get _stepOk => switch (_step) {
        1 => _files.isEmpty || _allPassed,
        _ => true,
      };

  String? get _stepHint {
    if (_step != 1) return null;
    if (_anyChecking) return tr('hint_checking');
    if (_files.isNotEmpty && !_allPassed) return tr('hint_fix');
    return null;
  }

  void _go(int s) {
    FocusScope.of(context).unfocus();
    HapticFeedback.selectionClick();
    setState(() => _step = s);
    if (s == 1 && _files.isEmpty && !_autoCam && !_blocked) {
      _autoCam = true; // camera first: open it once when the photo step appears
      Future.delayed(const Duration(milliseconds: 450), () {
        if (mounted && _step == 1 && _files.isEmpty) _pick(0);
      });
    }
  }

  Future<bool> _confirmExit() async {
    if (_sending) return false;
    if (_files.isEmpty && _desc.text.trim().isEmpty) return true;
    final r = await showCupertinoDialog<bool>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: Text(tr('cancel')),
        actions: [
          CupertinoDialogAction(onPressed: () => Navigator.pop(ctx, false), child: Text(tr('back'))),
          CupertinoDialogAction(
              isDestructiveAction: true, onPressed: () => Navigator.pop(ctx, true), child: Text(tr('cancel'))),
        ],
      ),
    );
    return r == true;
  }

  Widget _progressBar() {
    final c = AppColors.of(context);
    final names = [tr('step_issue'), tr('step_photo'), tr('step_location'), tr('step_send')];
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 6, 20, 4),
      child: Column(children: [
        Row(children: [
          for (var i = 0; i < 4; i++) ...[
            if (i > 0) const SizedBox(width: 6),
            Expanded(
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                height: 5,
                decoration: BoxDecoration(
                  color: i <= _step ? AppColors.blue : c.fill,
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
            ),
          ],
        ]),
        const SizedBox(height: 6),
        Row(children: [
          for (var i = 0; i < 4; i++)
            Expanded(
              child: Text(names[i],
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: i == _step ? FontWeight.w700 : FontWeight.w500,
                      color: i == _step ? AppColors.blue : c.textTertiary)),
            ),
        ]),
      ]),
    );
  }

  Widget _stepBody() {
    final c = AppColors.of(context);
    switch (_step) {
      case 0:
        return Column(key: const ValueKey(0), crossAxisAlignment: CrossAxisAlignment.start, children: [
          _label(tr('whats_issue')),
          GridView.count(
            crossAxisCount: 3,
            childAspectRatio: 0.95,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            children: [for (final cat in categories) _categoryTile(cat)],
          ),
        ]);
      case 1:
        return Column(key: const ValueKey(1), crossAxisAlignment: CrossAxisAlignment.start, children: [
          _label(tr('photo_title'), trailing: '${_files.length}/$_maxFiles'),
          if (_blocked) _pausedBanner(),
          if (_files.isEmpty) _shotGuide() else _checkedList(),
          if (_warning != null && !_blocked) _warningBanner(_warning!),
        ]);
      case 2:
        final noFix = _spot == null && locator.error != null;
        return Column(key: const ValueKey(2), crossAxisAlignment: CrossAxisAlignment.start, children: [
          _label(tr('where')),
          if (noFix) _warningBanner(tr('err_gps')),
          if (noFix) const SizedBox(height: 12),
          _locationCard(),
          _label(tr('details')),
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
                hintText: tr('details_hint'),
                hintStyle: T.body(context).copyWith(color: c.textTertiary),
                counterStyle: T.caption(context),
              ),
            ),
          ),
        ]);
      default:
        final signedIn = Api.accessToken != null && prefs.name.isNotEmpty;
        final cat = categoryOf(_category);
        return Column(key: const ValueKey(3), crossAxisAlignment: CrossAxisAlignment.start, children: [
          _label(tr('summary')),
          CardBox(
            padding: const EdgeInsets.all(14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                IconBadge(cat.icon, cat.color, size: 36),
                const SizedBox(width: 12),
                Expanded(child: Text(cat.label, style: T.headline(context))),
                TextButton(onPressed: () => _go(0), child: Text(tr('step_issue'))),
              ]),
              Divider(height: 18, thickness: 0.5, color: c.separator),
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  child: _files.isEmpty
                      ? Text(tr('no_photos'), style: T.sub(context))
                      : SizedBox(
                          height: 60,
                          child: ListView(scrollDirection: Axis.horizontal, children: [
                            for (final f in _files)
                              Padding(
                                padding: const EdgeInsets.only(right: 8),
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(10),
                                  child: SizedBox(width: 60, height: 60, child: LocalThumb(f, isVideo: Api.isVideo(f))),
                                ),
                              ),
                          ]),
                        ),
                ),
                TextButton(onPressed: () => _go(1), child: Text(tr('step_photo'))),
              ]),
              Divider(height: 18, thickness: 0.5, color: c.separator),
              Row(children: [
                Icon(CupertinoIcons.location_fill, size: 18, color: _spot != null ? AppColors.green : c.textTertiary),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    _spot == null
                        ? tr('tap_map')
                        : (_spot!.address?.isNotEmpty == true ? _spot!.address! : tr('pinned')),
                    maxLines: 3,
                    style: T.body(context).copyWith(fontSize: 15),
                  ),
                ),
                TextButton(onPressed: () => _go(2), child: Text(tr('step_location'))),
              ]),
              if (_desc.text.trim().isNotEmpty) ...[
                Divider(height: 18, thickness: 0.5, color: c.separator),
                Text(_desc.text.trim(), style: T.sub(context)),
              ],
            ]),
          ),
          if (signedIn)
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 16, 4, 0),
              child: Row(children: [
                const Icon(CupertinoIcons.person_crop_circle_fill_badge_checkmark, size: 18, color: AppColors.green),
                const SizedBox(width: 8),
                Expanded(child: Text(prefs.name, style: T.sub(context))),
              ]),
            )
          else ...[
            _label(tr('contact')),
            CardBox(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Column(children: [
                _field(_name, tr('name'), CupertinoIcons.person_fill, TextInputType.name),
                Divider(height: 1, thickness: 0.5, color: c.separator, indent: 34),
                _field(_phone, tr('mobile'), CupertinoIcons.phone_fill, TextInputType.phone),
              ]),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 8, 4, 0),
              child: Text(tr('contact_hint'), style: T.sub(context).copyWith(fontSize: 12.5)),
            ),
          ],
        ]);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final last = _step == 3;
    final hint = last ? _submitHint : _stepHint;
    final canNext = last ? _canSubmit : _stepOk && !_anyChecking;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        if (_step > 0 && !_sending) return _go(_step - 1);
        if (await _confirmExit() && context.mounted) Navigator.pop(context);
      },
      child: Scaffold(
        backgroundColor: c.bg,
        appBar: PreferredSize(
          preferredSize: const Size.fromHeight(52),
          child: Glass(
            child: SafeArea(
              bottom: false,
              child: SizedBox(
                height: 52,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Text(tr('new_report'), style: T.headline(context)),
                    Positioned(
                      left: 4,
                      child: CupertinoButton(
                        minimumSize: const Size(48, 48),
                        onPressed: _sending
                            ? null
                            : () async {
                                if (await _confirmExit() && context.mounted) Navigator.pop(context);
                              },
                        child: Text(tr('cancel')),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        body: GestureDetector(
          onTap: () => FocusScope.of(context).unfocus(),
          child: Column(children: [
            _progressBar(),
            Expanded(
              child: ListView(
                physics: const BouncingScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                children: [
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 260),
                    switchInCurve: Curves.easeOut,
                    child: _stepBody(),
                  ),
                ],
              ),
            ),
          ]),
        ),
        bottomNavigationBar: Glass(
          child: SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 10, 20, 10),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (hint != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(hint, textAlign: TextAlign.center, style: T.sub(context).copyWith(fontSize: 13)),
                    ),
                  Row(children: [
                    if (_step > 0 && !_sending) ...[
                      Pressable(
                        onTap: () => _go(_step - 1),
                        child: Container(
                          height: 56,
                          constraints: const BoxConstraints(minWidth: 88),
                          padding: const EdgeInsets.symmetric(horizontal: 18),
                          alignment: Alignment.center,
                          decoration: BoxDecoration(color: c.fill, borderRadius: BorderRadius.circular(18)),
                          child: Text(tr('back'),
                              style: TextStyle(color: c.text, fontSize: 16, fontWeight: FontWeight.w600)),
                        ),
                      ),
                      const SizedBox(width: 10),
                    ],
                    Expanded(
                      child: Pressable(
                        onTap: _sending
                            ? null
                            : () {
                                if (last) { _submit(); return; }
                                if (!canNext) { toast(context, hint ?? tr('hint_photo')); return; }
                                _go(_step + 1);
                              },
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 250),
                          height: 56,
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(18),
                            color: canNext || _sending ? AppColors.blue : c.fill,
                            boxShadow: canNext
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
                                        Text(_progress < 0.5 ? tr('uploading') : tr('analysing'),
                                            style: const TextStyle(
                                                color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
                                      ])
                                    : Text(
                                        last
                                            ? tr('submit')
                                            : (_step == 1 && _files.isEmpty ? tr('next') : tr('next')),
                                        style: TextStyle(
                                            color: canNext ? Colors.white : c.textTertiary,
                                            fontSize: 17,
                                            fontWeight: FontWeight.w600)),
                              ),
                            ]),
                          ),
                        ),
                      ),
                    ),
                  ]),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _pausedBanner() => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: CardBox(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const IconBadge(CupertinoIcons.hand_raised_fill, AppColors.red, size: 36),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Reporting paused until ${_hhmm(_blockedUntil!)}', style: T.headline(context)),
                const SizedBox(height: 3),
                Text(
                  _blockedReason?.isNotEmpty == true
                      ? _blockedReason!
                      : 'Too many photos without road damage. Try again later with a clear photo of the damage.',
                  style: T.sub(context),
                ),
              ],
            ),
          ),
        ],
      ),
    ),
  );

  Widget _warningBanner(String text) => Padding(
    padding: const EdgeInsets.only(top: 12),
    child: Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.orange.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(CupertinoIcons.exclamationmark_triangle_fill, color: AppColors.orange, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: T.sub(context).copyWith(color: AppColors.of(context).text)),
          ),
        ],
      ),
    ),
  );

  /// One card per attached file with its AI damage check status.
  Widget _checkedList() {
    final c = AppColors.of(context);
    return Column(
      children: [
        for (final f in _files) Padding(padding: const EdgeInsets.only(bottom: 10), child: _checkCard(f)),
        if (_files.length < _maxFiles && !_blocked)
          Pressable(
            onTap: _addMedia,
            child: Container(
              height: 56,
              decoration: BoxDecoration(
                color: AppColors.blue.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppColors.blue.withValues(alpha: 0.35), width: 1.2),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(CupertinoIcons.plus_circle_fill, color: AppColors.blue, size: 20),
                  const SizedBox(width: 8),
                  Text(
                    tr('add_more'),
                    style: const TextStyle(color: AppColors.blue, fontWeight: FontWeight.w600, fontSize: 15),
                  ),
                  const SizedBox(width: 8),
                  Text('${_files.length}/$_maxFiles', style: TextStyle(fontSize: 12.5, color: c.textSecondary)),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _checkCard(XFile f) {
    final chk = _checks[f];
    final state = chk?.state ?? _CheckState.checking;
    final r = chk?.result;
    final video = Api.isVideo(f);
    final (Color color, IconData icon, String title, String detail) = switch (state) {
      _CheckState.checking => (
        AppColors.blue,
        CupertinoIcons.viewfinder,
        'Checking for road damage...',
        video ? 'Videos take a few seconds.' : 'This takes a second or two.',
      ),
      _CheckState.pass => (AppColors.green, CupertinoIcons.checkmark_seal_fill, r!.headline, 'Ready to send.'),
      _CheckState.fail => (
        AppColors.red,
        CupertinoIcons.xmark_octagon_fill,
        r?.rateLimited == true ? 'Reporting paused' : 'No road damage found',
        r?.reason ?? 'Take a closer photo of the damage.',
      ),
      _CheckState.error => (
        AppColors.orange,
        CupertinoIcons.wifi_exclamationmark,
        'Check did not finish',
        chk?.error ?? '',
      ),
    };
    final preview = state == _CheckState.pass && r?.previewUrl != null ? api.url(r!.previewUrl) : null;
    return CardBox(
      padding: const EdgeInsets.all(10),
      radius: 18,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: SizedBox(
              width: 96,
              height: 96,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  preview != null
                      ? Image.network(
                          preview,
                          fit: BoxFit.cover,
                          errorBuilder: (_, _, _) => LocalThumb(f, isVideo: video),
                        )
                      : LocalThumb(f, isVideo: video),
                  if (state == _CheckState.checking)
                    Container(
                      color: Colors.black38,
                      child: const CupertinoActivityIndicator(color: Colors.white),
                    ),
                  Positioned(
                    left: 5,
                    right: 5,
                    bottom: 5,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(99)),
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          switch (state) {
                            _CheckState.checking => tr('ai_checking'),
                            _CheckState.pass => 'AI ${tr('ai_ok')}',
                            _CheckState.fail => 'AI ${tr('ai_fail')}',
                            _CheckState.error => tr('ai_retry'),
                          },
                          maxLines: 1,
                          style: const TextStyle(color: Colors.white, fontSize: 10.5, fontWeight: FontWeight.w700),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(icon, size: 17, color: color),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(title, style: T.headline(context).copyWith(fontSize: 15.5, color: color)),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(detail, style: T.sub(context).copyWith(fontSize: 13.5)),
                const SizedBox(height: 8),
                Row(
                  children: [
                    if (state == _CheckState.fail && r?.rateLimited != true)
                      _smallButton(tr('retake'), CupertinoIcons.camera_fill, AppColors.blue, () => _retake(f)),
                    if (state == _CheckState.error)
                      _smallButton(tr('retry'), CupertinoIcons.arrow_clockwise, AppColors.blue, () => _check(f)),
                    if (state != _CheckState.checking) ...[
                      const SizedBox(width: 8),
                      _smallButton(
                        tr('remove'),
                        CupertinoIcons.trash,
                        AppColors.of(context).textSecondary,
                        () => _remove(f),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _smallButton(String label, IconData icon, Color color, VoidCallback onTap) => Pressable(
    onTap: onTap,
    child: Container(
      constraints: const BoxConstraints(minHeight: 40),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(99)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 5),
          Text(
            label,
            style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: color),
          ),
        ],
      ),
    ),
  );

  Widget _label(String t, {String? trailing}) => Padding(
    padding: const EdgeInsets.fromLTRB(4, 24, 4, 10),
    child: Row(
      children: [
        Expanded(child: Text(t, style: T.headline(context).copyWith(fontSize: 18))),
        if (trailing != null) Text(trailing, style: T.caption(context)),
      ],
    ),
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
          child: Stack(
            fit: StackFit.expand,
            children: [
              PhotoTile(
                asset: cat.thumb,
                label: cat.label,
                radius: sel ? 16 : 20,
                labelSize: 13.5,
                icon: cat.icon,
                color: cat.color,
              ),
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
            ],
          ),
        ),
      ),
    );
  }

  /// Empty state for evidence: a real example of a good shot, then the three ways to add one.
  Widget _shotGuide() {
    return CardBox(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          ClipRRect(
            borderRadius: const BorderRadius.vertical(top: Radius.circular(22)),
            child: AspectRatio(
              aspectRatio: 16 / 9,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Image.asset('assets/photos/goodshot.jpg', fit: BoxFit.cover),
                  Positioned(
                    left: 12,
                    bottom: 12,
                    child: Glass(
                      radius: 99,
                      opacity: 0.85,
                      child: const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(CupertinoIcons.checkmark_alt_circle_fill, size: 14, color: AppColors.green),
                            SizedBox(width: 5),
                            Text('Good shot', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text(
              tr('photo_sub'),
              style: T.sub(context),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
            child: Column(
              children: [
                _pickButton(CupertinoIcons.camera_fill, tr('take_photo'), () => _pick(0), primary: true, tall: true),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(child: _pickButton(CupertinoIcons.videocam_fill, tr('record_video'), () => _pick(1))),
                    const SizedBox(width: 8),
                    Expanded(child: _pickButton(CupertinoIcons.photo_on_rectangle, tr('library'), () => _pick(2))),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _pickButton(IconData icon, String label, VoidCallback onTap, {bool primary = false, bool tall = false}) {
    final c = AppColors.of(context);
    return Pressable(
      onTap: onTap,
      child: Container(
        height: tall ? 68 : 60,
        width: double.infinity,
        decoration: BoxDecoration(color: primary ? AppColors.blue : c.fill, borderRadius: BorderRadius.circular(14)),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 22, color: primary ? Colors.white : AppColors.blue),
            const SizedBox(height: 3),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: primary ? Colors.white : c.text),
            ),
          ],
        ),
      ),
    );
  }

  Widget _locationCard() {
    final s = _spot;
    final has = s != null;
    final color = has ? AppColors.green : (locator.error != null ? AppColors.orange : AppColors.blue);
    return CardBox(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
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
                    MarkerLayer(
                      markers: [
                        Marker(
                          point: LatLng(s.lat, s.lon),
                          width: 34,
                          height: 34,
                          child: MapPin(color: categoryOf(_category).color, size: 34),
                        ),
                      ],
                    ),
                  const MapCredit(),
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                IconBadge(has ? CupertinoIcons.location_fill : CupertinoIcons.location_slash_fill, color, size: 40),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        locator.busy && !has
                            ? tr('finding_loc')
                            : has
                            ? (s.address?.isNotEmpty == true ? s.address! : tr('pinned'))
                            : tr('tap_map'),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: T.headline(context).copyWith(fontSize: 15.5),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        has
                            ? (_pinMoved
                                  ? tr('adjust_map')
                                  : '±${s.accuracy?.round() ?? '?'} m. ${tr('adjust_map')}')
                            : (locator.error ?? tr('err_gps')),
                        style: T.sub(context).copyWith(fontSize: 12.5),
                      ),
                    ],
                  ),
                ),
                locator.busy
                    ? const Padding(padding: EdgeInsets.all(8), child: CupertinoActivityIndicator())
                    : CupertinoButton(
                        padding: const EdgeInsets.all(8),
                        minimumSize: const Size(48, 48),
                        onPressed: _useMyLocation,
                        child: const Icon(CupertinoIcons.location_circle, size: 24),
                      ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _field(TextEditingController ctl, String hint, IconData icon, TextInputType type) {
    final c = AppColors.of(context);
    return Row(
      children: [
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
      ],
    );
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

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: widget.complaint.ticket));
    HapticFeedback.mediumImpact();
    if (mounted) toast(context, tr('copied'));
  }

  Future<void> _share() async {
    HapticFeedback.selectionClick();
    try {
      await SharePlus.instance.share(ShareParams(text: tr('share_text', {'t': widget.complaint.ticket})));
    } catch (_) {
      if (mounted) toast(context, tr('err_generic'), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.complaint;
    final colors = AppColors.of(context);
    final n = c.findings.length;
    final pending = c.media.any((m) => m.processing);
    final scale = CurvedAnimation(parent: _ac, curve: const Interval(0, 0.6, curve: Curves.elasticOut));
    final fade = CurvedAnimation(parent: _ac, curve: const Interval(0.35, 1, curve: Curves.easeOut));
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: MediaQuery.sizeOf(context).height - 120),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const SizedBox(height: 24),
                ScaleTransition(
                  scale: scale,
                  child: Container(
                    width: 104,
                    height: 104,
                    decoration: const BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: LinearGradient(colors: [Color(0xFF4CD964), Color(0xFF28B446)]),
                      boxShadow: [BoxShadow(color: Color(0x5530D158), blurRadius: 40, offset: Offset(0, 16))],
                    ),
                    child: const Icon(CupertinoIcons.checkmark_alt, color: Colors.white, size: 58),
                  ),
                ),
                const SizedBox(height: 24),
                FadeTransition(
                  opacity: fade,
                  child: Column(children: [
                    Text(tr('success_title'), textAlign: TextAlign.center, style: T.largeTitle(context).copyWith(fontSize: 30)),
                    const SizedBox(height: 8),
                    Text(tr('success_text'), textAlign: TextAlign.center, style: T.sub(context).copyWith(fontSize: 16)),
                    const SizedBox(height: 22),
                    CardBox(
                      child: Column(children: [
                        Text(tr('ticket'), style: T.caption(context)),
                        const SizedBox(height: 4),
                        SelectableText(c.ticket,
                            style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, letterSpacing: 0.5)),
                        const SizedBox(height: 12),
                        Row(children: [
                          Expanded(child: _action(CupertinoIcons.doc_on_doc, tr('copy'), _copy)),
                          const SizedBox(width: 10),
                          Expanded(child: _action(CupertinoIcons.share, tr('share'), _share)),
                        ]),
                        Divider(height: 24, thickness: 0.5, color: colors.separator),
                        _row(context, tr('issue'), categoryOf(c.category).label),
                        _row(
                          context,
                          'AI',
                          pending
                              ? tr('analysing')
                              : (n == 0 ? (c.media.isEmpty ? tr('no_photos') : tr('submitted')) : '$n x ${tr('ai_ok')}'),
                        ),
                      ]),
                    ),
                  ]),
                ),
                const SizedBox(height: 28),
                Pressable(
                  onTap: () => Navigator.of(context).pushReplacement(
                    CupertinoPageRoute(builder: (_) => DetailScreen(id: c.id, initial: c)),
                  ),
                  child: Container(
                    height: 56,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(color: AppColors.blue, borderRadius: BorderRadius.circular(18)),
                    child: Text(tr('track'),
                        style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
                  ),
                ),
                const SizedBox(height: 4),
                CupertinoButton(
                    minimumSize: const Size(48, 48),
                    onPressed: () => Navigator.pop(context),
                    child: Text(tr('done'))),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _action(IconData icon, String label, VoidCallback onTap) => Pressable(
        onTap: onTap,
        child: Container(
          height: 48,
          decoration: BoxDecoration(color: AppColors.of(context).fill, borderRadius: BorderRadius.circular(14)),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(icon, size: 18, color: AppColors.blue),
            const SizedBox(width: 8),
            Text(label, style: const TextStyle(color: AppColors.blue, fontWeight: FontWeight.w600, fontSize: 15)),
          ]),
        ),
      );

  Widget _row(BuildContext context, String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          Text(k, style: T.sub(context)),
          const SizedBox(width: 12),
          Expanded(child: Text(v, textAlign: TextAlign.right, style: T.body(context).copyWith(fontWeight: FontWeight.w500))),
        ]),
      );
}
