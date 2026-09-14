import type { Supplier } from '../types/supplier'

interface SupplierListProps {
  suppliers: Supplier[]
  isLoading: boolean
  error: Error | null
  deleteError: Error | null
  deletingId?: string
  onDelete: (supplierId: string) => void
}

const dateFormatter = new Intl.DateTimeFormat('en', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})

export function SupplierList({
  suppliers,
  isLoading,
  error,
  deleteError,
  deletingId,
  onDelete,
}: SupplierListProps) {
  return (
    <section className="panel list-panel">
      <div className="panel-heading list-heading">
        <div>
          <p className="section-kicker">Workspace</p>
          <h2>Supplier directory</h2>
        </div>
        <span className="record-count">
          {suppliers.length} {suppliers.length === 1 ? 'record' : 'records'}
        </span>
      </div>

      {deleteError ? (
        <p className="inline-error" role="alert">
          {deleteError.message}
        </p>
      ) : null}

      {isLoading ? (
        <div className="state-card" role="status">
          <span className="loading-ring" aria-hidden="true" />
          <strong>Loading supplier evidence…</strong>
        </div>
      ) : null}

      {error ? (
        <div className="state-card error-state" role="alert">
          <strong>We could not reach the evidence API.</strong>
          <span>{error.message}</span>
        </div>
      ) : null}

      {!isLoading && !error && suppliers.length === 0 ? (
        <div className="state-card empty-state">
          <span className="empty-icon" aria-hidden="true">
            +
          </span>
          <strong>No suppliers yet</strong>
          <span>Add the first supplier to begin the evidence workspace.</span>
        </div>
      ) : null}

      {!isLoading && !error && suppliers.length > 0 ? (
        <div className="supplier-list">
          {suppliers.map((supplier) => (
            <article className="supplier-card" key={supplier.id}>
              <div className="supplier-identity">
                <span className="country-badge">{supplier.country_code}</span>
                <div>
                  <h3>{supplier.legal_name}</h3>
                  <p>
                    Added {dateFormatter.format(new Date(supplier.created_at))}
                  </p>
                </div>
              </div>

              <div className="supplier-meta">
                <div className="commodity-tags" aria-label="Commodities">
                  {supplier.commodities.map((commodity) => (
                    <span key={commodity}>{commodity}</span>
                  ))}
                </div>
                {supplier.website ? (
                  <a href={supplier.website} target="_blank" rel="noreferrer">
                    Visit website <span aria-hidden="true">↗</span>
                  </a>
                ) : (
                  <span className="not-disclosed">Website not disclosed</span>
                )}
              </div>

              <button
                className="delete-button"
                type="button"
                disabled={deletingId === supplier.id}
                onClick={() => onDelete(supplier.id)}
                aria-label={`Delete ${supplier.legal_name}`}
              >
                {deletingId === supplier.id ? 'Removing…' : 'Remove'}
              </button>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}
