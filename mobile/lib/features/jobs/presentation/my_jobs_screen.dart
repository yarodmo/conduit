import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:conduit_mobile/features/auth/providers.dart';
import 'package:conduit_mobile/features/jobs/data/jobs_repository.dart';
import 'package:conduit_mobile/features/jobs/providers.dart';
import 'package:conduit_mobile/features/jobs/presentation/widgets/project_section.dart';
import 'package:conduit_mobile/shared/widgets/offline_banner.dart';
import 'package:conduit_mobile/shared/widgets/sync_status_indicator.dart';

class MyJobsScreen extends ConsumerWidget {
  const MyJobsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final jobsAsync = ref.watch(jobsBundleProvider);
    final user = ref.watch(authControllerProvider).asData?.value;

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Jobs'),
        actions: [
          const SyncStatusIndicator(),
          IconButton(
            icon: const Icon(Icons.assignment_outlined),
            tooltip: 'RFIs',
            onPressed: () => context.push('/rfis'),
          ),
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
            child: RefreshIndicator(
              onRefresh: () async {
                ref.invalidate(jobsBundleProvider);
                await ref.read(jobsBundleProvider.future);
              },
              child: jobsAsync.when(
                loading: () => const _LoadingView(),
                error: (e, _) => _ErrorView(
                  error: e,
                  onRetry: () => ref.invalidate(jobsBundleProvider),
                ),
                data: (bundle) => bundle.isEmpty
                    ? _EmptyView(userName: user?.fullName)
                    : _JobsList(bundle: bundle),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LoadingView extends StatelessWidget {
  const _LoadingView();

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: const [
        SizedBox(height: 100),
        Center(child: CircularProgressIndicator()),
        SizedBox(height: 16),
        Center(child: Text('Loading your jobs…')),
      ],
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.error, required this.onRetry});
  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 80),
        Icon(Icons.cloud_off,
            size: 64, color: Theme.of(context).hintColor),
        const SizedBox(height: 16),
        const Text(
          'Could not load your jobs',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        Text(
          error.toString(),
          textAlign: TextAlign.center,
          style: TextStyle(color: Theme.of(context).hintColor),
        ),
        const SizedBox(height: 24),
        Center(
          child: FilledButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Try again'),
          ),
        ),
      ],
    );
  }
}

class _EmptyView extends StatelessWidget {
  const _EmptyView({this.userName});
  final String? userName;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 80),
        Icon(Icons.work_off_outlined,
            size: 64, color: Theme.of(context).hintColor),
        const SizedBox(height: 16),
        Text(
          userName != null
              ? 'No zones assigned yet, $userName'
              : 'No zones assigned yet',
          textAlign: TextAlign.center,
          style:
              const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        Text(
          'Your project manager will assign zones from the web app. '
          'You will receive a push notification when a zone is assigned.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Theme.of(context).hintColor),
        ),
      ],
    );
  }
}

class _JobsList extends ConsumerWidget {
  const _JobsList({required this.bundle});

  final JobsBundle bundle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView.builder(
      itemCount: bundle.projects.length,
      itemBuilder: (context, index) {
        final project = bundle.projects[index];
        final zones = bundle.zonesByProject[project.id]!;
        return ProjectSection(
          project: project,
          zones: zones,
          onZoneTap: (zone) => context.push('/zones/${zone.id}'),
        );
      },
    );
  }
}
