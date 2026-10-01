from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── primitive types ────────────────────────────────────────────────────────────

CallStatus = Literal["UPLOADING", "QUEUED", "PROCESSING", "COMPLETED", "FAILED"]
JobStatus = Literal["QUEUED", "PROCESSING", "COMPLETED", "FAILED"]
SttVersion = Literal["v2", "v3", "unknown"]
SpeakerLabelingState = Literal["on", "off", "unknown"]
LabelRuleType = Literal["KEYWORD", "LLM"]
KeywordSearchPart = Literal["ANY", "OPENING", "MIDDLE", "CLOSING"]
LabelKind = Literal["FLAG", "FLAG_VALUE", "COMMENT"]
ChecklistConditionOperator = Literal["INCLUDE_ANY", "INCLUDE_ALL", "EXCLUDE_ANY", "EXCLUDE_ALL"]


# ── internal call creation ─────────────────────────────────────────────────────


class CallCreateInternalRequest(BaseModel):
    owner_user_id: str
    owner_login: str
    owner_company_id: str | None = None
    owner_company_name: str | None = None
    title: str = Field(min_length=1, max_length=255)
    source_file_name: str = Field(min_length=1, max_length=255)
    object_key: str
    object_bucket: str
    language: str = "ru-RU"


# ── label definitions ──────────────────────────────────────────────────────────


class LabelDefinitionCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=255)
    kind: LabelKind


class LabelDefinitionOut(BaseModel):
    id: str
    code: str
    name: str
    kind: LabelKind
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LabelDefinitionListOut(BaseModel):
    items: list[LabelDefinitionOut]


# ── label rules ────────────────────────────────────────────────────────────────


class LabelRuleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: LabelKind
    rule_type: LabelRuleType
    is_enabled: bool = True
    label_ids: list[str] = Field(default_factory=list)
    keyword_query: str | None = None
    keyword_search_part: KeywordSearchPart = "ANY"
    llm_prompt: str | None = None


class LabelRuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_enabled: bool | None = None
    label_ids: list[str] | None = None
    keyword_query: str | None = None
    keyword_search_part: KeywordSearchPart | None = None
    llm_prompt: str | None = None


class LabelRuleOut(BaseModel):
    id: str
    name: str
    rule_type: LabelRuleType
    is_enabled: bool
    kind: LabelKind
    label_ids: list[str]
    labels: list[LabelDefinitionOut]
    keyword_query: str | None = None
    keyword_search_part: KeywordSearchPart | None = None
    llm_prompt: str | None = None
    created_at: datetime
    updated_at: datetime


class LabelRuleListOut(BaseModel):
    items: list[LabelRuleOut]


# ── validate-prompt ────────────────────────────────────────────────────────────


class ValidatePromptRequest(BaseModel):
    prompt_text: str = Field(min_length=1)
    test_text: str = Field(min_length=1)
    kind: LabelKind
    label_id: str | None = None
    label_ids: list[str] | None = None


class ValidatePromptOut(BaseModel):
    valid: bool
    message: str
    parsed: ValidatePromptParsed | None = None


class ValidatePromptParsed(BaseModel):
    kind: LabelKind
    label_id: str | None = None
    matched: bool
    value_text: str | None = None
    comment: str | None = None


# ── call label results ─────────────────────────────────────────────────────────


class CallLabelResultOut(BaseModel):
    id: str
    rule_id: str | None
    rule_name: str | None
    label_id: str | None
    label_code: str | None
    label_name: str | None
    label_kind: LabelKind | None
    matched: bool
    value_number: float | None = None
    value_text: str | None = None
    comment_text: str | None = None
    comment_title_snapshot: str | None = None
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime


class CallCommentOut(BaseModel):
    """Single comment entry shown in the right column of a call card."""

    result_id: str
    rule_id: str | None
    label_id: str | None
    # FLAG/FLAG_VALUE → label name; COMMENT → comment_title_snapshot
    title: str
    # FLAG/FLAG_VALUE → comment_text (why); COMMENT → comment_text (the comment itself)
    body: str
    label_kind: LabelKind | None
    # Formatted value for FLAG_VALUE
    value_display: str | None = None
    evaluated_at: datetime


class ChecklistConditionTargetIn(BaseModel):
    label_id: str
    values: list[str] = Field(default_factory=list)
    # legacy support
    value: str | None = None


class ChecklistConditionLineIn(BaseModel):
    operator: ChecklistConditionOperator
    targets: list[ChecklistConditionTargetIn] = Field(min_length=1)


class ChecklistAnswerIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    score: float = Field(ge=0)
    conditions: list[ChecklistConditionLineIn] = Field(default_factory=list)


class ChecklistQuestionIn(BaseModel):
    id: str | None = None
    text: str = Field(min_length=1, max_length=1000)
    answers: list[ChecklistAnswerIn] = Field(min_length=1)


class ChecklistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_active: bool = True
    apply_filters: list[ChecklistConditionLineIn] = Field(default_factory=list)
    questions: list[ChecklistQuestionIn] = Field(min_length=1)


class ChecklistUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    apply_filters: list[ChecklistConditionLineIn] | None = None
    questions: list[ChecklistQuestionIn] | None = None


class ChecklistOut(BaseModel):
    id: str
    name: str
    description: str | None
    is_active: bool
    apply_filters: list[ChecklistConditionLineIn]
    questions: list[ChecklistQuestionIn]
    created_at: datetime
    updated_at: datetime


class ChecklistListOut(BaseModel):
    items: list[ChecklistOut]


class ChecklistLabelValueOptionOut(BaseModel):
    value: str
    usage_count: int


class ChecklistLabelValuesOut(BaseModel):
    items: dict[str, list[ChecklistLabelValueOptionOut]]


class ChecklistQuestionResultOut(BaseModel):
    question_id: str
    question_text: str
    answer_text: str | None
    score: float
    max_score: float
    passed: bool


class CallChecklistResultOut(BaseModel):
    checklist_id: str
    checklist_name: str
    is_applicable: bool
    total_score: float
    max_score: float
    completion_percent: float
    evaluated_at: datetime
    questions: list[ChecklistQuestionResultOut] = Field(default_factory=list)


# ── calls ──────────────────────────────────────────────────────────────────────


class CallOut(BaseModel):
    id: str
    title: str
    source_file_name: str
    owner_user_id: str
    owner_login: str
    owner_company_id: str | None = None
    owner_company_name: str | None = None
    language: str
    duration_seconds: int | None
    status: CallStatus
    progress: int
    error_message: str | None
    uploaded_at: datetime
    # new structured label results (only matched=True)
    label_results: list[CallLabelResultOut] = Field(default_factory=list)
    # matched=False results to diagnose why rules did not trigger
    label_results_unmatched: list[CallLabelResultOut] = Field(default_factory=list)
    # subset of matched results that should be manually checked
    label_results_needs_review: list[CallLabelResultOut] = Field(default_factory=list)
    # backward compat flat list for list view badges
    labels: list[str] = Field(default_factory=list)
    checklist_results: list[CallChecklistResultOut] = Field(default_factory=list)


class CallListOut(BaseModel):
    items: list[CallOut]
    page: int
    size: int
    total: int


# ── job ────────────────────────────────────────────────────────────────────────


class JobOut(BaseModel):
    id: str
    call_id: str
    status: JobStatus
    attempt: int
    operation_id: str | None
    last_error: str | None
    version: int


# ── transcript ────────────────────────────────────────────────────────────────


class SegmentOut(BaseModel):
    id: str
    start_ms: int
    end_ms: int
    text: str
    speaker_label: str | None
    confidence: float | None
    segment_order: int


class TranscriptOut(BaseModel):
    call_id: str
    full_text: str
    language: str
    stt_version: SttVersion = "unknown"
    speaker_labeling: SpeakerLabelingState = "unknown"
    segments: list[SegmentOut]


class UpdateSegmentRequest(BaseModel):
    text: str = Field(min_length=1)


class RetryResult(BaseModel):
    job_id: str
    status: JobStatus


# ── internal job completion ────────────────────────────────────────────────────


class JobOperationRegisterRequest(BaseModel):
    operation_id: str


class JobCompleteSegment(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    speaker_label: str | None = None
    confidence: float | None = None
    segment_order: int


class JobLlmRuleMatch(BaseModel):
    """Result of one LLM rule evaluation returned by transcription-service."""

    rule_id: str
    label_id: str | None = None
    # For FLAG: the chosen label_value from the allowed set
    label_value: str | None = None
    matched: bool
    # For FLAG_VALUE
    value_number: float | None = None
    value_text: str | None = None
    # Why this label was chosen (required when matched=True for FLAG/FLAG_VALUE)
    comment: str | None = None


class JobCompleteRequest(BaseModel):
    full_text: str
    language: str
    duration_seconds: int | None = None
    segments: list[JobCompleteSegment]
    llm_rule_matches: list[JobLlmRuleMatch] = Field(default_factory=list)


class JobFailRequest(BaseModel):
    error_message: str
