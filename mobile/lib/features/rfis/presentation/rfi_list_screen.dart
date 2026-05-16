import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:conduit_mobile/features/rfis/data/rfis_repository.dart';
import 'package:conduit_mobile/features/rfis/presentation/widgets/rfi_card.dart';
import 'package:conduit_mobile/shared/widgets/offline_banner.dart';

class RfiListScreen extends ConsumerWidget {
  const RfiListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rfisAsync = ref.watch(myRfisProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('RFIs')),
      body: Column(
        children: [
          const OfflineBanner(),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                ref.invalidate(myRfisProvider);
                await ref.read(myRfisProvider.future);
              },
              child: rfisAsync.when(
                loading: () => const Center(
                  child: CircularProgressIndicator(),
                ),
                error: (e, _) => ListView(
                  children: [
                    const SizedBox(height: 80),
                    Center(child: Text('Could not load RFIs: $e')),
                  ],
                ),
                data: (rfis) => rfis.isEmpty
                    ? _EmptyView()
                    : ListView.builder(
                        itemCount: rfis.length,
                        itemBuilder: (_, i) => RfiCard(
                          rfi: rfis[i],
                          onTap: () => context.push('/rfis/${rfis[i].id}'),
                        ),
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyView extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 80),
        Icon(
          Icons.inbox_outlined,
          size: 64,
          color: Theme.of(context).hintColor,
        ),
        const SizedBox(height: 16),
        const Text(
          'No RFIs yet',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        Text(
          'RFIs from your projects will show here. You will receive a push '
          'notification when one is answered or assigned to you.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Theme.of(context).hintColor),
        ),
      ],
    );
  }
}
