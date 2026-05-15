import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/network/dio_client.dart';
import 'package:conduit_mobile/core/storage/secure_storage_service.dart';
import 'package:conduit_mobile/features/auth/data/auth_api.dart';
import 'package:conduit_mobile/features/auth/domain/user.dart';

class AuthException implements Exception {
  AuthException(this.message);
  final String message;

  @override
  String toString() => message;
}

class AuthRepository {
  AuthRepository(this._api, this._storage);

  final AuthApi _api;
  final SecureStorageService _storage;

  Future<User> login(String email, String password) async {
    try {
      final tokens = await _api.login(
        LoginRequest(email: email, password: password),
      );
      await _storage.saveTokens(
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
      );

      final user = await _api.me();
      await _storage.saveSession(userId: user.id, orgId: user.orgId);
      return user;
    } on DioException catch (e) {
      final detail = e.response?.data is Map
          ? (e.response!.data as Map)['detail']?.toString()
          : null;
      throw AuthException(detail ?? 'Login failed. Please try again.');
    }
  }

  Future<User?> currentUser() async {
    final token = await _storage.readAccessToken();
    if (token == null || token.isEmpty) return null;
    try {
      return await _api.me();
    } on DioException {
      await _storage.clearAll();
      return null;
    }
  }

  Future<void> logout() async {
    try {
      await _api.logout();
    } on DioException {
      // ignore — clear local state regardless
    } finally {
      await _storage.clearAll();
    }
  }
}

final authApiProvider = Provider<AuthApi>(
  (ref) => AuthApi(ref.watch(dioProvider)),
);

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    ref.watch(authApiProvider),
    ref.watch(secureStorageProvider),
  ),
);
