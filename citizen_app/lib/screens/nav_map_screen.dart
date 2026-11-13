import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

import '../main.dart';
import 'public_map_screen.dart';

/// Opens the shared navigation map (same page as the web /map) full screen.
/// Deep links: [toLat]/[toLon]/[toName] pre-fill the destination, [startOnDirections] opens the
/// route planner and [mode] is one of car, bike or walk.
class NavMapScreen extends StatefulWidget {
  const NavMapScreen({
    super.key,
    this.toLat,
    this.toLon,
    this.toName,
    this.startOnDirections = false,
    this.mode,
  });
  final double? toLat, toLon;
  final String? toName;
  final bool startOnDirections;
  final String? mode;

  /// Convenience for pushing the screen.
  static Future<void> open(
    BuildContext context, {
    double? toLat,
    double? toLon,
    String? toName,
    bool startOnDirections = false,
    String? mode,
  }) {
    return Navigator.of(context).push(CupertinoPageRoute(
        builder: (_) => NavMapScreen(
            toLat: toLat, toLon: toLon, toName: toName, startOnDirections: startOnDirections, mode: mode)));
  }

  @override
  State<NavMapScreen> createState() => _NavMapScreenState();
}

class _NavMapScreenState extends State<NavMapScreen> {
  WebViewController? _wc;
  Timer? _timeout;
  bool _loading = true;
  bool _failed = false;
  String _failMsg = '';
  int _progress = 0;

  @override
  void initState() {
    super.initState();
    WakelockPlus.enable();
    _start();
  }

  @override
  void dispose() {
    _timeout?.cancel();
    WakelockPlus.disable();
    super.dispose();
  }

  String _lang() => ui.PlatformDispatcher.instance.locale.languageCode == 'hi' ? 'hi' : 'en';

  Uri _url(String server) {
    final q = <String, String>{'app': '1', 'lang': _lang()};
    if (widget.toLat != null && widget.toLon != null) {
      q['to'] = '${widget.toLat},${widget.toLon}';
      if (widget.toName != null && widget.toName!.isNotEmpty) q['name'] = widget.toName!;
    }
    if (widget.startOnDirections || (widget.toLat != null && widget.toLon != null)) q['dir'] = '1';
    if (widget.mode != null && widget.mode!.isNotEmpty) q['mode'] = widget.mode!;
    final base = Uri.parse(server);
    return base.replace(path: '${base.path.replaceAll(RegExp(r'/+$'), '')}/map', queryParameters: q);
  }

  Future<bool> _locationAllowed() async {
    try {
      var p = await Geolocator.checkPermission();
      if (p == LocationPermission.denied) p = await Geolocator.requestPermission();
      return p == LocationPermission.always || p == LocationPermission.whileInUse;
    } catch (_) {
      return false;
    }
  }

  Future<void> _start() async {
    _timeout?.cancel();
    setState(() {
      _loading = true;
      _failed = false;
      _progress = 0;
    });
    // fail safe: offer the basic map if the page is still not up after 15 seconds
    _timeout = Timer(const Duration(seconds: 15), () {
      if (mounted && _loading) _fail('The map is taking too long to open.');
    });
    unawaited(_locationAllowed());
    final ok = await api.ensureServer();
    if (!mounted) return;
    if (!ok) {
      _fail('Cannot reach the Disha AI server. Check that you are online and on the same network.');
      return;
    }
    var c = _wc;
    if (c == null) {
      c = WebViewController()
        ..setJavaScriptMode(JavaScriptMode.unrestricted)
        ..setBackgroundColor(const Color(0xFFF2F2F7))
        ..setNavigationDelegate(NavigationDelegate(
          onProgress: (p) {
            if (mounted && _loading) setState(() => _progress = p);
          },
          onPageFinished: (_) {
            _timeout?.cancel();
            if (mounted && !_failed) setState(() => _loading = false);
          },
          onWebResourceError: (e) {
            if (e.isForMainFrame ?? true) _fail('The map page could not be loaded.');
          },
          onHttpError: (e) {
            final code = e.response?.statusCode ?? 0;
            if (code >= 500 || code == 404) _fail('The server answered with an error ($code).');
          },
        ));
      final p = c.platform;
      if (p is AndroidWebViewController) {
        await p.setMediaPlaybackRequiresUserGesture(false);
        await p.setGeolocationPermissionsPromptCallbacks(
          onShowPrompt: (request) async {
            final allow = await _locationAllowed();
            return GeolocationPermissionsResponse(allow: allow, retain: allow);
          },
        );
        await p.setOnPlatformPermissionRequest((request) async {
          await request.grant();
        });
      }
      _wc = c;
    }
    try {
      await c.loadRequest(_url(prefs.server));
    } catch (_) {
      _fail('The map page could not be loaded.');
    }
  }

  void _fail(String msg) {
    _timeout?.cancel();
    if (!mounted || _failed) return;
    setState(() {
      _failed = true;
      _loading = false;
      _failMsg = msg;
    });
  }

  void _openBasic() {
    Navigator.of(context).pushReplacement(
        CupertinoPageRoute(builder: (_) => PublicMapScreen(startOnPlanner: widget.startOnDirections)));
  }

  Future<void> _onBack() async {
    final c = _wc;
    if (c != null && !_failed && await c.canGoBack()) {
      await c.goBack();
      return;
    }
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _onBack();
      },
      child: Scaffold(
        backgroundColor: const Color(0xFFF2F2F7),
        body: Stack(children: [
          if (_wc != null && !_failed) Positioned.fill(child: WebViewWidget(controller: _wc!)),
          if (_loading && !_failed) _loadingView(),
          if (_failed) _errorView(),
          if (_loading || _failed)
            Positioned(
              left: 10,
              top: MediaQuery.paddingOf(context).top + 8,
              child: _roundButton(CupertinoIcons.chevron_back, 'Back', () {
                if (mounted) Navigator.of(context).pop();
              }),
            ),
        ]),
      ),
    );
  }

  Widget _roundButton(IconData icon, String label, VoidCallback onTap) {
    return Semantics(
      button: true,
      label: label,
      child: Material(
        color: Colors.white,
        elevation: 3,
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: SizedBox(width: 42, height: 42, child: Icon(icon, size: 22, color: Colors.black87)),
        ),
      ),
    );
  }

  Widget _loadingView() {
    return Positioned.fill(
      child: Container(
        color: const Color(0xFFF2F2F7),
        alignment: Alignment.center,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(CupertinoIcons.location_north_fill, size: 44, color: Color(0xFF0A84FF)),
          const SizedBox(height: 18),
          const Text('Opening map',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: Colors.black87)),
          const SizedBox(height: 6),
          const Text('Getting roads and potholes ready', style: TextStyle(fontSize: 14, color: Colors.black54)),
          const SizedBox(height: 22),
          SizedBox(
            width: 180,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: _progress > 0 ? _progress / 100 : null,
                minHeight: 5,
                backgroundColor: Colors.black12,
                color: const Color(0xFF0A84FF),
              ),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _errorView() {
    return Positioned.fill(
      child: Container(
        color: const Color(0xFFF2F2F7),
        padding: const EdgeInsets.symmetric(horizontal: 28),
        alignment: Alignment.center,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(CupertinoIcons.wifi_slash, size: 52, color: Colors.black45),
          const SizedBox(height: 16),
          const Text('Map not available',
              style: TextStyle(fontSize: 21, fontWeight: FontWeight.w700, color: Colors.black87)),
          const SizedBox(height: 8),
          Text(_failMsg, textAlign: TextAlign.center, style: const TextStyle(fontSize: 15, color: Colors.black54)),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton(onPressed: _start, child: const Text('Retry')),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(onPressed: _openBasic, child: const Text('Open basic map')),
          ),
        ]),
      ),
    );
  }
}
