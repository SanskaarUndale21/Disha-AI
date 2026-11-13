import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:geolocator/geolocator.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../main.dart';
import '../theme.dart';
import '../widgets.dart';

/// Below this speed (m/s, about 7 km/h) frames are skipped: the vehicle is parked or crawling.
const _minSpeed = 2.0;
const _frameEvery = Duration(milliseconds: 1500);

final _notifications = FlutterLocalNotificationsPlugin();
bool _notificationsReady = false;

Future<void> _initNotifications() async {
  if (_notificationsReady) return;
  try {
    await _notifications.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(),
      ),
    );
    await _notifications
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
    _notificationsReady = true;
  } catch (_) {}
}

Future<void> _showRunning(int found) async {
  if (!_notificationsReady) return;
  try {
    await _notifications.show(
      id: 7,
      title: 'RoadWatch Drive Mode is recording',
      body: found == 0 ? 'Scanning the road ahead.' : 'Potholes found this drive: $found',
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          'drive_mode',
          'Drive Mode',
          channelDescription: 'Shown while Drive Mode uses the camera and GPS',
          importance: Importance.low,
          priority: Priority.low,
          ongoing: true,
          autoCancel: false,
          onlyAlertOnce: true,
        ),
      ),
    );
  } catch (_) {}
}

Future<void> _hideRunning() async {
  try {
    await _notifications.cancel(id: 7);
  } catch (_) {}
}

/// Opens Drive Mode after the safety warning has been accepted.
Future<void> openDriveMode(BuildContext context) async {
  final ok = await showCupertinoDialog<bool>(
    context: context,
    builder: (ctx) => CupertinoAlertDialog(
      title: const Text('Do not use the phone while driving'),
      content: const Padding(
        padding: EdgeInsets.only(top: 8),
        child: Text('Mount the phone on the dashboard with the camera facing the road before you start. '
            'Drive Mode works on its own. Never touch the phone while the vehicle is moving.'),
      ),
      actions: [
        CupertinoDialogAction(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
        CupertinoDialogAction(
            isDefaultAction: true, onPressed: () => Navigator.pop(ctx, true), child: const Text('Phone is mounted')),
      ],
    ),
  );
  if (ok == true && context.mounted) {
    await Navigator.of(context).push(CupertinoPageRoute(fullscreenDialog: true, builder: (_) => const DriveScreen()));
  }
}

class DriveScreen extends StatefulWidget {
  const DriveScreen({super.key});
  @override
  State<DriveScreen> createState() => _DriveScreenState();
}

class _DriveScreenState extends State<DriveScreen> {
  CameraController? _cam;
  StreamSubscription<Position>? _gps;
  Position? _pos;
  Timer? _timer;
  String? _session;
  bool _busy = false;
  bool _starting = true;
  bool _stopping = false;
  bool _testParked = false;
  String? _error;
  int _found = 0;
  int _frames = 0;
  String? _banner;
  Timer? _bannerTimer;
  String _status = 'Starting camera and GPS...';

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _bannerTimer?.cancel();
    _gps?.cancel();
    _cam?.dispose();
    WakelockPlus.disable();
    _hideRunning();
    super.dispose();
  }

  Future<void> _start() async {
    try {
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
        throw 'Drive Mode needs location access to place each pothole. Allow it in Settings.';
      }
      final cams = await availableCameras();
      final back = cams.firstWhere((c) => c.lensDirection == CameraLensDirection.back, orElse: () => cams.first);
      final cam = CameraController(back, ResolutionPreset.high, enableAudio: false, imageFormatGroup: ImageFormatGroup.jpeg);
      await cam.initialize();
      await cam.setFlashMode(FlashMode.off);
      _cam = cam;
      _gps = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.bestForNavigation, distanceFilter: 0),
      ).listen((p) => _pos = p);
      _session = await api.driveStart();
      await WakelockPlus.enable();
      await _initNotifications();
      await _showRunning(0);
      _timer = Timer.periodic(_frameEvery, (_) => _tick());
      if (mounted) setState(() => (_starting = false, _status = 'Waiting for the vehicle to move'));
    } catch (e) {
      if (mounted) setState(() => (_starting = false, _error = '$e'));
    }
  }

  Future<void> _tick() async {
    final cam = _cam, session = _session;
    if (_busy || _stopping || cam == null || session == null || !cam.value.isInitialized) return;
    final p = _pos;
    final speed = (p?.speed ?? 0) < 0 ? 0.0 : (p?.speed ?? 0);
    if (!_testParked && speed < _minSpeed) {
      if (mounted) setState(() => _status = 'Paused, the vehicle is not moving');
      return;
    }
    _busy = true;
    try {
      final shot = await cam.takePicture();
      final at = DateTime.now();
      final bytes = await shot.readAsBytes();
      final r = await api.driveFrame(session, bytes,
          lat: p?.latitude,
          lon: p?.longitude,
          accuracy: p?.accuracy,
          heading: p?.heading,
          speed: p?.speed,
          capturedAt: at);
      _frames++;
      final count = (r['canonical_count'] as num?)?.toInt() ?? _found;
      final fresh = [for (final d in (r['defects'] as List? ?? [])) if (d['new'] == true) d];
      if (fresh.isNotEmpty) {
        SystemSound.play(SystemSoundType.alert);
        HapticFeedback.heavyImpact();
        final name = '${fresh.first['class'] ?? 'pothole'}'.replaceAll('_', ' ');
        _showBanner('New ${name.toLowerCase()} found and pinned on the map');
      }
      if (count != _found) _showRunning(count);
      if (mounted) {
        setState(() {
          _found = count;
          _status = r['reason'] is String ? 'Skipped: ${r['reason']}' : 'Scanning the road ahead';
        });
      }
    } catch (e) {
      if (mounted) setState(() => _status = 'Frame not sent, retrying');
    } finally {
      _busy = false;
    }
  }

  void _showBanner(String text) {
    _bannerTimer?.cancel();
    setState(() => _banner = text);
    _bannerTimer = Timer(const Duration(seconds: 3), () => mounted ? setState(() => _banner = null) : null);
  }

  Future<void> _stop() async {
    if (_stopping) return;
    setState(() => _stopping = true);
    _timer?.cancel();
    Map<String, dynamic>? summary;
    try {
      if (_session != null) summary = await api.driveStop(_session!);
    } catch (_) {}
    await _hideRunning();
    await WakelockPlus.disable();
    if (!mounted) return;
    if (summary != null) {
      await showCupertinoDialog<void>(
        context: context,
        builder: (ctx) => CupertinoAlertDialog(
          title: const Text('Drive finished'),
          content: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text('Potholes found: ${summary!['unique_defects'] ?? _found}\n'
                'Distance: ${summary['distance_km'] ?? 0} km\n'
                'Frames checked: ${summary['frames'] ?? _frames}'),
          ),
          actions: [
            CupertinoDialogAction(isDefaultAction: true, onPressed: () => Navigator.pop(ctx), child: const Text('Done'))
          ],
        ),
      );
    }
    refreshTick.value++;
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final cam = _cam;
    final speedKmh = ((_pos?.speed ?? 0).clamp(0, 100) * 3.6).round();
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(fit: StackFit.expand, children: [
        if (cam != null && cam.value.isInitialized)
          FittedBox(
            fit: BoxFit.cover,
            child: SizedBox(
              width: cam.value.previewSize?.height ?? 1080,
              height: cam.value.previewSize?.width ?? 1920,
              child: CameraPreview(cam),
            ),
          )
        else
          Center(
            child: _error != null
                ? Padding(
                    padding: const EdgeInsets.all(32),
                    child: Text(_error!,
                        textAlign: TextAlign.center, style: const TextStyle(color: Colors.white, fontSize: 16)),
                  )
                : const CupertinoActivityIndicator(color: Colors.white),
          ),
        // top bar
        Positioned(
          left: 16,
          right: 16,
          top: MediaQuery.paddingOf(context).top + 10,
          child: Row(children: [
            Glass(
              radius: 99,
              opacity: 0.55,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                        color: _session != null && !_stopping ? AppColors.red : AppColors.of(context).textTertiary,
                        shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 7),
                  Text(_session != null && !_stopping ? 'Recording' : (_starting ? 'Starting' : 'Stopped'),
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5)),
                ]),
              ),
            ),
            const Spacer(),
            Glass(
              radius: 99,
              opacity: 0.55,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                child: Text('$speedKmh km/h', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5)),
              ),
            ),
          ]),
        ),
        if (_banner != null)
          Positioned(
            left: 16,
            right: 16,
            top: MediaQuery.paddingOf(context).top + 64,
            child: Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: AppColors.orange, borderRadius: BorderRadius.circular(16)),
              child: Row(children: [
                const Icon(CupertinoIcons.exclamationmark_triangle_fill, color: Colors.white),
                const SizedBox(width: 10),
                Expanded(
                    child: Text(_banner!,
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 15.5))),
              ]),
            ),
          ),
        // bottom panel
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: Glass(
            opacity: 0.82,
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 14),
                child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                    Text('$_found',
                        style: const TextStyle(fontSize: 54, fontWeight: FontWeight.w800, letterSpacing: -2, height: 1)),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Text('Potholes found this drive', style: T.headline(context)),
                      ),
                    ),
                  ]),
                  const SizedBox(height: 4),
                  Text(_status, style: T.sub(context)),
                  Row(children: [
                    Expanded(child: Text('Test while parked', style: T.sub(context).copyWith(fontSize: 13))),
                    CupertinoSwitch(value: _testParked, onChanged: (v) => setState(() => _testParked = v)),
                  ]),
                  const SizedBox(height: 6),
                  Pressable(
                    onTap: _stopping ? null : (_session == null ? () => Navigator.pop(context) : _stop),
                    child: Container(
                      height: 54,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(color: AppColors.red, borderRadius: BorderRadius.circular(16)),
                      child: _stopping
                          ? const CupertinoActivityIndicator(color: Colors.white)
                          : Text(_session == null ? 'Close' : 'Stop drive',
                              style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w700)),
                    ),
                  ),
                ]),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

/// Past drives for this device, from the server.
class DriveHistoryScreen extends StatefulWidget {
  const DriveHistoryScreen({super.key});
  @override
  State<DriveHistoryScreen> createState() => _DriveHistoryScreenState();
}

class _DriveHistoryScreenState extends State<DriveHistoryScreen> {
  List<Map<String, dynamic>>? _items;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await api.driveSessions();
      if (mounted) setState(() => (_items = r, _error = null));
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = _items ?? [];
    return Scaffold(
      appBar: AppBar(title: const Text('Drive history'), backgroundColor: AppColors.of(context).bg),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 40),
          children: [
            if (_items == null && _error == null)
              const Padding(padding: EdgeInsets.all(40), child: CupertinoActivityIndicator())
            else if (_error != null && items.isEmpty)
              Padding(padding: const EdgeInsets.all(30), child: Text(_error!, style: T.sub(context)))
            else if (items.isEmpty)
              Padding(
                padding: const EdgeInsets.all(30),
                child: Text('No drives yet. Start Drive Mode from Home.',
                    textAlign: TextAlign.center, style: T.sub(context)),
              )
            else
              for (final d in items)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: CardBox(
                    child: Row(children: [
                      const IconBadge(CupertinoIcons.car_detailed, AppColors.indigo, size: 42),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('${d['unique_defects'] ?? 0} potholes, ${d['distance_km'] ?? 0} km',
                              style: T.headline(context)),
                          const SizedBox(height: 2),
                          Text(
                            '${d['started_at'] != null ? timeAgo(DateTime.parse('${d['started_at']}Z').toLocal()) : ''}'
                            ', ${d['duration_min'] ?? 0} min, ${d['frames'] ?? 0} frames'
                            '${d['active'] == true ? ', still running' : ''}',
                            style: T.sub(context),
                          ),
                        ]),
                      ),
                    ]),
                  ),
                ),
          ],
        ),
      ),
    );
  }
}
