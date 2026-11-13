import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart' show Supabase;

import '../api.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';
import 'auth_screen.dart';
import '../notifications.dart';
import 'drive_screen.dart';
import 'notifications_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});
  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late final _name = TextEditingController(text: prefs.name);
  late final _phone = TextEditingController(text: prefs.phone);
  late final _server = TextEditingController(text: prefs.server);

  @override
  void dispose() {
    notifs.removeListener(_rebuild);
    _name.dispose();
    _phone.dispose();
    _server.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    FocusScope.of(context).unfocus();
    final serverChanged = _server.text.trim() != prefs.server;
    await prefs.save(name: _name.text, phone: _phone.text, server: _server.text);
    await api.updateMe(fullName: _name.text.trim(), phone: _phone.text.trim());
    await api.syncConfig();
    if (serverChanged) {
      await api.fetchAuthConfig();
      realtime.restart();
    }
    refreshTick.value++;
    if (mounted) {
      setState(() {});
      toast(context, 'Saved');
    }
  }

  String? get _email => Api.supabaseReady ? Supabase.instance.client.auth.currentUser?.email : null;

  Future<void> _signOut() async {
    await signOut();
    if (mounted) setState(() {});
  }

  void _signIn() => Navigator.of(context)
          .push(CupertinoPageRoute(fullscreenDialog: true, builder: (_) => const AuthScreen(canSkip: false)))
          .then((_) {
        if (mounted) {
          setState(() {
            _name.text = prefs.name;
            _phone.text = prefs.phone;
          });
        }
      });

  @override
  void initState() {
    super.initState();
    notifs.addListener(_rebuild);
  }

  void _rebuild() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final email = _email;
    final initials = prefs.name.trim().isEmpty
        ? '?'
        : prefs.name.trim().split(RegExp(r'\s+')).take(2).map((w) => w[0].toUpperCase()).join();
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: ListView(
        physics: const BouncingScrollPhysics(),
        padding: EdgeInsets.fromLTRB(20, MediaQuery.paddingOf(context).top + 12, 20, 120),
        children: [
          Text('Profile', style: T.largeTitle(context)),
          const SizedBox(height: 22),
          Center(
            child: Container(
              width: 92,
              height: 92,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(colors: [AppColors.blue, AppColors.indigo]),
              ),
              child: Text(initials, style: const TextStyle(color: Colors.white, fontSize: 34, fontWeight: FontWeight.w700)),
            ),
          ),
          const SizedBox(height: 10),
          Center(child: Text(prefs.name.isEmpty ? 'Citizen' : prefs.name, style: T.title(context))),
          const SizedBox(height: 4),
          Center(child: Text(email ?? 'Not signed in · reports linked to this phone', style: T.sub(context))),
          if (Api.supabaseReady)
            _group('ACCOUNT', [
              Pressable(
                onTap: email == null ? _signIn : _signOut,
                child: email == null
                    ? _row(CupertinoIcons.person_crop_circle_badge_plus, AppColors.blue, 'Sign in or create account', '',
                        chevron: true)
                    : _row(CupertinoIcons.square_arrow_right, AppColors.red, 'Sign out', ''),
              ),
            ]),
          _group('YOUR DETAILS', [
            _field(_name, 'Name', CupertinoIcons.person_fill, AppColors.blue, TextInputType.name),
            _field(_phone, 'Mobile', CupertinoIcons.phone_fill, AppColors.green, TextInputType.phone),
          ]),
          _group('NOTIFICATIONS', [
            Pressable(
              onTap: () => Navigator.of(context).push(CupertinoPageRoute(builder: (_) => const NotificationsScreen())),
              child: _row(CupertinoIcons.bell_fill, AppColors.orange, 'Notification centre',
                  notifs.unread == 0 ? '' : '${notifs.unread} new', chevron: true),
            ),
            _switch(CupertinoIcons.exclamationmark_triangle_fill, AppColors.red, 'Emergency alerts', notifs.emergencyOn,
                notifs.setEmergency),
            _switch(CupertinoIcons.location_fill, AppColors.green, 'Nearby damage and repairs', notifs.nearbyOn,
                notifs.setNearby),
            _switch(CupertinoIcons.doc_text_fill, AppColors.blue, 'My reports', notifs.mineOn, notifs.setMine),
          ]),
          _group('DRIVE MODE', [
            Pressable(
              onTap: () => Navigator.of(context).push(CupertinoPageRoute(builder: (_) => const DriveHistoryScreen())),
              child: _row(CupertinoIcons.car_detailed, AppColors.indigo, 'Drive history', '', chevron: true),
            ),
          ]),
          _group('HELP', [
            Pressable(
              onTap: () => callAgent(context, prefs.helpline),
              child: _row(CupertinoIcons.waveform, AppColors.indigo, 'Call RoadWatch agent', prettyPhone(prefs.helpline),
                  chevron: true),
            ),
          ]),
          _group('SERVER', [
            _field(_server, 'http://192.168.x.x:8000', CupertinoIcons.cloud_fill, AppColors.teal, TextInputType.url),
          ]),
          Padding(
            padding: const EdgeInsets.fromLTRB(6, 8, 6, 0),
            child: Text('Point this to the RoadWatch backend. On a real phone use your computer\'s LAN IP.',
                style: T.sub(context).copyWith(fontSize: 12.5)),
          ),
          const SizedBox(height: 24),
          Pressable(
            onTap: _save,
            child: Container(
              height: 54,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: AppColors.blue, borderRadius: BorderRadius.circular(16)),
              child: const Text('Save', style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
            ),
          ),
          const SizedBox(height: 20),
          Center(child: Text('RoadWatch Citizen 1.1', style: TextStyle(fontSize: 12, color: c.textTertiary))),
        ],
      ),
    );
  }

  Widget _group(String title, List<Widget> rows) {
    final c = AppColors.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(padding: const EdgeInsets.fromLTRB(6, 28, 6, 8), child: Text(title, style: T.caption(context))),
      CardBox(
        padding: const EdgeInsets.symmetric(horizontal: 14),
        radius: 18,
        child: Column(children: [
          for (var i = 0; i < rows.length; i++) ...[
            if (i > 0) Divider(height: 1, thickness: 0.5, color: c.separator, indent: 44),
            rows[i],
          ],
        ]),
      ),
    ]);
  }

  Widget _switch(IconData icon, Color color, String title, bool value, Future<void> Function(bool) onChanged) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          IconBadge(icon, color, size: 30),
          const SizedBox(width: 14),
          Expanded(child: Text(title, style: T.body(context))),
          Switch.adaptive(value: value, onChanged: (v) async {
            await onChanged(v);
            if (v) await notifs.requestPermission();
          }),
        ]),
      );

  Widget _row(IconData icon, Color color, String title, String value, {bool chevron = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(children: [
          IconBadge(icon, color, size: 30),
          const SizedBox(width: 14),
          Expanded(child: Text(title, style: T.body(context))),
          Text(value, style: T.sub(context)),
          if (chevron) ...[
            const SizedBox(width: 6),
            Icon(CupertinoIcons.chevron_right, size: 16, color: AppColors.of(context).textTertiary),
          ],
        ]),
      );

  Widget _field(TextEditingController ctl, String hint, IconData icon, Color color, TextInputType type) => Row(children: [
        IconBadge(icon, color, size: 30),
        const SizedBox(width: 14),
        Expanded(
          child: TextField(
            controller: ctl,
            keyboardType: type,
            autocorrect: false,
            style: T.body(context),
            decoration: InputDecoration(
              border: InputBorder.none,
              hintText: hint,
              hintStyle: T.body(context).copyWith(color: AppColors.of(context).textTertiary),
              contentPadding: const EdgeInsets.symmetric(vertical: 15),
            ),
          ),
        ),
      ]);
}
