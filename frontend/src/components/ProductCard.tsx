import { Link } from 'react-router-dom'
import ProductImage from './ProductImage'
import { formatPrice, type Product } from '../api'

export default function ProductCard({ product }: { product: Product }) {
  return (
    <Link to={`/products/${product.product_id}`} className="card" aria-label={product.name}>
      <div className="card__media">
        <ProductImage src={product.image_url} alt={product.name} />
        {!product.in_stock && <span className="card__badge">Sold out</span>}
      </div>
      <div className="card__body">
        <h3 className="card__title">{product.name}</h3>
        <p className="card__price">{formatPrice(product.price)}</p>
        <p className="card__description">{product.description}</p>
        <p className="card__meta">
          {product.garment_type}
          {product.in_stock && ` · ${product.available_sizes.length} sizes in stock`}
        </p>
      </div>
    </Link>
  )
}
