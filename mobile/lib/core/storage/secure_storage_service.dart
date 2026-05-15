import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Wraps flutter_secure_storage with Conduit's key conventions.
///
/// Stores: access_token, refresh_token, user_id, org_id.
/// NEVER store: full user PII, plain passwords.
class SecureStorageService {
  SecureStorageService(this._storage);

  static const _kAccessToken = 'conduit.access_token';
  static const _kRefreshToken = 'conduit.refresh_token';
  static const _kUserId = 'conduit.user_id';
  static const _kOrgId = 'conduit.org_id';

  final FlutterSecureStorage _storage;

  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _kAccessToken, value: accessToken);
    await _storage.write(key: _kRefreshToken, value: refreshToken);
  }

  Future<String?> readAccessToken() => _storage.read(key: _kAccessToken);
  Future<String?> readRefreshToken() => _storage.read(key: _kRefreshToken);

  Future<void> saveSession({
    required String userId,
    required String orgId,
  }) async {
    await _storage.write(key: _kUserId, value: userId);
    await _storage.write(key: _kOrgId, value: orgId);
  }

  Future<String?> readUserId() => _storage.read(key: _kUserId);
  Future<String?> readOrgId() => _storage.read(key: _kOrgId);

  Future<void> clearAll() => _storage.deleteAll();
}

final secureStorageProvider = Provider<SecureStorageService>((ref) {
  const options = AndroidOptions(encryptedSharedPreferences: true);
  const iosOptions = IOSOptions(accessibility: KeychainAccessibility.first_unlock);
  return SecureStorageService(
    const FlutterSecureStorage(aOptions: options, iOptions: iosOptions),
  );
});
