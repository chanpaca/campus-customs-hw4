import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ProductImage from '../components/ProductImage'
import { fetchProduct, formatPrice, type Product } from '../api'
import { usePageContext } from '../pageContext'

export default function ProductDetail() {
  const { productId } = useParams<{ productId: string }>()
  const { setProduct: setPageProduct } = usePageContext()
  const [product, setProduct] = useState<Product | null>(null)
  const [selectedSize, setSelectedSize] = useState<string | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    if (!productId) return
    let cancelled = false
    setStatus('loading')
    setSelectedSize(null)

    fetchProduct(productId)
      .then((result) => {
        if (cancelled) return
        setProduct(result)
        setSelectedSize(result.available_sizes[0] ?? null)
        setStatus('ready')
        // Tell the chat widget which product is on screen, so the agent can
        // resolve "this" / "how much is this?" to this item.
        setPageProduct({ product_id: result.product_id, title: result.name })
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })

    return () => {
      cancelled = true
      // Leaving the product page: clear the context so stale product info
      // isn't sent from Home/About/Products.
      setPageProduct(null)
    }
  }, [productId, setPageProduct])

  if (status === 'loading') {
    return (
      <div className="page page--narrow">
        <p className="muted">Loading…</p>
      </div>
    )
  }

  if (status === 'error' || !product) {
    return (
      <div className="page page--narrow">
        <h1>We couldn't find that style.</h1>
        <p className="muted">
          It may have been renamed or pulled from the line.{' '}
          <Link to="/products">Back to the catalogue</Link>.
        </p>
      </div>
    )
  }

  const selectedStock = product.sizes.find((size) => size.size === selectedSize)?.quantity ?? 0

  return (
    <div className="page">
      <nav className="crumbs">
        <Link to="/products">Products</Link>
        <span aria-hidden="true">/</span>
        <span>{product.name}</span>
      </nav>

      <div className="detail">
        <div className="detail__media">
          <ProductImage src={product.image_url} alt={product.name} loading="eager" />
        </div>

        <div className="detail__info">
          <p className="eyebrow">{product.garment_type}</p>
          <h1>{product.name}</h1>
          <p className="detail__price">{formatPrice(product.price)}</p>
          <p className="detail__description">{product.description}</p>

          <div className="detail__block">
            <h2>Colors</h2>
            <ul className="pills">
              {product.colors.map((color) => (
                <li key={color} className="pill">
                  {color}
                </li>
              ))}
            </ul>
          </div>

          <div className="detail__block">
            <h2>Size</h2>
            <div className="sizes" role="group" aria-label="Choose a size">
              {product.sizes.map((size) => {
                const soldOut = size.quantity === 0
                const classes = ['size']
                if (size.size === selectedSize) classes.push('size--active')
                if (soldOut) classes.push('size--out')
                return (
                  <button
                    key={size.size}
                    type="button"
                    className={classes.join(' ')}
                    disabled={soldOut}
                    onClick={() => setSelectedSize(size.size)}
                    title={soldOut ? 'Sold out' : `${size.quantity} in stock`}
                  >
                    {size.size}
                  </button>
                )
              })}
            </div>

            <p className="detail__stock">
              {!product.in_stock
                ? 'Sold out in every size — check back after the next press run.'
                : selectedStock === 0
                  ? 'Pick an available size.'
                  : selectedStock <= 5
                    ? `Only ${selectedStock} left in ${selectedSize}.`
                    : `${selectedStock} in stock in ${selectedSize}.`}
            </p>
          </div>

          <button type="button" className="button button--primary button--wide" disabled={!product.in_stock}>
            {product.in_stock ? 'Add to bag' : 'Sold out'}
          </button>

          <dl className="detail__specs">
            <div>
              <dt>Style code</dt>
              <dd>{product.product_id}</dd>
            </div>
            <div>
              <dt>Total units on hand</dt>
              <dd>{product.total_stock}</dd>
            </div>
          </dl>

          <div className="detail__block">
            <h2>Tagged</h2>
            <ul className="pills pills--quiet">
              {product.search_tags.map((tag) => (
                <li key={tag} className="pill">
                  {tag}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
