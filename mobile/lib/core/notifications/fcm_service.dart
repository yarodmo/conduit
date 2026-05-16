import 'dart:io';

import 'package:dio/dio.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/network/dio_client.dart';

/// Push notification types emitted by backend M8.
class FcmEventType {
  const FcmEventType._();
  static const rfiAssigned = 'rfi_assigned';
  static const rfiAnswered = 'rfi_answered';
  static const rfiApproachingDeadline = 'rfi_approaching_deadline';
  static const zoneAssigned = 'zone_assigned';
  static const zoneBlocked = 'zone_blocked';
  static const takeoffCompleted = 'takeoff_completed';
  static const takeoffRequiresReview = 'takeoff_requires_review';
  static const mentionInComment = 'mention_in_comment';
  static const loginNewDevice = 'login_new_device';
}

/// Initializes Firebase Messaging, requests permission, registers token
/// with backend M8 endpoint.
///
/// Foreground messages are exposed via [foregroundMessageStream]. Background
/// + terminated handlers must be set up in main.dart (top-level functions).
class FcmService {
  FcmService(this._messaging, this._dio);

  final FirebaseMessaging _messaging;
  final Dio _dio;

  Stream<RemoteMessage> get foregroundMessageStream =>
      FirebaseMessaging.onMessage;

  Stream<RemoteMessage> get messageOpenedStream =>
      FirebaseMessaging.onMessageOpenedApp;

  Future<bool> requestPermission() async {
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );
    return settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional;
  }

  Future<String?> getToken() => _messaging.getToken();

  Future<void> registerWithBackend({String? deviceName}) async {
    final token = await getToken();
    if (token == null || token.isEmpty) return;

    try {
      await _dio.post<dynamic>(
        '/api/v1/devices/fcm-token',
        data: {
          'token': token,
          if (deviceName != null) 'device_name': deviceName,
          'platform': _platformLabel(),
        },
      );
    } on DioException {
      // Non-fatal — will retry on next app open or token rotation
    }

    _messaging.onTokenRefresh.listen((newToken) async {
      try {
        await _dio.post<dynamic>(
          '/api/v1/devices/fcm-token',
          data: {
            'token': newToken,
            'platform': _platformLabel(),
          },
        );
      } on DioException {
        // ignore
      }
    });
  }

  String _platformLabel() {
    if (Platform.isIOS) return 'ios';
    if (Platform.isAndroid) return 'android';
    return 'unknown';
  }
}

final firebaseMessagingProvider =
    Provider<FirebaseMessaging>((_) => FirebaseMessaging.instance);

final fcmServiceProvider = Provider<FcmService>(
  (ref) => FcmService(
    ref.watch(firebaseMessagingProvider),
    ref.watch(dioProvider),
  ),
);
