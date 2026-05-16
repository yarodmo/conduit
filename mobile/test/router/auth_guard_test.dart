import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:conduit_mobile/core/router/app_router.dart';
import 'package:conduit_mobile/features/auth/data/auth_repository.dart';
import 'package:conduit_mobile/features/auth/domain/user.dart';
import 'package:conduit_mobile/features/auth/providers.dart';

class _MockAuthRepo extends Mock implements AuthRepository {}

void main() {
  late _MockAuthRepo repo;

  setUp(() => repo = _MockAuthRepo());

  Future<Widget> _buildApp(ProviderContainer container) async {
    final router = container.read(appRouterProvider);
    return UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(routerConfig: router),
    );
  }

  testWidgets('unauthed user redirected to /login', (tester) async {
    when(() => repo.currentUser()).thenAnswer((_) async => null);
    final container = ProviderContainer(overrides: [
      authRepositoryProvider.overrideWithValue(repo),
    ]);
    addTearDown(container.dispose);

    await tester.pumpWidget(await _buildApp(container));
    await tester.pumpAndSettle();

    // Login screen marker
    expect(find.text('Conduit'), findsOneWidget);
    expect(find.text('MEP Intelligence. Connected.'), findsOneWidget);
  });

  testWidgets('authed user lands on My Jobs', (tester) async {
    const user = User(
      id: 'user-1',
      email: 'tech@conduit.build',
      fullName: 'Field Tech',
      orgId: 'org-1',
    );
    when(() => repo.currentUser()).thenAnswer((_) async => user);

    final container = ProviderContainer(overrides: [
      authRepositoryProvider.overrideWithValue(repo),
    ]);
    addTearDown(container.dispose);

    await tester.pumpWidget(await _buildApp(container));
    // Wait for auth restore + jobs FutureProvider to settle (will fail
    // to load jobs without a real API but the screen still renders).
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.text('My Jobs'), findsOneWidget);
  });
}
