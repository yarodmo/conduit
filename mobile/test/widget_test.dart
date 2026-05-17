// Smoke test — verifies the app entry compiles and the theme is wired.
//
// Full app render requires Hive bootstrap (see test/router/auth_guard_test.dart
// for full router + auth flow coverage).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:conduit_mobile/core/config/theme.dart';

void main() {
  test('Conduit theme exposes light and dark', () {
    expect(ConduitTheme.light, isA<ThemeData>());
    expect(ConduitTheme.dark, isA<ThemeData>());
    expect(ConduitTheme.primaryBlue, equals(const Color(0xFF1E3A5F)));
  });

  test('Conduit theme buttons enforce minimum 56px height (anti-Procore)', () {
    final btnTheme = ConduitTheme.light.elevatedButtonTheme.style;
    final minSize = btnTheme?.minimumSize?.resolve({}) ?? Size.zero;
    expect(minSize.height, greaterThanOrEqualTo(56));
  });
}
