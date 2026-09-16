import { useState, type FormEvent } from 'react'
import type { RagAnswer } from '../types/rag'

interface RagAssistantProps {
  brandName?: string
  answer?: RagAnswer
  indexedChunkCount: number
  isAsking: boolean
  error: Error | null
  onAsk: (question: string) => Promise<void>
}

export function RagAssistant({
  brandName,
  answer,
  indexedChunkCount,
  isAsking,
  error,
  onAsk,
}: RagAssistantProps) {
  const [question, setQuestion] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await onAsk(question)
  }

  return (
    <section className="rag-assistant panel" aria-labelledby="rag-assistant-title">
      <div className="rag-assistant-intro">
        <div>
          <p className="section-kicker">Grounded RAG assistant</p>
          <h2 id="rag-assistant-title">Question the evidence, not the model</h2>
          <p>
            Semantic retrieval finds the most relevant source passages. The
            answer is returned only with citations to those passages.
          </p>
        </div>
        <div className="rag-index-status" aria-label="RAG index status">
          <strong>{indexedChunkCount}</strong>
          <span>indexed chunks</span>
        </div>
      </div>

      <div className="rag-assistant-grid">
        <form className="rag-question-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Question about {brandName ?? 'the selected brand'}</span>
            <textarea
              required
              minLength={3}
              maxLength={500}
              rows={5}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="What evidence describes working conditions for women?"
            />
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={isAsking || indexedChunkCount === 0}
          >
            {isAsking ? 'Retrieving evidence…' : 'Ask indexed evidence'}
            <span aria-hidden="true">→</span>
          </button>
          {indexedChunkCount === 0 ? (
            <p className="rag-helper-note">
              Upload a new document or index a legacy document before asking a question.
            </p>
          ) : null}
          {error ? <p className="form-error">{error.message}</p> : null}
        </form>

        <div className="rag-answer" aria-live="polite">
          {!answer ? (
            <div className="rag-answer-empty">
              <span aria-hidden="true">RAG</span>
              <p>The cited answer will appear here.</p>
            </div>
          ) : (
            <>
              <div className="rag-answer-heading">
                <span>
                  {answer.insufficient_evidence
                    ? 'Insufficient evidence'
                    : 'Grounded answer'}
                </span>
                <small>{answer.retrieval_model}</small>
              </div>
              <p className="rag-answer-text">{answer.answer}</p>
              {answer.citations.length > 0 ? (
                <div className="rag-citation-list">
                  {answer.citations.map((citation) => (
                    <article className="rag-citation" key={citation.chunk_id}>
                      <header>
                        <strong>[{citation.number}] {citation.source_title}</strong>
                        <span>{Math.round(citation.similarity * 100)}% match</span>
                      </header>
                      <blockquote>“{citation.excerpt}”</blockquote>
                      <footer>
                        <span>{citation.source_provider} · {citation.source_location}</span>
                        <a href={citation.source_url} target="_blank" rel="noreferrer">
                          Open source ↗
                        </a>
                      </footer>
                    </article>
                  ))}
                </div>
              ) : null}
              <p className="rag-model-note">
                Generated with {answer.generation_model} · {answer.prompt_version}
              </p>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
