import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * Scrolls to the top whenever the route changes.
 *
 * React Router keeps the previous scroll position across navigations. Without
 * this, clicking a chat product card while scrolled down a long page (About Us,
 * the Products grid) would change the URL but leave the viewport at the bottom —
 * the shopper would land on the footer instead of the product. Keyed on the
 * pathname so in-page query/hash changes don't force a jump.
 */
export default function ScrollToTop() {
  const { pathname } = useLocation()

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [pathname])

  return null
}
