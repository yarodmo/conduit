import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/features/auth/data/auth_repository.dart';
import 'package:conduit_mobile/features/auth/domain/user.dart';

/// Holds the currently signed-in user. Null when logged out.
///
/// `build()` attempts to restore session from secure storage on app start.
class AuthController extends AsyncNotifier<User?> {
  @override
  Future<User?> build() async {
    return ref.read(authRepositoryProvider).currentUser();
  }

  Future<void> login(String email, String password) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref.read(authRepositoryProvider).login(email, password),
    );
  }

  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    state = const AsyncData(null);
  }
}

final authControllerProvider =
    AsyncNotifierProvider<AuthController, User?>(AuthController.new);

/// Convenience: true if a user is signed in.
final isAuthenticatedProvider = Provider<bool>((ref) {
  return ref.watch(authControllerProvider).asData?.value != null;
});
