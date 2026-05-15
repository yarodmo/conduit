import 'package:flutter_test/flutter_test.dart';
import 'package:hive_ce/hive.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:conduit_mobile/shared/sync/sync_op.dart';
import 'package:conduit_mobile/shared/sync/sync_queue_service.dart';
import 'package:uuid/uuid.dart';

class _FakePathProvider extends PathProviderPlatform {
  @override
  Future<String?> getApplicationDocumentsPath() async => '.';
  @override
  Future<String?> getTemporaryPath() async => '.';
}

void main() {
  late Box<SyncOp> box;
  late SyncQueueService service;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    PathProviderPlatform.instance = _FakePathProvider();
    Hive.init('.');
    if (!Hive.isAdapterRegistered(1)) {
      Hive.registerAdapter(SyncOpAdapter());
    }
  });

  setUp(() async {
    box = await Hive.openBox<SyncOp>('test_sync_queue_${const Uuid().v4()}');
    service = SyncQueueService(box, const Uuid());
  });

  tearDown(() async {
    await box.deleteFromDisk();
  });

  test('enqueue stores op with generated client uuid', () async {
    final op = await service.enqueue(
      operation: SyncOpType.createReport,
      payload: {'zone_id': 'z1', 'progress_pct': 50},
    );

    expect(op.clientUuid, isNotEmpty);
    expect(op.operation, SyncOpType.createReport);
    expect(op.payload['zone_id'], 'z1');
    expect(op.retryCount, 0);
    expect(service.pendingCount, 1);
  });

  test('pending count tracks enqueued ops', () async {
    expect(service.pendingCount, 0);
    await service.enqueue(operation: 'op1', payload: {});
    await service.enqueue(operation: 'op2', payload: {});
    await service.enqueue(operation: 'op3', payload: {});
    expect(service.pendingCount, 3);
  });

  test('markFailed increments retryCount and stores error', () async {
    final op = await service.enqueue(operation: 'op', payload: {});
    await service.markFailed(op, 'Network timeout');

    expect(op.retryCount, 1);
    expect(op.lastError, 'Network timeout');
  });

  test('hasExceededRetries true after 5 retries', () async {
    final op = await service.enqueue(operation: 'op', payload: {});
    for (var i = 0; i < 5; i++) {
      await service.markFailed(op, 'err');
    }
    expect(op.hasExceededRetries, isTrue);
  });

  test('remove deletes op from box', () async {
    final op = await service.enqueue(operation: 'op', payload: {});
    expect(service.pendingCount, 1);
    await service.remove(op);
    expect(service.pendingCount, 0);
  });

  test('clear empties the queue', () async {
    await service.enqueue(operation: 'a', payload: {});
    await service.enqueue(operation: 'b', payload: {});
    await service.clear();
    expect(service.pendingCount, 0);
  });

  test('client uuids are unique across enqueues', () async {
    final op1 = await service.enqueue(operation: 'op', payload: {});
    final op2 = await service.enqueue(operation: 'op', payload: {});
    expect(op1.clientUuid, isNot(op2.clientUuid));
  });
}
