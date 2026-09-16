import type {
  EvidenceFindingStatus,
  EvidenceSourceType,
  ReviewDecision,
  ReviewStatus,
  SocialDimension,
} from './brandEvidence'

export interface ExtractedFinding {
  id: string
  dimension: SocialDimension
  status: EvidenceFindingStatus
  statement: string
  excerpt: string
  source_location: string | null
  rationale: string
  review_status: ReviewStatus
  reviewed_at: string | null
  published_claim_id: string | null
}

export interface EvidenceDocument {
  id: string
  brand_id: string
  brand_name: string
  filename: string
  media_type: string
  byte_size: number
  content_sha256: string
  character_count: number
  source_title: string
  source_provider: string
  source_url: string
  source_type: EvidenceSourceType
  published_at: string | null
  model_name: string
  prompt_version: string
  extraction_status: 'completed' | 'failed'
  chunk_count: number
  created_at: string
  findings: ExtractedFinding[]
}

export interface EvidenceDocumentListResponse {
  items: EvidenceDocument[]
  total: number
}

export interface EvidenceDocumentInput {
  file: File
  sourceTitle: string
  sourceProvider: string
  sourceUrl: string
  sourceType: EvidenceSourceType
  publishedAt: string
}

export type FindingReviewDecision = ReviewDecision
