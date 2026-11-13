import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:supabase_flutter/supabase_flutter.dart' show Supabase;
import 'package:uuid/uuid.dart';

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

  Future<Complaint> submit({
    required String category,
    required String description,
    required List<XFile> files,
    double? lat,
    double? lon,
    String? address,
    void Function(double)? onProgress,
  }) async {
    final req = http.MultipartRequest('POST', Uri.parse('${prefs.server}/api/complaints'))..headers.addAll(_headers);
    req.fields.addAll({
      'category': category,
      'description': description,
      'device_id': prefs.deviceId,
      if (prefs.name.isNotEmpty) 'citizen_name': prefs.name,
      if (prefs.phone.isNotEmpty) 'citizen_phone': prefs.phone,
      if (lat != null) 'lat': '$lat',
      if (lon != null) 'lon': '$lon',
      if (address != null && address.isNotEmpty) 'address': address,
    });
    for (var i = 0; i < files.length; i++) {
      final f = files[i];
      req.files.add(http.MultipartFile.fromBytes('files', await f.readAsBytes(), filename: _fileName(f, i)));
      onProgress?.call((i + 1) / (files.length + 1) * 0.5);
    }
    try {
      final streamed = await req.send().timeout(const Duration(minutes: 5));
      final body = await streamed.stream.bytesToString();
      if (streamed.statusCode >= 400) throw ApiException(_err(body, streamed.statusCode));
      onProgress?.call(1);
      return Complaint.fromJson(jsonDecode(body));
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException("Upload failed. Check your connection and try again.");
    }
  }

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
