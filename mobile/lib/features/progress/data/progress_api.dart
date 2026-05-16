import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';
import 'package:conduit_mobile/features/progress/domain/progress_report.dart';

part 'progress_api.g.dart';

@RestApi()
abstract class ProgressApi {
  factory ProgressApi(Dio dio, {String baseUrl}) = _ProgressApi;

  @POST('/api/v1/projects/{project_id}/zones/{zone_id}/reports')
  Future<ProgressReportResponse> submitReport(
    @Path('project_id') String projectId,
    @Path('zone_id') String zoneId,
    @Body() ProgressReportCreate body,
  );
}
