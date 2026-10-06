import { useEffect, useState } from 'react'
import ProductCard from '../components/ProductCard'
import { fetchCategories, fetchProducts, type Category, type Product } from '../api'

// Price bands for fast browsing. `test` filters the already-fetched list
// client-side, so clicking a band is instant (no round-trip).
const PRICE_BANDS: { key: string; label: string; test: (price: number) => boolean }[] = [
  { key: 'under50', label: 'Under $50', test: (p) => p < 50 },
  { key: '50to75', label: '$50–$75', test: (p) => p >= 50 && p <= 75 },
  { key: 'over75', label: 'Over $75', test: (p) => p > 75 },
]

export default function Products() {
  const [products, setProducts] = useState<Product[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [activeCategory, setActiveCategory] = useState<string>('')
  const [search, setSearch] = useState('')
  const [inStockOnly, setInStockOnly] = useState(false)
  const [priceBand, setPriceBand] = useState<string>('')
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  const hasActiveFilters =
    search !== '' || activeCategory !== '' || inStockOnly || priceBand !== ''

  function clearFilters() {
    setSearch('')
    setActiveCategory('')
    setInStockOnly(false)
    setPriceBand('')
  }

  // Price filtering is applied client-side on the fetched results for instant feedback.
  const band = PRICE_BANDS.find((b) => b.key === priceBand)
  const visibleProducts = band ? products.filter((p) => band.test(p.price)) : products

  useEffect(() => {
    fetchCategories()
      .then((response) => setCategories(response.categories))
      .catch(() => setCategories([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    // Debounce so typing in the search box doesn't fire a request per keystroke.
    const timer = setTimeout(() => {
      fetchProducts({
        q: search || undefined,
        category: activeCategory || undefined,
        in_stock_only: inStockOnly,
      })
        .then((response) => {
          if (cancelled) return
          setProducts(response.products)
          setStatus('ready')
        })
        .catch(() => {
          if (!cancelled) setStatus('error')
        })
    }, 200)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [search, activeCategory, inStockOnly])

  return (
    <div className="page">
      <header className="page__head">
        <p className="eyebrow">The catalogue</p>
        <h1>Every style we press, in every size we cut.</h1>
        <p className="lede">
          Tees, crewnecks, hoodies, quarter-zips and outerwear — stocked XS through XXL and
          restocked when the shelf gets thin.
        </p>
      </header>

      <div className="filters">
        <input
          type="search"
          className="filters__search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search styles, colors or tags…"
          aria-label="Search products"
        />

        <div className="filters__chips" role="group" aria-label="Filter by category">
          <button
            type="button"
            className={activeCategory === '' ? 'chip chip--active' : 'chip'}
            onClick={() => setActiveCategory('')}
          >
            All
          </button>
          {categories.map((category) => (
            <button
              key={category.category}
              type="button"
              className={activeCategory === category.category ? 'chip chip--active' : 'chip'}
              onClick={() => setActiveCategory(category.category)}
            >
              {category.category} <span className="chip__count">{category.count}</span>
            </button>
          ))}
        </div>

        <div className="filters__chips" role="group" aria-label="Filter by price">
          {PRICE_BANDS.map((pb) => (
            <button
              key={pb.key}
              type="button"
              className={priceBand === pb.key ? 'chip chip--active' : 'chip'}
              onClick={() => setPriceBand(priceBand === pb.key ? '' : pb.key)}
            >
              {pb.label}
            </button>
          ))}
        </div>

        <label className="filters__toggle">
          <input
            type="checkbox"
            checked={inStockOnly}
            onChange={(event) => setInStockOnly(event.target.checked)}
          />
          In stock only
        </label>

        {hasActiveFilters && (
          <button type="button" className="filters__clear" onClick={clearFilters}>
            Clear filters
          </button>
        )}
      </div>

      {status === 'error' && (
        <p className="notice notice--error">
          Could not reach the catalogue API. Start the backend with{' '}
          <code>uvicorn backend.main:app --reload --port 8000</code> and reload.
        </p>
      )}

      {status === 'ready' && (
        <p className="muted result-count">
          {visibleProducts.length} {visibleProducts.length === 1 ? 'style' : 'styles'}
        </p>
      )}

      {status === 'ready' && visibleProducts.length === 0 ? (
        <p className="notice">Nothing matched that. Try a broader search or clear the filters.</p>
      ) : (
        <div className="grid">
          {visibleProducts.map((product) => (
            <ProductCard key={product.product_id} product={product} />
          ))}
        </div>
      )}
    </div>
  )
}
