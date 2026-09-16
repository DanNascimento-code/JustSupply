import { useState, type FormEvent } from 'react'
import type { BrandSummary, EvidenceSourceType } from '../types/brandEvidence'
import type {
  EvidenceDocument,
  EvidenceDocumentInput,
  FindingReviewDecision,
} from '../types/documentIngestion'

interface DocumentIngestionWorkspaceProps {
  brands: BrandSummary[]
  selectedBrandId: string
  documents: EvidenceDocument[]
  isLoading: boolean
  isUploading: boolean
  reviewingFindingId?: string
  indexingDocumentId?: string
  uploadError: Error | null
  reviewError: Error | null
  onBrandChange: (brandId: string) => void
  onUpload: (input: EvidenceDocumentInput) => Promise<void>
  onReview: (findingId: string, decision: FindingReviewDecision) => void
  onIndex: (documentId: string) => void
}

interface FormValues {
  sourceTitle: string
  sourceProvider: string
  sourceUrl: string
  sourceType: EvidenceSourceType
  publishedAt: string
}

const initialValues: FormValues = {
  sourceTitle: '',
  sourceProvider: '',
  sourceUrl: '',
  sourceType: 'corporate_report',
  publishedAt: '',
}

const dimensionLabels = {
  women_workers: 'Women workers',
  minority_inclusion: 'Minority inclusion',
}

export function DocumentIngestionWorkspace({
  brands,
  selectedBrandId,
  documents,
  isLoading,
  isUploading,
  reviewingFindingId,
  indexingDocumentId,
  uploadError,
  reviewError,
  onBrandChange,
  onUpload,
  onReview,
  onIndex,
}: DocumentIngestionWorkspaceProps) {
  const [values, setValues] = useState<FormValues>(initialValues)
  const [file, setFile] = useState<File | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    setFormError(null)
    if (!file) {
      setFormError('Choose a PDF, TXT, or Markdown document.')
      return
    }
    try {
      await onUpload({ file, ...values })
      setValues(initialValues)
      setFile(null)
      form.reset()
    } catch {
      // The mutation error is rendered below the form.
    }
  }

  return (
    <section className="ai-ingestion-panel panel">
      <div className="ai-ingestion-heading">
        <div>
          <p className="section-kicker">AI-assisted intake</p>
          <h2>Extract findings from a source document</h2>
          <p>
            The model proposes narrowly supported findings. Nothing reaches
            Consumer until a person approves it.
          </p>
        </div>
        <span className="ai-model-badge">Structured output</span>
      </div>

      <div className="ai-ingestion-grid">
        <form className="document-upload-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Document brand</span>
            <select
              required
              value={selectedBrandId}
              onChange={(event) => onBrandChange(event.target.value)}
            >
              {brands.map((brand) => (
                <option value={brand.id} key={brand.id}>{brand.name}</option>
              ))}
            </select>
          </label>

          <label className="file-drop-field">
            <span>Evidence document</span>
            <input
              aria-label="Evidence document"
              type="file"
              accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <small>{file?.name ?? 'PDF, TXT, or Markdown · maximum 5 MB'}</small>
          </label>

          <div className="field-row">
            <label className="field">
              <span>Document source title</span>
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
              <span>Document publisher</span>
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
            <span>Public source URL</span>
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
              <span>Document source type</span>
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
              <span>Document publication date</span>
              <input
                type="date"
                value={values.publishedAt}
                onChange={(event) =>
                  setValues((current) => ({ ...current, publishedAt: event.target.value }))
                }
              />
            </label>
          </div>

          {formError ? <p className="form-error">{formError}</p> : null}
          {uploadError ? <p className="form-error">{uploadError.message}</p> : null}
          <button className="primary-button" type="submit" disabled={isUploading}>
            {isUploading ? 'Extracting evidence…' : 'Upload and extract with AI'}
            <span aria-hidden="true">→</span>
          </button>
          <p className="ai-privacy-note">
            The document text is sent to the configured OpenAI model for extraction.
          </p>
        </form>

        <div className="document-review-column">
          <div className="document-review-heading">
            <div>
              <p className="section-kicker">AI review queue</p>
              <h3>Extracted findings</h3>
            </div>
            <span>{documents.reduce((total, item) => total + item.findings.length, 0)} findings</span>
          </div>

          {reviewError ? <p className="form-error">{reviewError.message}</p> : null}
          {isLoading ? (
            <div className="document-empty-state"><span className="loading-ring" /></div>
          ) : documents.length === 0 ? (
            <div className="document-empty-state">
              <strong>No document extractions yet</strong>
              <p>Upload a source to create the first review queue.</p>
            </div>
          ) : (
            <div className="document-list">
              {documents.map((document) => (
                <article className="document-card" key={document.id}>
                  <header>
                    <div>
                      <span>{document.filename}</span>
                      <h4>{document.source_title}</h4>
                      <p>
                        {document.model_name} · {document.character_count.toLocaleString()} characters
                        {' · '}{document.chunk_count} indexed chunks
                      </p>
                    </div>
                    <a href={document.source_url} target="_blank" rel="noreferrer">Open source ↗</a>
                  </header>
                  {document.chunk_count === 0 ? (
                    <button
                      className="secondary-button document-index-button"
                      type="button"
                      disabled={indexingDocumentId === document.id}
                      onClick={() => onIndex(document.id)}
                    >
                      {indexingDocumentId === document.id
                        ? 'Indexing…'
                        : 'Index for RAG'}
                    </button>
                  ) : null}
                  {document.findings.length === 0 ? (
                    <p className="no-findings-note">
                      The model found no directly supported social evidence.
                    </p>
                  ) : (
                    <div className="extracted-finding-list">
                      {document.findings.map((finding) => (
                        <div className="extracted-finding" key={finding.id}>
                          <div className="finding-heading">
                            <span>{dimensionLabels[finding.dimension]}</span>
                            <span className={`review-badge review-${finding.review_status}`}>
                              {finding.review_status}
                            </span>
                          </div>
                          <strong>{finding.statement}</strong>
                          <blockquote>“{finding.excerpt}”</blockquote>
                          <p>{finding.rationale}</p>
                          {finding.source_location ? <small>{finding.source_location}</small> : null}
                          {finding.review_status === 'pending' ? (
                            <div className="review-actions">
                              <button
                                className="approve-button"
                                type="button"
                                disabled={reviewingFindingId === finding.id}
                                onClick={() => onReview(finding.id, 'approved')}
                              >
                                Approve AI finding
                              </button>
                              <button
                                className="reject-button"
                                type="button"
                                disabled={reviewingFindingId === finding.id}
                                onClick={() => onReview(finding.id, 'rejected')}
                              >
                                Reject
                              </button>
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
