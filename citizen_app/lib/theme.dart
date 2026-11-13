import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';

/// Design language: Indian road infrastructure.
/// Asphalt, concrete, thermoplastic lane yellow, highway-sign green, info-sign blue, hazard red.
/// Typeface: Barlow (drawn from highway signage); condensed cut for headings.
class Palette {
  static const asphalt = Color(0xFF1F2326);
  static const asphaltSoft = Color(0xFF2C3135);
  static const yellow = Color(0xFFFFC20E);
  static const yellowDeep = Color(0xFFE5A900);
  static const green = Color(0xFF0B6B4A);
  static const blue = Color(0xFF1F5FAD);
  static const red = Color(0xFFD52B2B);
  static const white = Color(0xFFFFFFFF);
}

class AppColors {
  final Color bg, surface, raised, ink, inkSoft, inkFaint, line, fill;
  const AppColors._(this.bg, this.surface, this.raised, this.ink, this.inkSoft, this.inkFaint, this.line, this.fill);

  static const light = AppColors._(
    Color(0xFFECEDEE), // concrete
    Color(0xFFFFFFFF),
    Color(0xFFF6F7F7),
    Color(0xFF15181A),
    Color(0xFF575F66),
    Color(0xFF8A9299),
    Color(0xFFD9DCDF),
    Color(0xFFE4E6E8),
  );
  static const dark = AppColors._(
    Color(0xFF16191B), // night asphalt
    Color(0xFF212528),
    Color(0xFF2A2F33),
    Color(0xFFF1F2F3),
    Color(0xFFA9B0B6),
    Color(0xFF737B82),
    Color(0xFF353A3F),
    Color(0xFF30353A),
  );

  static AppColors of(BuildContext c) => Theme.of(c).brightness == Brightness.dark ? dark : light;
}

class Category {
  final String key, label, hint, photo;
  final IconData icon;
  const Category(this.key, this.label, this.hint, this.photo, this.icon);
  String get thumb => 'assets/photos/${photo}_sq.jpg';
}

final categories = [
  Category('pothole', 'Pothole', 'A hole or crater in the road', 'pothole', PhosphorIconsBold.circleDashed),
  Category('crack', 'Cracks', 'Cracked or split surface', 'crack', PhosphorIconsBold.lightning),
  Category('waterlogging', 'Waterlogging', 'Water standing on the road', 'waterlogging', PhosphorIconsBold.drop),
  Category('broken_road', 'Broken edge', 'Road edge or surface caved in', 'broken_road', PhosphorIconsBold.warning),
  Category('other', 'Something else', 'Open manhole, debris, anything', 'other', PhosphorIconsBold.dotsThreeCircle),
];

Category categoryOf(String key) => categories.firstWhere((c) => c.key == key, orElse: () => categories.last);

class StatusStyle {
  final String label, step;
  final Color color;
  final IconData icon;
  const StatusStyle(this.label, this.step, this.color, this.icon);
}

const statusOrder = ['submitted', 'in_review', 'in_progress', 'resolved'];

StatusStyle statusStyle(String s) => switch (s) {
      'in_review' => const StatusStyle('Being reviewed', 'Review', Palette.blue, PhosphorIconsBold.magnifyingGlass),
      'in_progress' => const StatusStyle('Repair crew assigned', 'Repair', Palette.yellowDeep, PhosphorIconsBold.hardHat),
      'resolved' => const StatusStyle('Fixed', 'Fixed', Palette.green, PhosphorIconsBold.checkCircle),
      'rejected' => const StatusStyle('Closed', 'Closed', Palette.red, PhosphorIconsBold.xCircle),
      _ => const StatusStyle('Received', 'Received', Color(0xFF5B636A), PhosphorIconsBold.paperPlaneTilt),
    };

const fontBody = 'Barlow';
const fontDisplay = 'BarlowCondensed';

ThemeData buildTheme(Brightness b) {
  final c = b == Brightness.dark ? AppColors.dark : AppColors.light;
  final base = ThemeData(brightness: b, useMaterial3: true, fontFamily: fontBody);
  return base.copyWith(
    scaffoldBackgroundColor: c.bg,
    colorScheme: ColorScheme.fromSeed(
      seedColor: Palette.yellow,
      brightness: b,
      primary: b == Brightness.dark ? Palette.yellow : Palette.asphalt,
      surface: c.surface,
    ),
    textTheme: base.textTheme.apply(bodyColor: c.ink, displayColor: c.ink, fontFamily: fontBody),
    splashFactory: NoSplash.splashFactory,
    highlightColor: Colors.transparent,
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: c.ink,
      selectionColor: Palette.yellow.withValues(alpha: 0.45),
      selectionHandleColor: Palette.yellowDeep,
    ),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: CupertinoPageTransitionsBuilder(),
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
    }),
    cupertinoOverrideTheme: CupertinoThemeData(
      brightness: b,
      primaryColor: c.ink,
      textTheme: CupertinoTextThemeData(textStyle: TextStyle(fontFamily: fontBody, fontSize: 16, color: c.ink)),
    ),
  );
}

/// Type scale (ratio ~1.25). Condensed for display, regular Barlow for reading.
class T {
  static TextStyle display(BuildContext c) => TextStyle(
      fontFamily: fontDisplay, fontSize: 40, height: 1.0, fontWeight: FontWeight.w800, color: AppColors.of(c).ink);
  static TextStyle h1(BuildContext c) => TextStyle(
      fontFamily: fontDisplay, fontSize: 32, height: 1.05, fontWeight: FontWeight.w800, color: AppColors.of(c).ink);
  static TextStyle h2(BuildContext c) => TextStyle(
      fontFamily: fontDisplay, fontSize: 24, height: 1.1, fontWeight: FontWeight.w700, color: AppColors.of(c).ink);
  static TextStyle h3(BuildContext c) => TextStyle(
      fontFamily: fontDisplay, fontSize: 20, height: 1.15, fontWeight: FontWeight.w700, color: AppColors.of(c).ink);
  static TextStyle body(BuildContext c) =>
      TextStyle(fontSize: 16, height: 1.45, fontWeight: FontWeight.w400, color: AppColors.of(c).ink);
  static TextStyle bodyStrong(BuildContext c) =>
      TextStyle(fontSize: 16, height: 1.35, fontWeight: FontWeight.w600, color: AppColors.of(c).ink);
  static TextStyle sub(BuildContext c) =>
      TextStyle(fontSize: 14.5, height: 1.4, fontWeight: FontWeight.w400, color: AppColors.of(c).inkSoft);
  static TextStyle small(BuildContext c) =>
      TextStyle(fontSize: 13, height: 1.35, fontWeight: FontWeight.w500, color: AppColors.of(c).inkFaint);
}
