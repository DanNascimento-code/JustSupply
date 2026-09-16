interface ValidationIssue {
  msg: string
}

interface ApiErrorResponse {
  detail?: string | ValidationIssue[]
}

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
).replace(/\/$/, '')

export async function errorMessage(response: Response): Promise<string> {
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

export async function apiRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const headers = new Headers(options?.headers)
  if (!(options?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response))
  }

  return (await response.json()) as T
}
