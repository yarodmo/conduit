import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:conduit_mobile/core/notifications/fcm_service.dart';
import 'package:conduit_mobile/features/jobs/providers.dart';
import 'package:conduit_mobile/shared/services/zone_preload_service.dart';

/// Wires FCM streams to in-app banners + deep links via go_router.
///
/// Mount this once near app startup (in main.dart after `runApp`).
class NotificationHandler {
  NotificationHandler(this._ref, this._fcm);

  final Ref _ref;
  final FcmService _fcm;

  void start(BuildContext context) {
    _fcm.foregroundMessageStream.listen((msg) => _onForegroundMessage(context, msg));
    _fcm.messageOpenedStream.listen((msg) => _onOpenedApp(context, msg));
  }

  void _onForegroundMessage(BuildContext context, RemoteMessage msg) {
    final type = msg.data['type']?.toString() ?? 'general';
    final notif = msg.notification;
    final title = notif?.title ?? _defaultTitle(type);
    final body = notif?.body ?? '';

    // Refresh jobs list when zone-related events arrive
    if (type == FcmEventType.zoneAssigned ||
        type == FcmEventType.zoneBlocked) {
      _ref.invalidate(jobsBundleProvider);
    }

    // Auto-download AI cache + plan tiles for newly assigned zones (PROMPT 9)
    if (type == FcmEventType.zoneAssigned) {
      final projectId = msg.data['project_id']?.toString();
      if (projectId != null && projectId.isNotEmpty) {
        unawaited(
          _ref.read(zonePreloadServiceProvider).preloadForProject(projectId),
        );
      }
    }

    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: const TextStyle(fontWeight: FontWeight.bold)),
            if (body.isNotEmpty)
              Text(body, maxLines: 2, overflow: TextOverflow.ellipsis),
          ],
        ),
        action: SnackBarAction(
          label: 'Open',
          onPressed: () => _openFromData(context, msg.data),
        ),
        duration: const Duration(seconds: 6),
      ),
    );
  }

  void _onOpenedApp(BuildContext context, RemoteMessage msg) {
    if (!context.mounted) return;
    _openFromData(context, msg.data);
  }

  void _openFromData(BuildContext context, Map<String, dynamic> data) {
    final type = data['type']?.toString() ?? '';
    final router = GoRouter.of(context);

    switch (type) {
      case FcmEventType.rfiAssigned:
      case FcmEventType.rfiAnswered:
      case FcmEventType.rfiApproachingDeadline:
        final rfiId = data['rfi_id'] as String?;
        if (rfiId != null) router.push('/rfis/$rfiId');
      case FcmEventType.zoneAssigned:
      case FcmEventType.zoneBlocked:
        router.go('/');
      default:
      // No-op for other types in the field tech app
    }
  }

  String _defaultTitle(String type) => switch (type) {
        FcmEventType.rfiAssigned => 'RFI assigned to you',
        FcmEventType.rfiAnswered => 'RFI answered',
        FcmEventType.rfiApproachingDeadline => 'RFI deadline approaching',
        FcmEventType.zoneAssigned => 'New zone assigned',
        FcmEventType.zoneBlocked => 'Zone blocked',
        FcmEventType.mentionInComment => 'You were mentioned',
        FcmEventType.loginNewDevice => 'New device sign-in',
        _ => 'Conduit',
      };
}

final notificationHandlerProvider = Provider<NotificationHandler>(
  (ref) => NotificationHandler(ref, ref.watch(fcmServiceProvider)),
);
