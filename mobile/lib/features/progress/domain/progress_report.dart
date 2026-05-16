import 'package:json_annotation/json_annotation.dart';

part 'progress_report.g.dart';

/// Quick status pick for the field tech: maps to backend ZoneStatus.
enum ReportStatusPick {
  onTrack('IN_PROGRESS', 'On Track'),
  issues('IN_PROGRESS', 'Issues'),
  blocked('BLOCKED', 'Blocked');

  const ReportStatusPick(this.zoneStatus, this.label);

  final String zoneStatus;
  final String label;
}

@JsonSerializable(fieldRename: FieldRename.snake, includeIfNull: false)
class MaterialUsedEntry {
  const MaterialUsedEntry({
    required this.catalogItemId,
    required this.qty,
  });

  factory MaterialUsedEntry.fromJson(Map<String, dynamic> json) =>
      _$MaterialUsedEntryFromJson(json);

  final String catalogItemId;
  final double qty;

  Map<String, dynamic> toJson() => _$MaterialUsedEntryToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake, includeIfNull: false)
class ProgressReportCreate {
  const ProgressReportCreate({
    required this.progressPct,
    required this.status,
    this.notes,
    this.materialsUsed,
    this.gpsLat,
    this.gpsLng,
  });

  final int progressPct;
  final String status;
  final String? notes;
  final List<MaterialUsedEntry>? materialsUsed;
  final double? gpsLat;
  final double? gpsLng;

  Map<String, dynamic> toJson() => _$ProgressReportCreateToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class ProgressReportResponse {
  const ProgressReportResponse({
    required this.id,
    required this.zoneId,
    required this.progressPct,
    required this.status,
    required this.createdAt,
  });

  factory ProgressReportResponse.fromJson(Map<String, dynamic> json) =>
      _$ProgressReportResponseFromJson(json);

  final String id;
  final String zoneId;
  final int progressPct;
  final String status;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => _$ProgressReportResponseToJson(this);
}
