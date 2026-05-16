import 'package:json_annotation/json_annotation.dart';

part 'plan.g.dart';

enum PlanStatus {
  @JsonValue('uploaded')
  uploaded,
  @JsonValue('processing')
  processing,
  @JsonValue('ready')
  ready,
  @JsonValue('failed')
  failed,
}

@JsonSerializable(fieldRename: FieldRename.snake)
class Plan {
  const Plan({
    required this.id,
    required this.projectId,
    required this.name,
    required this.status,
    required this.pageCount,
    required this.createdAt,
  });

  factory Plan.fromJson(Map<String, dynamic> json) => _$PlanFromJson(json);

  final String id;
  final String projectId;
  final String name;
  final PlanStatus status;
  final int pageCount;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => _$PlanToJson(this);

  bool get isReady => status == PlanStatus.ready;
}

@JsonSerializable(fieldRename: FieldRename.snake)
class PlanPageMeta {
  const PlanPageMeta({
    required this.pageNumber,
    required this.width,
    required this.height,
  });

  factory PlanPageMeta.fromJson(Map<String, dynamic> json) =>
      _$PlanPageMetaFromJson(json);

  final int pageNumber;
  final int width;
  final int height;

  Map<String, dynamic> toJson() => _$PlanPageMetaToJson(this);
}
