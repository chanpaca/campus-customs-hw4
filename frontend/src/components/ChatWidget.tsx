import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import ProductImage from './ProductImage'
import { fetchChatHistory, formatPrice, sendChatMessage, type ChatProduct, type ChatTurn } from '../api'
import { usePageContext } from '../pageContext'
import { useAuth } from '../auth'

type ChatMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  products?: ChatProduct[]
}

const GREETING: ChatMessage = {
  id: 0,
  role: 'assistant',
  content:
    "Hi! I'm Handsome Dan, the Campus Customs shopping assistant. Ask me for a navy hoodie, " +
    'something for The Game, or whatever is still in stock in a medium.',
}

// Quick-start chips shown before the shopper has typed anything. The label is
// what they see; the message is what actually gets sent to the agent.
const SUGGESTIONS: { label: string; message: string }[] = [
  { label: 'Show hoodies', message: 'What hoodies do you have?' },
  { label: 'Check size availability', message: 'Which sizes are in stock right now?' },
  { label: 'Store hours', message: 'What are your store hours and where are you located?' },
]

export default function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const transcriptRef = useRef<HTMLDivElement>(null)
  const { product: pageProduct } = usePageContext()
  const { user } = useAuth()

  useEffect(() => {
    const node = transcriptRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages, isOpen, sending])

  // On login, repopulate the window with the user's saved conversation.
  // On logout (or as a guest), reset to just the greeting.
  useEffect(() => {
    if (!user) {
      setMessages([GREETING])
      return
    }
    let cancelled = false
    fetchChatHistory()
      .then((past) => {
        if (cancelled) return
        if (past.length === 0) {
          setMessages([GREETING])
          return
        }
        const restored: ChatMessage[] = past.map((message, index) => ({
          id: index + 1,
          role: message.role,
          content: message.content,
          products: message.products,
        }))
        setMessages([GREETING, ...restored])
      })
      .catch(() => {
        if (!cancelled) setMessages([GREETING])
      })
    return () => {
      cancelled = true
    }
  }, [user])

  async function send(rawText: string) {
    const text = rawText.trim()
    if (!text || sending) return

    setError(null)
    setDraft('')

    // Build the history to replay (everything so far except the opening greeting).
    const history: ChatTurn[] = messages
      .filter((message) => message.id !== GREETING.id)
      .map((message) => ({ role: message.role, content: message.content }))

    setMessages((previous) => [...previous, { id: previous.length, role: 'user', content: text }])
    setSending(true)

    try {
      const response = await sendChatMessage(text, history, pageProduct)
      setMessages((previous) => [
        ...previous,
        {
          id: previous.length,
          role: 'assistant',
          content: response.reply,
          products: response.products,
        },
      ])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The assistant is unavailable right now.')
    } finally {
      setSending(false)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void send(draft)
  }

  return (
    <div className="chat">
      {isOpen && (
        <section className="chat__panel" aria-label="Campus Customs shopping assistant">
          <header className="chat__header">
            <div>
              <strong>Shopping assistant</strong>
              <span className="chat__status">Handsome Dan</span>
            </div>
            <button
              type="button"
              className="chat__close"
              onClick={() => setIsOpen(false)}
              aria-label="Close chat"
            >
              ×
            </button>
          </header>

          <div className="chat__transcript" ref={transcriptRef}>
            {messages.map((message) => (
              <div key={message.id} className={`chat__turn chat__turn--${message.role}`}>
                <p className={`chat__bubble chat__bubble--${message.role}`}>{message.content}</p>
                {message.products && message.products.length > 0 && (
                  <div className="chat__cards">
                    {message.products.map((product) => (
                      <Link
                        key={product.product_id}
                        to={`/products/${product.product_id}`}
                        className="chat-card"
                        onClick={() => setIsOpen(false)}
                      >
                        <div className="chat-card__media">
                          <ProductImage src={product.image_url} alt={product.name} loading="eager" />
                          {!product.in_stock && <span className="chat-card__badge">Sold out</span>}
                        </div>
                        <div className="chat-card__body">
                          <span className="chat-card__name">{product.name}</span>
                          <span className="chat-card__price">{formatPrice(product.price)}</span>
                          {product.reason && (
                            <span className="chat-card__reason">{product.reason}</span>
                          )}
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {sending && (
              <div
                className="chat__bubble chat__bubble--assistant chat__bubble--typing"
                aria-live="polite"
                aria-label="Handsome Dan is typing"
              >
                <span className="chat__dot" />
                <span className="chat__dot" />
                <span className="chat__dot" />
              </div>
            )}

            {error && (
              <p className="chat__error" role="alert">
                {error}
              </p>
            )}

            {/* Quick-start chips, shown until the shopper sends their first message. */}
            {messages.length === 1 && !sending && (
              <div className="chat__suggestions" aria-label="Quick actions">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion.label}
                    type="button"
                    className="chat__chip"
                    onClick={() => void send(suggestion.message)}
                  >
                    {suggestion.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <form className="chat__composer" onSubmit={handleSubmit}>
            <input
              type="text"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask about a style, size, or color…"
              aria-label="Message the shopping assistant"
              disabled={sending}
            />
            <button type="submit" disabled={!draft.trim() || sending}>
              Send
            </button>
          </form>
        </section>
      )}

      <button
        type="button"
        className="chat__launcher"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
      >
        {isOpen ? 'Close chat' : 'Ask Handsome Dan'}
      </button>
    </div>
  )
}
