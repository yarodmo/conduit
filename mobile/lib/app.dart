import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/config/theme.dart';
import 'package:conduit_mobile/core/notifications/fcm_service.dart';
import 'package:conduit_mobile/core/notifications/notification_handler.dart';
import 'package:conduit_mobile/core/router/app_router.dart';
import 'package:conduit_mobile/features/auth/providers.dart';

class ConduitApp extends ConsumerStatefulWidget {
  const ConduitApp({super.key});

  @override
  ConsumerState<ConduitApp> createState() => _ConduitAppState();
}

class _ConduitAppState extends ConsumerState<ConduitApp> {
  @override
  void initState() {
    super.initState();
    // Register FCM token once a user is logged in.
    ref.listenManual<AsyncValue>(authControllerProvider, (prev, next) async {
      final wasAnonymous = prev?.asData?.value == null;
      final isAuthed = next.asData?.value != null;
      if (wasAnonymous && isAuthed) {
        final fcm = ref.read(fcmServiceProvider);
        final granted = await fcm.requestPermission();
        if (granted) {
          await fcm.registerWithBackend();
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(appRouterProvider);
    return MaterialApp.router(
      title: 'Conduit',
      debugShowCheckedModeBanner: false,
      theme: ConduitTheme.light,
      darkTheme: ConduitTheme.dark,
      routerConfig: router,
      builder: (context, child) => _NotificationWrapper(child: child),
    );
  }
}

/// Wires FCM streams to the app's BuildContext once a router scope exists.
class _NotificationWrapper extends ConsumerStatefulWidget {
  const _NotificationWrapper({required this.child});
  final Widget? child;

  @override
  ConsumerState<_NotificationWrapper> createState() =>
      _NotificationWrapperState();
}

class _NotificationWrapperState extends ConsumerState<_NotificationWrapper> {
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_started) {
      _started = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          ref.read(notificationHandlerProvider).start(context);
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) => widget.child ?? const SizedBox.shrink();
}
