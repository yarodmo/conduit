import 'package:json_annotation/json_annotation.dart';

part 'zone.g.dart';

enum ZoneStatus {
  @JsonValue('NOT_STARTED')
  notStarted,
  @JsonValue('IN_PROGRESS')
  inProgress,
  @JsonValue('COMPLETED')
  completed,
  @JsonValue('BLOCKED')
  blocked;

  String get displayLabel => switch (this) {
        ZoneStatus.notStarted => 'Not started',
        ZoneStatus.inProgress => 'In progress',
        ZoneStatus.completed => 'Completed',
        ZoneStatus.blocked => 'Blocked',
      };

  String get serverValue => switch (this) {
        ZoneStatus.notStarted => 'NOT_STARTED',
        ZoneStatus.inProgress => 'IN_PROGRESS',
        ZoneStatus.completed => 'COMPLETED',
        ZoneStatus.blocked => 'BLOCKED',
      };
}

@JsonSerializable(fieldRename: FieldRename.snake)
class Zone {
  const Zone({
    required this.id,
    required this.name,
    required this.systems,
    required this.status,
    required this.orderIndex,
    required this.createdAt,
    this.assignedTo,
    this.blockedReason,
  });

  factory Zone.fromJson(Map<String, dynamic> json) => _$ZoneFromJson(json);

  final String id;
  final String name;
  final List<String> systems;
  final ZoneStatus status;
  @JsonKey(name: 'assigned_to')
  final String? assignedTo;
  final int orderIndex;
  final String? blockedReason;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => _$ZoneToJson(this);

  bool get isBlocked => status == ZoneStatus.blocked;
  bool get isComplete => status == ZoneStatus.completed;
}

@JsonSerializable(fieldRename: FieldRename.snake)
class ZoneStatusUpdate {
  const ZoneStatusUpdate({required this.status, this.blockedReason});

  final String status;
  final String? blockedReason;

  Map<String, dynamic> toJson() => _$ZoneStatusUpdateToJson(this);
}
