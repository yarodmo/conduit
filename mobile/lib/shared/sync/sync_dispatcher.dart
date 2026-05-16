import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/network/dio_client.dart';
import 'package:conduit_mobile/shared/sync/sync_op.dart';

/// Result of executing a single sync operation.
class DispatchResult {
  const DispatchResult({required this.success, this.error, this.retryable = true});

  /// Operation succeeded — remove from queue.
  final bool success;

  /// Human-readable error message (stored on the op when failed).
  final String? error;

  /// True if the op should remain in queue for retry; false to drop.
  final bool retryable;
}

/// Translates a SyncOp into the matching backend HTTP call.
///
/// Uses the shared Dio client (with auth + org_id interceptors), so each
/// retry automatically carries the current user's JWT + org context.
class SyncDispatcher {
  SyncDispatcher(this._dio);

  final Dio _dio;

  Future<DispatchResult> dispatch(SyncOp op) async {
    try {
      switch (op.operation) {
        case SyncOpType.createReport:
          await _createReport(op);
        case SyncOpType.updateZoneStatus:
          await _updateZoneStatus(op);
        case SyncOpType.registerFcmToken:
          await _registerFcmToken(op);
        default:
          return DispatchResult(
            success: false,
            retryable: false,
            error: 'Unknown operation: ${op.operation}',
          );
      }
      return const DispatchResult(success: true);
    } on DioException catch (e) {
      final isNetwork = e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.receiveTimeout;
      final status = e.response?.statusCode;
      // 4xx (except 401 already auto-refreshed) = validation error — drop
      final isFatalClient =
          status != null && status >= 400 && status < 500 && status != 401;
      return DispatchResult(
        success: false,
        retryable: isNetwork || !isFatalClient,
        error: e.response?.data?.toString() ?? e.message ?? 'Dio error',
      );
    } on Exception catch (e) {
      return DispatchResult(success: false, error: e.toString());
    }
  }

  Future<void> _createReport(SyncOp op) async {
    final projectId = op.payload['project_id'] as String;
    final zoneId = op.payload['zone_id'] as String;
    final body = op.payload['body'] as Map<dynamic, dynamic>;
    await _dio.post<dynamic>(
      '/api/v1/projects/$projectId/zones/$zoneId/reports',
      data: body,
    );
  }

  Future<void> _updateZoneStatus(SyncOp op) async {
    final projectId = op.payload['project_id'] as String;
    final zoneId = op.payload['zone_id'] as String;
    await _dio.patch<dynamic>(
      '/api/v1/projects/$projectId/zones/$zoneId/status',
      data: {
        'status': op.payload['status'],
        if (op.payload['blocked_reason'] != null)
          'blocked_reason': op.payload['blocked_reason'],
      },
    );
  }

  Future<void> _registerFcmToken(SyncOp op) async {
    await _dio.post<dynamic>('/api/v1/devices/fcm-token', data: op.payload);
  }
}

final syncDispatcherProvider = Provider<SyncDispatcher>(
  (ref) => SyncDispatcher(ref.watch(dioProvider)),
);
