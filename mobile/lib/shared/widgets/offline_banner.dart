import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/config/theme.dart';
import 'package:conduit_mobile/core/network/connectivity_provider.dart';
import 'package:conduit_mobile/shared/sync/sync_queue_service.dart';

/// Persistent banner showing offline + pending sync state.
///
/// States:
///  - 🟢 Live           → hidden (online + queue empty)
///  - 🟡 Syncing...     → online + non-empty queue (sync engine working)
///  - 🟡 Offline — N    → offline + pending changes
class OfflineBanner extends ConsumerWidget {
  const OfflineBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isOnline = ref.watch(isOnlineProvider);
    final pending = ref.watch(pendingSyncCountProvider).asData?.value ?? 0;

    if (isOnline && pending == 0) return const SizedBox.shrink();

    final (label, color, icon) = isOnline
        ? ('Syncing $pending pending changes…', Colors.blue.shade700,
            Icons.sync)
        : (
            'Working offline — $pending changes pending',
            ConduitTheme.warningYellow.withValues(alpha: 0.95),
            Icons.cloud_off_outlined,
          );

    return Material(
      color: color,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(
            children: [
              Icon(icon, color: Colors.black87, size: 20),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    color: Colors.black87,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
