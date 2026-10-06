import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import ProductCard from '../components/ProductCard'
import { fetchProducts, type Product } from '../api'

export default function Home() {
  const [featured, setFeatured] = useState<Product[]>([])

  useEffect(() => {
    fetchProducts({ in_stock_only: true })
      .then((response) => setFeatured(response.products.slice(0, 3)))
      .catch(() => setFeatured([]))
  }, [])

  return (
    <div className="page">
      <section className="hero">
        <div className="hero__copy">
          <p className="eyebrow">Printed in New Haven since the first cold snap</p>
          <h1>
            Everything you own should feel like
            <span className="hero__accent"> a home game.</span>
          </h1>
          <p className="lede">
            Campus Customs makes the heavyweight fleece, the softened cotton tees, and the
            quarter-zips that end up in every group photo from September through Commencement.
            One blue, done properly, on garments that survive four years of laundry rooms.
          </p>
          <div className="hero__actions">
            <Link to="/products" className="button button--primary">
              Shop the catalogue
            </Link>
            <Link to="/about" className="button button--ghost">
              Our story
            </Link>
          </div>
        </div>
        <aside className="hero__panel">
          <h2>What we are known for</h2>
          <dl>
            <div>
              <dt>Heavyweight fleece</dt>
              <dd>Crewnecks and hoodies with enough weight to hold their shape on Old Campus.</dd>
            </div>
            <div>
              <dt>Game-day graphics</dt>
              <dd>Rivalry tees worth keeping long after the final score stops mattering.</dd>
            </div>
            <div>
              <dt>Team-specific marks</dt>
              <dd>Left-chest lettering for everyone from the sailing team to the fencers.</dd>
            </div>
          </dl>
        </aside>
      </section>

      <section className="strip">
        <div>
          <strong>102 styles</strong>
          <span>Tees, crewnecks, hoodies, quarter-zips and outerwear</span>
        </div>
        <div>
          <strong>XS–XXL</strong>
          <span>Every style cut in the full six-size run</span>
        </div>
        <div>
          <strong>$32–$98</strong>
          <span>Student-budget pricing, no outlet-rack quality</span>
        </div>
      </section>

      <section className="section">
        <div className="section__head">
          <h2>In stock right now</h2>
          <Link to="/products" className="section__link">
            See all products →
          </Link>
        </div>
        {featured.length > 0 ? (
          <div className="grid">
            {featured.map((product) => (
              <ProductCard key={product.product_id} product={product} />
            ))}
          </div>
        ) : (
          <p className="muted">
            Loading the catalogue… if this persists, start the backend with{' '}
            <code>uvicorn backend.main:app --reload --port 8000</code>.
          </p>
        )}
      </section>

      <section className="section band">
        <h2>Built for the walk from Science Hill</h2>
        <p>
          We design for the fifteen minutes outdoors between a 9 a.m. section and a lab, which is
          why the fleece is brushed on the inside, the cuffs are ribbed tight enough to stay put,
          and the navy stays navy after a winter of getting rained on. Pick a size, wear it for
          four years, hand it to a sibling.
        </p>
      </section>
    </div>
  )
}
