export type SearchQueryType = 'barcode' | 'text'

export type AssessmentDimension =
  | 'vegan_composition'
  | 'environmental_impact'
  | 'women_workers'
  | 'minority_inclusion'

export type FoodCategory =
  | 'baby_food'
  | 'bakery'
  | 'beverages'
  | 'biscuits_cookies'
  | 'breakfast_cereals'
  | 'candy'
  | 'chocolate'
  | 'coffee_tea'
  | 'condiments_sauces'
  | 'dairy'
  | 'dairy_alternatives'
  | 'desserts'
  | 'frozen_foods'
  | 'ice_cream'
  | 'meat_alternatives'
  | 'pasta_noodles'
  | 'ready_meals'
  | 'snacks_chips'
  | 'spreads'
  | 'yogurt'
  | 'other'

export type AssessmentStatus =
  | 'supported'
  | 'mixed'
  | 'concern'
  | 'not_disclosed'
  | 'unknown'

export type EvidenceScope = 'product' | 'brand'

export type VerificationLevel =
  | 'catalog_data'
  | 'multiple_sources'
  | 'single_source'
  | 'unverified'

export interface AssessmentSource {
  title: string
  provider_name: string
  url: string
  published_at: string | null
  source_location: string | null
}

export interface ConsumerAssessment {
  dimension: AssessmentDimension
  title: string
  status: AssessmentStatus
  finding: string
  evidence_scope: EvidenceScope
  verification: VerificationLevel
  verification_note: string
  limitations: string | null
  sources: AssessmentSource[]
}

export interface ProductResearchMetadata {
  researched_at: string
  model_name: string
  source_count: number
  legal_entity: string | null
  parent_company: string | null
  jurisdiction: string | null
  entity_source_url: string | null
}

export type CommunityReportStatus = 'pending_review' | 'published_unverified' | 'rejected'
export type CommunityReportOutcome = 'positive' | 'negative'

export interface CommunityReportAssessment {
  dimension: AssessmentDimension
  outcome: CommunityReportOutcome
}

export interface CommunityReportOutcomeCounts {
  positive: number
  negative: number
}

export interface CommunityReportSummary {
  total: number
  pending_review: number
  assessment_counts: Partial<Record<AssessmentDimension, CommunityReportOutcomeCounts>>
}

export interface CommunityReport {
  id: string
  product_name: string | null
  barcode: string | null
  category: FoodCategory
  assessments: CommunityReportAssessment[]
  status: CommunityReportStatus
  has_photo: boolean
  document_count: number
  submitted_at: string
  notice: string
}

export interface CommunityReportAttachment {
  id: string
  file_name: string
  mime_type: string
  download_url: string
}

export interface PublicCommunityReport {
  id: string
  product_name: string | null
  barcode: string | null
  category: FoodCategory
  assessments: CommunityReportAssessment[]
  observations: string
  evidence_url: string | null
  photo_url: string | null
  documents: CommunityReportAttachment[]
  status: 'published_unverified'
  published_at: string
}

export interface PublicCommunityReportList {
  items: PublicCommunityReport[]
  total: number
  disclaimer: string
}

export interface ConsumerProduct {
  barcode: string | null
  name: string
  brand: string | null
  category: FoodCategory | null
  catalog_product: boolean
  image_url: string | null
  source_url: string
  source_name: string
  last_updated_at: string | null
  evidence_coverage_percent: number
  assessments: ConsumerAssessment[]
  research: ProductResearchMetadata | null
  community_reports: CommunityReportSummary
}

export interface ConsumerSearchResponse {
  query: string
  query_type: SearchQueryType
  items: ConsumerProduct[]
  total: number
  disclaimer: string
}

export interface ProductResearchResponse {
  product: ConsumerProduct
  cached: boolean
}

export interface ConsumerCitation {
  number: number
  evidence_id: string
  title: string
  provider_name: string
  url: string
  excerpt: string
  similarity: number
}

export interface ConsumerAnswer {
  question: string
  answer: string
  insufficient_evidence: boolean
  citations: ConsumerCitation[]
  retrieval_model: string
  generation_model: string
  prompt_version: string
  cached: boolean
}
