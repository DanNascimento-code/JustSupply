import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { researchConsumerProduct } from '../api/consumer'
import type { ConsumerProduct } from '../types/consumer'
import { useI18n, type Language } from '../i18n'
import { AssessmentGrid } from './AssessmentGrid'
import { ConsumerEvidenceAssistant } from './ConsumerEvidenceAssistant'

interface ConsumerProductCardProps {
  product: ConsumerProduct
}

function formatDate(
  value: string | null,
  language: Language,
  translate: (key: 'updateUnavailable' | 'updated', values?: Record<string, string>) => string,
): string {
  if (value === null) return translate('updateUnavailable')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return translate('updateUnavailable')
  const formatted = new Intl.DateTimeFormat(language, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date)
  return translate('updated', { date: formatted })
}

export function ConsumerProductCard({ product: initialProduct }: ConsumerProductCardProps) {
  const { language, t } = useI18n()
  const [product, setProduct] = useState(initialProduct)
  const researchMutation = useMutation({
    mutationFn: (refresh: boolean) => researchConsumerProduct(product.barcode, language, refresh),
    onSuccess: (response) => setProduct(response.product),
  })

  return (
    <article className="consumer-product-card">
      <div className="product-overview">
        <div className="product-image-frame">
          {product.image_url ? (
            <img src={product.image_url} alt={t('packageAlt', { name: product.name })} loading="lazy" />
          ) : (
            <span aria-hidden="true">JS</span>
          )}
        </div>

        <div className="product-identity">
          <p className="product-brand">{product.brand ?? t('brandNotDisclosed')}</p>
          <h2>{product.name}</h2>
          <div className="product-metadata">
            <span>{t('barcode', { barcode: product.barcode })}</span>
            <span>{formatDate(product.last_updated_at, language, t)}</span>
          </div>
        </div>

        <div
          className="coverage-meter"
          aria-label={`${product.evidence_coverage_percent}% ${t('evidenceCoverage')}`}
        >
          <span>{t('evidenceCoverage')}</span>
          <strong>{product.evidence_coverage_percent}%</strong>
          <div className="coverage-track" aria-hidden="true">
            <span style={{ width: `${product.evidence_coverage_percent}%` }} />
          </div>
        </div>
      </div>

      <div className="research-control">
        <div>
          <p className="section-kicker">{t('aiResearch')}</p>
          <strong>
            {product.research
              ? t('sourcesResearched', { count: product.research.source_count })
              : t('researchPrompt')}
          </strong>
          <p>{t('researchExplanation')}</p>
        </div>
        <button
          type="button"
          className="primary-button"
          disabled={researchMutation.isPending}
          onClick={() => researchMutation.mutate(Boolean(product.research))}
        >
          {researchMutation.isPending
            ? t('researching')
            : product.research
              ? t('refreshResearch')
              : t('researchGemini')}
        </button>
        {researchMutation.isError ? (
          <p className="form-error" role="alert">{t('researchFailed')}</p>
        ) : null}
      </div>

      <AssessmentGrid assessments={product.assessments} />

      <ConsumerEvidenceAssistant
        barcode={product.barcode}
        productName={product.name}
        enabled={product.research !== null}
      />

      <div className="product-source">
        <span>{t('catalogDataFrom', { source: product.source_name })}</span>
        <a href={product.source_url} target="_blank" rel="noreferrer">
          {t('inspectCatalog')} <span aria-hidden="true">↗</span>
        </a>
      </div>
    </article>
  )
}
