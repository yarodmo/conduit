import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_ce/hive.dart';
import 'package:mocktail/mocktail.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:uuid/uuid.dart';
import 'package:conduit_mobile/core/network/connectivity_provider.dart';
import 'package:conduit_mobile/features/jobs/data/jobs_repository.dart';
import 'package:conduit_mobile/shared/sync/sync_dispatcher.dart';
import 'package:conduit_mobile/shared/sync/sync_engine.dart';
import 'package:conduit_mobile/shared/sync/sync_op.dart';
import 'package:conduit_mobile/shared/sync/sync_queue_service.dart';

class _MockDispatcher extends Mock implements SyncDispatcher {}

class _MockJobsRepo extends Mock implements JobsRepository {}

class _FakePathProvider extends PathProviderPlatform {
  @override
  Future<String?> getApplicationDocumentsPath() async => '.';
  @override
  Future<String?> getTemporaryPath() async => '.';
}

void main() {
  late Box<SyncOp> box;
  late SyncQueueService queue;
  late _MockDispatcher dispatcher;
  late ProviderContainer container;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    PathProviderPlatform.instance = _FakePathProvider();
    Hive.init('.');
    if (!Hive.isAdapterRegistered(1)) Hive.registerAdapter(SyncOpAdapter());
    registerFallbackValue(
      SyncOp(
        clientUuid: 'fallback',
        clientTimestamp: DateTime.now(),
        operation: 'noop',
        payload: const {},
      ),
    );
  });

  setUp(() async {
    box = await Hive.openBox<SyncOp>(
        'test_engine_${DateTime.now().microsecondsSinceEpoch}');
    queue = SyncQueueService(box, const Uuid());
    dispatcher = _MockDispatcher();
    container = ProviderContainer(
      overrides: [
        syncQueueServiceProvider.overrideWithValue(queue),
        syncDispatcherProvider.overrideWithValue(dispatcher),
        connectivityProvider.overrideWith(
          (_) => Stream.value(ConnectivityState.online),
        ),
        jobsRepositoryProvider.overrideWithValue(_MockJobsRepo()),
      ],
    );
  });

  tearDown(() async {
    container.dispose();
    await box.deleteFromDisk();
  });

  test('drain processes successful ops and removes from queue', () async {
    await queue.enqueue(operation: SyncOpType.createReport, payload: {});
    await queue.enqueue(operation: SyncOpType.updateZoneStatus, payload: {});

    when(() => dispatcher.dispatch(any()))
        .thenAnswer((_) async => const DispatchResult(success: true));

    final engine = container.read(syncEngineProvider);
    final count = await engine.drain();

    expect(count, 2);
    expect(queue.pendingCount, 0);
  });

  test('drain stops on retryable error (network still down)', () async {
    await queue.enqueue(operation: SyncOpType.createReport, payload: {});
    await queue.enqueue(operation: SyncOpType.updateZoneStatus, payload: {});

    when(() => dispatcher.dispatch(any())).thenAnswer(
      (_) async => const DispatchResult(
        success: false,
        error: 'Network unavailable',
      ),
    );

    final engine = container.read(syncEngineProvider);
    final count = await engine.drain();

    expect(count, 0);
    expect(queue.pendingCount, 2); // both still in queue
    expect(queue.pendingOps.first.retryCount, 1);
  });

  test('drain drops non-retryable (4xx) op', () async {
    await queue.enqueue(operation: SyncOpType.createReport, payload: {});

    when(() => dispatcher.dispatch(any())).thenAnswer(
      (_) async => const DispatchResult(
        success: false,
        retryable: false,
        error: 'Validation failed',
      ),
    );

    final engine = container.read(syncEngineProvider);
    await engine.drain();

    expect(queue.pendingCount, 0);
  });

  test('drain drops ops that have exceeded retry limit', () async {
    final op = await queue.enqueue(
      operation: SyncOpType.createReport,
      payload: {},
    );
    // Manually exhaust retries
    for (var i = 0; i < 5; i++) {
      await queue.markFailed(op, 'err');
    }
    expect(op.hasExceededRetries, isTrue);

    when(() => dispatcher.dispatch(any()))
        .thenAnswer((_) async => const DispatchResult(success: true));

    final engine = container.read(syncEngineProvider);
    await engine.drain();

    // Op should have been removed without dispatching
    expect(queue.pendingCount, 0);
  });

  test('drain is re-entrant safe', () async {
    await queue.enqueue(operation: SyncOpType.createReport, payload: {});
    when(() => dispatcher.dispatch(any()))
        .thenAnswer((_) async => const DispatchResult(success: true));

    final engine = container.read(syncEngineProvider);
    final results = await Future.wait([engine.drain(), engine.drain()]);
    // Only one drain processes (other returns 0)
    expect(results.reduce((a, b) => a + b), 1);
  });
}
