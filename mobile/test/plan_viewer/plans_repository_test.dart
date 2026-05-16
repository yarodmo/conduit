import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_ce/hive.dart';
import 'package:mocktail/mocktail.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:retrofit/retrofit.dart';
import 'package:conduit_mobile/features/plan_viewer/data/plans_api.dart';
import 'package:conduit_mobile/features/plan_viewer/data/plans_repository.dart';

class _MockPlansApi extends Mock implements PlansApi {}

class _FakePathProvider extends PathProviderPlatform {
  @override
  Future<String?> getApplicationDocumentsPath() async => '.';
  @override
  Future<String?> getTemporaryPath() async => '.';
}

void main() {
  late PlansRepository repo;
  late _MockPlansApi api;
  late Box<List<int>> cacheBox;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    PathProviderPlatform.instance = _FakePathProvider();
    Hive.init('.');
  });

  setUp(() async {
    final boxName =
        'test_plans_cache_${DateTime.now().microsecondsSinceEpoch}';
    cacheBox = await Hive.openBox<List<int>>(boxName);
    api = _MockPlansApi();
    repo = PlansRepository(api, cacheBox);
  });

  tearDown(() async {
    await cacheBox.deleteFromDisk();
  });

  test('fetchTile returns cached bytes without hitting API', () async {
    final bytes = Uint8List.fromList([1, 2, 3, 4]);
    await cacheBox.put('plan-1/1/0/0/0', bytes);

    final result = await repo.fetchTile(planId: 'plan-1', page: 1);
    expect(result, bytes);
    verifyNever(() => api.getTile(any(), any(), any(), any(), any()));
  });

  test('fetchTile hits API on cache miss + persists to cache', () async {
    final body = [9, 8, 7];
    when(() => api.getTile('plan-1', 2, 0, 0, 0)).thenAnswer(
      (_) async => HttpResponse(
        body,
        Response(
          requestOptions: RequestOptions(path: ''),
          statusCode: 200,
        ),
      ),
    );

    final result = await repo.fetchTile(planId: 'plan-1', page: 2);
    expect(result, Uint8List.fromList(body));
    expect(cacheBox.get('plan-1/2/0/0/0'), body);
  });

  test('fetchTile throws PlanCacheMissException on network error', () async {
    when(() => api.getTile('plan-1', 3, 0, 0, 0)).thenThrow(
      DioException(
        requestOptions: RequestOptions(path: ''),
        type: DioExceptionType.connectionError,
      ),
    );
    expect(
      () => repo.fetchTile(planId: 'plan-1', page: 3),
      throwsA(isA<PlanCacheMissException>()),
    );
  });

  test('isPageCached reflects cache state', () async {
    expect(repo.isPageCached(planId: 'plan-1', page: 1), isFalse);
    await cacheBox.put('plan-1/1/0/0/0', [1]);
    expect(repo.isPageCached(planId: 'plan-1', page: 1), isTrue);
  });

  test('evictPlan removes all keys for that plan', () async {
    await cacheBox.put('plan-1/1/0/0/0', [1]);
    await cacheBox.put('plan-1/2/0/0/0', [2]);
    await cacheBox.put('plan-2/1/0/0/0', [3]);

    await repo.evictPlan('plan-1');

    expect(cacheBox.containsKey('plan-1/1/0/0/0'), isFalse);
    expect(cacheBox.containsKey('plan-1/2/0/0/0'), isFalse);
    expect(cacheBox.containsKey('plan-2/1/0/0/0'), isTrue);
  });

  test('precachePlan attempts each page and counts successes', () async {
    when(() => api.getTile('plan-x', any(), 0, 0, 0)).thenAnswer(
      (_) async => HttpResponse(
        [1],
        Response(
          requestOptions: RequestOptions(path: ''),
          statusCode: 200,
        ),
      ),
    );

    final ok = await repo.precachePlan('plan-x', 3);
    expect(ok, 3);
    expect(repo.isPageCached(planId: 'plan-x', page: 1), isTrue);
    expect(repo.isPageCached(planId: 'plan-x', page: 3), isTrue);
  });
}
