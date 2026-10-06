import { useEffect, useState } from 'react'

type Props = {
  src: string
  alt: string
  loading?: 'eager' | 'lazy'
}

/**
 * Product image with an explicit failure state.
 *
 * If the backend is down or an image file is missing, the browser would
 * otherwise paint its broken-link icon. This swaps in a labelled placeholder
 * tile instead, so a missing asset reads as "no image" rather than as a bug.
 */
export default function ProductImage({ src, alt, loading = 'lazy' }: Props) {
  const [failed, setFailed] = useState(false)

  // A new product (or a retried fetch) deserves a fresh attempt.
  useEffect(() => setFailed(false), [src])

  if (failed) {
    return (
      <div className="product-image product-image--missing" role="img" aria-label={`${alt} — image unavailable`}>
        <span>Image unavailable</span>
      </div>
    )
  }

  return (
    <img
      className="product-image"
      src={src}
      alt={alt}
      loading={loading}
      onError={() => setFailed(true)}
    />
  )
}
