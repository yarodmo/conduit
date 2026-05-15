import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:conduit_mobile/features/auth/data/auth_repository.dart';
import 'package:conduit_mobile/features/auth/domain/user.dart';
import 'package:conduit_mobile/features/jobs/data/jobs_repository.dart';
import 'package:conduit_mobile/features/jobs/domain/project.dart';
import 'package:conduit_mobile/features/jobs/domain/zone.dart';
import 'package:conduit_mobile/features/jobs/presentation/my_jobs_screen.dart';
import 'package:conduit_mobile/features/jobs/providers.dart';

class _MockJobsRepo extends Mock implements JobsRepository {}

class _MockAuthRepo extends Mock implements AuthRepository {}

void main() {
  late _MockJobsRepo jobsRepo;
  late _MockAuthRepo authRepo;

  const sampleUser = User(
    id: 'user-1',
    email: 'tech@conduit.build',
    fullName: 'Field Tech',
    orgId: 'org-1',
  );

  final sampleProject = Project(
    id: 'proj-1',
    name: 'Riverside School Wing B',
    complexity: ProjectComplexity.standard,
    isActive: true,
    createdAt: DateTime(2026, 5, 1),
    city: 'Miami',
    state: 'FL',
  );

  final sampleZones = [
    Zone(
      id: 'zone-1',
      name: 'Mechanical Room L1',
      systems: const ['HVAC'],
      status: ZoneStatus.inProgress,
      assignedTo: 'user-1',
      orderIndex: 0,
      createdAt: DateTime.now(),
    ),
    Zone(
      id: 'zone-2',
      name: 'Electrical Room L2',
      systems: const ['Electrical'],
      status: ZoneStatus.blocked,
      assignedTo: 'user-1',
      orderIndex: 1,
      blockedReason: 'Missing structural drawing for wall opening',
      createdAt: DateTime.now(),
    ),
  ];

  setUp(() {
    jobsRepo = _MockJobsRepo();
    authRepo = _MockAuthRepo();
    when(() => authRepo.currentUser()).thenAnswer((_) async => sampleUser);
  });

  Widget _wrap() => ProviderScope(
        overrides: [
          jobsRepositoryProvider.overrideWithValue(jobsRepo),
          authRepositoryProvider.overrideWithValue(authRepo),
        ],
        child: const MaterialApp(home: MyJobsScreen()),
      );

  testWidgets('shows loading then jobs list', (tester) async {
    when(() => jobsRepo.fetchJobs(forceRefresh: any(named: 'forceRefresh')))
        .thenAnswer((_) async => JobsBundle(
              projects: [sampleProject],
              zonesByProject: {sampleProject.id: sampleZones},
              blockedCount: 1,
            ));

    await tester.pumpWidget(_wrap());
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    await tester.pumpAndSettle();

    expect(find.text('Riverside School Wing B'), findsOneWidget);
    expect(find.text('Miami, FL'), findsOneWidget);
    expect(find.text('Mechanical Room L1'), findsOneWidget);
    expect(find.text('Electrical Room L2'), findsOneWidget);
    expect(find.text('1 blocked'), findsOneWidget);
  });

  testWidgets('shows empty view when no zones', (tester) async {
    when(() => jobsRepo.fetchJobs(forceRefresh: any(named: 'forceRefresh')))
        .thenAnswer((_) async => const JobsBundle(
              projects: [],
              zonesByProject: {},
              blockedCount: 0,
            ));

    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    expect(find.textContaining('No zones assigned yet'), findsOneWidget);
  });

  testWidgets('shows error view + retry button', (tester) async {
    when(() => jobsRepo.fetchJobs(forceRefresh: any(named: 'forceRefresh')))
        .thenThrow(Exception('Network unavailable'));

    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    expect(find.text('Could not load your jobs'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('blocked zone shows red badge + reason', (tester) async {
    when(() => jobsRepo.fetchJobs(forceRefresh: any(named: 'forceRefresh')))
        .thenAnswer((_) async => JobsBundle(
              projects: [sampleProject],
              zonesByProject: {sampleProject.id: sampleZones},
              blockedCount: 1,
            ));

    await tester.pumpWidget(_wrap());
    await tester.pumpAndSettle();

    expect(
      find.text('Missing structural drawing for wall opening'),
      findsOneWidget,
    );
  });

  test('JobsBundle.isEmpty matches semantics', () {
    expect(
      const JobsBundle(
              projects: [], zonesByProject: {}, blockedCount: 0)
          .isEmpty,
      isTrue,
    );
    expect(
      JobsBundle(
        projects: [sampleProject],
        zonesByProject: {sampleProject.id: sampleZones},
        blockedCount: 1,
      ).isEmpty,
      isFalse,
    );
  });

  test('JobsBundle.totalZones sums correctly', () {
    final bundle = JobsBundle(
      projects: [sampleProject],
      zonesByProject: {sampleProject.id: sampleZones},
      blockedCount: 1,
    );
    expect(bundle.totalZones, 2);
  });
}
