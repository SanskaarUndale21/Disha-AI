import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'main.dart' show api, locator;
import 'theme.dart';

enum NotifKind { emergency, complaint, repair, severe, route }

class AppNotification {
  final int id;
  final NotifKind kind;
  final String title, body;
  final DateTime at;
  final bool read;
  const AppNotification(this.id, this.kind, this.title, this.body, this.at, {this.read = false});

  AppNotification asRead() => AppNotification(id, kind, title, body, at, read: true);

  Map<String, dynamic> toJson() =>
      {'id': id, 'k': kind.name, 't': title, 'b': body, 'at': at.toIso8601String(), 'r': read};

  static AppNotification? fromJson(Object? j) {
    try {
      final m = j as Map;
      return AppNotification(m['id'] as int, NotifKind.values.byName('${m['k']}'), '${m['t']}', '${m['b']}',
          DateTime.parse('${m['at']}'),
          read: m['r'] == true);
    } catch (_) {
      return null;
    }
  }
}

const _nearKm = 3.0;

double distanceKm(double lat1, double lon1, double lat2, double lon2) {
  const r = 6371.0;
  double rad(double d) => d * math.pi / 180;
  final a = math.pow(math.sin(rad(lat2 - lat1) / 2), 2) +
      math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.pow(math.sin(rad(lon2 - lon1) / 2), 2);
  return 2 * r * math.asin(math.sqrt(a));
}

/// In-app notification centre plus system notifications for emergencies, report updates and nearby road damage.
class NotificationService extends ChangeNotifier {
  final _plugin = FlutterLocalNotificationsPlugin();
  SharedPreferences? _sp;
  bool _ready = false;
  final List<AppNotification> items = [];
  final Set<String> _seen = {};
  Map<String, String>? _statuses;
  Timer? _poll;

  /// Set while an emergency banner should be visible in the app.
  final emergencyBanner = ValueNotifier<AppNotification?>(null);
  double? emergencyLat, emergencyLon;

  /// False when the user (or the system) blocked notifications; the UI shows a hint.
  final permissionGranted = ValueNotifier<bool>(true);

  bool get emergencyOn => _sp?.getBool('n_emergency') ?? true;
  bool get nearbyOn => _sp?.getBool('n_nearby') ?? true;
  bool get mineOn => _sp?.getBool('n_mine') ?? true;
  int get unread => items.where((n) => !n.read).length;

  Future<void> setEmergency(bool v) async {
    await _sp?.setBool('n_emergency', v);
    notifyListeners();
  }

  Future<void> setNearby(bool v) async {
    await _sp?.setBool('n_nearby', v);
    notifyListeners();
  }

  Future<void> setMine(bool v) async {
    await _sp?.setBool('n_mine', v);
    notifyListeners();
  }

  static final _alarmVibration = Int64List.fromList([0, 900, 300, 900, 300, 900, 300, 1200]);
  static const _alarmSound = UriAndroidNotificationSound('content://settings/system/alarm_alert');

  Future<void> init() async {
    try {
      _sp = await SharedPreferences.getInstance();
      for (final j in (jsonDecode(_sp!.getString('n_inbox') ?? '[]') as List)) {
        final n = AppNotification.fromJson(j);
        if (n != null) items.add(n);
      }
    } catch (_) {}
    if (!kIsWeb) {
      try {
        await _plugin.initialize(
          settings: const InitializationSettings(
            android: AndroidInitializationSettings('@mipmap/ic_launcher'),
            iOS: DarwinInitializationSettings(),
          ),
        );
        final android = _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
        await android?.createNotificationChannel(AndroidNotificationChannel(
          'emergency',
          'Emergency alerts',
          description: 'Loud alarm when a fall or accident is detected on the road',
          importance: Importance.max,
          playSound: true,
          sound: _alarmSound,
          audioAttributesUsage: AudioAttributesUsage.alarm,
          enableVibration: true,
          vibrationPattern: _alarmVibration,
          enableLights: true,
        ));
        await android?.createNotificationChannel(const AndroidNotificationChannel(
          'updates',
          'Report and road updates',
          description: 'Status of your reports, repairs and new damage near you',
          importance: Importance.high,
        ));
        final ok = await android?.requestNotificationsPermission();
        if (ok == false) permissionGranted.value = false;
        _ready = true;
      } catch (_) {}
    }
    notifyListeners();
  }

  /// Asks again (used from Profile when permission was refused earlier).
  Future<void> requestPermission() async {
    try {
      final android = _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
      final ok = await android?.requestNotificationsPermission();
      permissionGranted.value = ok != false;
    } catch (_) {}
  }

  /// Polls the user's own complaints as a fallback when the live socket misses a status change.
  void startPolling() {
    _poll?.cancel();
    _poll = Timer.periodic(const Duration(seconds: 90), (_) => checkComplaints());
    checkComplaints();
  }

  Future<void> checkComplaints() async {
    try {
      final list = await api.myComplaints();
      final now = {for (final c in list) c.ticket: c.status};
      final before = _statuses;
      _statuses = now;
      if (before == null || !mineOn) return;
      for (final c in list) {
        final old = before[c.ticket];
        if (old != null && old != c.status) _complaintChanged(c.ticket, c.status, c.adminNote);
      }
    } catch (_) {}
  }

  void _complaintChanged(String ticket, String status, String? note) {
    if (!_seen.add('c:$ticket:$status')) return;
    _statuses?[ticket] = status;
    final label = statusStyle(status).label.toLowerCase();
    add(NotifKind.complaint, 'Report $ticket is now $label',
        (note != null && note.isNotEmpty) ? note : 'Status updated by the city',
        show: true);
  }

  Future<(double, double)?> _here() async {
    final s = locator.spot;
    if (s != null) return (s.lat, s.lon);
    if (kIsWeb) return null;
    try {
      final p = await Geolocator.getLastKnownPosition();
      if (p != null) return (p.latitude, p.longitude);
    } catch (_) {}
    return null;
  }

  Future<void> handleEvent(String type, Map<String, dynamic> d) async {
    switch (type) {
      case 'complaint.updated':
        if (!mineOn) return;
        _complaintChanged('${d['ticket'] ?? d['id']}', '${d['status'] ?? ''}', d['admin_note'] as String?);
      case 'emergency.fall':
        if (!emergencyOn) return;
        if (!_seen.add('e:${d['id']}')) return;
        var msg = '${d['message'] ?? 'A person may be down on the road.'}';
        final h = await _here();
        final lat = (d['lat'] as num?)?.toDouble(), lon = (d['lon'] as num?)?.toDouble();
        if (h != null && lat != null && lon != null) {
          msg += ' About ${_dist(distanceKm(h.$1, h.$2, lat, lon))} from you.';
        }
        emergencyLat = lat;
        emergencyLon = lon;
        emergencyBanner.value = add(NotifKind.emergency, 'Emergency: fall detected', msg, show: true);
      case 'map.repair':
        if (!nearbyOn) return;
        if (!_seen.add('r:${d['uid'] ?? d['number']}')) return;
        final km = await _km(d);
        if (km == null || km > _nearKm) return;
        add(NotifKind.repair, 'Road repaired near you', 'Defect #${d['number'] ?? ''} was fixed ${_dist(km)} away.',
            show: true);
      case 'map.defect':
        if (!nearbyOn || d['new'] != true) return;
        final sev = '${d['severity'] ?? ''}'.toLowerCase();
        if (!{'severe', 'high', 'critical', 'serious'}.contains(sev)) return;
        if (!_seen.add('d:${d['uid'] ?? d['number']}')) return;
        final km = await _km(d);
        if (km == null || km > _nearKm) return;
        final cls = '${d['class'] ?? 'damage'}'.replaceAll('_', ' ');
        add(NotifKind.severe, 'Severe road damage near you', 'A new $cls was reported ${_dist(km)} away. Drive carefully.',
            show: true);
    }
  }

  Future<double?> _km(Map<String, dynamic> d) async {
    final lat = (d['lat'] as num?)?.toDouble(), lon = (d['lon'] as num?)?.toDouble();
    final h = await _here();
    if (lat == null || lon == null || h == null) return null;
    return distanceKm(h.$1, h.$2, lat, lon);
  }

  static String _dist(double km) => km < 1 ? '${(km * 1000).round()} m' : '${km.toStringAsFixed(1)} km';

  void routeChanged(String body) => add(NotifKind.route, 'Your planned route changed', body, show: true);

  AppNotification add(NotifKind kind, String title, String body, {bool show = false}) {
    final n = AppNotification(DateTime.now().microsecondsSinceEpoch & 0x3fffffff, kind, title, body, DateTime.now());
    items.insert(0, n);
    if (items.length > 100) items.removeRange(100, items.length);
    _save();
    notifyListeners();
    if (show) _system(n);
    return n;
  }

  Future<void> _system(AppNotification n) async {
    if (!_ready) return;
    final emergency = n.kind == NotifKind.emergency;
    try {
      await _plugin.show(
        id: n.id,
        title: n.title,
        body: n.body,
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails(
            emergency ? 'emergency' : 'updates',
            emergency ? 'Emergency alerts' : 'Report and road updates',
            importance: emergency ? Importance.max : Importance.high,
            priority: Priority.max,
            category: emergency ? AndroidNotificationCategory.alarm : AndroidNotificationCategory.status,
            fullScreenIntent: emergency,
            playSound: true,
            sound: emergency ? _alarmSound : null,
            audioAttributesUsage: emergency ? AudioAttributesUsage.alarm : AudioAttributesUsage.notification,
            enableVibration: true,
            vibrationPattern: emergency ? _alarmVibration : null,
            styleInformation: BigTextStyleInformation(n.body),
            color: emergency ? AppColors.red : AppColors.blue,
          ),
          iOS: DarwinNotificationDetails(
              presentSound: true, interruptionLevel: emergency ? InterruptionLevel.critical : InterruptionLevel.active),
        ),
      );
    } catch (_) {}
  }

  void markRead(int id) {
    final i = items.indexWhere((n) => n.id == id);
    if (i < 0 || items[i].read) return;
    items[i] = items[i].asRead();
    _save();
    notifyListeners();
  }

  void markAllRead() {
    for (var i = 0; i < items.length; i++) {
      items[i] = items[i].asRead();
    }
    _save();
    notifyListeners();
  }

  void remove(int id) {
    items.removeWhere((n) => n.id == id);
    _save();
    notifyListeners();
  }

  void clear() {
    items.clear();
    _save();
    notifyListeners();
  }

  void dismissBanner() => emergencyBanner.value = null;

  void _save() {
    try {
      _sp?.setString('n_inbox', jsonEncode([for (final n in items) n.toJson()]));
    } catch (_) {}
  }
}

final notifs = NotificationService();
