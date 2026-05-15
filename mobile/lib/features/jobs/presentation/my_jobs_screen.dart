import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/features/auth/providers.dart';
import 'package:conduit_mobile/shared/widgets/offline_banner.dart';
import 'package:conduit_mobile/shared/widgets/sync_status_indicator.dart';

/// Placeholder — fully implemented in Sprint 5 Turn 2.
class MyJobsScreen extends ConsumerWidget {
  const MyJobsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authControllerProvider).asData?.value;
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Jobs'),
        actions: [
          const SyncStatusIndicator(),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () =>
                ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
      body: Column(
        children: [
          const OfflineBanner(),
          Expanded(
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  user == null
                      ? 'Loading session…'
                      : 'Welcome, ${user.fullName}\n\nZones list — implemented in Turn 2.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 16),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
