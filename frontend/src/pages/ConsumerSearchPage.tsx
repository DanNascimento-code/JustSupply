import { useMutation } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { searchConsumerProducts } from '../api/consumer'
import { ConsumerProductCard } from '../components/ConsumerProductCard'
import { useI18n } from '../i18n'

const exampleQueries = ['Oatly', 'dark chocolate', '3017620422003'] as const

export function ConsumerSearchPage() {
  const { language, t } = useI18n()
  const [query, setQuery] = useState('')
  const lastSearch = useRef<string | null>(null)
  const searchMutation = useMutation({
    mutationFn: ({ query: value, language: selectedLanguage }: {
      query: string
      language: typeof language
    }) => searchConsumerProducts(value, selectedLanguage),
  })

  function runSearch(searchQuery: string) {
    const normalizedQuery = searchQuery.trim()
    if (normalizedQuery.length >= 2) {
      lastSearch.current = normalizedQuery
      searchMutation.mutate({ query: normalizedQuery, language })
    }
  }

  useEffect(() => {
    if (lastSearch.current) {
      searchMutation.mutate({ query: lastSearch.current, language })
    }
    // The mutation is intentionally repeated whenever the requested language changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language])

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
          <p className="eyebrow">{t('eyebrow')}</p>
          <h1>{t('heroTitle')}</h1>
          <p className="hero-description">{t('heroDescription')}</p>

          <form className="consumer-search" onSubmit={handleSubmit} role="search">
            <label htmlFor="consumer-query">{t('searchLabel')}</label>
            <div className="search-control">
              <span className="search-icon" aria-hidden="true">⌕</span>
              <input
                id="consumer-query"
                required
                minLength={2}
                maxLength={120}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t('searchPlaceholder')}
                autoComplete="off"
              />
              <button type="submit" disabled={searchMutation.isPending}>
                {searchMutation.isPending ? t('searching') : t('searchEvidence')}
              </button>
            </div>
            <p className="search-note">
              {t('searchNote')}
            </p>
          </form>

          <div className="example-searches" aria-label={t('exampleSearches')}>
            <span>{t('tryExample')}</span>
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
          <p className="section-kicker">{t('resultGuide')}</p>
          <h2>{t('noEvidenceTitle')}</h2>
          <p>{t('noEvidenceBody')}</p>
          <div className="mini-legend">
            <span><i className="legend-supported" /> {t('supported')}</span>
            <span><i className="legend-concern" /> {t('concern')}</span>
            <span><i className="legend-missing" /> {t('notDisclosed')}</span>
          </div>
        </aside>
      </section>

      <section className="consumer-results" aria-live="polite">
        {searchMutation.isPending ? (
          <div className="consumer-state">
            <span className="loading-ring" aria-hidden="true" />
            <strong>{t('checkingEvidence')}</strong>
            <p>{t('waitMessage')}</p>
          </div>
        ) : null}

        {searchMutation.isError ? (
          <div className="consumer-state error-state" role="alert">
            <strong>{t('searchFailed')}</strong>
          </div>
        ) : null}

        {result && !searchMutation.isPending ? (
          <>
            <div className="results-heading">
              <div>
                <p className="section-kicker">{t('searchResult')}</p>
                <h2>
                  {result.total === 0
                    ? t('noMatches', { query: result.query })
                    : result.total === 1
                      ? t('oneMatch', { query: result.query })
                      : t('manyMatches', { count: result.total, query: result.query })}
                </h2>
              </div>
              <span className="query-type-badge">
                {result.query_type === 'barcode' ? t('barcodeSearch') : t('textSearch')}
              </span>
            </div>

            {result.total === 0 ? (
              <div className="consumer-state empty-consumer-state">
                <span className="empty-icon" aria-hidden="true">?</span>
                <strong>{t('noCatalogRecord')}</strong>
                <p>{t('noCatalogHelp')}</p>
              </div>
            ) : (
              <div className="consumer-product-list">
                {result.items.map((product) => (
                  <ConsumerProductCard product={product} key={`${product.barcode}-${language}`} />
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
              <h2>{t('findCatalog')}</h2>
              <p>{t('findCatalogBody')}</p>
            </article>
            <article>
              <span>02</span>
              <h2>{t('readDimension')}</h2>
              <p>{t('readDimensionBody')}</p>
            </article>
            <article>
              <span>03</span>
              <h2>{t('inspectSource')}</h2>
              <p>{t('inspectSourceBody')}</p>
            </article>
          </div>
        ) : null}
      </section>
    </main>
  )
}
