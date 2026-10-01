export type CallStatus = 'UPLOADING' | 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED'

export type LabelKind = 'FLAG' | 'FLAG_VALUE' | 'COMMENT'

export interface LabelResult {
  id: string
  rule_id: string
  rule_name: string | null
  label_id: string
  label_code: string | null
  label_name: string | null
  label_kind: LabelKind | null
  matched: boolean
  value_number: number | null
  value_text: string | null
  comment_text: string | null
  comment_title_snapshot: string | null
  needs_review?: boolean
  review_reasons?: string[]
  evaluated_at: string
}

export interface CallComment {
  result_id: string
  rule_id: string
  label_id: string
  title: string
  body: string
  label_kind: LabelKind | null
  value_display: string | null
  evaluated_at: string
}

export interface CallItem {
  id: string
  title: string
  source_file_name: string
  owner_user_id: string
  owner_login: string
  language: string
  duration_seconds: number | null
  status: CallStatus
  progress: number
  error_message: string | null
  uploaded_at: string
  label_results: LabelResult[]
  label_results_unmatched?: LabelResult[]
  label_results_needs_review?: LabelResult[]
  labels: string[]
  checklist_results?: CallChecklistResult[]
}

export interface CallListResponse {
  items: CallItem[]
  page: number
  size: number
  total: number
}

export interface TranscriptSegment {
  id: string
  start_ms: number
  end_ms: number
  text: string
  speaker_label: string | null
  confidence: number | null
  segment_order: number
}

export interface TranscriptResponse {
  call_id: string
  full_text: string
  language: string
  stt_version: 'v2' | 'v3' | 'unknown'
  speaker_labeling: 'on' | 'off' | 'unknown'
  segments: TranscriptSegment[]
}

export type RuleType = 'KEYWORD' | 'LLM'
export type SearchPart = 'ANY' | 'OPENING' | 'MIDDLE' | 'CLOSING'
export type RuleKind = 'FLAG' | 'FLAG_VALUE' | 'COMMENT'
export type ChecklistConditionOperator = 'INCLUDE_ANY' | 'INCLUDE_ALL' | 'EXCLUDE_ANY' | 'EXCLUDE_ALL'

export interface LabelDefinition {
  id: string
  code: string
  name: string
  kind: LabelKind
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface LabelRule {
  id: string
  name: string
  rule_type: RuleType
  is_enabled: boolean
  keyword_query: string | null
  keyword_search_part: SearchPart | null
  llm_prompt: string | null
  kind: RuleKind
  label_ids: string[]
  labels: LabelDefinition[]
  created_at: string
  updated_at: string
}

export interface ValidatePromptResponse {
  valid: boolean
  message: string
  parsed: {
    kind: RuleKind
    label_id: string | null
    matched: boolean
    value_text?: string
    comment?: string
  } | null
}

export interface ChecklistConditionTarget {
  label_id: string
  values: string[]
  value: string | null
}

export interface ChecklistConditionLine {
  operator: ChecklistConditionOperator
  targets: ChecklistConditionTarget[]
}

export interface ChecklistAnswer {
  text: string
  score: number
  conditions: ChecklistConditionLine[]
}

export interface ChecklistQuestion {
  id?: string
  text: string
  answers: ChecklistAnswer[]
}

export interface Checklist {
  id: string
  name: string
  description: string | null
  is_active: boolean
  apply_filters: ChecklistConditionLine[]
  questions: ChecklistQuestion[]
  created_at: string
  updated_at: string
}

export interface ChecklistListResponse {
  items: Checklist[]
}

export interface ChecklistLabelValueOption {
  value: string
  usage_count: number
}

export interface ChecklistLabelValuesResponse {
  items: Record<string, ChecklistLabelValueOption[]>
}

export interface ChecklistQuestionResult {
  question_id: string
  question_text: string
  answer_text: string | null
  score: number
  max_score: number
  passed: boolean
}

export interface CallChecklistResult {
  checklist_id: string
  checklist_name: string
  is_applicable: boolean
  total_score: number
  max_score: number
  completion_percent: number
  evaluated_at: string
  questions: ChecklistQuestionResult[]
}
