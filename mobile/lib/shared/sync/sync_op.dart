import 'package:hive_ce/hive.dart';

part 'sync_op.g.dart';

/// A pending mutation in the offline sync queue.
///
/// Each op has a `clientUuid` used by the backend for idempotent dedup
/// (M6 sync engine).
@HiveType(typeId: 1)
class SyncOp extends HiveObject {
  SyncOp({
    required this.clientUuid,
    required this.clientTimestamp,
    required this.operation,
    required this.payload,
    this.retryCount = 0,
    this.lastError,
  });

  @HiveField(0)
  String clientUuid;

  @HiveField(1)
  DateTime clientTimestamp;

  @HiveField(2)
  String operation;

  @HiveField(3)
  Map<dynamic, dynamic> payload;

  @HiveField(4)
  int retryCount;

  @HiveField(5)
  String? lastError;

  bool get hasExceededRetries => retryCount >= 5;

  @override
  String toString() =>
      'SyncOp($operation, uuid=$clientUuid, retries=$retryCount)';
}

/// Operation type constants — keep stable across versions.
class SyncOpType {
  const SyncOpType._();

  static const String createReport = 'create_report';
  static const String updateZoneStatus = 'update_zone_status';
  static const String registerFcmToken = 'register_fcm_token';
  static const String submitMarkup = 'submit_markup';
}
