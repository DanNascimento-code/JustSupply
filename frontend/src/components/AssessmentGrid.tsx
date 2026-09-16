import type {
  AssessmentStatus,
  ConsumerAssessment,
} from '../types/consumer'

interface AssessmentGridProps {
  assessments: ConsumerAssessment[]
}

const statusContent: Record<
  AssessmentStatus,
  { label: string; symbol: string }
> = {
  supported: { label: 'Evidence supports', symbol: '✓' },
  mixed: { label: 'Mixed evidence', symbol: '≈' },
  concern: { label: 'Concern found', symbol: '!' },
  not_disclosed: { label: 'Not disclosed', symbol: '—' },
  unknown: { label: 'Unknown', symbol: '?' },
}

export function AssessmentGrid({ assessments }: AssessmentGridProps) {
  return (
    <div className="assessment-grid">
      {assessments.map((assessment) => {
        const status = statusContent[assessment.status]
        return (
          <article
            className={`assessment-card status-${assessment.status}`}
            key={assessment.dimension}
          >
            <div className="assessment-heading">
              <span className="assessment-symbol" aria-hidden="true">
                {status.symbol}
              </span>
              <div>
                <h3>{assessment.title}</h3>
                <span className="assessment-status">{status.label}</span>
              </div>
            </div>
            <p>{assessment.finding}</p>
            <span className="scope-label">
              {assessment.evidence_scope === 'product'
                ? 'Product-level evidence'
                : 'Brand-level evidence gap'}
            </span>
            {assessment.sources.length > 0 ? (
              <div className="assessment-sources">
                {assessment.sources.map((source) => (
                  <a href={source.url} target="_blank" rel="noreferrer" key={source.url}>
                    {source.provider_name} <span aria-hidden="true">↗</span>
                  </a>
                ))}
              </div>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}
