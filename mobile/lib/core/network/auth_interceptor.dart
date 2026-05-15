import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/config/env.dart';
import 'package:conduit_mobile/core/storage/secure_storage_service.dart';

/// Injects `Authorization: Bearer <jwt>` and refreshes on 401.
///
/// On refresh failure: clears tokens, propagates 401 so the auth guard
/// in go_router redirects to /login.
class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._ref);

  final Ref _ref;
  bool _refreshing = false;

  SecureStorageService get _storage => _ref.read(secureStorageProvider);

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final token = await _storage.readAccessToken();
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode != 401 || _refreshing) {
      return handler.next(err);
    }
    _refreshing = true;
    try {
      final refreshToken = await _storage.readRefreshToken();
      if (refreshToken == null) {
        await _storage.clearAll();
        return handler.next(err);
      }

      final refreshDio = Dio(BaseOptions(baseUrl: Env.apiBaseUrl));
      final resp = await refreshDio.post<Map<String, dynamic>>(
        '/api/v1/refresh',
        data: {'refresh_token': refreshToken},
      );

      final newAccess = resp.data?['access_token'] as String?;
      final newRefresh = resp.data?['refresh_token'] as String?;
      if (newAccess == null || newRefresh == null) {
        await _storage.clearAll();
        return handler.next(err);
      }
      await _storage.saveTokens(
        accessToken: newAccess,
        refreshToken: newRefresh,
      );

      // Retry original request with new token
      final retryOptions = err.requestOptions
        ..headers['Authorization'] = 'Bearer $newAccess';
      final retried = await Dio(BaseOptions(baseUrl: Env.apiBaseUrl))
          .fetch<dynamic>(retryOptions);
      return handler.resolve(retried);
    } on DioException {
      await _storage.clearAll();
      return handler.next(err);
    } finally {
      _refreshing = false;
    }
  }
}
