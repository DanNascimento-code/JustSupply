export type SearchQueryType = 'barcode' | 'text'

export type AssessmentDimension =
  | 'vegan_composition'
  | 'environmental_impact'
  | 'women_workers'
  | 'minority_inclusion'

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
}

export interface ConsumerProduct {
  barcode: string
  name: string
  brand: string | null
  image_url: string | null
  source_url: string
  source_name: string
  last_updated_at: string | null
  evidence_coverage_percent: number
  assessments: ConsumerAssessment[]
  research: ProductResearchMetadata | null
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
}
