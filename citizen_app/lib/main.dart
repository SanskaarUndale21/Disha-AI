import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:supabase_flutter/supabase_flutter.dart';

import 'api.dart';
import 'i18n.dart';
import 'location.dart';
import 'notifications.dart';
import 'realtime.dart';
import 'screens/auth_screen.dart';
import 'screens/home_screen.dart';
import 'screens/notifications_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/nav_map_screen.dart';
import 'screens/report_screen.dart';
import 'screens/reports_screen.dart';
import 'theme.dart';
import 'widgets.dart';

late Prefs prefs;
late Api api;
late Realtime realtime;
final locator = Locator();

/// Web-only design preview: ?preview=home|reports|profile|report opens that screen without signing in.
final String? previewScreen = kIsWeb ? Uri.base.queryParameters['preview'] : null;
final messengerKey = GlobalKey<ScaffoldMessengerState>();

/// Bumped whenever a complaint is filed or updated so lists refresh.
final refreshTick = ValueNotifier<int>(0);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  prefs = await Prefs.load();
  await loadLang();
  api = Api(prefs);
  if (previewScreen != null) await prefs.setSkippedAuth(true);
  if (prefs.supabaseUrl.isEmpty) {
    await api.fetchAuthConfig();
  } else {
    api.fetchAuthConfig(); // refresh cache in the background
  }
  await initSupabase();
  api.ensureServer().then((ok) {
    if (ok) {
      api.syncConfig();
      realtime.restart();
      refreshTick.value++;
    }
  });
  await notifs.init();
  realtime = Realtime(prefs, onEvent: _onEvent)..start();
  notifs.startPolling();
  if (Api.supabaseReady) {
    Supabase.instance.client.auth.onAuthStateChange.listen((s) {
      if (s.event == AuthChangeEvent.tokenRefreshed || s.event == AuthChangeEvent.signedOut) realtime.restart();
    });
  }
  runApp(const CitizenApp());
}

Future<void> initSupabase() async {
  if (Api.supabaseReady || prefs.supabaseUrl.isEmpty || prefs.supabaseKey.isEmpty) return;
  try {
    await Supabase.initialize(url: prefs.supabaseUrl, publishableKey: prefs.supabaseKey);
    Api.supabaseReady = true;
  } catch (_) {}
}

/// After sign in: pull the server profile into local prefs, reconnect live updates, refresh lists.
Future<void> onSignedIn() async {
  await prefs.setSkippedAuth(false);
  final me = await api.me();
  if (me != null) {
    final name = (me['full_name'] as String?) ?? '';
    final phone = (me['phone'] as String?) ?? '';
    await prefs.save(name: name.isNotEmpty ? name : null, phone: phone.isNotEmpty ? phone : null);
    if (name.isEmpty && prefs.name.isNotEmpty) await api.updateMe(fullName: prefs.name);
  }
  realtime.restart();
  refreshTick.value++;
}

Future<void> signOut() async {
  if (Api.supabaseReady) await Supabase.instance.client.auth.signOut();
  await prefs.setSkippedAuth(false);
  realtime.restart();
  refreshTick.value++;
}

void _onEvent(String type, Map<String, dynamic> data) {
  notifs.handleEvent(type, data);
  if (!type.startsWith('complaint.')) return;
  refreshTick.value++;
  if (type != 'complaint.updated') return;
  final st = statusStyle('${data['status'] ?? ''}');
  final ticket = data['ticket'] ?? 'Your report';
  HapticFeedback.mediumImpact();
  messengerKey.currentState
    ?..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      behavior: SnackBarBehavior.floating,
      backgroundColor: const Color(0xF21C1C1E),
      elevation: 0,
      duration: const Duration(seconds: 5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 90),
      content: Row(children: [
        IconBadge(st.icon, st.color, size: 34),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Text('$ticket: ${st.label}',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 15)),
            Text(
              (data['admin_note'] as String?)?.isNotEmpty == true ? data['admin_note'] : 'Status updated by the city',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Color(0xCCFFFFFF), fontSize: 13),
            ),
          ]),
        ),
      ]),
    ));
}

class CitizenApp extends StatelessWidget {
  const CitizenApp({super.key});
  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<String>(
      valueListenable: langNotifier,
      builder: (context, l, _) => MaterialApp(
        title: 'Disha AI',
        debugShowCheckedModeBanner: false,
        scaffoldMessengerKey: messengerKey,
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        // rebuild the whole tree on language change; the open tab is kept in _ShellState.lastTab
        builder: (context, child) => KeyedSubtree(key: ValueKey(l), child: child ?? const SizedBox.shrink()),
        home: const AuthGate(),
      ),
    );
  }
}

/// Shows the sign-in screen first when the backend uses accounts, unless the citizen chose to skip.
class AuthGate extends StatefulWidget {
  const AuthGate({super.key});
  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  @override
  Widget build(BuildContext context) {
    if (!Api.supabaseReady) return const Shell();
    return StreamBuilder<AuthState>(
      stream: Supabase.instance.client.auth.onAuthStateChange,
      builder: (context, _) {
        final signedIn = Supabase.instance.client.auth.currentSession != null;
        return ListenableBuilder(
          listenable: prefs,
          builder: (context, _) => AnimatedSwitcher(
            duration: const Duration(milliseconds: 350),
            child: signedIn || prefs.skippedAuth
                ? const Shell(key: ValueKey('shell'))
                : AuthScreen(key: const ValueKey('auth'), onDone: () => setState(() {})),
          ),
        );
      },
    );
  }
}

class Shell extends StatefulWidget {
  const Shell({super.key});
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  static int lastTab = 0;
  int _tab = switch (previewScreen) { 'reports' => 1, 'profile' => 2, _ => lastTab };

  @override
  void initState() {
    super.initState();
    if (previewScreen == 'report') {
      WidgetsBinding.instance.addPostFrameCallback(
          (_) => Navigator.of(context).push(CupertinoPageRoute(builder: (_) => const ReportScreen())));
    }
  }

  void go(int i) => setState(() => (_tab = i, lastTab = i));

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final c = AppColors.of(context);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      child: Scaffold(
        extendBody: true,
        body: Stack(children: [
          IndexedStack(index: _tab, children: [
            HomeScreen(onSeeAll: () => go(1)),
            const ReportsScreen(),
            const ProfileScreen(),
          ]),
          const EmergencyBanner(),
        ]),
        bottomNavigationBar: Glass(
          child: Container(
            decoration: BoxDecoration(border: Border(top: BorderSide(color: c.separator, width: 0.5))),
            child: SafeArea(
              top: false,
              child: SizedBox(
                height: 58,
                child: Row(children: [
                  _tabItem(0, CupertinoIcons.house_fill, tr('nav_home')),
                  _actionItem(CupertinoIcons.map_fill, tr('nav_map'),
                      () => Navigator.of(context).push(CupertinoPageRoute(builder: (_) => const NavMapScreen(startOnDirections: true)))),
                  _tabItem(1, CupertinoIcons.doc_text_fill, tr('nav_reports')),
                  _tabItem(2, CupertinoIcons.person_crop_circle_fill, tr('nav_profile')),
                ]),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _actionItem(IconData icon, String label, VoidCallback onTap) {
    final color = AppColors.blue;
    return Expanded(
      child: Pressable(
        scale: 0.9,
        onTap: onTap,
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(icon, color: color, size: 25),
          const SizedBox(height: 3),
          Text(label, style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w600, color: color)),
        ]),
      ),
    );
  }

  Widget _tabItem(int i, IconData icon, String label) {
    final active = _tab == i;
    final color = active ? AppColors.blue : AppColors.of(context).textTertiary;
    return Expanded(
      child: Pressable(
        scale: 0.9,
        onTap: () => go(i),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          AnimatedScale(
            scale: active ? 1.08 : 1,
            duration: const Duration(milliseconds: 200),
            child: Icon(icon, color: color, size: 25),
          ),
          const SizedBox(height: 3),
          Text(label, style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w600, color: color)),
        ]),
      ),
    );
  }
}
