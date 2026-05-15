import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/config/theme.dart';
import 'package:conduit_mobile/core/router/app_router.dart';

class ConduitApp extends ConsumerWidget {
  const ConduitApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);
    return MaterialApp.router(
      title: 'Conduit',
      debugShowCheckedModeBanner: false,
      theme: ConduitTheme.light,
      darkTheme: ConduitTheme.dark,
      routerConfig: router,
    );
  }
}
