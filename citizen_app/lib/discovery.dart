import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Finds the Disha AI backend when the saved address stops working
/// (laptop switched Wi-Fi, router gave it a new IP, wired vs wireless...).
class ServerDiscovery {
  static const port = 8000;

  /// Extra addresses baked in at build time: --dart-define=SERVERS=http://a:8000,http://b:8000
  static List<String> get builtIn => const String.fromEnvironment('SERVERS')
      .split(',')
      .map((s) => s.trim())
      .where((s) => s.isNotEmpty)
      .toList();

  /// True when [base] answers like a Disha AI backend.
  static Future<bool> ping(String base, {Duration timeout = const Duration(seconds: 3)}) async {
    try {
      final r = await http.get(Uri.parse('$base/api/citizen/config')).timeout(timeout);
      return r.statusCode == 200 && r.body.contains('helpline');
    } catch (_) {
      return false;
    }
  }

  /// Tries known addresses first, then scans the phone's own /24 subnet for port 8000.
  static Future<String?> find(List<String> known) async {
    final seen = <String>{};
    for (final k in [...known, ...builtIn]) {
      final base = k.replaceAll(RegExp(r'/+$'), '');
      if (base.isEmpty || !seen.add(base)) continue;
      if (await ping(base, timeout: const Duration(seconds: 2))) return base;
    }
    if (kIsWeb) return null;
    for (final prefix in await _subnets()) {
      final hit = await _scan(prefix);
      if (hit != null) return hit;
    }
    return null;
  }

  static Future<List<String>> _subnets() async {
    final out = <String>[];
    try {
      for (final ni in await NetworkInterface.list(type: InternetAddressType.IPv4)) {
        for (final a in ni.addresses) {
          final ip = a.address;
          if (a.isLoopback || ip.startsWith('169.254.')) continue;
          // mobile data (carrier NAT) addresses cannot reach a laptop on Wi-Fi, skip the big ranges
          final parts = ip.split('.');
          if (parts.length != 4) continue;
          final p = '${parts[0]}.${parts[1]}.${parts[2]}';
          if (!out.contains(p)) out.add(p);
        }
      }
    } catch (_) {}
    // Wi-Fi style private ranges first
    out.sort((a, b) => (a.startsWith('192.168.') ? 0 : 1).compareTo(b.startsWith('192.168.') ? 0 : 1));
    return out;
  }

  /// Opens TCP connections to x.x.x.1-254:8000 in parallel batches; confirms candidates with [ping].
  static Future<String?> _scan(String prefix) async {
    const batch = 64;
    for (var start = 1; start < 255; start += batch) {
      final hosts = [for (var i = start; i < start + batch && i < 255; i++) '$prefix.$i'];
      final open = await Future.wait(hosts.map((h) async {
        try {
          final s = await Socket.connect(h, port, timeout: const Duration(milliseconds: 450));
          s.destroy();
          return h;
        } catch (_) {
          return null;
        }
      }));
      for (final h in open.whereType<String>()) {
        final base = 'http://$h:$port';
        if (await ping(base)) return base;
      }
    }
    return null;
  }
}
