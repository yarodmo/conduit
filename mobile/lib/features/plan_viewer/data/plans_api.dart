import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:retrofit/retrofit.dart';
import 'package:conduit_mobile/features/plan_viewer/domain/plan.dart';

part 'plans_api.g.dart';

@RestApi()
abstract class PlansApi {
  factory PlansApi(Dio dio, {String baseUrl}) = _PlansApi;

  @GET('/api/v1/projects/{project_id}/plans')
  Future<List<Plan>> listPlans(@Path('project_id') String projectId);

  @GET('/api/v1/plans/{plan_id}/metadata')
  Future<PlanMetadata> getMetadata(@Path('plan_id') String planId);

  /// Returns raw image bytes (WebP). Use the lowest zoom level (z=0,x=0,y=0)
  /// for a full-page overview suitable for mobile InteractiveViewer.
  @GET('/api/v1/plans/{plan_id}/pages/{page}/tiles/{z}/{x}/{y}')
  @DioResponseType(ResponseType.bytes)
  Future<HttpResponse<List<int>>> getTile(
    @Path('plan_id') String planId,
    @Path('page') int page,
    @Path('z') int z,
    @Path('x') int x,
    @Path('y') int y,
  );
}

class PlanMetadata {
  const PlanMetadata({required this.plan, required this.pages});

  factory PlanMetadata.fromJson(Map<String, dynamic> json) {
    final pagesJson = (json['pages'] as List<dynamic>?) ?? [];
    return PlanMetadata(
      plan: Plan.fromJson(json['plan'] as Map<String, dynamic>),
      pages: pagesJson
          .map((p) => PlanPageMeta.fromJson(p as Map<String, dynamic>))
          .toList(),
    );
  }

  final Plan plan;
  final List<PlanPageMeta> pages;

  Map<String, dynamic> toJson() => {
        'plan': plan.toJson(),
        'pages': pages.map((p) => p.toJson()).toList(),
      };
}

/// Helper to convert HttpResponse<List<int>> → Uint8List.
extension TileBytes on HttpResponse<List<int>> {
  Uint8List get bytes => Uint8List.fromList(data);
}
