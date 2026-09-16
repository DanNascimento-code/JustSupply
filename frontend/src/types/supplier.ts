export type Commodity = 'cocoa' | 'coffee'

export interface Supplier {
  id: string
  legal_name: string
  country_code: string
  website: string | null
  commodities: Commodity[]
  created_at: string
  updated_at: string
}

export interface SupplierInput {
  legal_name: string
  country_code: string
  website: string | null
  commodities: Commodity[]
}

export interface SupplierListResponse {
  items: Supplier[]
  total: number
}
