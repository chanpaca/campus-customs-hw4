export type SizeStock = {
  size: string
  quantity: number
}

export type Product = {
  product_id: string
  name: string
  garment_type: string
  category: string
  description: string
  colors: string[]
  search_tags: string[]
  image_file_path: string
  image_url: string
  price: number
  sizes: SizeStock[]
  available_sizes: string[]
  total_stock: number
  in_stock: boolean
}

export type ProductListResponse = {
  total: number
  count: number
  offset: number
  limit: number
  products: Product[]
}

export type Category = {
  category: string
  count: number
}

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} — ${path}`)
  }
  return (await response.json()) as T
}

export type AuthUser = {
  id: number
  first_name: string | null
  last_name: string | null
  name: string
  email: string
}

export type AuthResponse = {
  token: string
  user: AuthUser
}

/** Pull a human-readable message out of a FastAPI error body. */
async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    // Pydantic validation errors arrive as a list of {msg, loc}.
    if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      return body.detail[0].msg.replace(/^Value error,\s*/, '')
    }
  } catch {
    // fall through to the generic message
  }
  return fallback
}

async function postAuth<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await errorMessage(response, `${response.status} ${response.statusText}`))
  }
  return (await response.json()) as T
}

export function registerUser(payload: {
  first_name: string
  last_name: string
  email: string
  password: string
}): Promise<AuthResponse> {
  return postAuth<AuthResponse>('/api/auth/register', payload)
}

export function loginUser(payload: { email: string; password: string }): Promise<AuthResponse> {
  return postAuth<AuthResponse>('/api/auth/login', payload)
}

export async function fetchMe(token: string): Promise<AuthUser> {
  const response = await fetch('/api/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    throw new Error('session-invalid')
  }
  return (await response.json()) as AuthUser
}

export function fetchProducts(params: {
  q?: string
  category?: string
  in_stock_only?: boolean
} = {}): Promise<ProductListResponse> {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.category) query.set('category', params.category)
  if (params.in_stock_only) query.set('in_stock_only', 'true')
  const suffix = query.toString() ? `?${query}` : ''
  return getJSON<ProductListResponse>(`/api/products${suffix}`)
}

export function fetchProduct(productId: string): Promise<Product> {
  return getJSON<Product>(`/api/products/${encodeURIComponent(productId)}`)
}

export function fetchCategories(): Promise<{ categories: Category[] }> {
  return getJSON<{ categories: Category[] }>('/api/categories')
}

export function formatPrice(price: number): string {
  return `$${price.toFixed(2)}`
}

export type ChatProduct = {
  product_id: string
  name: string
  price: number
  image_url: string
  garment_type: string
  in_stock: boolean
  reason: string | null
}

export type ChatTurn = {
  role: 'user' | 'assistant'
  content: string
}

export type PageContext = {
  product_id: string
  title: string
}

export type ChatResponse = {
  reply: string
  products: ChatProduct[]
}

const TOKEN_KEY = 'campus_customs_token'

/** Send a message to the Campus Customs agent, replaying prior turns for context. */
export async function sendChatMessage(
  message: string,
  history: ChatTurn[],
  pageContext: PageContext | null = null,
): Promise<ChatResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  // Attach the session token when signed in, so the backend can identify the
  // customer (for memory + personalization). Guests simply omit it.
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch('/api/chat', {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, history, page_context: pageContext ?? undefined }),
  })
  if (!response.ok) {
    throw new Error(await errorMessage(response, 'The assistant is unavailable right now.'))
  }
  return (await response.json()) as ChatResponse
}

export type ChatHistoryMessage = {
  role: 'user' | 'assistant'
  content: string
  products: ChatProduct[]
}

/**
 * Fetch the logged-in user's past conversation to repopulate the chat window.
 * Returns an empty list for guests (no token) instead of erroring.
 */
export async function fetchChatHistory(): Promise<ChatHistoryMessage[]> {
  const token = localStorage.getItem(TOKEN_KEY)
  if (!token) return []
  const response = await fetch('/api/chat/history', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) return []
  const data = (await response.json()) as { messages: ChatHistoryMessage[] }
  return data.messages
}
