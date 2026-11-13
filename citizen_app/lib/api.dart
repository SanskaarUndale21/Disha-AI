import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart' show Supabase;
import 'package:uuid/uuid.dart';

import 'discovery.dart';

const defaultHelpline = '+918064270577';

/// Local settings: backend URL, citizen profile, device id.
class Prefs extends ChangeNotifier {
  Prefs._(this._p);
  final SharedPreferences _p;

  static Future<Prefs> load() async {
    final p = Prefs._(await SharedPreferences.getInstance());
    if (p._p.getString('device_id') == null) await p._p.setString('device_id', const Uuid().v4());
    return p;
  }

  static const _envServer = String.fromEnvironment('SERVER');

  static String get defaultServerUrl => _defaultServer;

  static String get _defaultServer {
    if (_envServer.isNotEmpty) return _envServer;
    if (kIsWeb) return 'http://127.0.0.1:8000';
    if (defaultTargetPlatform == TargetPlatform.android) return 'http://10.0.2.2:8000';
    return 'http://127.0.0.1:8000';
  }

  String get server => (_p.getString('server') ?? _defaultServer).replaceAll(RegExp(r'/+$'), '');
  String get name => _p.getString('name') ?? '';
  String get phone => _p.getString('phone') ?? '';
  String get helpline => _p.getString('helpline') ?? defaultHelpline;
  String get deviceId => _p.getString('device_id')!;
  String get supabaseUrl => _p.getString('sb_url') ?? '';
  String get supabaseKey => _p.getString('sb_key') ?? '';
  bool get authRequired => _p.getBool('auth_required') ?? false;
  bool get skippedAuth => _p.getBool('skipped_auth') ?? false;

  Future<void> setAuthConfig(String url, String key, bool required) async {
    await _p.setString('sb_url', url);
    await _p.setString('sb_key', key);
    await _p.setBool('auth_required', required);
  }

  Future<void> setSkippedAuth(bool v) async {
    await _p.setBool('skipped_auth', v);
    notifyListeners();
  }

  Future<void> save({String? server, String? name, String? phone, String? helpline}) async {
    if (server != null) await _p.setString('server', server.trim());
    if (name != null) await _p.setString('name', name.trim());
    if (phone != null) await _p.setString('phone', phone.trim());
    if (helpline != null && helpline.isNotEmpty) await _p.setString('helpline', helpline.trim());
    notifyListeners();
  }
}

class Finding {
  final String className, severity;
  final String? riskLevel, defectUid, cropUrl;
  final double confidence;
  Finding.fromJson(Map<String, dynamic> j)
      : className = j['class_name'] ?? 'unknown',
        severity = j['severity'] ?? '',
        riskLevel = j['risk_level'],
        defectUid = j['defect_uid'],
        cropUrl = j['crop_url'],
        confidence = (j['confidence'] ?? 0).toDouble();

  String get label => className.replaceAll('_', ' ');
}

class MediaItem {
  final String mediaType, status;
  final String? mediaUrl, annotatedUrl;
  final double progress;
  MediaItem.fromJson(Map<String, dynamic> j)
      : mediaType = j['media_type'] ?? 'image',
        status = j['status'] ?? 'stored',
        mediaUrl = j['media_url'],
        annotatedUrl = j['annotated_url'],
        progress = (j['progress'] ?? 0).toDouble();
  bool get isVideo => mediaType == 'video';
  bool get processing => status == 'running' || status == 'processing';
}

class Complaint {
  final int id;
  final String ticket, category, description, status;
  final String? address, adminNote, citizenName;
  final double? lat, lon;
  final DateTime createdAt, updatedAt;
  final List<MediaItem> media;
  final List<Finding> findings;

  Complaint.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        ticket = j['ticket'] ?? '#${j['id']}',
        category = j['category'] ?? 'other',
        description = j['description'] ?? '',
        status = j['status'] ?? 'submitted',
        address = j['address'],
        adminNote = j['admin_note'],
        citizenName = j['citizen_name'],
        lat = (j['lat'] as num?)?.toDouble(),
        lon = (j['lon'] as num?)?.toDouble(),
        createdAt = DateTime.parse('${j['created_at']}Z').toLocal(),
        updatedAt = DateTime.parse('${j['updated_at'] ?? j['created_at']}Z').toLocal(),
        media = [for (final m in (j['media'] as List? ?? [])) MediaItem.fromJson(m)],
        findings = [for (final f in (j['findings'] as List? ?? [])) Finding.fromJson(f)];
}

/// Result of the AI pre-check that every photo or video must pass before a report can be sent.
class ScreenResult {
  final String verdict, reason, mediaType;
  final String? token, previewUrl, warning;
  final DateTime? blockedUntil;
  final double maxConfidence;
  final List<Map<String, dynamic>> damage;

  ScreenResult.fromJson(Map<String, dynamic> j)
      : verdict = '${j['verdict'] ?? 'fail'}',
        reason = '${j['reason'] ?? ''}',
        mediaType = '${j['media_type'] ?? 'image'}',
        token = j['token'] as String?,
        previewUrl = j['preview_url'] as String?,
        warning = (j['warning'] as String?)?.trim().isEmpty == true ? null : j['warning'] as String?,
        blockedUntil = j['blocked_until'] == null ? null : DateTime.tryParse('${j['blocked_until']}')?.toLocal(),
        maxConfidence = ((j['max_confidence'] ?? 0) as num).toDouble(),
        damage = [for (final d in (j['damage'] as List? ?? [])) Map<String, dynamic>.from(d)];

  bool get passed => verdict == 'pass';
  bool get rateLimited => verdict == 'rate_limited';

  /// e.g. "Pothole found, 82% sure"
  String get headline {
    if (!passed || damage.isEmpty) return reason;
    final top = damage.reduce((a, b) => ((a['confidence'] ?? 0) as num) >= ((b['confidence'] ?? 0) as num) ? a : b);
    final name = '${top['class'] ?? 'damage'}'.replaceAll('_', ' ');
    final pct = (((top['confidence'] ?? maxConfidence) as num) * 100).round();
    final more = damage.length > 1 ? ' and ${damage.length - 1} more' : '';
    return '${name[0].toUpperCase()}${name.substring(1)} found, $pct% sure$more';
  }
}

class ApiException implements Exception {
  final String message;
  ApiException(this.message);
  @override
  String toString() => message;
}

class Api {
  Api(this.prefs);
  final Prefs prefs;

  /// Set once Supabase.initialize succeeded.
  static bool supabaseReady = false;

  static String? get accessToken =>
      supabaseReady ? Supabase.instance.client.auth.currentSession?.accessToken : null;

  Map<String, String> get _headers {
    final t = accessToken;
    return t == null ? {} : {'Authorization': 'Bearer $t'};
  }

  String get _dev => 'device_id=${Uri.encodeQueryComponent(prefs.deviceId)}';

  /// Fetches Supabase settings from the backend and caches them for offline starts.
  Future<void> fetchAuthConfig() async {
    try {
      final r = await http.get(Uri.parse('${prefs.server}/api/auth/config')).timeout(const Duration(seconds: 4));
      if (r.statusCode != 200) return;
      final j = jsonDecode(r.body);
      await prefs.setAuthConfig(j['supabase_url'] ?? '', j['supabase_key'] ?? '', j['auth_required'] == true);
    } catch (_) {}
  }

  Future<Map<String, dynamic>?> me() async {
    if (accessToken == null) return null;
    try {
      return Map<String, dynamic>.from(await _get('/api/me'));
    } catch (_) {
      return null;
    }
  }

  Future<void> updateMe({String? fullName, String? phone}) async {
    if (accessToken == null) return;
    try {
      await http.patch(Uri.parse('${prefs.server}/api/me'),
          headers: {..._headers, 'Content-Type': 'application/json'},
          body: jsonEncode({'full_name': ?fullName, 'phone': ?phone})).timeout(const Duration(seconds: 10));
    } catch (_) {}
  }

  String url(String? path) => path == null ? '' : (path.startsWith('http') ? path : '${prefs.server}$path');

  Future<dynamic> _get(String path) async {
    try {
      final r = await http.get(Uri.parse('${prefs.server}$path'), headers: _headers).timeout(const Duration(seconds: 15));
      if (r.statusCode >= 400) throw ApiException(_err(r.body, r.statusCode));
      return jsonDecode(r.body);
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException("Can't reach the RoadWatch server. Check your connection or the server address in Profile.");
    }
  }

  static String _err(String body, int code) {
    try {
      final d = jsonDecode(body)['detail'];
      return d is String ? d : 'Request failed ($code)';
    } catch (_) {
      return 'Request failed ($code)';
    }
  }

  /// Makes sure [prefs.server] points at a live backend. If it doesn't, searches the local network
  /// and saves what it finds. Returns true when a backend is reachable.
  Future<bool> ensureServer() async {
    if (await ServerDiscovery.ping(prefs.server)) return true;
    final found = await ServerDiscovery.find([prefs.server, Prefs.defaultServerUrl]);
    if (found == null) return false;
    await prefs.save(server: found);
    return true;
  }

  Future<void> syncConfig() async {
    try {
      final c = await _get('/api/citizen/config');
      if (c['helpline'] is String) await prefs.save(helpline: c['helpline']);
    } catch (_) {}
  }

  Future<List<Complaint>> myComplaints() async {
    final d = await _get('/api/complaints?$_dev');
    return [for (final c in d as List) Complaint.fromJson(c)];
  }

  /// Known road defects (from all inspections) for the map. Best effort: empty on failure.
  Future<List<Map<String, dynamic>>> defects() async {
    try {
      final d = await _get('/api/defects?status=active');
      return [for (final x in d as List) if (x['lat'] != null) Map<String, dynamic>.from(x)];
    } catch (_) {
      return [];
    }
  }

  Future<Complaint> complaint(int id) async => Complaint.fromJson(await _get('/api/complaints/$id?$_dev'));

  /// Uploads one photo or video for the AI damage check. Retries once on a moved server.
  Future<ScreenResult> screen(XFile file, int index) async {
    final bytes = await file.readAsBytes();
    final name = _fileName(file, index);

    Future<ScreenResult> send() async {
      final req = http.MultipartRequest('POST', Uri.parse('${prefs.server}/api/screening/check'))
        ..headers.addAll(_headers)
        ..fields['device_id'] = prefs.deviceId;
      if (prefs.phone.isNotEmpty) req.fields['phone'] = prefs.phone;
      req.files.add(http.MultipartFile.fromBytes('file', bytes, filename: name));
      final streamed = await req.send().timeout(const Duration(seconds: 120));
      final body = await streamed.stream.bytesToString();
      Map<String, dynamic>? j;
      try {
        j = Map<String, dynamic>.from(jsonDecode(body));
      } catch (_) {}
      if (j != null && j['verdict'] != null) return ScreenResult.fromJson(j);
      throw ApiException(_err(body, streamed.statusCode));
    }

    try {
      return await send();
    } on ApiException {
      rethrow;
    } catch (_) {
      final before = prefs.server;
      if (await ensureServer() && prefs.server != before) {
        try {
          return await send();
        } on ApiException {
          rethrow;
        } catch (_) {}
      }
      throw ApiException("Couldn't reach the server to check this file. Check your internet and tap Retry.");
    }
  }

  Future<Complaint> submit({
    List<String> screeningTokens = const [],
    required String category,
    required String description,
    required List<XFile> files,
    double? lat,
    double? lon,
    String? address,
    void Function(double)? onProgress,
  }) async {
    final fields = {
      'category': category,
      'description': description,
      'device_id': prefs.deviceId,
      if (prefs.name.isNotEmpty) 'citizen_name': prefs.name,
      if (prefs.phone.isNotEmpty) 'citizen_phone': prefs.phone,
      if (lat != null) 'lat': '$lat',
      if (lon != null) 'lon': '$lon',
      if (address != null && address.isNotEmpty) 'address': address,
      if (screeningTokens.isNotEmpty) 'screening_tokens': screeningTokens.join(','),
    };
    final parts = <(List<int>, String)>[];
    for (var i = 0; i < files.length; i++) {
      parts.add((await files[i].readAsBytes(), _fileName(files[i], i)));
      onProgress?.call((i + 1) / (files.length + 1) * 0.4);
    }

    Future<Complaint> send() async {
      final req = http.MultipartRequest('POST', Uri.parse('${prefs.server}/api/complaints'))
        ..headers.addAll(_headers)
        ..fields.addAll(fields);
      for (final (bytes, name) in parts) {
        req.files.add(http.MultipartFile.fromBytes('files', bytes, filename: name));
      }
      onProgress?.call(0.5);
      final streamed = await req.send().timeout(const Duration(minutes: 5));
      final body = await streamed.stream.bytesToString();
      if (streamed.statusCode >= 400) throw ApiException(_err(body, streamed.statusCode));
      onProgress?.call(1);
      return Complaint.fromJson(jsonDecode(body));
    }

    try {
      return await send();
    } on ApiException {
      rethrow;
    } catch (_) {
      // Server moved (new Wi-Fi / IP). Find it on the network and try once more.
      final before = prefs.server;
      if (await ensureServer() && prefs.server != before) {
        try {
          return await send();
        } on ApiException {
          rethrow;
        } catch (_) {}
      }
      throw ApiException(
          "Can't reach the RoadWatch server at ${prefs.server}. Put your phone on the same Wi-Fi as the computer "
          'running it, or set the address in Profile > Server.');
    }
  }

  Future<Map<String, dynamic>> _postJson(String path, Map<String, dynamic> body) async {
    try {
      final r = await http
          .post(Uri.parse('${prefs.server}$path'),
              headers: {..._headers, 'Content-Type': 'application/json'}, body: jsonEncode(body))
          .timeout(const Duration(seconds: 20));
      if (r.statusCode >= 400) throw ApiException(_err(r.body, r.statusCode));
      return Map<String, dynamic>.from(jsonDecode(r.body));
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException("Can't reach the RoadWatch server. Check your internet connection.");
    }
  }

  // ---------- drive mode ----------
  Future<String> driveStart() async =>
      '${(await _postJson('/api/drive/start', {'device_id': prefs.deviceId}))['session_id']}';

  Future<Map<String, dynamic>> driveStop(String sessionId) => _postJson('/api/drive/stop', {'session_id': sessionId});

  /// One camera frame with the GPS fix taken at capture time.
  Future<Map<String, dynamic>> driveFrame(String sessionId, List<int> jpeg,
      {double? lat, double? lon, double? accuracy, double? heading, double? speed, required DateTime capturedAt}) async {
    final req = http.MultipartRequest('POST', Uri.parse('${prefs.server}/api/drive/frame'))
      ..headers.addAll(_headers)
      ..fields.addAll({
        'session_id': sessionId,
        'device_id': prefs.deviceId,
        'captured_at': capturedAt.toUtc().toIso8601String(),
        if (lat != null) 'lat': '$lat',
        if (lon != null) 'lon': '$lon',
        if (accuracy != null) 'accuracy': '$accuracy',
        if (heading != null) 'heading': '$heading',
        if (speed != null) 'speed': '$speed',
      })
      ..files.add(http.MultipartFile.fromBytes('file', jpeg, filename: 'frame.jpg'));
    final streamed = await req.send().timeout(const Duration(seconds: 30));
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode >= 400) throw ApiException(_err(body, streamed.statusCode));
    return Map<String, dynamic>.from(jsonDecode(body));
  }

  Future<List<Map<String, dynamic>>> driveSessions() async {
    final d = await _get('/api/drive/sessions?$_dev');
    return [for (final x in d as List) Map<String, dynamic>.from(x)];
  }

  // ---------- dashcam video import ----------
  Future<Map<String, dynamic>> importVideo(XFile video,
      {List<int>? gpx, String? gpxName, double? lat, double? lon, void Function(double)? onProgress}) async {
    final bytes = await video.readAsBytes();
    onProgress?.call(0.3);
    final req = http.MultipartRequest('POST', Uri.parse('${prefs.server}/api/inspections'))
      ..headers.addAll(_headers)
      ..fields.addAll({
        'inspector': 'citizen: ${prefs.name.isNotEmpty ? prefs.name : 'dashcam import'}',
        'notes': 'Dashcam clip imported from the citizen app',
        if (lat != null) 'lat': '$lat',
        if (lon != null) 'lon': '$lon',
      })
      ..files.add(http.MultipartFile.fromBytes('file', bytes, filename: _fileName(video, 0)));
    if (gpx != null) req.files.add(http.MultipartFile.fromBytes('gpx_file', gpx, filename: gpxName ?? 'track.gpx'));
    try {
      final streamed = await req.send().timeout(const Duration(minutes: 10));
      final body = await streamed.stream.bytesToString();
      if (streamed.statusCode >= 400) throw ApiException(_err(body, streamed.statusCode));
      onProgress?.call(1);
      return Map<String, dynamic>.from(jsonDecode(body));
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException('Upload failed. Check your connection and try again.');
    }
  }

  Future<Map<String, dynamic>> jobStatus(String jobId) async => Map<String, dynamic>.from(await _get('/api/jobs/$jobId'));

  // ---------- complaint routing + public map ----------
  Future<Map<String, dynamic>> routeFor(String ticket) async =>
      Map<String, dynamic>.from(await _get('/api/route/${Uri.encodeComponent(ticket)}'));

  Future<List<Map<String, dynamic>>> publicDefects() async {
    final d = await _get('/api/public/defects');
    return [for (final x in d as List) Map<String, dynamic>.from(x)];
  }

  /// Density grid for the public map. Null when the endpoint is not available.
  Future<Map<String, dynamic>?> publicZones({int cellM = 300}) async {
    try {
      return Map<String, dynamic>.from(await _get('/api/public/zones?cell_m=$cellM'));
    } catch (_) {
      return null;
    }
  }

  /// Anonymised recent reports from everyone. Empty when the endpoint is not available.
  Future<List<Map<String, dynamic>>> publicComplaints({int limit = 40}) async {
    try {
      final d = await _get('/api/public/complaints?limit=$limit');
      return [for (final x in d as List) Map<String, dynamic>.from(x)];
    } catch (_) {
      return [];
    }
  }

  Future<Map<String, dynamic>?> publicSummary() async {
    try {
      return Map<String, dynamic>.from(await _get('/api/public/summary'));
    } catch (_) {
      return null;
    }
  }

  /// Compares drive routes by time and reported road damage. Throws [ApiException] with a readable message.
  Future<Map<String, dynamic>> routePlan(String origin, String dest) async => Map<String, dynamic>.from(await _get(
      '/api/routeplan?origin=${Uri.encodeQueryComponent(origin)}&dest=${Uri.encodeQueryComponent(dest)}'));

  static const _videoExt = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'];

  static bool isVideo(XFile f) {
    final n = f.name.toLowerCase();
    return (f.mimeType?.startsWith('video') ?? false) || _videoExt.any(n.endsWith);
  }

  static String _fileName(XFile f, int i) {
    final n = f.name;
    if (RegExp(r'\.[a-zA-Z0-9]{2,4}$').hasMatch(n)) return n;
    return 'media_$i${isVideo(f) ? '.mp4' : '.jpg'}';
  }
}
