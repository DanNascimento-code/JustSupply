import type {
  ApiErrorResponse,
  Supplier,
  SupplierInput,
  SupplierListResponse,
} from '../types/supplier'

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
).replace(/\/$/, '')

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorResponse
    if (typeof body.detail === 'string') {
      return body.detail
    }
    if (Array.isArray(body.detail)) {
      return body.detail.map((issue) => issue.msg).join(' ')
    }
  } catch {
    return `The API returned status ${response.status}.`
  }
  return `The API returned status ${response.status}.`
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }

  return (await response.json()) as T
}

export function listSuppliers(): Promise<SupplierListResponse> {
  return request<SupplierListResponse>('/api/v1/suppliers')
}

export function createSupplier(payload: SupplierInput): Promise<Supplier> {
  return request<Supplier>('/api/v1/suppliers', {
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
