import type {
  AssessmentStatus,
  ConsumerAssessment,
} from '../types/consumer'
import { useI18n } from '../i18n'

interface AssessmentGridProps {
  assessments: ConsumerAssessment[]
}

export function AssessmentGrid({ assessments }: AssessmentGridProps) {
  const { t } = useI18n()
  const statusContent: Record<AssessmentStatus, { label: string; symbol: string }> = {
    supported: { label: t('evidenceSupports'), symbol: '✓' },
    mixed: { label: t('mixedEvidence'), symbol: '≈' },
    concern: { label: t('concernFound'), symbol: '!' },
    not_disclosed: { label: t('notDisclosed'), symbol: '—' },
    unknown: { label: t('unknown'), symbol: '?' },
  }
  const verificationLabels = {
    catalog_data: t('catalogData'),
    multiple_sources: t('multipleSources'),
    single_source: t('singleSource'),
    unverified: t('unverified'),
  }
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
            <div className="assessment-evidence-labels">
              <span className="scope-label">
                {assessment.evidence_scope === 'product'
                  ? t('productEvidence')
                  : t('brandEvidence')}
              </span>
              <span className={`verification-label verification-${assessment.verification}`}>
                {verificationLabels[assessment.verification]}
              </span>
            </div>
            <p className="verification-note">{assessment.verification_note}</p>
            {assessment.limitations ? (
              <details className="assessment-limitations">
                <summary>{t('limitations')}</summary>
                <p>{assessment.limitations}</p>
              </details>
            ) : null}
            {assessment.sources.length > 0 ? (
              <div className="assessment-sources">
                {assessment.sources.map((source, index) => (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    key={`${source.url}-${index}`}
                    title={source.title}
                  >
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
