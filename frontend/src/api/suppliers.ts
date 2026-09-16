import type { Supplier, SupplierInput, SupplierListResponse } from '../types/supplier'
import { API_BASE_URL, apiRequest, errorMessage } from './client'

export function listSuppliers(): Promise<SupplierListResponse> {
  return apiRequest<SupplierListResponse>('/api/v1/suppliers')
}

export function createSupplier(payload: SupplierInput): Promise<Supplier> {
  return apiRequest<Supplier>('/api/v1/suppliers', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteSupplier(supplierId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/suppliers/${supplierId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }
}
