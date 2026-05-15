import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_ce_flutter/hive_flutter.dart';
import 'package:uuid/uuid.dart';
import 'package:conduit_mobile/core/storage/hive_setup.dart';
import 'package:conduit_mobile/shared/sync/sync_op.dart';

/// Manages the offline mutation queue. Drains are handled by SyncEngine
/// (turn 6 — separate provider).
///
/// Idempotency: each enqueued op carries a `clientUuid` consumed by
/// the backend M6 `/sync/push` deduplication logic.
class SyncQueueService {
  SyncQueueService(this._box, [Uuid? uuid]) : _uuid = uuid ?? const Uuid();

  final Box<SyncOp> _box;
  final Uuid _uuid;

  Future<SyncOp> enqueue({
    required String operation,
    required Map<String, dynamic> payload,
  }) async {
    final op = SyncOp(
      clientUuid: _uuid.v4(),
      clientTimestamp: DateTime.now().toUtc(),
      operation: operation,
      payload: payload,
    );
    await _box.add(op);
    return op;
  }

  int get pendingCount => _box.length;

  List<SyncOp> get pendingOps => _box.values.toList();

  Stream<int> watchPendingCount() =>
      _box.watch().map((_) => _box.length).distinct();

  Future<void> markFailed(SyncOp op, String error) async {
    op
      ..retryCount += 1
      ..lastError = error;
    await op.save();
  }

  Future<void> remove(SyncOp op) => op.delete();

  Future<void> clear() => _box.clear();
}

final syncQueueServiceProvider = Provider<SyncQueueService>((ref) {
  final box = Hive.box<SyncOp>(HiveSetup.syncQueueBox);
  return SyncQueueService(box);
});

/// Reactive count for UI badges/indicators.
final pendingSyncCountProvider = StreamProvider<int>((ref) {
  return ref.watch(syncQueueServiceProvider).watchPendingCount();
});
