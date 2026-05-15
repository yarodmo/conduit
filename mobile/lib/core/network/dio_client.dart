import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/config/env.dart';
import 'package:conduit_mobile/core/network/auth_interceptor.dart';
import 'package:conduit_mobile/core/network/org_id_interceptor.dart';

/// Single Dio instance, configured with all Conduit interceptors.
final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(
    BaseOptions(
      baseUrl: Env.apiBaseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      headers: {'Content-Type': 'application/json'},
      responseType: ResponseType.json,
    ),
  );

  dio.interceptors.addAll([
    AuthInterceptor(ref),
    OrgIdInterceptor(ref),
    if (Env.isDevelopment)
      LogInterceptor(
        request: true,
        requestBody: false,
        responseBody: false,
        error: true,
        logPrint: (obj) {
          // Replace with logger package in production
        },
      ),
  ]);

  return dio;
});
