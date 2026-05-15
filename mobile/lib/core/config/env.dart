/// Environment configuration read at compile time via `--dart-define`.
///
/// Build with:
/// `flutter build apk --dart-define=API_BASE_URL=https://api.climbpeakdigital.com`
class Env {
  const Env._();

  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://api.climbpeakdigital.com',
  );

  static const String environment = String.fromEnvironment(
    'ENVIRONMENT',
    defaultValue: 'production',
  );

  static const bool isProduction = environment == 'production';
  static const bool isDevelopment = environment == 'development';
}
