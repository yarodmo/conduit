import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';
import 'package:conduit_mobile/features/jobs/domain/project.dart';
import 'package:conduit_mobile/features/jobs/domain/zone.dart';

part 'zones_api.g.dart';

@RestApi()
abstract class ZonesApi {
  factory ZonesApi(Dio dio, {String baseUrl}) = _ZonesApi;

  @GET('/api/v1/projects')
  Future<List<Project>> listProjects();

  @GET('/api/v1/projects/{project_id}/zones')
  Future<List<Zone>> listZones(@Path('project_id') String projectId);

  @PATCH('/api/v1/projects/{project_id}/zones/{zone_id}/status')
  Future<Zone> updateStatus(
    @Path('project_id') String projectId,
    @Path('zone_id') String zoneId,
    @Body() ZoneStatusUpdate body,
  );

  @GET('/api/v1/projects/{project_id}/zones/{zone_id}')
  Future<Zone> getZone(
    @Path('project_id') String projectId,
    @Path('zone_id') String zoneId,
  );
}
