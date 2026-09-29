import type {
  ConsumerAnswer,
  CommunityReport,
  ConsumerSearchResponse,
  ProductResearchResponse,
  PublicCommunityReportList,
  FoodCategory,
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

export function listCommunityReports(
  language: Language,
  barcode?: string,
  productName?: string,
  category?: FoodCategory,
): Promise<PublicCommunityReportList> {
  const searchParams = new URLSearchParams({ language })
  if (barcode) searchParams.set('barcode', barcode)
  if (productName) searchParams.set('product_name', productName)
  if (category) searchParams.set('category', category)
  return apiRequest<PublicCommunityReportList>(
    `/api/v1/consumer/reports?${searchParams.toString()}`,
  )
}

export function submitCommunityReport(
  form: FormData,
  language: Language,
): Promise<CommunityReport> {
  const searchParams = new URLSearchParams({ language })
  return apiRequest<CommunityReport>(
    `/api/v1/consumer/reports?${searchParams.toString()}`,
    { method: 'POST', body: form },
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

export function researchConsumerLabel(
  barcode: string,
  image: File,
  language: Language,
): Promise<ProductResearchResponse> {
  const form = new FormData()
  form.append('image', image)
  const searchParams = new URLSearchParams({ language })
  return apiRequest<ProductResearchResponse>(
    `/api/v1/consumer/products/${barcode}/research-label?${searchParams.toString()}`,
    { method: 'POST', body: form },
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
