import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/config/theme.dart';
import 'package:conduit_mobile/core/network/connectivity_provider.dart';
import 'package:conduit_mobile/shared/sync/sync_queue_service.dart';

/// Compact icon-only indicator for app bars.
/// Three states:
///   🟢 connected, queue empty
///   🟡 connected, syncing (queue draining)
///   🔴 offline
class SyncStatusIndicator extends ConsumerWidget {
  const SyncStatusIndicator({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isOnline = ref.watch(isOnlineProvider);
    final pending = ref.watch(pendingSyncCountProvider).asData?.value ?? 0;

    final (color, tooltip) = !isOnline
        ? (ConduitTheme.errorRed, 'Offline — $pending pending')
        : pending > 0
            ? (ConduitTheme.warningYellow, 'Syncing $pending changes…')
            : (ConduitTheme.successGreen, 'Live');

    return Tooltip(
      message: tooltip,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 8),
        width: 12,
        height: 12,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      ),
    );
  }
}
