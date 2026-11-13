import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// iOS-inspired design tokens. Light + dark aware via [AppColors.of].
class AppColors {
  final Color bg, card, cardAlt, text, textSecondary, textTertiary, separator, fill;
  const AppColors._(this.bg, this.card, this.cardAlt, this.text, this.textSecondary, this.textTertiary,
      this.separator, this.fill);

  static const light = AppColors._(
    Color(0xFFF2F2F7), Colors.white, Color(0xFFF7F7FA), Color(0xFF0B0B0F), Color(0xFF6E6E73),
    Color(0xFFAEAEB2), Color(0x1F3C3C43), Color(0x14767680),
  );
  static const dark = AppColors._(
    Color(0xFF000000), Color(0xFF1C1C1E), Color(0xFF2C2C2E), Color(0xFFF5F5F7), Color(0xFF98989F),
    Color(0xFF636366), Color(0x33545458), Color(0x3D767680),
  );

  static AppColors of(BuildContext c) => Theme.of(c).brightness == Brightness.dark ? dark : light;

  static const blue = Color(0xFF0A84FF);
  static const indigo = Color(0xFF5E5CE6);
  static const green = Color(0xFF30D158);
  static const orange = Color(0xFFFF9F0A);
  static const red = Color(0xFFFF453A);
  static const teal = Color(0xFF40C8E0);
  static const purple = Color(0xFFBF5AF2);
  static const yellow = Color(0xFFFFD60A);
}

class Category {
  final String key, label, hint, photo;
  final IconData icon;
  final Color color;
  const Category(this.key, this.label, this.hint, this.icon, this.color, this.photo);

  /// Real road photo for this kind of damage (square crop for tiles, full frame for headers).
  String get thumb => 'assets/photos/${photo}_sq.jpg';
  String get image => 'assets/photos/$photo.jpg';
}

const categories = [
  Category('pothole', 'Pothole', 'Holes or craters', CupertinoIcons.circle_grid_hex_fill, AppColors.orange, 'pothole'),
  Category('crack', 'Cracks', 'Surface cracking', CupertinoIcons.bolt_fill, AppColors.yellow, 'crack'),
  Category('waterlogging', 'Waterlogging', 'Flooded stretch', CupertinoIcons.drop_fill, AppColors.teal, 'waterlogging'),
  Category('broken_road', 'Broken road', 'Caved or washed out', CupertinoIcons.exclamationmark_triangle_fill,
      AppColors.red, 'broken_road'),
  Category('other', 'Other', 'Open manhole, debris', CupertinoIcons.ellipsis_circle_fill, AppColors.purple, 'other'),
];

Category categoryOf(String key) => categories.firstWhere((c) => c.key == key, orElse: () => categories.last);

class StatusStyle {
  final String label;
  final Color color;
  final IconData icon;
  const StatusStyle(this.label, this.color, this.icon);
}

const statusOrder = ['submitted', 'in_review', 'in_progress', 'resolved'];

StatusStyle statusStyle(String s) => switch (s) {
      'in_review' => const StatusStyle('In review', AppColors.indigo, CupertinoIcons.eye_fill),
      'in_progress' => const StatusStyle('Repair underway', AppColors.orange, CupertinoIcons.hammer_fill),
      'resolved' => const StatusStyle('Resolved', AppColors.green, CupertinoIcons.checkmark_seal_fill),
      'rejected' => const StatusStyle('Closed', AppColors.red, CupertinoIcons.xmark_circle_fill),
      _ => const StatusStyle('Submitted', AppColors.blue, CupertinoIcons.paperplane_fill),
    };

ThemeData buildTheme(Brightness b) {
  final c = b == Brightness.dark ? AppColors.dark : AppColors.light;
  final base = ThemeData(brightness: b, useMaterial3: true);
  final text = GoogleFonts.interTextTheme(base.textTheme).apply(bodyColor: c.text, displayColor: c.text);
  return base.copyWith(
    scaffoldBackgroundColor: c.bg,
    colorScheme: ColorScheme.fromSeed(seedColor: AppColors.blue, brightness: b, surface: c.card),
    textTheme: text,
    splashFactory: NoSplash.splashFactory,
    highlightColor: Colors.transparent,
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: CupertinoPageTransitionsBuilder(),
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
    }),
    cupertinoOverrideTheme: CupertinoThemeData(
      brightness: b,
      primaryColor: AppColors.blue,
      textTheme: CupertinoTextThemeData(textStyle: GoogleFonts.inter(fontSize: 16, color: c.text)),
    ),
  );
}

class T {
  static TextStyle largeTitle(BuildContext c) =>
      TextStyle(fontSize: 34, fontWeight: FontWeight.w800, letterSpacing: -1.1, color: AppColors.of(c).text);
  static TextStyle title(BuildContext c) =>
      TextStyle(fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: -0.6, color: AppColors.of(c).text);
  static TextStyle headline(BuildContext c) =>
      TextStyle(fontSize: 17, fontWeight: FontWeight.w600, letterSpacing: -0.3, color: AppColors.of(c).text);
  static TextStyle body(BuildContext c) =>
      TextStyle(fontSize: 16, height: 1.35, letterSpacing: -0.2, color: AppColors.of(c).text);
  static TextStyle sub(BuildContext c) =>
      TextStyle(fontSize: 14, height: 1.3, letterSpacing: -0.1, color: AppColors.of(c).textSecondary);
  static TextStyle caption(BuildContext c) => TextStyle(
      fontSize: 12, fontWeight: FontWeight.w600, letterSpacing: 0.2, color: AppColors.of(c).textSecondary);
}
