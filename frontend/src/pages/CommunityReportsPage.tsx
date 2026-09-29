import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { API_BASE_URL } from '../api/client'
import { listCommunityReports } from '../api/consumer'
import { FOOD_CATEGORIES, foodCategoryKey } from '../communityCategories'
import { useI18n } from '../i18n'
import type { AssessmentDimension, FoodCategory } from '../types/consumer'

const concernKeys: Record<AssessmentDimension, 'reportNotVegan' | 'reportEnvironmental' | 'reportWomen' | 'reportMinorities'> = {
  vegan_composition: 'reportNotVegan',
  environmental_impact: 'reportEnvironmental',
  women_workers: 'reportWomen',
  minority_inclusion: 'reportMinorities',
}

export function CommunityReportsPage() {
  const { language, t } = useI18n()
  const [searchParams, setSearchParams] = useSearchParams()
  const barcode = searchParams.get('barcode') ?? undefined
  const productName = searchParams.get('product_name') ?? undefined
  const requestedCategory = searchParams.get('category') as FoodCategory | null
  const category = requestedCategory && FOOD_CATEGORIES.includes(requestedCategory)
    ? requestedCategory
    : undefined
  const reports = useQuery({
    queryKey: ['community-reports', language, barcode, productName, category],
    queryFn: () => listCommunityReports(language, barcode, productName, category),
  })

  function filterByCategory(value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set('category', value)
    else next.delete('category')
    setSearchParams(next)
  }

  return (
    <main className="community-reports-page">
      <div className="community-reports-heading">
        <div>
          <p className="section-kicker">{t('communityReports')}</p>
          <h1>{t('publicReportsTitle')}</h1>
          <p>{t('publicReportsBody')}</p>
        </div>
        <Link className="secondary-link" to="/">{t('backToSearch')}</Link>
      </div>

      <label className="community-category-filter">
        {t('filterByCategory')}
        <select value={category ?? ''} onChange={(event) => filterByCategory(event.target.value)}>
          <option value="">{t('allCategories')}</option>
          {FOOD_CATEGORIES.map((foodCategory) => (
            <option key={foodCategory} value={foodCategory}>
              {t(foodCategoryKey(foodCategory))}
            </option>
          ))}
        </select>
      </label>

      {reports.isPending ? <div className="consumer-state">{t('loadingCommunityReports')}</div> : null}
      {reports.isError ? <div className="consumer-state error-state">{t('communityReportsFailed')}</div> : null}
      {reports.data ? (
        <>
          <div className="public-report-warning" role="note">
            <strong>{t('unverifiedCommunityContent')}</strong>
            <p>{reports.data.disclaimer}</p>
          </div>
          {reports.data.total === 0 ? (
            <div className="consumer-state"><strong>{t('noCommunityReports')}</strong></div>
          ) : (
            <div className="public-report-list">
              {reports.data.items.map((report) => (
                <article className="public-report-card" key={report.id}>
                  <div className="public-report-header">
                    <div>
                      <span>{t('unverifiedBadge')}</span>
                      <h2>{report.product_name ?? t('unnamedReportedProduct')}</h2>
                      {report.barcode ? <p>{t('barcode', { barcode: report.barcode })}</p> : null}
                    </div>
                    <time dateTime={report.published_at}>
                      {new Intl.DateTimeFormat(language, { dateStyle: 'medium' }).format(new Date(report.published_at))}
                    </time>
                  </div>
                  <div className="public-report-concerns">
                    <span className="community-category-badge">
                      {t(foodCategoryKey(report.category))}
                    </span>
                    {report.assessments.map((assessment) => (
                      <span
                        aria-label={`${t(concernKeys[assessment.dimension])}: ${t(assessment.outcome === 'positive' ? 'reportYes' : 'reportNo')}`}
                        className={`community-outcome-${assessment.outcome}`}
                        key={assessment.dimension}
                      >
                        {t(concernKeys[assessment.dimension])}: <strong>
                          {t(assessment.outcome === 'positive' ? 'reportYes' : 'reportNo')}
                        </strong>
                      </span>
                    ))}
                  </div>
                  <div className="public-report-observations">
                    <strong>{t('reportDetails')}</strong>
                    <p>{report.observations}</p>
                  </div>
                  {report.photo_url ? (
                    <a href={`${API_BASE_URL}${report.photo_url}`} target="_blank" rel="noreferrer">
                      <img src={`${API_BASE_URL}${report.photo_url}`} alt={t('communityPhotoAlt', { name: report.product_name ?? t('unnamedReportedProduct') })} />
                    </a>
                  ) : null}
                  <div className="public-report-links">
                    {report.evidence_urls.map((url, index) => (
                      <a href={url} key={url} target="_blank" rel="noreferrer">
                        {t('openSubmittedSource')} {index + 1} ↗
                      </a>
                    ))}
                    {report.documents.map((document) => (
                      <a href={`${API_BASE_URL}${document.download_url}`} key={document.id}>
                        {t('downloadSubmittedDocument', { name: document.file_name })}
                      </a>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      ) : null}
    </main>
  )
}
