import { useState, type FormEvent } from 'react'
import type {
  BrandEvidenceInput,
  BrandSummary,
  EvidenceFindingStatus,
  EvidenceSourceType,
  SocialDimension,
} from '../types/brandEvidence'

interface BrandEvidenceFormProps {
  brands: BrandSummary[]
  selectedBrandId: string
  isSubmitting: boolean
  onBrandChange: (brandId: string) => void
  onSubmit: (payload: BrandEvidenceInput) => Promise<void>
}

interface EvidenceFormValues {
  dimension: SocialDimension
  status: EvidenceFindingStatus
  statement: string
  sourceTitle: string
  sourceProvider: string
  sourceUrl: string
  sourceType: EvidenceSourceType
  excerpt: string
  sourceLocation: string
  publishedAt: string
}

const initialValues: EvidenceFormValues = {
  dimension: 'women_workers',
  status: 'supported',
  statement: '',
  sourceTitle: '',
  sourceProvider: '',
  sourceUrl: '',
  sourceType: 'corporate_report',
  excerpt: '',
  sourceLocation: '',
  publishedAt: '',
}

export function BrandEvidenceForm({
  brands,
  selectedBrandId,
  isSubmitting,
  onBrandChange,
  onSubmit,
}: BrandEvidenceFormProps) {
  const [values, setValues] = useState<EvidenceFormValues>(initialValues)
  const [formError, setFormError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    if (!selectedBrandId) {
      setFormError('Select a known brand before adding evidence.')
      return
    }

    try {
      await onSubmit({
        dimension: values.dimension,
        status: values.status,
        statement: values.statement.trim(),
        source_title: values.sourceTitle.trim(),
        source_provider: values.sourceProvider.trim(),
        source_url: values.sourceUrl.trim(),
        source_type: values.sourceType,
        excerpt: values.excerpt.trim() || null,
        source_location: values.sourceLocation.trim() || null,
        published_at: values.publishedAt
          ? `${values.publishedAt}T00:00:00Z`
          : null,
      })
      setValues((current) => ({
        ...initialValues,
        dimension: current.dimension,
      }))
    } catch (error) {
      setFormError(
        error instanceof Error ? error.message : 'The evidence could not be saved.',
      )
    }
  }

  return (
    <aside className="panel evidence-form-panel">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Evidence intake</p>
          <h2>Add a social finding</h2>
        </div>
        <span className="step-number" aria-hidden="true">01</span>
      </div>
      <p className="panel-intro">
        Describe only what the source supports. New findings remain pending
        until they are reviewed in the panel beside this form.
      </p>

      <form onSubmit={handleSubmit}>
        <label className="field">
          <span>Brand</span>
          <select
            required
            value={selectedBrandId}
            onChange={(event) => onBrandChange(event.target.value)}
            disabled={brands.length === 0}
          >
            {brands.length === 0 ? (
              <option value="">No known brands yet</option>
            ) : null}
            {brands.map((brand) => (
              <option value={brand.id} key={brand.id}>{brand.name}</option>
            ))}
          </select>
        </label>

        <div className="field-row">
          <label className="field">
            <span>Impact dimension</span>
            <select
              value={values.dimension}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  dimension: event.target.value as SocialDimension,
                }))
              }
            >
              <option value="women_workers">Women workers</option>
              <option value="minority_inclusion">Minority inclusion</option>
            </select>
          </label>

          <label className="field">
            <span>Finding</span>
            <select
              value={values.status}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  status: event.target.value as EvidenceFindingStatus,
                }))
              }
            >
              <option value="supported">Evidence supports</option>
              <option value="mixed">Mixed evidence</option>
              <option value="concern">Concern found</option>
            </select>
          </label>
        </div>

        <label className="field">
          <span>Evidence-based statement</span>
          <textarea
            required
            minLength={10}
            maxLength={2000}
            rows={4}
            value={values.statement}
            onChange={(event) =>
              setValues((current) => ({ ...current, statement: event.target.value }))
            }
            placeholder="Explain the specific finding without making a broader accusation."
          />
        </label>

        <div className="field-row">
          <label className="field">
            <span>Source title</span>
            <input
              required
              minLength={3}
              maxLength={300}
              value={values.sourceTitle}
              onChange={(event) =>
                setValues((current) => ({ ...current, sourceTitle: event.target.value }))
              }
              placeholder="e.g. 2025 Impact Report"
            />
          </label>
          <label className="field">
            <span>Publisher</span>
            <input
              required
              minLength={2}
              maxLength={200}
              value={values.sourceProvider}
              onChange={(event) =>
                setValues((current) => ({ ...current, sourceProvider: event.target.value }))
              }
              placeholder="Organization name"
            />
          </label>
        </div>

        <label className="field">
          <span>Source URL</span>
          <input
            required
            type="url"
            value={values.sourceUrl}
            onChange={(event) =>
              setValues((current) => ({ ...current, sourceUrl: event.target.value }))
            }
            placeholder="https://example.org/report"
          />
        </label>

        <div className="field-row">
          <label className="field">
            <span>Source type</span>
            <select
              value={values.sourceType}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  sourceType: event.target.value as EvidenceSourceType,
                }))
              }
            >
              <option value="corporate_report">Corporate report</option>
              <option value="certification">Certification</option>
              <option value="ngo_report">NGO report</option>
              <option value="news">News</option>
              <option value="academic_research">Academic research</option>
              <option value="public_database">Public database</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label className="field">
            <span>Publication date</span>
            <input
              type="date"
              value={values.publishedAt}
              onChange={(event) =>
                setValues((current) => ({ ...current, publishedAt: event.target.value }))
              }
            />
          </label>
        </div>

        <label className="field">
          <span>Relevant excerpt (optional)</span>
          <textarea
            maxLength={5000}
            rows={3}
            value={values.excerpt}
            onChange={(event) =>
              setValues((current) => ({ ...current, excerpt: event.target.value }))
            }
            placeholder="Copy only the passage that supports this finding."
          />
        </label>

        <label className="field">
          <span>Source location (optional)</span>
          <input
            maxLength={500}
            value={values.sourceLocation}
            onChange={(event) =>
              setValues((current) => ({ ...current, sourceLocation: event.target.value }))
            }
            placeholder="e.g. page 18, section 3"
          />
        </label>

        {formError ? <p className="form-error">{formError}</p> : null}

        <button
          className="primary-button"
          type="submit"
          disabled={isSubmitting || brands.length === 0}
        >
          {isSubmitting ? 'Saving evidence…' : 'Save as pending'}
          <span aria-hidden="true">→</span>
        </button>
      </form>
    </aside>
  )
}
