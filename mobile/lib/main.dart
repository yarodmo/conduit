import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/app.dart';
import 'package:conduit_mobile/core/storage/hive_setup.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await HiveSetup.initialize();
  runApp(const ProviderScope(child: ConduitApp()));
}
