import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { askConsumerEvidence } from '../api/consumer'
import { useI18n } from '../i18n'

interface ConsumerEvidenceAssistantProps {
  barcode: string
  productName: string
  enabled: boolean
}

export function ConsumerEvidenceAssistant({
  barcode,
  productName,
  enabled,
}: ConsumerEvidenceAssistantProps) {
  const { language, t } = useI18n()
  const [question, setQuestion] = useState('')
  const answerMutation = useMutation({
    mutationFn: (value: string) => askConsumerEvidence(barcode, value, language),
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalized = question.trim()
    if (normalized.length >= 3) answerMutation.mutate(normalized)
  }

  return (
    <section className="consumer-evidence-assistant">
      <div>
        <p className="section-kicker">{t('askEvidence')}</p>
        <h3>{t('specificQuestion', { name: productName })}</h3>
        <p>{t('assistantExplanation')}</p>
      </div>
      <form onSubmit={handleSubmit}>
        <label htmlFor={`question-${barcode}`}>{t('questionLabel', { name: productName })}</label>
        <div className="assistant-question-control">
          <input
            id={`question-${barcode}`}
            required
            minLength={3}
            maxLength={500}
            value={question}
            disabled={!enabled || answerMutation.isPending}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={
              enabled
                ? t('questionPlaceholder')
                : t('researchFirst')
            }
          />
          <button type="submit" disabled={!enabled || answerMutation.isPending}>
            {answerMutation.isPending ? t('checking') : t('ask')}
          </button>
        </div>
      </form>
      {answerMutation.isError ? (
        <p className="form-error" role="alert">{t('questionFailed')}</p>
      ) : null}
      {answerMutation.data ? (
        <div className="consumer-answer" aria-live="polite">
          <strong>
            {answerMutation.data.insufficient_evidence
              ? t('insufficientEvidence')
              : t('evidenceAnswer')}
          </strong>
          <p>{answerMutation.data.answer}</p>
          {answerMutation.data.citations.map((citation) => (
            <a href={citation.url} target="_blank" rel="noreferrer" key={citation.evidence_id}>
              [{citation.number}] {citation.title} · {t('match', { value: Math.round(citation.similarity * 100) })}
            </a>
          ))}
        </div>
      ) : null}
    </section>
  )
}
