import { useMutation } from '@tanstack/react-query'
import { useRef, useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE_URL } from '../api/client'
import { researchConsumerLabel, researchConsumerProduct } from '../api/consumer'
import { foodCategoryKey } from '../communityCategories'
import type { AssessmentDimension, ConsumerProduct } from '../types/consumer'
import { useI18n, type Language } from '../i18n'
import { AssessmentGrid } from './AssessmentGrid'
import { ConsumerEvidenceAssistant } from './ConsumerEvidenceAssistant'

interface ConsumerProductCardProps {
  product: ConsumerProduct
}

const communityDimensionKeys: Record<AssessmentDimension, 'communityDimension_vegan_composition' | 'communityDimension_environmental_impact' | 'communityDimension_women_workers' | 'communityDimension_minority_inclusion'> = {
  vegan_composition: 'communityDimension_vegan_composition',
  environmental_impact: 'communityDimension_environmental_impact',
  women_workers: 'communityDimension_women_workers',
  minority_inclusion: 'communityDimension_minority_inclusion',
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
  const labelInput = useRef<HTMLInputElement>(null)
  const researchMutation = useMutation({
    mutationFn: (refresh: boolean) => {
      if (!product.barcode) throw new Error(t('researchRequiresBarcode'))
      return researchConsumerProduct(product.barcode, language, refresh)
    },
    onSuccess: (response) => setProduct(response.product),
  })
  const labelMutation = useMutation({
    mutationFn: (image: File) => {
      if (!product.barcode) throw new Error(t('researchRequiresBarcode'))
      return researchConsumerLabel(product.barcode, image, language)
    },
    onSuccess: (response) => {
      setProduct(response.product)
      if (labelInput.current) labelInput.current.value = ''
    },
  })

  function handleLabelImage(event: ChangeEvent<HTMLInputElement>) {
    const image = event.target.files?.[0]
    if (image) labelMutation.mutate(image)
  }

  const communityReportParams = new URLSearchParams()
  if (product.barcode) communityReportParams.set('barcode', product.barcode)
  communityReportParams.set('product_name', product.name)

  return (
    <article className="consumer-product-card">
      <div className="product-overview">
        <div className="product-image-frame">
          {product.image_url ? (
            <img
              src={product.image_url.startsWith('/') ? `${API_BASE_URL}${product.image_url}` : product.image_url}
              alt={t('packageAlt', { name: product.name })}
              loading="lazy"
            />
          ) : (
            <span aria-hidden="true">JS</span>
          )}
        </div>

        <div className="product-identity">
          <p className="product-brand">{product.brand ?? t('brandNotDisclosed')}</p>
          <h2>{product.name}</h2>
          <div className="product-metadata">
            {product.barcode ? <span>{t('barcode', { barcode: product.barcode })}</span> : null}
            {product.category ? <span>{t(foodCategoryKey(product.category))}</span> : null}
            <span>{formatDate(product.last_updated_at, language, t)}</span>
          </div>
        </div>

        {product.catalog_product ? (
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
        ) : null}
      </div>

      {product.catalog_product && product.barcode ? <div className="research-control">
        <div>
          <p className="section-kicker">{t('aiResearch')}</p>
          <strong>
            {product.research
              ? t('sourcesResearched', { count: product.research.source_count })
              : t('researchPrompt')}
          </strong>
          <p>{t('researchExplanation')}</p>
          {product.research?.legal_entity ? (
            <p>
              {t('resolvedEntity', { entity: product.research.legal_entity })}
              {product.research.parent_company
                ? ` · ${t('parentCompany', { company: product.research.parent_company })}`
                : ''}
              {product.research.jurisdiction
                ? ` · ${t('reportingJurisdiction', { jurisdiction: product.research.jurisdiction })}`
                : ''}
              {product.research.entity_source_url ? (
                <> · <a href={product.research.entity_source_url} target="_blank" rel="noreferrer">
                  {t('inspectEntitySource')} <span aria-hidden="true">↗</span>
                </a></>
              ) : null}
            </p>
          ) : null}
        </div>
        <div className="research-actions">
          <button
            type="button"
            className="primary-button"
            disabled={researchMutation.isPending || labelMutation.isPending}
            onClick={() => researchMutation.mutate(Boolean(product.research))}
          >
            {researchMutation.isPending
              ? t('researching')
              : product.research
                ? t('refreshResearch')
                : t('researchGemini')}
          </button>
          <label className={`label-upload-button ${labelMutation.isPending ? 'is-disabled' : ''}`}>
            {labelMutation.isPending ? t('analyzingLabel') : t('analyzeLabelPhoto')}
            <input
              ref={labelInput}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={researchMutation.isPending || labelMutation.isPending}
              onChange={handleLabelImage}
            />
          </label>
        </div>
        {researchMutation.isError || labelMutation.isError ? (
          <p className="form-error" role="alert">
            {labelMutation.error instanceof Error
              ? labelMutation.error.message
              : researchMutation.error instanceof Error
              ? researchMutation.error.message
              : t('researchFailed')}
          </p>
        ) : null}
      </div> : null}

      {product.assessments.length > 0 ? <AssessmentGrid assessments={product.assessments} /> : null}

      {product.community_reports.total > 0 ? (
        <div className="community-report-summary">
          <strong>{t('communitySignalCount', { count: product.community_reports.total })}</strong>
          <p>{t('communitySignalDisclaimer')}</p>
          <div>
            {Object.entries(product.community_reports.assessment_counts).map(([dimension, counts]) => (
              <span key={dimension}>
                {t('communityAssessmentCount', {
                  dimension: t(communityDimensionKeys[dimension as AssessmentDimension]),
                  positive: counts.positive,
                  negative: counts.negative,
                })}
              </span>
            ))}
          </div>
          <Link
            className="secondary-link"
            to={`/community-reports?${communityReportParams.toString()}`}
          >
            {t('viewCommunityReports')}
          </Link>
        </div>
      ) : null}

      {product.catalog_product && product.barcode ? (
        <ConsumerEvidenceAssistant
          barcode={product.barcode}
          productName={product.name}
          enabled={product.research !== null}
        />
      ) : null}

      <div className="product-source">
        <span>
          {t(product.catalog_product ? 'catalogDataFrom' : 'communityDataFrom', {
            source: product.source_name,
          })}
        </span>
        <a
          href={product.source_url.startsWith('/') ? product.source_url : product.source_url}
          target={product.source_url.startsWith('/') ? undefined : '_blank'}
          rel={product.source_url.startsWith('/') ? undefined : 'noreferrer'}
        >
          {t(product.catalog_product ? 'inspectCatalog' : 'viewCommunityReports')}{' '}
          <span aria-hidden="true">↗</span>
        </a>
      </div>
    </article>
  )
}
