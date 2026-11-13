import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../main.dart';
import '../theme.dart';
import '../widgets.dart';

/// Email + password sign in / sign up (Supabase Auth). Citizens can also continue without an account.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, this.canSkip = true, this.onDone});
  final bool canSkip;
  final VoidCallback? onDone;
  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool _signUp = false;
  bool _busy = false;
  bool _hide = true;
  String? _error, _info;
  final _email = TextEditingController();
  final _password = TextEditingController();
  late final _name = TextEditingController(text: prefs.name);

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    super.dispose();
  }

  void _finish() {
    if (widget.onDone != null) {
      widget.onDone!();
    } else if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
    }
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    final email = _email.text.trim(), pw = _password.text;
    if (!email.contains('@') || pw.length < 6) {
      setState(() => _error = 'Enter a valid email and a password of at least 6 characters');
      return;
    }
    setState(() => (_busy = true, _error = null, _info = null));
    final auth = Supabase.instance.client.auth;
    try {
      if (_signUp) {
        final name = _name.text.trim();
        final r = await auth.signUp(email: email, password: pw, data: {if (name.isNotEmpty) 'full_name': name});
        if (name.isNotEmpty) await prefs.save(name: name);
        if (r.session == null) {
          setState(() => (_info = 'Check $email to confirm your account, then sign in.', _signUp = false));
          return;
        }
      } else {
        await auth.signInWithPassword(email: email, password: pw);
      }
      await onSignedIn();
      if (mounted) _finish();
    } on AuthException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error = "Couldn't reach the sign-in service. Check your connection.");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _skip() async {
    await prefs.setSkippedAuth(true);
    if (mounted) _finish();
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final top = MediaQuery.paddingOf(context).top;
    return Scaffold(
      body: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: ListView(
          physics: const ClampingScrollPhysics(),
          padding: EdgeInsets.zero,
          children: [
            SizedBox(
              height: 280 + top,
              child: Stack(fit: StackFit.expand, children: [
                Image.asset('assets/photos/street.jpg', fit: BoxFit.cover),
                DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [const Color(0x33000000), const Color(0x00000000), c.bg],
                      stops: const [0, 0.45, 1],
                    ),
                  ),
                ),
                if (!widget.canSkip)
                  Positioned(
                    top: top + 8,
                    right: 14,
                    child: Pressable(
                      onTap: () => Navigator.pop(context),
                      child: Glass(
                        radius: 99,
                        opacity: 0.6,
                        child: SizedBox(
                            width: 40, height: 40, child: Icon(CupertinoIcons.xmark, size: 18, color: c.text)),
                      ),
                    ),
                  ),
                Positioned(
                  left: 24,
                  bottom: 8,
                  child: Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(22),
                      boxShadow: const [BoxShadow(color: Color(0x40000000), blurRadius: 24, offset: Offset(0, 10))],
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(22),
                      child: Image.asset('assets/icon/icon.png', width: 76, height: 76),
                    ),
                  ),
                ),
              ]),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 18, 24, 28),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Text('RoadWatch', style: T.largeTitle(context)),
                const SizedBox(height: 6),
                Text(
                  _signUp ? 'Create an account to track every report' : 'Sign in to track your reports anywhere',
                  style: T.sub(context).copyWith(fontSize: 15.5),
                ),
                const SizedBox(height: 22),
                CupertinoSlidingSegmentedControl<bool>(
                  groupValue: _signUp,
                  onValueChanged: (v) => setState(() => (_signUp = v ?? false, _error = null)),
                  children: const {
                    false: Padding(padding: EdgeInsets.symmetric(vertical: 7), child: Text('Sign in')),
                    true: Text('Create account'),
                  },
                ),
                const SizedBox(height: 16),
                CardBox(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Column(children: [
                    AnimatedSize(
                      duration: const Duration(milliseconds: 220),
                      curve: Curves.easeOut,
                      child: _signUp
                          ? Column(children: [
                              _field(_name, 'Full name', CupertinoIcons.person_fill, TextInputType.name),
                              Divider(height: 1, thickness: 0.5, color: c.separator, indent: 32),
                            ])
                          : const SizedBox(width: double.infinity),
                    ),
                    _field(_email, 'Email', CupertinoIcons.mail_solid, TextInputType.emailAddress),
                    Divider(height: 1, thickness: 0.5, color: c.separator, indent: 32),
                    _field(_password, 'Password', CupertinoIcons.lock_fill, TextInputType.visiblePassword,
                        obscure: _hide,
                        suffix: CupertinoButton(
                          padding: EdgeInsets.zero,
                          minimumSize: const Size(32, 32),
                          onPressed: () => setState(() => _hide = !_hide),
                          child: Icon(_hide ? CupertinoIcons.eye : CupertinoIcons.eye_slash,
                              size: 18, color: c.textTertiary),
                        )),
                  ]),
                ),
                if (_error != null || _info != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(6, 12, 6, 0),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon(
                          _error != null
                              ? CupertinoIcons.exclamationmark_circle_fill
                              : CupertinoIcons.envelope_badge_fill,
                          size: 16,
                          color: _error != null ? AppColors.red : AppColors.green),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(_error ?? _info!,
                            style: TextStyle(fontSize: 13.5, color: _error != null ? AppColors.red : AppColors.green)),
                      ),
                    ]),
                  ),
                const SizedBox(height: 22),
                Pressable(
                  onTap: _busy ? null : _submit,
                  child: Container(
                    height: 56,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: AppColors.blue,
                      borderRadius: BorderRadius.circular(18),
                      boxShadow: const [BoxShadow(color: Color(0x550A84FF), blurRadius: 20, offset: Offset(0, 8))],
                    ),
                    child: _busy
                        ? const CupertinoActivityIndicator(color: Colors.white)
                        : Text(_signUp ? 'Create account' : 'Sign in',
                            style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600)),
                  ),
                ),
                if (widget.canSkip) ...[
                  const SizedBox(height: 8),
                  CupertinoButton(
                    onPressed: _busy ? null : _skip,
                    child: Text('Continue without an account',
                        style: TextStyle(fontSize: 15, color: c.textSecondary, fontWeight: FontWeight.w500)),
                  ),
                  Text('You can still file reports. They stay linked to this phone only.',
                      textAlign: TextAlign.center, style: T.sub(context).copyWith(fontSize: 12.5)),
                ],
              ]),
            ),
          ],
        ),
      ),
    );
  }

  Widget _field(TextEditingController ctl, String hint, IconData icon, TextInputType type,
      {bool obscure = false, Widget? suffix}) {
    final c = AppColors.of(context);
    return Row(children: [
      Icon(icon, size: 18, color: c.textTertiary),
      const SizedBox(width: 14),
      Expanded(
        child: TextField(
          controller: ctl,
          keyboardType: type,
          obscureText: obscure,
          autocorrect: false,
          enableSuggestions: !obscure,
          textCapitalization: type == TextInputType.name ? TextCapitalization.words : TextCapitalization.none,
          onSubmitted: (_) => _submit(),
          style: T.body(context),
          decoration: InputDecoration(
            border: InputBorder.none,
            hintText: hint,
            hintStyle: T.body(context).copyWith(color: c.textTertiary),
            contentPadding: const EdgeInsets.symmetric(vertical: 16),
          ),
        ),
      ),
      ?suffix,
    ]);
  }
}
