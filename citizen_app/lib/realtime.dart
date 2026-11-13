import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'api.dart';

/// Live updates from the backend event bus (/ws/events).
/// Citizens get events addressed to them, e.g. "complaint.updated" when an officer changes their report status.
class Realtime {
  Realtime(this.prefs, {required this.onEvent});
  final Prefs prefs;
  final void Function(String type, Map<String, dynamic> data) onEvent;

  WebSocketChannel? _ch;
  StreamSubscription? _sub;
  Timer? _ping, _retry;
  int _attempt = 0;
  bool _stopped = true;
  final connected = ValueNotifier<bool>(false);

  void start() {
    _stopped = false;
    _connect();
  }

  /// Reconnect with fresh credentials (after sign in / sign out / server change).
  void restart() {
    _close();
    _attempt = 0;
    if (!_stopped) _connect();
  }

  void stop() {
    _stopped = true;
    _close();
  }

  void _connect() {
    _retry?.cancel();
    final base = prefs.server.replaceFirst(RegExp(r'^http'), 'ws');
    final token = Api.accessToken;
    final uri = Uri.parse('$base/ws/events${token != null ? '?token=${Uri.encodeQueryComponent(token)}' : ''}');
    try {
      final ch = WebSocketChannel.connect(uri);
      _ch = ch;
      _sub = ch.stream.listen(_onMessage, onDone: _scheduleRetry, onError: (_) => _scheduleRetry());
      ch.ready.then((_) {
        _attempt = 0;
        connected.value = true;
      }).catchError((_) {});
      _ping = Timer.periodic(const Duration(seconds: 25), (_) {
        try {
          ch.sink.add('ping');
        } catch (_) {}
      });
    } catch (_) {
      _scheduleRetry();
    }
  }

  void _onMessage(dynamic raw) {
    try {
      final m = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = m['type'] as String? ?? '';
      if (type == 'hello' || type == 'auth.error') return;
      final data = m['data'];
      onEvent(type, data is Map<String, dynamic> ? data : <String, dynamic>{});
    } catch (_) {}
  }

  void _scheduleRetry() {
    connected.value = false;
    _close(keepRetry: true);
    if (_stopped) return;
    _attempt++;
    final secs = (_attempt * 2).clamp(2, 30);
    _retry = Timer(Duration(seconds: secs), _connect);
  }

  void _close({bool keepRetry = false}) {
    _ping?.cancel();
    if (!keepRetry) _retry?.cancel();
    _sub?.cancel();
    try {
      _ch?.sink.close();
    } catch (_) {}
    _ch = null;
    _sub = null;
  }
}
