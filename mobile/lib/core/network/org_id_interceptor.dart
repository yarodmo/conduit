import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/storage/secure_storage_service.dart';

/// Injects `X-Organization-ID` header on every request.
///
/// Backend tenant-isolation middleware reads this for org scoping.
class OrgIdInterceptor extends Interceptor {
  OrgIdInterceptor(this._ref);

  final Ref _ref;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final orgId =
        await _ref.read(secureStorageProvider).readOrgId();
    if (orgId != null && orgId.isNotEmpty) {
      options.headers['X-Organization-ID'] = orgId;
    }
    handler.next(options);
  }
}
