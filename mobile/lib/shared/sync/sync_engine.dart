import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/network/connectivity_provider.dart';
import 'package:conduit_mobile/features/jobs/providers.dart';
import 'package:conduit_mobile/shared/sync/sync_dispatcher.dart';
import 'package:conduit_mobile/shared/sync/sync_op.dart';
import 'package:conduit_mobile/shared/sync/sync_queue_service.dart';

/// Drains the pending sync queue when the device is online.
///
/// Triggered by:
///  - Connectivity change (offline → online)
///  - Manual `drain()` from UI (pull-to-refresh)
///  - App startup
///
/// Backoff: 2s → 4s → 8s → 16s → 32s per op retryCount.
/// Drop policy: ops with retryCount >= 5 are removed with a logged error.
class SyncEngine {
  SyncEngine(this._ref, this._queue, this._dispatcher);

  final Ref _ref;
  final SyncQueueService _queue;
  final SyncDispatcher _dispatcher;

  static const _backoffSeconds = [2, 4, 8, 16, 32];

  bool _draining = false;
  StreamSubscription<ConnectivityState>? _connectivitySub;

  /// Subscribe to connectivity transitions.
  void start() {
    _connectivitySub?.cancel();
    _connectivitySub = _ref.read(connectivityProvider.stream).listen((state) {
      if (state == ConnectivityState.online) {
        unawaited(drain());
      }
    });
    // Attempt immediate drain on startup
    unawaited(drain());
  }

  Future<void> stop() async {
    await _connectivitySub?.cancel();
  }

  /// Drain queue. Safe to call concurrently — re-entries are no-ops.
  /// Returns the number of successfully dispatched ops.
  Future<int> drain() async {
    if (_draining) return 0;
    _draining = true;
    var processed = 0;
    try {
      final ops = _queue.pendingOps;
      for (final op in ops) {
        if (op.hasExceededRetries) {
          await _queue.remove(op);
          continue;
        }

        if (op.retryCount > 0) {
          final delay = _backoffSeconds[
              (op.retryCount - 1).clamp(0, _backoffSeconds.length - 1)];
          await Future<void>.delayed(Duration(seconds: delay));
        }

        final result = await _dispatcher.dispatch(op);
        if (result.success) {
          await _queue.remove(op);
          processed++;
        } else if (!result.retryable) {
          await _queue.markFailed(op, result.error ?? 'Non-retryable error');
          await _queue.remove(op);
        } else {
          await _queue.markFailed(op, result.error ?? 'Network error');
          // Stop draining further — likely still offline
          break;
        }
      }

      if (processed > 0) {
        // Refresh jobs view so freshly-synced changes appear
        _ref.invalidate(jobsBundleProvider);
      }
    } finally {
      _draining = false;
    }
    return processed;
  }
}

/// App-scoped sync engine. Mount once via `ref.read(syncEngineProvider).start()`.
final syncEngineProvider = Provider<SyncEngine>((ref) {
  final engine = SyncEngine(
    ref,
    ref.watch(syncQueueServiceProvider),
    ref.watch(syncDispatcherProvider),
  );
  ref.onDispose(engine.stop);
  return engine;
});
