import type { ConsumerProduct } from '../types/consumer'
import { AssessmentGrid } from './AssessmentGrid'

interface ConsumerProductCardProps {
  product: ConsumerProduct
}

function formatDate(value: string | null): string {
  if (value === null) {
    return 'Update date not available'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Update date not available'
  }
  return `Updated ${new Intl.DateTimeFormat('en', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date)}`
}

export function ConsumerProductCard({ product }: ConsumerProductCardProps) {
  return (
    <article className="consumer-product-card">
      <div className="product-overview">
        <div className="product-image-frame">
          {product.image_url ? (
            <img
              src={product.image_url}
              alt={`${product.name} package`}
              loading="lazy"
            />
          ) : (
            <span aria-hidden="true">JS</span>
          )}
        </div>

        <div className="product-identity">
          <p className="product-brand">{product.brand ?? 'Brand not disclosed'}</p>
          <h2>{product.name}</h2>
          <div className="product-metadata">
            <span>Barcode {product.barcode}</span>
            <span>{formatDate(product.last_updated_at)}</span>
          </div>
        </div>

        <div
          className="coverage-meter"
          aria-label={`${product.evidence_coverage_percent}% evidence coverage`}
        >
          <span>Evidence coverage</span>
          <strong>{product.evidence_coverage_percent}%</strong>
          <div className="coverage-track" aria-hidden="true">
            <span style={{ width: `${product.evidence_coverage_percent}%` }} />
          </div>
        </div>
      </div>

      <AssessmentGrid assessments={product.assessments} />

      <div className="product-source">
        <span>Catalog data from {product.source_name}</span>
        <a href={product.source_url} target="_blank" rel="noreferrer">
          Inspect source <span aria-hidden="true">↗</span>
        </a>
      </div>
    </article>
  )
}
