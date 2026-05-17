import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:conduit_mobile/features/rfis/data/rfis_api.dart';
import 'package:conduit_mobile/features/rfis/data/rfis_repository.dart';
import 'package:conduit_mobile/features/rfis/domain/rfi.dart';

class _MockRfisApi extends Mock implements RfisApi {}

void main() {
  late _MockRfisApi api;
  late RfisRepository repo;

  setUp(() {
    api = _MockRfisApi();
    repo = RfisRepository(api);
  });

  RfiListItem rfi(String id, DateTime date) => RfiListItem(
        id: id,
        rfiNumber: 'RFI-$id',
        title: 'Test RFI $id',
        status: RfiStatus.submitted,
        urgency: RfiUrgency.medium,
        source: 'MANUAL',
        createdAt: date,
      );

  test('listAcrossUserProjects aggregates and sorts by createdAt desc',
      () async {
    final p1Older = rfi('a', DateTime(2026, 5, 1));
    final p1Newer = rfi('b', DateTime(2026, 5, 10));
    final p2Newest = rfi('c', DateTime(2026, 5, 14));

    when(() => api.listForProject('proj-1', any()))
        .thenAnswer((_) async => [p1Older, p1Newer]);
    when(() => api.listForProject('proj-2', any()))
        .thenAnswer((_) async => [p2Newest]);

    final results = await repo.listAcrossUserProjects(['proj-1', 'proj-2']);

    expect(results.length, 3);
    expect(results[0].id, 'c'); // newest first
    expect(results[1].id, 'b');
    expect(results[2].id, 'a');
  });

  test('listAcrossUserProjects skips projects that throw', () async {
    when(() => api.listForProject('good', any()))
        .thenAnswer((_) async => [rfi('x', DateTime(2026, 5, 5))]);
    when(() => api.listForProject('bad', any()))
        .thenThrow(Exception('Server error'));

    final results = await repo.listAcrossUserProjects(['good', 'bad']);

    expect(results.length, 1);
    expect(results.first.id, 'x');
  });

  test('listAcrossUserProjects empty input returns empty', () async {
    final results = await repo.listAcrossUserProjects([]);
    expect(results, isEmpty);
    verifyNever(() => api.listForProject(any(), any()));
  });
}
