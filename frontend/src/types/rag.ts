export interface RagCitation {
  number: number
  chunk_id: string
  document_id: string
  source_title: string
  source_provider: string
  source_url: string
  filename: string
  source_location: string
  excerpt: string
  similarity: number
}

export interface RagAnswer {
  question: string
  answer: string
  insufficient_evidence: boolean
  citations: RagCitation[]
  retrieval_model: string
  generation_model: string
  prompt_version: string
}

export interface DocumentIndexResult {
  document_id: string
  chunk_count: number
  embedding_model: string
}
