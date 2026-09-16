import type { ConsumerSearchResponse } from '../types/consumer'
import { apiRequest } from './client'

export function searchConsumerProducts(
  query: string,
): Promise<ConsumerSearchResponse> {
  const searchParams = new URLSearchParams({ query })
  return apiRequest<ConsumerSearchResponse>(
    `/api/v1/consumer/products?${searchParams.toString()}`,
  )
}
