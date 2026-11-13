import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';
import 'package:supabase_flutter/supabase_flutter.dart' show Supabase;

import '../api.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';
import 'auth_screen.dart';
import 'home_screen.dart' show HelplinePlate;

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});
  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late final _name = TextEditingController(text: prefs.name);
  late final _phone = TextEditingController(text: prefs.phone);
  late final _server = TextEditingController(text: prefs.server);
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _server.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    FocusScope.of(context).unfocus();
    setState(() => _saving = true);
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
      setState(() => _saving = false);
      toast(context, 'Profile saved');
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
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final email = _email;
    final initials = prefs.name.trim().isEmpty
        ? null
        : prefs.name.trim().split(RegExp(r'\s+')).take(2).map((w) => w[0].toUpperCase()).join();
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: SafeArea(
        bottom: false,
        child: ListView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
          children: [
            Row(children: [
              Container(
                width: 64,
                height: 64,
                alignment: Alignment.center,
                decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(14)),
                child: initials != null
                    ? Text(initials,
                        style: const TextStyle(
                            fontFamily: fontDisplay, color: Palette.yellow, fontSize: 30, fontWeight: FontWeight.w800))
                    : const Icon(PhosphorIconsFill.user, color: Palette.yellow, size: 30),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(prefs.name.isEmpty ? 'Your profile' : prefs.name, style: T.h1(context)),
                  const SizedBox(height: 2),
                  Text(email ?? 'Not signed in. Reports stay on this phone.', style: T.sub(context)),
                ]),
              ),
            ]),
            if (Api.supabaseReady) ...[
              const SizedBox(height: 18),
              email == null
                  ? YellowButton(label: 'Sign in or create account', icon: PhosphorIconsBold.signIn, onTap: _signIn)
                  : const SizedBox.shrink(),
            ],
            const SectionTitle('Contact details'),
            Text('Shared with the repair team only if they need to reach you about a report.', style: T.sub(context)),
            const SizedBox(height: 12),
            _field(_name, 'Name', PhosphorIconsBold.user, TextInputType.name),
            const SizedBox(height: 10),
            _field(_phone, 'Mobile number', PhosphorIconsBold.phone, TextInputType.phone),
            const SectionTitle('Help'),
            HelplinePlate(number: prefs.helpline),
            const SectionTitle('Server'),
            Text('The RoadWatch backend this app talks to. On a phone, use the computer\'s Wi-Fi address.',
                style: T.sub(context)),
            const SizedBox(height: 12),
            _field(_server, 'http://192.168.1.10:8000', PhosphorIconsBold.hardDrives, TextInputType.url),
            const SizedBox(height: 24),
            Pressable(
              onTap: _saving ? null : _save,
              child: Container(
                height: 54,
                alignment: Alignment.center,
                decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(12)),
                child: _saving
                    ? const CupertinoActivityIndicator(color: Colors.white)
                    : const Text('Save profile',
                        style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w700)),
              ),
            ),
            if (email != null) ...[
              const SizedBox(height: 8),
              Center(
                child: CupertinoButton(
                  onPressed: _signOut,
                  child: const Text('Sign out',
                      style: TextStyle(color: Palette.red, fontSize: 16, fontWeight: FontWeight.w600)),
                ),
              ),
            ],
            const SizedBox(height: 16),
            Center(child: Text('RoadWatch citizen app, version 1.0', style: TextStyle(fontSize: 12.5, color: c.inkFaint))),
          ],
        ),
      ),
    );
  }

  Widget _field(TextEditingController ctl, String hint, IconData icon, TextInputType type) {
    final c = AppColors.of(context);
    return TextField(
      controller: ctl,
      keyboardType: type,
      autocorrect: false,
      style: T.body(context),
      decoration: InputDecoration(
        filled: true,
        fillColor: c.surface,
        prefixIcon: Icon(icon, size: 20, color: c.inkSoft),
        hintText: hint,
        hintStyle: T.body(context).copyWith(color: c.inkFaint),
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 15),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: c.line)),
        focusedBorder:
            OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: c.ink, width: 2)),
      ),
    );
  }
}
