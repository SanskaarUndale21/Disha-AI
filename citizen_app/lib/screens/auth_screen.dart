import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';
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
      setState(() => _error = 'Enter a valid email and a password of at least 6 characters.');
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
          setState(() => (_info = 'We sent a link to $email. Open it to confirm, then sign in here.', _signUp = false));
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
      setState(() => _error = 'Sign-in is unreachable. Check your internet connection and try again.');
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
              height: 300 + top,
              child: Stack(fit: StackFit.expand, children: [
                Image.asset('assets/photos/street.jpg', fit: BoxFit.cover),
                const DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [Color(0x55000000), Color(0x00000000), Color(0xE61F2326)],
                      stops: [0, 0.35, 1],
                    ),
                  ),
                ),
                Positioned(
                  top: top + 16,
                  left: 20,
                  child: const SignPlate(
                    face: Palette.asphalt,
                    legend: Colors.white,
                    radius: 10,
                    padding: EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                    child: Text('RoadWatch',
                        style: TextStyle(
                            fontFamily: fontDisplay, fontSize: 22, fontWeight: FontWeight.w800, color: Colors.white)),
                  ),
                ),
                if (!widget.canSkip)
                  Positioned(
                    top: top + 16,
                    right: 16,
                    child: Pressable(
                      onTap: () => Navigator.pop(context),
                      child: Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(color: Palette.asphalt, borderRadius: BorderRadius.circular(12)),
                        child: const Icon(PhosphorIconsBold.x, color: Colors.white, size: 20, semanticLabel: 'Close'),
                      ),
                    ),
                  ),
                const Positioned(
                  left: 20,
                  right: 20,
                  bottom: 22,
                  child: Text('Report bad roads.\nTrack every repair.',
                      style: TextStyle(
                          fontFamily: fontDisplay, fontSize: 38, height: 1.02, fontWeight: FontWeight.w800, color: Colors.white)),
                ),
              ]),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 22, 20, 28),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  _modeTab(false, 'Sign in'),
                  _modeTab(true, 'Create account'),
                ]),
                Divider(height: 1, thickness: 1, color: c.line),
                const SizedBox(height: 18),
                AnimatedSize(
                  duration: const Duration(milliseconds: 200),
                  curve: Curves.easeOut,
                  alignment: Alignment.topCenter,
                  child: _signUp
                      ? Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: _field(_name, 'Full name', PhosphorIconsBold.user, TextInputType.name),
                        )
                      : const SizedBox(width: double.infinity),
                ),
                _field(_email, 'Email', PhosphorIconsBold.envelopeSimple, TextInputType.emailAddress),
                const SizedBox(height: 10),
                _field(_password, 'Password', PhosphorIconsBold.lockSimple, TextInputType.visiblePassword,
                    obscure: _hide,
                    suffix: IconButton(
                      onPressed: () => setState(() => _hide = !_hide),
                      tooltip: _hide ? 'Show password' : 'Hide password',
                      icon: Icon(_hide ? PhosphorIconsBold.eye : PhosphorIconsBold.eyeSlash, size: 20, color: c.inkSoft),
                    )),
                if (_error != null || _info != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon(_error != null ? PhosphorIconsFill.warningCircle : PhosphorIconsFill.envelopeSimpleOpen,
                          size: 18, color: _error != null ? Palette.red : Palette.green),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(_error ?? _info!,
                            style: TextStyle(fontSize: 14.5, color: _error != null ? Palette.red : Palette.green)),
                      ),
                    ]),
                  ),
                const SizedBox(height: 20),
                YellowButton(
                  label: _signUp ? 'Create account' : 'Sign in',
                  icon: _signUp ? PhosphorIconsBold.userPlus : PhosphorIconsBold.signIn,
                  busy: _busy,
                  onTap: _submit,
                ),
                if (widget.canSkip) ...[
                  const SizedBox(height: 10),
                  CupertinoButton(
                    onPressed: _busy ? null : _skip,
                    child: Text('Continue without an account',
                        style: TextStyle(
                            fontSize: 16,
                            color: c.ink,
                            fontWeight: FontWeight.w600,
                            decoration: TextDecoration.underline,
                            decorationColor: Palette.yellow,
                            decorationThickness: 2.5)),
                  ),
                  Text('You can still report damage. Your reports stay on this phone.',
                      textAlign: TextAlign.center, style: T.small(context)),
                ],
              ]),
            ),
          ],
        ),
      ),
    );
  }

  Widget _modeTab(bool signUp, String label) {
    final c = AppColors.of(context);
    final active = _signUp == signUp;
    return Pressable(
      onTap: () => setState(() => (_signUp = signUp, _error = null)),
      child: Padding(
        padding: const EdgeInsets.only(right: 24),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label,
              style: TextStyle(
                  fontSize: 17, fontWeight: active ? FontWeight.w700 : FontWeight.w500, color: active ? c.ink : c.inkFaint)),
          const SizedBox(height: 8),
          AnimatedContainer(
              duration: const Duration(milliseconds: 180), height: 3, width: active ? 32 : 0, color: Palette.yellow),
        ]),
      ),
    );
  }

  Widget _field(TextEditingController ctl, String hint, IconData icon, TextInputType type,
      {bool obscure = false, Widget? suffix}) {
    final c = AppColors.of(context);
    return TextField(
      controller: ctl,
      keyboardType: type,
      obscureText: obscure,
      autocorrect: false,
      enableSuggestions: !obscure,
      textCapitalization: type == TextInputType.name ? TextCapitalization.words : TextCapitalization.none,
      onSubmitted: (_) => _submit(),
      style: T.body(context),
      decoration: InputDecoration(
        filled: true,
        fillColor: c.surface,
        prefixIcon: Icon(icon, size: 20, color: c.inkSoft),
        suffixIcon: suffix,
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
