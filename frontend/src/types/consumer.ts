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
  sources: AssessmentSource[]
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
}

export interface ConsumerSearchResponse {
  query: string
  query_type: SearchQueryType
  items: ConsumerProduct[]
  total: number
  disclaimer: string
}
