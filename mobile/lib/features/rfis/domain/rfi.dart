import 'package:json_annotation/json_annotation.dart';

part 'rfi.g.dart';

enum RfiStatus {
  @JsonValue('DRAFT')
  draft,
  @JsonValue('SUBMITTED')
  submitted,
  @JsonValue('UNDER_REVIEW')
  underReview,
  @JsonValue('ANSWERED')
  answered,
  @JsonValue('CLOSED')
  closed,
  @JsonValue('REJECTED')
  rejected;

  String get label => switch (this) {
        RfiStatus.draft => 'Draft',
        RfiStatus.submitted => 'Submitted',
        RfiStatus.underReview => 'Under review',
        RfiStatus.answered => 'Answered',
        RfiStatus.closed => 'Closed',
        RfiStatus.rejected => 'Rejected',
      };
}

enum RfiUrgency {
  @JsonValue('LOW')
  low,
  @JsonValue('MEDIUM')
  medium,
  @JsonValue('HIGH')
  high,
  @JsonValue('CRITICAL')
  critical;

  String get label => name.toUpperCase();
}

@JsonSerializable(fieldRename: FieldRename.snake)
class RfiComment {
  const RfiComment({
    required this.id,
    required this.authorId,
    required this.content,
    required this.isOfficialResponse,
    required this.createdAt,
  });

  factory RfiComment.fromJson(Map<String, dynamic> json) =>
      _$RfiCommentFromJson(json);

  final String id;
  final String authorId;
  final String content;
  final bool isOfficialResponse;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => _$RfiCommentToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class Rfi {
  const Rfi({
    required this.id,
    required this.projectId,
    required this.rfiNumber,
    required this.title,
    required this.description,
    required this.status,
    required this.urgency,
    required this.source,
    required this.createdAt,
    this.assignedTo,
    this.markupId,
    this.dueDate,
    this.submittedAt,
    this.answeredAt,
    this.closedAt,
    this.comments = const [],
    this.changeOrderId,
  });

  factory Rfi.fromJson(Map<String, dynamic> json) => _$RfiFromJson(json);

  final String id;
  final String projectId;
  final String rfiNumber;
  final String title;
  final String description;
  final RfiStatus status;
  final RfiUrgency urgency;
  final String source;
  final String? assignedTo;
  final String? markupId;
  final DateTime? dueDate;
  final DateTime? submittedAt;
  final DateTime? answeredAt;
  final DateTime? closedAt;
  final DateTime createdAt;
  final List<RfiComment> comments;
  final String? changeOrderId;

  Map<String, dynamic> toJson() => _$RfiToJson(this);

  bool get isOpen =>
      status != RfiStatus.closed && status != RfiStatus.rejected;
}

@JsonSerializable(fieldRename: FieldRename.snake)
class RfiListItem {
  const RfiListItem({
    required this.id,
    required this.rfiNumber,
    required this.title,
    required this.status,
    required this.urgency,
    required this.source,
    required this.createdAt,
    this.assignedTo,
    this.dueDate,
  });

  factory RfiListItem.fromJson(Map<String, dynamic> json) =>
      _$RfiListItemFromJson(json);

  final String id;
  final String rfiNumber;
  final String title;
  final RfiStatus status;
  final RfiUrgency urgency;
  final String source;
  final String? assignedTo;
  final DateTime? dueDate;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => _$RfiListItemToJson(this);
}
