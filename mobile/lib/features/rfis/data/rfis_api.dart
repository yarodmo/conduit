import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';
import 'package:conduit_mobile/features/rfis/domain/rfi.dart';

part 'rfis_api.g.dart';

@RestApi()
abstract class RfisApi {
  factory RfisApi(Dio dio, {String baseUrl}) = _RfisApi;

  @GET('/api/v1/projects/{project_id}/rfis')
  Future<List<RfiListItem>> listForProject(
    @Path('project_id') String projectId,
    @Query('status') String? statusFilter,
  );

  @GET('/api/v1/rfis/{rfi_id}')
  Future<Rfi> getRfi(@Path('rfi_id') String rfiId);
}
