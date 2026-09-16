import type {
  BrandClaim,
  ReviewDecision,
} from '../types/brandEvidence'

interface BrandClaimListProps {
  claims: BrandClaim[]
  isLoading: boolean
  reviewingId?: string
  reviewError: Error | null
  onReview: (claimId: string, decision: ReviewDecision) => void
}

const dimensionLabels = {
  women_workers: 'Women workers',
  minority_inclusion: 'Minority inclusion',
} as const

const findingLabels = {
  supported: 'Evidence supports',
  mixed: 'Mixed evidence',
  concern: 'Concern found',
} as const

export function BrandClaimList({
  claims,
  isLoading,
  reviewingId,
  reviewError,
  onReview,
}: BrandClaimListProps) {
  return (
    <section className="panel evidence-review-panel">
      <div className="panel-heading evidence-list-heading">
        <div>
          <p className="section-kicker">Human review</p>
          <h2>Brand findings</h2>
        </div>
        <span className="record-count">
          {claims.length} {claims.length === 1 ? 'finding' : 'findings'}
        </span>
      </div>

      {isLoading ? (
        <div className="state-card">
          <span className="loading-ring" aria-hidden="true" />
          <strong>Loading brand evidence…</strong>
        </div>
      ) : null}

      {!isLoading && claims.length === 0 ? (
        <div className="state-card">
          <span className="empty-icon" aria-hidden="true">+</span>
          <strong>No social evidence yet</strong>
          <span>Add a source with the form to begin human review.</span>
        </div>
      ) : null}

      {!isLoading && claims.length > 0 ? (
        <div className="brand-claim-list">
          {claims.map((claim) => (
            <article className="brand-claim-card" key={claim.id}>
              <div className="claim-card-heading">
                <div>
                  <span className="claim-dimension">
                    {dimensionLabels[claim.dimension]}
                  </span>
                  <h3>{findingLabels[claim.status]}</h3>
                </div>
                <span className={`review-badge review-${claim.review_status}`}>
                  {claim.review_status}
                </span>
              </div>
              <p>{claim.statement}</p>

              <div className="claim-sources">
                {claim.sources.map((source) => (
                  <a href={source.url} target="_blank" rel="noreferrer" key={source.url}>
                    {source.title} · {source.provider_name} ↗
                  </a>
                ))}
              </div>

              {claim.review_status === 'pending' ? (
                <div className="review-actions">
                  <button
                    type="button"
                    className="approve-button"
                    disabled={reviewingId === claim.id}
                    onClick={() => onReview(claim.id, 'approved')}
                  >
                    Approve for Consumer
                  </button>
                  <button
                    type="button"
                    className="reject-button"
                    disabled={reviewingId === claim.id}
                    onClick={() => onReview(claim.id, 'rejected')}
                  >
                    Reject
                  </button>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      {reviewError ? <p className="inline-error">{reviewError.message}</p> : null}
    </section>
  )
}
