import 'dart:async';
import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:image_picker/image_picker.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../api.dart';
import '../main.dart';
import '../widgets.dart';

const _charcoal = Color(0xFF3D405B);
const _sage = Color(0xFF81B29A);
const _peach = Color(0xFFF2CC8F);
const _ivory = Color(0xFFF4F1DE);
const _terracotta = Color(0xFFE07A5F);
const _bgTop = Color(0xFF16182A);
const _bgBottom = Color(0xFF1F2133);

/// Opens the in-app voice call with Disha, full screen.
Future<void> openCallScreen(BuildContext context) {
  HapticFeedback.mediumImpact();
  return Navigator.of(context, rootNavigator: true).push(PageRouteBuilder(
    fullscreenDialog: true,
    opaque: true,
    transitionDuration: const Duration(milliseconds: 350),
    pageBuilder: (_, _, _) => const CallScreen(),
    transitionsBuilder: (_, a, _, child) => FadeTransition(opacity: a, child: child),
  ));
}

enum _Phase { pick, connecting, live, filing, ticket, ended }

enum _Mode { idle, listening, thinking, speaking, scanning }

class _Lang {
  final String code, locale, name, native;
  const _Lang(this.code, this.locale, this.name, this.native);
}

const _langs = [
  _Lang('en', 'en-IN', 'English', 'English'),
  _Lang('hi', 'hi-IN', 'Hindi', 'हिन्दी'),
  _Lang('kn', 'kn-IN', 'Kannada', 'ಕನ್ನಡ'),
  _Lang('mr', 'mr-IN', 'Marathi', 'मराठी'),
];

class _Shot {
  _Shot(this.file, this.isVideo);
  final XFile file;
  final bool isVideo;
  bool checking = true;
  ScreenResult? result;
  String? error;
  bool get passed => result?.passed == true;
}

class CallScreen extends StatefulWidget {
  const CallScreen({super.key});
  @override
  State<CallScreen> createState() => _CallScreenState();
}

class _CallScreenState extends State<CallScreen> with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  _Phase _phase = _Phase.pick;
  _Mode _mode = _Mode.idle;
  _Lang _lang = _langs.first;

  final _stt = SpeechToText();
  final _tts = FlutterTts();
  final _input = TextEditingController();
  final _level = ValueNotifier<double>(0);
  final _secs = ValueNotifier<int>(0);
  late final AnimationController _anim = AnimationController(vsync: this, duration: const Duration(seconds: 20));

  Timer? _clock, _restart, _recTimer;
  bool _sttReady = false, _micDenied = false, _muted = false, _ending = false, _disposed = false;
  bool _speakingNow = false, _busy = false, _ttsMissing = false;
  int _sttFails = 0;
  String? _sttLocale;

  String? _sessionId, _placeText, _notice, _filingError;
  String _dishaLine = '', _heard = '', _stage = '', _expect = 'speech';
  List<String> _suggest = [];
  Map<String, dynamic> _fields = {};
  double? _lat, _lon;

  CameraController? _cam;
  List<CameraDescription> _cams = [];
  int _camIndex = 0;
  bool _camOn = false, _camDenied = false, _recording = false, _camBusy = false;
  final List<_Shot> _shots = [];

  Complaint? _ticket;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduce = MediaQuery.of(context).disableAnimations;
    if (reduce) {
      _anim.stop();
    } else if (!_anim.isAnimating) {
      _anim.repeat();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    if (s == AppLifecycleState.paused && _phase == _Phase.live) {
      _stopListening();
      _tts.stop();
    }
    if (s == AppLifecycleState.resumed && _phase == _Phase.live && !_speakingNow && !_busy) _scheduleListen();
  }

  @override
  void dispose() {
    _disposed = true;
    WidgetsBinding.instance.removeObserver(this);
    _clock?.cancel();
    _restart?.cancel();
    _recTimer?.cancel();
    try {
      _stt.cancel();
    } catch (_) {}
    try {
      _tts.stop();
    } catch (_) {}
    _cam?.dispose();
    _anim.dispose();
    _input.dispose();
    _level.dispose();
    _secs.dispose();
    WakelockPlus.disable();
    super.dispose();
  }

  void _set(VoidCallback f) {
    if (mounted && !_disposed) setState(f);
  }

  // ------------------------------------------------------------ connect
  Future<void> _connect(_Lang l) async {
    _lang = l;
    _set(() => _phase = _Phase.connecting);
    WakelockPlus.enable();
    final spotFuture = locator.locate();
    await _setupTts();
    await _setupStt();
    final spot = await spotFuture;
    if (spot != null) {
      _lat = spot.lat;
      _lon = spot.lon;
      _placeText = spot.area ?? spot.address ?? 'Location found';
    } else {
      _placeText = null;
      _notice = locator.error ?? 'Location is off, so I will ask you for the place.';
    }
    try {
      final r = await api.callStart(l.code, _lat, _lon);
      _sessionId = '${r['session_id']}';
      _secs.value = 0;
      _clock = Timer.periodic(const Duration(seconds: 1), (_) => _secs.value++);
      _set(() => _phase = _Phase.live);
      await _apply(r);
    } catch (e) {
      _set(() {
        _phase = _Phase.pick;
        _notice = '$e';
      });
      if (mounted) toast(context, '$e', error: true);
    }
  }

  Future<void> _setupTts() async {
    try {
      await _tts.awaitSpeakCompletion(true);
      final avail = await _tts.isLanguageAvailable(_lang.locale);
      if (avail != true) _ttsMissing = true;
      await _tts.setLanguage(_lang.locale);
      await _tts.setSpeechRate(0.45);
      await _tts.setPitch(1.05);
      await _tts.setVolume(1.0);
      final voices = await _tts.getVoices;
      if (voices is List) {
        final mine = [
          for (final v in voices)
            if (v is Map && '${v['locale']}'.replaceAll('_', '-').toLowerCase() == _lang.locale.toLowerCase()) v
        ];
        Map? pick;
        for (final v in mine) {
          final n = '${v['name']}'.toLowerCase();
          if (n.contains('female') || RegExp(r'-(f|fe)[a-z]*(-|$)').hasMatch(n) || n.contains('x-${_lang.code}a-') == false && n.contains('-sfg')) {
            pick = v;
            break;
          }
        }
        pick ??= mine.isEmpty ? null : mine.first;
        if (pick != null) {
          await _tts.setVoice({'name': '${pick['name']}', 'locale': '${pick['locale']}'});
        }
      }
    } catch (_) {
      _ttsMissing = true;
    }
  }

  Future<void> _setupStt() async {
    try {
      _sttReady = await _stt.initialize(onStatus: _onSttStatus, onError: _onSttError);
      if (!_sttReady) {
        _micDenied = true;
        return;
      }
      final locs = await _stt.locales();
      final want = _lang.locale.replaceAll('-', '_').toLowerCase();
      for (final l in locs) {
        if (l.localeId.replaceAll('-', '_').toLowerCase() == want) _sttLocale = l.localeId;
      }
      if (_sttLocale == null) {
        _notice = '${_lang.name} voice typing is not installed on this phone. You can type your answers.';
      }
    } catch (_) {
      _sttReady = false;
      _micDenied = true;
    }
  }

  // ------------------------------------------------------------ dialogue
  Future<void> _apply(Map<String, dynamic> r) async {
    if (_ending) return;
    _stage = '${r['stage'] ?? ''}';
    _expect = '${r['expect'] ?? 'speech'}';
    _fields = Map<String, dynamic>.from(r['fields'] ?? {});
    final say = '${r['say'] ?? ''}'.trim();
    final done = r['done'] == true;
    _set(() {
      _suggest = [for (final s in (r['suggest'] as List? ?? [])) '$s'];
      _dishaLine = say;
      _busy = false;
    });
    if (_expect == 'camera' && !done) _ensureCamera();
    await _speak(say);
    if (_ending || _disposed) return;
    if (done) {
      if (_stage == 'done' && _fields['category'] != null) {
        await _file();
      } else {
        _set(() => _phase = _Phase.ended);
        _clock?.cancel();
      }
      return;
    }
    if (_expect == 'camera') {
      _set(() => _mode = _Mode.scanning);
    } else {
      _set(() => _mode = _Mode.idle);
    }
    _scheduleListen();
  }

  Future<void> _speak(String text) async {
    if (text.isEmpty) return;
    await _stopListening();
    _speakingNow = true;
    _set(() => _mode = _Mode.speaking);
    try {
      if (!_ttsMissing) {
        await _tts.speak(text).timeout(Duration(seconds: 8 + text.length ~/ 6));
      } else {
        await Future.delayed(Duration(milliseconds: 1200 + text.length * 30));
      }
    } catch (_) {}
    _speakingNow = false;
  }

  Future<void> _send(String text) async {
    final t = text.trim();
    if (t.isEmpty || _sessionId == null || _busy || _ending) return;
    _busy = true;
    _restart?.cancel();
    await _stopListening();
    _tts.stop();
    _input.clear();
    _set(() {
      _heard = t.startsWith('__media__') ? _heard : t;
      _mode = _Mode.thinking;
      _suggest = [];
    });
    try {
      final r = await api.callTurn(_sessionId!, t);
      await _apply(r);
    } catch (e) {
      _busy = false;
      if (mounted) toast(context, '$e', error: true);
      _set(() => _mode = _Mode.idle);
      _scheduleListen();
    }
  }

  // ------------------------------------------------------------ speech to text
  void _scheduleListen([int ms = 350]) {
    _restart?.cancel();
    if (_muted || !_sttReady || _ending || _disposed || _phase != _Phase.live) return;
    _restart = Timer(Duration(milliseconds: ms), _startListening);
  }

  Future<void> _startListening() async {
    if (_muted || !_sttReady || _ending || _disposed || _speakingNow || _busy || _phase != _Phase.live) return;
    if (_stt.isListening) return;
    try {
      await _stt.listen(
        onResult: _onResult,
        onSoundLevelChange: (v) {
          final n = ((v + 2) / 12).clamp(0.0, 1.0);
          _level.value = _level.value * 0.6 + n * 0.4;
        },
        listenOptions: SpeechListenOptions(
          partialResults: true,
          cancelOnError: false,
          listenMode: ListenMode.dictation,
          localeId: _sttLocale,
          listenFor: const Duration(seconds: 40),
          pauseFor: const Duration(seconds: 3),
        ),
      );
      _set(() => _mode = _expect == 'camera' ? _Mode.scanning : _Mode.listening);
    } catch (_) {
      _sttFails++;
      if (_sttFails < 4) _scheduleListen(1200);
    }
  }

  Future<void> _stopListening() async {
    _level.value = 0;
    try {
      if (_stt.isListening) await _stt.stop();
    } catch (_) {}
  }

  void _onResult(SpeechRecognitionResult r) {
    if (_busy || _speakingNow) return;
    _sttFails = 0;
    _set(() => _heard = r.recognizedWords);
    if (r.finalResult && r.recognizedWords.trim().isNotEmpty) _send(r.recognizedWords);
  }

  void _onSttStatus(String s) {
    if ((s == 'done' || s == 'notListening') && !_busy && !_speakingNow && _phase == _Phase.live) {
      _level.value = 0;
      _scheduleListen(_sttFails > 0 ? 1000 : 350);
    }
  }

  void _onSttError(SpeechRecognitionError e) {
    _sttFails++;
    final m = e.errorMsg;
    if (m == 'error_permission') {
      _set(() {
        _micDenied = true;
        _sttReady = false;
      });
      return;
    }
    if (_busy || _speakingNow || _phase != _Phase.live) return;
    if (_sttFails <= 8) _scheduleListen(_sttFails > 2 ? 1500 : 600);
  }

  void _toggleMute() {
    HapticFeedback.selectionClick();
    _set(() => _muted = !_muted);
    if (_muted) {
      _restart?.cancel();
      _stopListening();
      _set(() => _mode = _expect == 'camera' ? _Mode.scanning : _Mode.idle);
    } else {
      if (!_sttReady) {
        _setupStt().then((_) {
          _set(() {});
          _scheduleListen();
        });
      } else {
        _scheduleListen();
      }
    }
  }

  // ------------------------------------------------------------ camera
  Future<void> _ensureCamera() async {
    if (_camOn || _camBusy) return;
    await _openCamera(_camIndex);
  }

  Future<void> _openCamera(int index) async {
    if (_camBusy) return;
    _camBusy = true;
    try {
      if (_cams.isEmpty) _cams = await availableCameras();
      if (_cams.isEmpty) throw CameraException('none', 'No camera');
      final back = _cams.indexWhere((c) => c.lensDirection == CameraLensDirection.back);
      _camIndex = index >= 0 && index < _cams.length ? index : (back < 0 ? 0 : back);
      if (index == 0 && back > 0) _camIndex = back;
      final old = _cam;
      final c = CameraController(_cams[_camIndex], ResolutionPreset.medium,
          enableAudio: false, imageFormatGroup: ImageFormatGroup.jpeg);
      await c.initialize();
      old?.dispose();
      _cam = c;
      _set(() {
        _camOn = true;
        _camDenied = false;
      });
    } on CameraException catch (e) {
      _set(() {
        _camOn = false;
        _camDenied = e.code.toLowerCase().contains('access') || e.code.toLowerCase().contains('denied');
        _notice = _camDenied
            ? 'Camera is off for this app. Allow it in Settings, or pick a photo from your gallery.'
            : 'The camera could not start. You can pick a photo from your gallery.';
      });
    } catch (_) {
      _set(() {
        _camOn = false;
        _notice = 'The camera could not start. You can pick a photo from your gallery.';
      });
    } finally {
      _camBusy = false;
    }
  }

  Future<void> _closeCamera() async {
    final c = _cam;
    _cam = null;
    _set(() => _camOn = false);
    await c?.dispose();
  }

  void _toggleCamera() {
    HapticFeedback.selectionClick();
    if (_camOn) {
      _closeCamera();
    } else {
      _openCamera(_camIndex);
    }
  }

  void _flip() {
    if (_cams.length < 2) return toast(context, 'No second camera on this phone.');
    HapticFeedback.selectionClick();
    _openCamera((_camIndex + 1) % _cams.length);
  }

  Future<void> _shutter() async {
    final c = _cam;
    if (c == null || !c.value.isInitialized || c.value.isTakingPicture || _recording) return;
    HapticFeedback.mediumImpact();
    try {
      final f = await c.takePicture();
      _addShot(f, false);
    } catch (_) {
      if (mounted) toast(context, 'Could not take the photo. Try again.', error: true);
    }
  }

  Future<void> _recStart() async {
    final c = _cam;
    if (c == null || !c.value.isInitialized || _recording || c.value.isRecordingVideo) return;
    HapticFeedback.heavyImpact();
    try {
      await c.startVideoRecording();
      _set(() => _recording = true);
      _recTimer = Timer(const Duration(seconds: 8), _recStop);
    } catch (_) {
      if (mounted) toast(context, 'Could not record. Try a photo instead.', error: true);
    }
  }

  Future<void> _recStop() async {
    _recTimer?.cancel();
    final c = _cam;
    if (c == null || !_recording) return;
    _set(() => _recording = false);
    try {
      final f = await c.stopVideoRecording();
      _addShot(f, true);
    } catch (_) {
      if (mounted) toast(context, 'That clip was too short. Hold the button a little longer.', error: true);
    }
  }

  Future<void> _gallery() async {
    try {
      final f = await ImagePicker().pickMedia();
      if (f != null) _addShot(f, Api.isVideo(f));
    } catch (_) {
      if (mounted) toast(context, 'Could not open your gallery. Allow photo access in Settings.', error: true);
    }
  }

  Future<void> _addShot(XFile f, bool video) async {
    final s = _Shot(f, video);
    _set(() {
      _shots.add(s);
      _mode = _Mode.thinking;
      _heard = '';
    });
    await _stopListening();
    try {
      s.result = await api.screen(f, _shots.length - 1);
    } catch (e) {
      s.error = '$e';
    }
    s.checking = false;
    _set(() {});
    if (_expect != 'camera' && _stage != 'ask_media') {
      _set(() => _mode = _Mode.idle);
      return;
    }
    await _send('__media__:${_shots.length}:${s.passed ? 'pass' : 'fail'}');
  }

  // ------------------------------------------------------------ filing
  String _categoryKey() {
    final c = '${_fields['category'] ?? 'other'}';
    const ok = {'pothole', 'crack', 'waterlogging', 'broken_road'};
    return ok.contains(c) ? c : 'other';
  }

  String _description() {
    final d = '${_fields['description'] ?? ''}'.trim();
    if (d.length >= 5) return d;
    final label = '${_fields['issue_label'] ?? _fields['category'] ?? 'road problem'}'.replaceAll('_', ' ');
    final parts = <String>[
      '${_fields['category']}' == 'manhole' ? 'Open manhole reported by voice call with Disha.' : 'Reported by voice call with Disha: $label.',
      if ('${_fields['place'] ?? ''}'.isNotEmpty) 'Place: ${_fields['place']}.',
      if ('${_fields['landmark'] ?? ''}'.isNotEmpty && '${_fields['landmark']}' != 'null') 'Landmark: ${_fields['landmark']}.',
      if ('${_fields['severity'] ?? ''}'.isNotEmpty && '${_fields['severity']}' != 'null') 'Severity: ${_fields['severity']}.',
    ];
    return parts.join(' ');
  }

  Future<void> _file() async {
    _set(() {
      _phase = _Phase.filing;
      _mode = _Mode.thinking;
      _filingError = null;
    });
    try {
      final good = [for (final s in _shots) if (s.passed) s];
      final lat = (_fields['lat'] as num?)?.toDouble() ?? _lat;
      final lon = (_fields['lon'] as num?)?.toDouble() ?? _lon;
      final c = await api.submit(
        category: _categoryKey(),
        description: _description(),
        files: [for (final s in good) s.file],
        screeningTokens: [for (final s in good) ?s.result?.token],
        lat: lat,
        lon: lon,
        address: '${_fields['address'] ?? _fields['place'] ?? ''}',
      );
      HapticFeedback.heavyImpact();
      refreshTick.value++;
      _clock?.cancel();
      await _closeCamera();
      _set(() {
        _ticket = c;
        _phase = _Phase.ticket;
        _mode = _Mode.idle;
      });
    } catch (e) {
      _set(() {
        _filingError = '$e';
        _mode = _Mode.idle;
      });
    }
  }

  Future<void> _end() async {
    if (_ending) return;
    _ending = true;
    HapticFeedback.mediumImpact();
    _clock?.cancel();
    _restart?.cancel();
    await _stopListening();
    try {
      await _tts.stop();
    } catch (_) {}
    await _closeCamera();
    if (mounted) Navigator.of(context).maybePop();
  }

  // ------------------------------------------------------------ UI
  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _phase == _Phase.pick || _phase == _Phase.ticket || _phase == _Phase.ended || _ending,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _end();
      },
      child: Scaffold(
        resizeToAvoidBottomInset: true,
        backgroundColor: _bgTop,
        body: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [_bgTop, _bgBottom]),
          ),
          child: SafeArea(
            child: switch (_phase) {
              _Phase.pick => _pickView(),
              _Phase.connecting => _connectingView(),
              _Phase.ticket => _ticketView(),
              _Phase.ended => _endedView(),
              _ => _liveView(),
            },
          ),
        ),
      ),
    );
  }

  TextStyle _mono(double size, {Color? color, double spacing = 2}) =>
      TextStyle(fontFamily: 'monospace', fontSize: size, letterSpacing: spacing, color: color ?? _sage, fontWeight: FontWeight.w600);

  TextStyle _text(double size, {Color? color, FontWeight w = FontWeight.w500, double? h}) =>
      TextStyle(fontFamily: 'Barlow', fontSize: size, color: color ?? _ivory, fontWeight: w, height: h);

  Widget _orb(double size) {
    final reduce = MediaQuery.of(context).disableAnimations;
    return RepaintBoundary(
      child: SizedBox(
        width: size,
        height: size,
        child: CustomPaint(
          painter: _OrbPainter(
            time: _anim,
            level: _level,
            mode: _mode,
            reduce: reduce,
          ),
        ),
      ),
    );
  }

  String get _modeLabel => switch (_mode) {
        _Mode.listening => 'LISTENING',
        _Mode.thinking => 'THINKING',
        _Mode.speaking => 'SPEAKING',
        _Mode.scanning => 'SCANNING ROAD',
        _Mode.idle => _muted ? 'MUTED' : 'ON CALL',
      };

  Widget _pickView() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
      child: Column(children: [
        Align(
          alignment: Alignment.centerLeft,
          child: IconButton(
            onPressed: () => Navigator.of(context).maybePop(),
            icon: const Icon(Icons.close_rounded, color: _ivory),
            tooltip: 'Close',
          ),
        ),
        const Spacer(),
        _orb(200),
        const SizedBox(height: 20),
        Text('DISHA', style: _mono(12, spacing: 6)),
        const SizedBox(height: 8),
        Text('Talk to Disha', style: _text(30, w: FontWeight.w700)),
        const SizedBox(height: 6),
        Text('Pick your language. Disha will ask a few questions and file the complaint for you.',
            textAlign: TextAlign.center, style: _text(15, color: _ivory.withValues(alpha: 0.7), h: 1.35)),
        if (_notice != null) ...[
          const SizedBox(height: 10),
          Text(_notice!, textAlign: TextAlign.center, style: _text(13, color: _peach)),
        ],
        const Spacer(),
        GridView.count(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisCount: 2,
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
          childAspectRatio: 2.3,
          children: [
            for (final l in _langs)
              Pressable(
                onTap: () => _connect(l),
                child: Container(
                  decoration: BoxDecoration(
                    color: _charcoal.withValues(alpha: 0.55),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: _sage.withValues(alpha: 0.35)),
                  ),
                  alignment: Alignment.center,
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(l.native, style: _text(20, w: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(l.locale.toUpperCase(), style: _mono(10, spacing: 1.5)),
                  ]),
                ),
              ),
          ],
        ),
        const SizedBox(height: 14),
        Text('Microphone, camera and location are used only during the call.',
            textAlign: TextAlign.center, style: _text(12, color: _ivory.withValues(alpha: 0.5))),
      ]),
    );
  }

  Widget _connectingView() => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          _orb(220),
          const SizedBox(height: 18),
          Text('CONNECTING', style: _mono(12, spacing: 5)),
          const SizedBox(height: 8),
          Text('Finding your location', style: _text(15, color: _ivory.withValues(alpha: 0.65))),
        ]),
      );

  Widget _topBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Row(children: [
        ValueListenableBuilder<int>(
          valueListenable: _secs,
          builder: (_, s, _) => Text(
              '${(s ~/ 60).toString().padLeft(2, '0')}:${(s % 60).toString().padLeft(2, '0')}',
              style: _mono(13, color: _ivory, spacing: 1.5)),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Align(
            alignment: Alignment.centerLeft,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: _charcoal.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: (_placeText == null ? _peach : _sage).withValues(alpha: 0.4)),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(_placeText == null ? Icons.location_off_rounded : Icons.place_rounded,
                    size: 14, color: _placeText == null ? _peach : _sage),
                const SizedBox(width: 5),
                Flexible(
                  child: Text(_placeText ?? 'No location',
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: _text(12, color: _ivory)),
                ),
              ]),
            ),
          ),
        ),
        Text(_lang.locale, style: _mono(11)),
      ]),
    );
  }

  Widget _liveView() {
    final scanning = _camOn && (_expect == 'camera');
    return Column(children: [
      _topBar(),
      if (_notice != null || _micDenied)
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Text(
            _micDenied
                ? 'Microphone is off for this app. Allow it in Settings to talk, or type your answers below.'
                : _notice!,
            textAlign: TextAlign.center,
            style: _text(12, color: _peach),
          ),
        ),
      Expanded(child: scanning ? _scanArea() : _orbArea()),
      if (_shots.isNotEmpty) _thumbs(),
      _captions(),
      _chips(),
      _textBar(),
      _controls(),
    ]);
  }

  Widget _orbArea() {
    return LayoutBuilder(builder: (context, box) {
      final size = math.min(math.min(box.maxWidth, box.maxHeight) - 8, 320.0);
      return Stack(alignment: Alignment.center, children: [
        Center(child: _orb(size < 120 ? 120 : size)),
        Positioned(
          bottom: 4,
          child: Text(_modeLabel, style: _mono(11, spacing: 4)),
        ),
        if (_camOn && _cam != null && _cam!.value.isInitialized)
          Positioned(top: 8, right: 16, child: _pip()),
      ]);
    });
  }

  Widget _pip() => ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: Container(
          width: 84,
          height: 112,
          decoration: BoxDecoration(border: Border.all(color: _sage.withValues(alpha: 0.5)), borderRadius: BorderRadius.circular(14)),
          child: _previewFill(),
        ),
      );

  Widget _previewFill() {
    final c = _cam;
    if (c == null || !c.value.isInitialized) return const ColoredBox(color: Colors.black);
    final ps = c.value.previewSize;
    if (ps == null) return CameraPreview(c);
    return ClipRect(
      child: FittedBox(
        fit: BoxFit.cover,
        child: SizedBox(width: ps.height, height: ps.width, child: CameraPreview(c)),
      ),
    );
  }

  Widget _scanArea() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: Stack(fit: StackFit.expand, children: [
          _previewFill(),
          IgnorePointer(child: CustomPaint(painter: _BracketPainter(_recording ? _terracotta : _sage))),
          Positioned(top: 10, left: 10, child: _orb(84)),
          Positioned(
            top: 14,
            right: 14,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(12)),
              child: Text(_recording ? 'RECORDING' : (_mode == _Mode.thinking ? 'CHECKING' : 'SCANNING ROAD'),
                  style: _mono(10, color: _recording ? _terracotta : _sage, spacing: 2)),
            ),
          ),
          Positioned(left: 0, right: 0, bottom: 14, child: _captureBar()),
        ]),
      ),
    );
  }

  Widget _captureBar() {
    final busy = _mode == _Mode.thinking;
    return Row(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.center, children: [
      _roundBtn(Icons.photo_library_rounded, 'Gallery', _gallery, size: 48, bg: Colors.black54),
      const SizedBox(width: 22),
      Semantics(
        button: true,
        label: 'Take photo',
        child: GestureDetector(
          onTap: busy ? null : _shutter,
          child: Container(
            width: 76,
            height: 76,
            decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: _ivory, width: 4)),
            padding: const EdgeInsets.all(6),
            child: Container(decoration: BoxDecoration(shape: BoxShape.circle, color: busy ? Colors.white38 : _ivory)),
          ),
        ),
      ),
      const SizedBox(width: 22),
      Semantics(
        button: true,
        label: 'Hold to record a short clip',
        child: GestureDetector(
          onLongPressStart: busy ? null : (_) => _recStart(),
          onLongPressEnd: (_) => _recStop(),
          onTap: () => toast(context, 'Hold this button to record a short clip.'),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            width: 48,
            height: 48,
            decoration: BoxDecoration(shape: BoxShape.circle, color: _recording ? _terracotta : Colors.black54),
            child: Icon(Icons.videocam_rounded, color: _ivory, size: _recording ? 28 : 24),
          ),
        ),
      ),
    ]);
  }

  Widget _thumbs() {
    return SizedBox(
      height: 64,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        itemCount: _shots.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (_, i) {
          final s = _shots[i];
          final color = s.checking ? _peach : (s.passed ? _sage : _terracotta);
          final label = s.checking ? 'CHECKING' : (s.passed ? 'PASS' : (s.result?.rateLimited == true ? 'WAIT' : 'FAIL'));
          return Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: color, width: 1.5),
              color: _charcoal,
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: Stack(fit: StackFit.expand, children: [
                if (s.isVideo)
                  const Center(child: Icon(Icons.play_circle_fill_rounded, color: _ivory, size: 26))
                else
                  FutureBuilder<Uint8List>(
                    future: s.file.readAsBytes(),
                    builder: (_, snap) => snap.hasData
                        ? Image.memory(snap.data!, fit: BoxFit.cover, cacheWidth: 120)
                        : const SizedBox.shrink(),
                  ),
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Container(
                    color: color.withValues(alpha: 0.9),
                    padding: const EdgeInsets.symmetric(vertical: 1),
                    child: Text(label, textAlign: TextAlign.center, style: _mono(8, color: _bgTop, spacing: 0.8)),
                  ),
                ),
              ]),
            ),
          );
        },
      ),
    );
  }

  Widget _captions() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(22, 6, 22, 4),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 150),
        child: SingleChildScrollView(
          reverse: false,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            if (_dishaLine.isNotEmpty)
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 250),
                child: Text(_dishaLine,
                    key: ValueKey(_dishaLine),
                    style: _text(_dishaLine.length > 110 ? 17 : 20, w: FontWeight.w600, h: 1.3)),
              ),
            if (_filingError != null) ...[
              const SizedBox(height: 6),
              Text(_filingError!, style: _text(13, color: _terracotta)),
              const SizedBox(height: 6),
              Pressable(
                onTap: _file,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
                  decoration: BoxDecoration(color: _sage, borderRadius: BorderRadius.circular(18)),
                  child: Text('Try filing again', style: _text(14, color: _bgTop, w: FontWeight.w700)),
                ),
              ),
            ],
            if (_heard.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text('You: $_heard', maxLines: 2, overflow: TextOverflow.ellipsis, style: _text(13, color: _peach)),
            ],
          ]),
        ),
      ),
    );
  }

  Widget _chips() {
    if (_suggest.isEmpty) return const SizedBox(height: 4);
    return SizedBox(
      height: 44,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 5),
        itemCount: _suggest.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (_, i) => Pressable(
          onTap: () => _send(_suggest[i]),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: _sage.withValues(alpha: 0.16),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: _sage.withValues(alpha: 0.55)),
            ),
            child: Text(_suggest[i], style: _text(14, color: _ivory)),
          ),
        ),
      ),
    );
  }

  Widget _textBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 2, 16, 4),
      child: Row(children: [
        Expanded(
          child: TextField(
            controller: _input,
            style: _text(15),
            cursorColor: _sage,
            textInputAction: TextInputAction.send,
            onSubmitted: _send,
            decoration: InputDecoration(
              hintText: 'Type your answer',
              hintStyle: _text(15, color: _ivory.withValues(alpha: 0.4)),
              isDense: true,
              filled: true,
              fillColor: _charcoal.withValues(alpha: 0.5),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(22), borderSide: BorderSide.none),
            ),
          ),
        ),
        const SizedBox(width: 8),
        _roundBtn(Icons.arrow_upward_rounded, 'Send', () => _send(_input.text), size: 44, bg: _sage, fg: _bgTop),
      ]),
    );
  }

  Widget _roundBtn(IconData icon, String label, VoidCallback? onTap,
      {double size = 56, Color? bg, Color fg = _ivory, bool active = false}) {
    return Semantics(
      button: true,
      label: label,
      child: Pressable(
        onTap: onTap,
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: bg ?? (active ? _ivory : _charcoal.withValues(alpha: 0.75)),
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: Icon(icon, color: active ? _bgTop : fg, size: size * 0.45),
        ),
      ),
    );
  }

  Widget _controls() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 14),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
        _roundBtn(_muted ? Icons.mic_off_rounded : Icons.mic_rounded, _muted ? 'Unmute' : 'Mute', _toggleMute, active: _muted),
        _roundBtn(_camOn ? Icons.videocam_rounded : Icons.videocam_off_rounded, _camOn ? 'Camera off' : 'Camera on',
            _toggleCamera, active: _camOn),
        _roundBtn(Icons.cameraswitch_rounded, 'Flip camera', _camOn ? _flip : null),
        _roundBtn(Icons.call_end_rounded, 'End call', _end, size: 64, bg: _terracotta),
      ]),
    );
  }

  Widget _endedView() => Padding(
        padding: const EdgeInsets.all(28),
        child: Column(children: [
          const Spacer(),
          _orb(160),
          const SizedBox(height: 18),
          Text('CALL ENDED', style: _mono(12, spacing: 5)),
          const SizedBox(height: 10),
          Text(_dishaLine, textAlign: TextAlign.center, style: _text(18, h: 1.35)),
          const SizedBox(height: 8),
          Text('No complaint was filed.', style: _text(14, color: _ivory.withValues(alpha: 0.6))),
          const Spacer(),
          _wideBtn('Close', () => Navigator.of(context).maybePop(), _sage),
        ]),
      );

  Widget _wideBtn(String label, VoidCallback onTap, Color color) => Pressable(
        onTap: onTap,
        child: Container(
          height: 52,
          alignment: Alignment.center,
          decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(26)),
          child: Text(label, style: _text(16, color: _bgTop, w: FontWeight.w700)),
        ),
      );

  Widget _ticketView() {
    final c = _ticket!;
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(children: [
        const Spacer(),
        _orb(150),
        const SizedBox(height: 16),
        Text('COMPLAINT REGISTERED', style: _mono(12, spacing: 4)),
        const SizedBox(height: 16),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: _charcoal.withValues(alpha: 0.7),
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: _peach.withValues(alpha: 0.5)),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('TICKET', style: _mono(10, color: _peach, spacing: 3)),
            const SizedBox(height: 4),
            Text(c.ticket, style: _text(34, w: FontWeight.w800)),
            const SizedBox(height: 12),
            Text(categoryLabel(c.category), style: _text(16, w: FontWeight.w600)),
            if ((c.address ?? '').isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(c.address!, style: _text(14, color: _ivory.withValues(alpha: 0.7), h: 1.3)),
            ],
            const SizedBox(height: 10),
            Text('Status: ${c.status.replaceAll('_', ' ')}', style: _text(13, color: _sage)),
          ]),
        ),
        const Spacer(),
        _wideBtn('Done', () => Navigator.of(context).maybePop(), _sage),
      ]),
    );
  }

  static String categoryLabel(String k) => switch (k) {
        'pothole' => 'Pothole',
        'crack' => 'Road cracks',
        'waterlogging' => 'Waterlogging',
        'broken_road' => 'Broken road',
        _ => 'Road problem',
      };

  // filing state overlays the live view
  @override
  void didUpdateWidget(covariant CallScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
  }
}

// ---------------------------------------------------------------- painters

class _OrbPainter extends CustomPainter {
  _OrbPainter({required this.time, required this.level, required this.mode, required this.reduce})
      : super(repaint: Listenable.merge([time, level]));
  final Animation<double> time;
  final ValueNotifier<double> level;
  final _Mode mode;
  final bool reduce;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2;
    final t = reduce ? 0.0 : time.value * 20; // seconds
    final speaking = mode == _Mode.speaking;
    final listening = mode == _Mode.listening;
    final thinking = mode == _Mode.thinking;
    final accent = speaking ? _peach : _sage;
    // simulated sound while Disha speaks
    final amp = reduce
        ? 0.25
        : speaking
            ? 0.35 + 0.25 * (math.sin(t * 7.3) * 0.5 + 0.5) + 0.2 * (math.sin(t * 3.1 + 1) * 0.5 + 0.5)
            : listening
                ? 0.12 + level.value * 0.9
                : thinking
                    ? 0.2 + 0.08 * math.sin(t * 4)
                    : 0.14 + 0.04 * math.sin(t * 1.3);

    // glow
    final glow = Paint()
      ..shader = RadialGradient(colors: [
        accent.withValues(alpha: 0.30 + amp * 0.2),
        _peach.withValues(alpha: 0.06),
        Colors.transparent,
      ], stops: const [0.0, 0.55, 1.0])
          .createShader(Rect.fromCircle(center: c, radius: r));
    canvas.drawCircle(c, r, glow);

    // concentric rings
    for (var i = 0; i < 3; i++) {
      final k = 0.34 + i * 0.1;
      final pulse = reduce ? 0.0 : math.sin(t * 1.6 - i * 0.9) * 0.012 * (1 + amp * 3);
      final p = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.1
        ..color = (i == 1 ? _peach : accent).withValues(alpha: 0.35 - i * 0.08);
      canvas.drawCircle(c, r * (k + pulse), p);
    }

    // HUD arcs
    final arc = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 1.2;
    final rot = reduce ? 0.0 : t * 0.12;
    final rot2 = reduce ? 0.0 : -t * 0.08;
    arc.color = accent.withValues(alpha: 0.55);
    for (var i = 0; i < 3; i++) {
      canvas.drawArc(Rect.fromCircle(center: c, radius: r * 0.86), rot + i * 2.09, 1.2, false, arc);
    }
    arc.color = _ivory.withValues(alpha: 0.25);
    arc.strokeWidth = 0.9;
    for (var i = 0; i < 4; i++) {
      canvas.drawArc(Rect.fromCircle(center: c, radius: r * 0.94), rot2 + i * 1.57, 0.55, false, arc);
    }
    // tick marks
    final tick = Paint()
      ..color = _ivory.withValues(alpha: 0.18)
      ..strokeWidth = 1;
    for (var i = 0; i < 60; i++) {
      final a = i / 60 * math.pi * 2 + rot2 * 0.5;
      final len = i % 5 == 0 ? 0.035 : 0.018;
      canvas.drawLine(c + Offset(math.cos(a), math.sin(a)) * (r * 0.98),
          c + Offset(math.cos(a), math.sin(a)) * (r * (0.98 - len)), tick);
    }

    // radial waveform
    const n = 72;
    final base = r * 0.46;
    final bar = Paint()
      ..strokeCap = StrokeCap.round
      ..strokeWidth = math.max(1.6, r * 0.014);
    for (var i = 0; i < n; i++) {
      final a = i / n * math.pi * 2;
      final wob = reduce
          ? 0.5
          : (math.sin(a * 5 + t * 3.2) * 0.5 + 0.5) * 0.55 + (math.sin(a * 9 - t * 4.4) * 0.5 + 0.5) * 0.45;
      final len = r * (0.025 + 0.2 * amp * wob);
      final p1 = c + Offset(math.cos(a), math.sin(a)) * base;
      final p2 = c + Offset(math.cos(a), math.sin(a)) * (base + len);
      bar.color = Color.lerp(accent, _ivory, wob * 0.5)!.withValues(alpha: 0.85);
      canvas.drawLine(p1, p2, bar);
    }

    // core
    final core = Paint()
      ..shader = RadialGradient(colors: [
        _ivory.withValues(alpha: 0.9),
        accent.withValues(alpha: 0.55),
        accent.withValues(alpha: 0.0),
      ], stops: const [0.0, 0.5, 1.0])
          .createShader(Rect.fromCircle(center: c, radius: r * (0.2 + amp * 0.08)));
    canvas.drawCircle(c, r * (0.2 + amp * 0.08), core);
  }

  @override
  bool shouldRepaint(covariant _OrbPainter old) => old.mode != mode || old.reduce != reduce;
}

class _BracketPainter extends CustomPainter {
  _BracketPainter(this.color);
  final Color color;
  @override
  void paint(Canvas canvas, Size s) {
    final p = Paint()
      ..color = color.withValues(alpha: 0.9)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;
    const m = 36.0, l = 28.0;
    final r = Rect.fromLTRB(m, m * 2.2, s.width - m, s.height - m * 2.6);
    for (final corner in [
      [r.topLeft, const Offset(1, 0), const Offset(0, 1)],
      [r.topRight, const Offset(-1, 0), const Offset(0, 1)],
      [r.bottomLeft, const Offset(1, 0), const Offset(0, -1)],
      [r.bottomRight, const Offset(-1, 0), const Offset(0, -1)],
    ]) {
      final o = corner[0];
      canvas.drawLine(o, o + (corner[1]) * l, p);
      canvas.drawLine(o, o + (corner[2]) * l, p);
    }
  }

  @override
  bool shouldRepaint(covariant _BracketPainter old) => old.color != color;
}
