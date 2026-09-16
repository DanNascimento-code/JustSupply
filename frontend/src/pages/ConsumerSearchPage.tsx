import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { searchConsumerProducts } from '../api/consumer'
import { ConsumerProductCard } from '../components/ConsumerProductCard'

const exampleQueries = ['Oatly', 'dark chocolate', '3017620422003'] as const

export function ConsumerSearchPage() {
  const [query, setQuery] = useState('')
  const searchMutation = useMutation({ mutationFn: searchConsumerProducts })

  function runSearch(searchQuery: string) {
    const normalizedQuery = searchQuery.trim()
    if (normalizedQuery.length >= 2) {
      searchMutation.mutate(normalizedQuery)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    runSearch(query)
  }

  function searchExample(example: string) {
    setQuery(example)
    runSearch(example)
  }

  const result = searchMutation.data

  return (
    <main className="consumer-page" id="top">
      <section className="consumer-hero">
        <div className="consumer-hero-copy">
          <p className="eyebrow">Ethical shopping, grounded in evidence</p>
          <h1>Look beyond the label.</h1>
          <p className="hero-description">
            Search a product, brand, or barcode to see what available evidence
            says about vegan composition, environmental impact, women workers,
            and the inclusion of historically excluded people.
          </p>

          <form className="consumer-search" onSubmit={handleSubmit} role="search">
            <label htmlFor="consumer-query">Product, brand, or barcode</label>
            <div className="search-control">
              <span className="search-icon" aria-hidden="true">⌕</span>
              <input
                id="consumer-query"
                required
                minLength={2}
                maxLength={120}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Try a brand, product name, or barcode"
                autoComplete="off"
              />
              <button type="submit" disabled={searchMutation.isPending}>
                {searchMutation.isPending ? 'Searching…' : 'Search evidence'}
              </button>
            </div>
            <p className="search-note">
              Search runs only when submitted to respect the public catalog's
              request limit.
            </p>
          </form>

          <div className="example-searches" aria-label="Example searches">
            <span>Try an example</span>
            {exampleQueries.map((example) => (
              <button
                type="button"
                key={example}
                onClick={() => searchExample(example)}
                disabled={searchMutation.isPending}
              >
                {example}
              </button>
            ))}
          </div>
        </div>

        <aside className="evidence-principle-card">
          <span className="principle-index">01</span>
          <p className="section-kicker">How to read a result</p>
          <h2>No evidence is not the same as negative evidence.</h2>
          <p>
            JustSupply separates a documented concern from information that a
            company has simply not disclosed. Every finding also shows whether
            it applies to a product or a brand.
          </p>
          <div className="mini-legend">
            <span><i className="legend-supported" /> Supported</span>
            <span><i className="legend-concern" /> Concern</span>
            <span><i className="legend-missing" /> Not disclosed</span>
          </div>
        </aside>
      </section>

      <section className="consumer-results" aria-live="polite">
        {searchMutation.isPending ? (
          <div className="consumer-state">
            <span className="loading-ring" aria-hidden="true" />
            <strong>Checking the available evidence…</strong>
            <p>This can take a few seconds.</p>
          </div>
        ) : null}

        {searchMutation.isError ? (
          <div className="consumer-state error-state" role="alert">
            <strong>We could not complete this search.</strong>
            <p>{searchMutation.error.message}</p>
          </div>
        ) : null}

        {result && !searchMutation.isPending ? (
          <>
            <div className="results-heading">
              <div>
                <p className="section-kicker">Search result</p>
                <h2>
                  {result.total === 0
                    ? `No matches for “${result.query}”`
                    : `${result.total} ${result.total === 1 ? 'match' : 'matches'} for “${result.query}”`}
                </h2>
              </div>
              <span className="query-type-badge">
                {result.query_type === 'barcode' ? 'Barcode search' : 'Text search'}
              </span>
            </div>

            {result.total === 0 ? (
              <div className="consumer-state empty-consumer-state">
                <span className="empty-icon" aria-hidden="true">?</span>
                <strong>No catalog record was found</strong>
                <p>Check the spelling or try the barcode printed on the package.</p>
              </div>
            ) : (
              <div className="consumer-product-list">
                {result.items.map((product) => (
                  <ConsumerProductCard product={product} key={product.barcode} />
                ))}
              </div>
            )}

            <p className="evidence-disclaimer">{result.disclaimer}</p>
          </>
        ) : null}

        {searchMutation.isIdle ? (
          <div className="consumer-intro-grid">
            <article>
              <span>01</span>
              <h2>Find a catalog record</h2>
              <p>Use a product name, its brand, or the barcode on its package.</p>
            </article>
            <article>
              <span>02</span>
              <h2>Read each dimension</h2>
              <p>
                See favorable evidence, concerns, uncertainty, and disclosure
                gaps separately.
              </p>
            </article>
            <article>
              <span>03</span>
              <h2>Inspect the source</h2>
              <p>
                Follow the catalog link instead of treating a summary as an
                unquestionable verdict.
              </p>
            </article>
          </div>
        ) : null}
      </section>
    </main>
  )
}
