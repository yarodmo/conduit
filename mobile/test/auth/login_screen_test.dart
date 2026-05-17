import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:conduit_mobile/features/auth/data/auth_repository.dart';
import 'package:conduit_mobile/features/auth/domain/user.dart';
import 'package:conduit_mobile/features/auth/presentation/login_screen.dart';
import 'package:conduit_mobile/features/auth/providers.dart';

class _MockAuthRepo extends Mock implements AuthRepository {}

void main() {
  late _MockAuthRepo repo;

  setUp(() {
    repo = _MockAuthRepo();
  });

  Widget wrap() {
    return ProviderScope(
      overrides: [
        authRepositoryProvider.overrideWithValue(repo),
      ],
      child: const MaterialApp(home: LoginScreen()),
    );
  }

  testWidgets('login screen renders all required fields', (tester) async {
    when(() => repo.currentUser()).thenAnswer((_) async => null);

    await tester.pumpWidget(wrap());
    await tester.pumpAndSettle();

    expect(find.text('Conduit'), findsOneWidget);
    expect(find.text('MEP Intelligence. Connected.'), findsOneWidget);
    expect(find.byKey(const Key('login_email_field')), findsOneWidget);
    expect(find.byKey(const Key('login_password_field')), findsOneWidget);
    expect(find.byKey(const Key('login_submit_button')), findsOneWidget);
  });

  testWidgets('shows validation error for empty email', (tester) async {
    when(() => repo.currentUser()).thenAnswer((_) async => null);

    await tester.pumpWidget(wrap());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('login_submit_button')));
    await tester.pump();

    expect(find.text('Required'), findsWidgets);
  });

  testWidgets('shows validation error for invalid email format', (tester) async {
    when(() => repo.currentUser()).thenAnswer((_) async => null);

    await tester.pumpWidget(wrap());
    await tester.pumpAndSettle();

    await tester.enterText(
        find.byKey(const Key('login_email_field')), 'not-an-email');
    await tester.enterText(
        find.byKey(const Key('login_password_field')), 'password123');
    await tester.tap(find.byKey(const Key('login_submit_button')));
    await tester.pump();

    expect(find.text('Invalid email'), findsOneWidget);
  });

  testWidgets('shows error when login fails', (tester) async {
    when(() => repo.currentUser()).thenAnswer((_) async => null);
    when(() => repo.login(any(), any())).thenThrow(
      AuthException('Invalid credentials'),
    );

    await tester.pumpWidget(wrap());
    await tester.pumpAndSettle();

    await tester.enterText(
        find.byKey(const Key('login_email_field')), 'user@conduit.build');
    await tester.enterText(
        find.byKey(const Key('login_password_field')), 'wrongpassword');
    await tester.tap(find.byKey(const Key('login_submit_button')));
    await tester.pumpAndSettle();

    expect(find.text('Invalid credentials'), findsOneWidget);
  });

  testWidgets('successful login updates state', (tester) async {
    const user = User(
      id: 'user-1',
      email: 'user@conduit.build',
      fullName: 'Test User',
      orgId: 'org-1',
    );
    when(() => repo.currentUser()).thenAnswer((_) async => null);
    when(() => repo.login(any(), any())).thenAnswer((_) async => user);

    final container = ProviderContainer(overrides: [
      authRepositoryProvider.overrideWithValue(repo),
    ]);
    addTearDown(container.dispose);

    await container.read(authControllerProvider.future);
    await container
        .read(authControllerProvider.notifier)
        .login('user@conduit.build', 'password123');

    expect(container.read(authControllerProvider).asData?.value, user);
    expect(container.read(isAuthenticatedProvider), isTrue);
  });
}
