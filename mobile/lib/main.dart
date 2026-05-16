import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/app.dart';
import 'package:conduit_mobile/core/storage/hive_setup.dart';

/// Background FCM handler — must be a top-level function annotated
/// with @pragma('vm:entry-point') for AOT compatibility.
@pragma('vm:entry-point')
Future<void> firebaseBackgroundHandler(RemoteMessage message) async {
  // Background work: trigger zone pre-fetch on `zone_assigned` push.
  // Real impl in Sprint 5 Turn 6 (sync engine integration).
  await Firebase.initializeApp();
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await HiveSetup.initialize();

  // Firebase init — graceful on misconfiguration (e.g. tests, dev without
  // google-services.json). FCM will be a no-op until configured.
  try {
    await Firebase.initializeApp();
    FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);
  } on Exception {
    // Firebase not configured — app continues without push notifications.
  }

  runApp(const ProviderScope(child: ConduitApp()));
}
