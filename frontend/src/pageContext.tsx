import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

export type PageProduct = {
  product_id: string
  title: string
}

type PageContextValue = {
  /** The product the shopper is currently viewing, or null if not on a product page. */
  product: PageProduct | null
  setProduct: (product: PageProduct | null) => void
}

const PageContext = createContext<PageContextValue | null>(null)

/**
 * Tracks what the shopper is looking at, so the chat widget can tell the agent.
 * ProductDetail sets this when it loads a product and clears it on unmount; the
 * ChatWidget reads it and sends it with each message as page context.
 */
export function PageContextProvider({ children }: { children: ReactNode }) {
  const [product, setProduct] = useState<PageProduct | null>(null)
  const value = useMemo(() => ({ product, setProduct }), [product])
  return <PageContext.Provider value={value}>{children}</PageContext.Provider>
}

export function usePageContext(): PageContextValue {
  const context = useContext(PageContext)
  if (!context) {
    throw new Error('usePageContext must be used within a PageContextProvider')
  }
  return context
}
