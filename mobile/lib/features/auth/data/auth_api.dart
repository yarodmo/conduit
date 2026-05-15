import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';
import 'package:conduit_mobile/features/auth/domain/user.dart';

part 'auth_api.g.dart';

@RestApi()
abstract class AuthApi {
  factory AuthApi(Dio dio, {String baseUrl}) = _AuthApi;

  @POST('/api/v1/login')
  Future<TokenPair> login(@Body() LoginRequest request);

  @POST('/api/v1/refresh')
  Future<TokenPair> refresh(@Body() Map<String, dynamic> body);

  @GET('/api/v1/me')
  Future<User> me();

  @POST('/api/v1/logout')
  Future<void> logout();
}
