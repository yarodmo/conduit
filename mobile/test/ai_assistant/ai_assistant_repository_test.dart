import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_ce/hive.dart';
import 'package:mocktail/mocktail.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:conduit_mobile/features/ai_assistant/data/ai_assistant_api.dart';
import 'package:conduit_mobile/features/ai_assistant/data/ai_assistant_repository.dart';

class _MockApi extends Mock implements AiAssistantApi {}

class _FakePathProvider extends PathProviderPlatform {
  @override
  Future<String?> getApplicationDocumentsPath() async => '.';
  @override
  Future<String?> getTemporaryPath() async => '.';
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  PathProviderPlatform.instance = _FakePathProvider();

  late _MockApi api;
  late Box<dynamic> box;
  late AiAssistantRepository repo;

  setUpAll(() {
    registerFallbackValue(const AiAskRequest(query: ''));
    registerFallbackValue(const AiCacheRequest(projectId: ''));
  });

  setUp(() async {
    Hive.init('.');
    box = await Hive.openBox<dynamic>(
      'ai_test_${DateTime.now().microsecondsSinceEpoch}',
    );
    api = _MockApi();
    repo = AiAssistantRepository(api, box);
  });

  tearDown(() async {
    await box.close();
  });

  test('cache hit returns cached answer without calling API', () async {
    when(() => api.generateCache(any())).thenAnswer(
      (_) async => const AiCacheGenerateResponse(entries: [
        AiCacheEntry(query: 'What is the conduit gauge?', answer: 'EMT 3/4"'),
      ]),
    );
    await repo.preloadCache('proj-1');

    final response =
        await repo.ask('What is the conduit gauge?', projectId: 'proj-1');

    expect(response.fromCache, isTrue);
    expect(response.answer, 'EMT 3/4"');
    verifyNever(() => api.ask(any()));
  });

  test('cache miss calls API and returns live answer', () async {
    when(() => api.ask(any())).thenAnswer(
      (_) async => const AiAskResponse(answer: 'Use 12 AWG', cached: false),
    );

    final response = await repo.ask('What wire size?', projectId: 'proj-1');

    expect(response.fromCache, isFalse);
    expect(response.answer, 'Use 12 AWG');
    verify(() => api.ask(any())).called(1);
  });

  test('preloadCache writes all entries to Hive box', () async {
    when(() => api.generateCache(any())).thenAnswer(
      (_) async => const AiCacheGenerateResponse(entries: [
        AiCacheEntry(query: 'Q1', answer: 'A1'),
        AiCacheEntry(query: 'Q2', answer: 'A2'),
        AiCacheEntry(query: 'Q3', answer: 'A3'),
      ]),
    );

    await repo.preloadCache('proj-1');

    final r1 = await repo.ask('Q1', projectId: 'proj-1');
    final r2 = await repo.ask('Q2', projectId: 'proj-1');
    final r3 = await repo.ask('Q3', projectId: 'proj-1');

    expect(r1.fromCache, isTrue);
    expect(r1.answer, 'A1');
    expect(r2.fromCache, isTrue);
    expect(r2.answer, 'A2');
    expect(r3.fromCache, isTrue);
    expect(r3.answer, 'A3');
  });

  test('API failure returns graceful offline message', () async {
    when(() => api.ask(any())).thenThrow(
      DioException(
        requestOptions: RequestOptions(path: '/api/v1/assistant/ask'),
        type: DioExceptionType.connectionError,
      ),
    );

    final response = await repo.ask('Anything?');

    expect(response.fromCache, isFalse);
    expect(response.answer, contains('Unable to reach'));
  });

  test('cache key is case-insensitive and trims whitespace', () async {
    when(() => api.generateCache(any())).thenAnswer(
      (_) async => const AiCacheGenerateResponse(entries: [
        AiCacheEntry(query: 'How deep is the trench?', answer: '24 inches'),
      ]),
    );
    await repo.preloadCache('proj-1');

    final r1 = await repo.ask('  HOW DEEP IS THE TRENCH?  ',
        projectId: 'proj-1');

    expect(r1.fromCache, isTrue);
    expect(r1.answer, '24 inches');
  });
}
