import type {
  ConsumerAnswer,
  ConsumerSearchResponse,
  ProductResearchResponse,
} from '../types/consumer'
import type { Language } from '../i18n'
import { apiRequest } from './client'

export function searchConsumerProducts(
  query: string,
  language: Language,
): Promise<ConsumerSearchResponse> {
  const searchParams = new URLSearchParams({ query, language })
  return apiRequest<ConsumerSearchResponse>(
    `/api/v1/consumer/products?${searchParams.toString()}`,
  )
}

export function researchConsumerProduct(
  barcode: string,
  language: Language,
  refresh = false,
): Promise<ProductResearchResponse> {
  const searchParams = new URLSearchParams({ refresh: String(refresh), language })
  return apiRequest<ProductResearchResponse>(
    `/api/v1/consumer/products/${barcode}/research?${searchParams.toString()}`,
    { method: 'POST' },
  )
}

export function askConsumerEvidence(
  barcode: string,
  question: string,
  language: Language,
): Promise<ConsumerAnswer> {
  return apiRequest<ConsumerAnswer>(
    `/api/v1/consumer/products/${barcode}/ask`,
    { method: 'POST', body: JSON.stringify({ question, top_k: 4, language }) },
  )
}
