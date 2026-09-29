import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { submitCommunityReport } from '../api/consumer'
import { FOOD_CATEGORIES, foodCategoryKey } from '../communityCategories'
import { useI18n } from '../i18n'
import type { AssessmentDimension, CommunityReportOutcome, FoodCategory } from '../types/consumer'

const assessmentOptions: { dimension: AssessmentDimension; labelKey: 'reportNotVegan' | 'reportEnvironmental' | 'reportWomen' | 'reportMinorities' }[] = [
  { dimension: 'vegan_composition', labelKey: 'reportNotVegan' },
  { dimension: 'environmental_impact', labelKey: 'reportEnvironmental' },
  { dimension: 'women_workers', labelKey: 'reportWomen' },
  { dimension: 'minority_inclusion', labelKey: 'reportMinorities' },
]

export function CommunityReportForm() {
  const { language, t } = useI18n()
  const [productName, setProductName] = useState('')
  const [barcode, setBarcode] = useState('')
  const [category, setCategory] = useState<FoodCategory | ''>('')
  const [details, setDetails] = useState('')
  const [evidenceUrls, setEvidenceUrls] = useState([''])
  const [photo, setPhoto] = useState<File | null>(null)
  const [documents, setDocuments] = useState<File[]>([])
  const [assessments, setAssessments] = useState<Partial<Record<AssessmentDimension, CommunityReportOutcome>>>({})
  const [validationError, setValidationError] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: (form: FormData) => submitCommunityReport(form, language),
    onSuccess: () => {
      setProductName('')
      setBarcode('')
      setCategory('')
      setDetails('')
      setEvidenceUrls([''])
      setPhoto(null)
      setDocuments([])
      setAssessments({})
      setValidationError(null)
    },
  })

  function setAssessment(dimension: AssessmentDimension, outcome: CommunityReportOutcome) {
    setAssessments((current) => ({ ...current, [dimension]: outcome }))
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!productName.trim() && !barcode.trim()) {
      setValidationError(t('reportIdentityRequired'))
      return
    }
    if (Object.keys(assessments).length === 0) {
      setValidationError(t('reportConcernRequired'))
      return
    }
    if (!category) {
      setValidationError(t('reportCategoryRequired'))
      return
    }
    setValidationError(null)
    const form = new FormData()
    if (productName.trim()) form.append('product_name', productName.trim())
    if (barcode.trim()) form.append('barcode', barcode.trim())
    form.append('category', category)
    form.append('details', details.trim())
    Array.from(new Set(evidenceUrls.map((url) => url.trim()).filter(Boolean))).forEach((url) => {
      form.append('evidence_urls', url)
    })
    if (photo) form.append('photo', photo)
    documents.forEach((document) => form.append('documents', document))
    Object.entries(assessments).forEach(([dimension, outcome]) => {
      if (outcome) form.append(dimension, outcome)
    })
    mutation.mutate(form)
  }

  return (
    <section className="community-report-section" aria-labelledby="community-report-title">
      <div className="community-report-copy">
        <p className="section-kicker">{t('communityReports')}</p>
        <h2 id="community-report-title">{t('reportProductTitle')}</h2>
        <p>{t('reportProductBody')}</p>
        <div className="report-trust-note">
          <strong>{t('reportReviewTitle')}</strong>
          <span>{t('reportReviewBody')}</span>
        </div>
      </div>

      <form className="community-report-form" onSubmit={handleSubmit}>
        <div className="report-identity-grid">
          <label>
            {t('reportProductName')}
            <input
              value={productName}
              minLength={2}
              maxLength={300}
              onChange={(event) => setProductName(event.target.value)}
              placeholder={t('reportProductNamePlaceholder')}
            />
          </label>
          <label>
            {t('reportBarcode')}
            <input
              value={barcode}
              inputMode="numeric"
              pattern="[0-9]{8,14}"
              onChange={(event) => setBarcode(event.target.value)}
              placeholder={t('reportBarcodePlaceholder')}
            />
          </label>
        </div>

        <label>
          {t('reportCategory')}
          <select
            required
            value={category}
            onChange={(event) => setCategory(event.target.value as FoodCategory | '')}
          >
            <option value="">{t('reportCategoryPlaceholder')}</option>
            {FOOD_CATEGORIES.map((foodCategory) => (
              <option key={foodCategory} value={foodCategory}>
                {t(foodCategoryKey(foodCategory))}
              </option>
            ))}
          </select>
        </label>

        <fieldset>
          <legend>{t('reportConcernLegend')}</legend>
          <div className="report-assessment-grid">
            {assessmentOptions.map(({ dimension, labelKey }) => (
              <div className="report-assessment-option" key={dimension}>
                <span>{t(labelKey)}</span>
                <div role="group" aria-label={t(labelKey)}>
                  <label>
                    <input
                      type="radio"
                      name={dimension}
                      value="positive"
                      checked={assessments[dimension] === 'positive'}
                      onChange={() => setAssessment(dimension, 'positive')}
                    />
                    {t('reportYes')}
                  </label>
                  <label>
                    <input
                      type="radio"
                      name={dimension}
                      value="negative"
                      checked={assessments[dimension] === 'negative'}
                      onChange={() => setAssessment(dimension, 'negative')}
                    />
                    {t('reportNo')}
                  </label>
                </div>
              </div>
            ))}
          </div>
        </fieldset>

        <label>
          {t('reportDetails')}
          <textarea
            required
            minLength={10}
            maxLength={1500}
            value={details}
            onChange={(event) => setDetails(event.target.value)}
            placeholder={t('reportDetailsPlaceholder')}
          />
        </label>

        <div className="report-identity-grid">
          <div className="report-source-list">
            <span>{t('reportSourceUrl')}</span>
            {evidenceUrls.map((url, index) => (
              <div className="report-source-row" key={index}>
                <input
                  aria-label={`${t('reportSourceUrl')} ${index + 1}`}
                  type="url"
                  value={url}
                  onChange={(event) => setEvidenceUrls((current) =>
                    current.map((item, itemIndex) =>
                      itemIndex === index ? event.target.value : item,
                    ))}
                  placeholder="https://"
                />
                {evidenceUrls.length > 1 ? (
                  <button
                    type="button"
                    aria-label={`${t('removeSourceLink')} ${index + 1}`}
                    onClick={() => setEvidenceUrls((current) =>
                      current.filter((_, itemIndex) => itemIndex !== index),
                    )}
                  >
                    {t('removeSourceLink')}
                  </button>
                ) : null}
              </div>
            ))}
            <button
              className="add-source-link"
              type="button"
              disabled={evidenceUrls.length >= 5}
              onClick={() => setEvidenceUrls((current) => [...current, ''])}
            >
              {t('addSourceLink')}
            </button>
            <small>{t('reportSourceHelp')}</small>
          </div>
          <label>
            {t('reportPhoto')}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => setPhoto(event.target.files?.[0] ?? null)}
            />
            <small>{t('reportPhotoHelp')}</small>
          </label>
          <label>
            {t('reportDocuments')}
            <input
              type="file"
              multiple
              accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,.pdf,.docx,.txt"
              onChange={(event) => setDocuments(Array.from(event.target.files ?? []).slice(0, 3))}
            />
            <small>{t('reportDocumentsHelp')}</small>
          </label>
        </div>

        {validationError ? <p className="form-error" role="alert">{validationError}</p> : null}
        {mutation.isError ? (
          <p className="form-error" role="alert">
            {mutation.error instanceof Error ? mutation.error.message : t('reportFailed')}
          </p>
        ) : null}
        {mutation.data ? (
          <p className="report-success" role="status">{mutation.data.notice}</p>
        ) : null}

        <button className="primary-button" type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? t('reportSubmitting') : t('reportSubmit')}
        </button>
      </form>
    </section>
  )
}
