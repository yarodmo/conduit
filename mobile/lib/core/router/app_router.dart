import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:conduit_mobile/features/auth/presentation/login_screen.dart';
import 'package:conduit_mobile/features/auth/providers.dart';
import 'package:conduit_mobile/features/jobs/presentation/my_jobs_screen.dart';
import 'package:conduit_mobile/features/plan_viewer/presentation/plan_viewer_screen.dart';
import 'package:conduit_mobile/features/progress/presentation/progress_report_screen.dart';
import 'package:conduit_mobile/features/rfis/presentation/rfi_detail_screen.dart';
import 'package:conduit_mobile/features/rfis/presentation/rfi_list_screen.dart';

/// Route name constants — use these instead of raw strings.
class Routes {
  const Routes._();

  static const String login = '/login';
  static const String myJobs = '/';
  static const String zoneDetail = '/zones/:zoneId';
  static const String zonePlan = '/zones/:zoneId/plan';
  static const String zoneReport = '/zones/:zoneId/report';
  static const String rfiList = '/rfis';
  static const String rfiDetail = '/rfis/:rfiId';
  static const String assistant = '/assistant';
}

final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: Routes.myJobs,
    refreshListenable: _AuthRefreshListenable(ref),
    redirect: (context, state) {
      final auth = ref.read(authControllerProvider);
      if (auth.isLoading) return null;

      final isAuthed = auth.asData?.value != null;
      final isLogin = state.matchedLocation == Routes.login;

      if (!isAuthed && !isLogin) return Routes.login;
      if (isAuthed && isLogin) return Routes.myJobs;
      return null;
    },
    routes: [
      GoRoute(
        path: Routes.login,
        builder: (_, __) => const LoginScreen(),
      ),
      GoRoute(
        path: Routes.myJobs,
        builder: (_, __) => const MyJobsScreen(),
      ),
      GoRoute(
        path: '/plans/:planId',
        builder: (_, state) => PlanViewerScreen(
          planId: state.pathParameters['planId']!,
        ),
      ),
      GoRoute(
        path: '/projects/:projectId/zones/:zoneId/report',
        builder: (_, state) => ProgressReportScreen(
          projectId: state.pathParameters['projectId']!,
          zoneId: state.pathParameters['zoneId']!,
        ),
      ),
      GoRoute(
        path: Routes.rfiList,
        builder: (_, __) => const RfiListScreen(),
      ),
      GoRoute(
        path: '/rfis/:rfiId',
        builder: (_, state) => RfiDetailScreen(
          rfiId: state.pathParameters['rfiId']!,
        ),
      ),
      // Additional routes registered in subsequent turns
    ],
    errorBuilder: (_, state) => Scaffold(
      body: Center(child: Text('Route not found: ${state.uri.path}')),
    ),
  );
});

/// Adapter so GoRouter rebuilds redirects when AsyncNotifier auth state changes.
class _AuthRefreshListenable extends ChangeNotifier {
  _AuthRefreshListenable(Ref ref) {
    ref.listen(authControllerProvider, (_, __) => notifyListeners());
  }
}
