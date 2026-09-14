import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createSupplier, deleteSupplier, listSuppliers } from './api/suppliers'
import { SupplierForm } from './components/SupplierForm'
import { SupplierList } from './components/SupplierList'
import type { SupplierInput } from './types/supplier'

const supplierQueryKey = ['suppliers'] as const

function App() {
  const queryClient = useQueryClient()
  const suppliersQuery = useQuery({
    queryKey: supplierQueryKey,
    queryFn: listSuppliers,
  })
  const createMutation = useMutation({
    mutationFn: createSupplier,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: supplierQueryKey })
    },
  })
  const deleteMutation = useMutation({
    mutationFn: deleteSupplier,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: supplierQueryKey })
    },
  })

  const suppliers = suppliersQuery.data?.items ?? []
  const countries = new Set(suppliers.map((supplier) => supplier.country_code)).size
  const commodities = new Set(
    suppliers.flatMap((supplier) => supplier.commodities),
  ).size

  async function handleCreate(payload: SupplierInput) {
    await createMutation.mutateAsync(payload)
  }

  function handleDelete(supplierId: string) {
    deleteMutation.mutate(supplierId)
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="JustSupply home">
          <span className="brand-mark" aria-hidden="true">
            JS
          </span>
          <span>JustSupply</span>
        </a>
        <span className="environment-badge">Evidence workspace</span>
      </header>

      <main id="top">
        <section className="hero-section">
          <div className="hero-copy">
            <p className="eyebrow">Supplier due diligence, made traceable</p>
            <h1>Know what the evidence supports.</h1>
            <p className="hero-description">
              Organize supplier information without flattening complex ethical
              questions into a single score. Keep every conclusion connected to
              evidence, provenance, and human review.
            </p>
          </div>
          <div
            className={`connection-status ${suppliersQuery.isError ? 'is-error' : ''}`}
            role="status"
          >
            <span className="status-dot" aria-hidden="true" />
            {suppliersQuery.isPending
              ? 'Connecting to evidence API…'
              : suppliersQuery.isError
                ? 'API unavailable'
                : 'Evidence API connected'}
          </div>
        </section>

        <section className="metrics" aria-label="Supplier summary">
          <article className="metric-card">
            <span className="metric-label">Suppliers</span>
            <strong>{suppliersQuery.data?.total ?? 0}</strong>
            <span className="metric-detail">in the workspace</span>
          </article>
          <article className="metric-card">
            <span className="metric-label">Countries</span>
            <strong>{countries}</strong>
            <span className="metric-detail">represented</span>
          </article>
          <article className="metric-card">
            <span className="metric-label">Commodities</span>
            <strong>{commodities}</strong>
            <span className="metric-detail">currently tracked</span>
          </article>
        </section>

        <section className="workspace-grid">
          <SupplierForm
            isSubmitting={createMutation.isPending}
            onSubmit={handleCreate}
          />
          <SupplierList
            suppliers={suppliers}
            isLoading={suppliersQuery.isPending}
            error={suppliersQuery.error}
            deleteError={deleteMutation.error}
            deletingId={
              deleteMutation.isPending ? deleteMutation.variables : undefined
            }
            onDelete={handleDelete}
          />
        </section>
      </main>

      <footer>
        <span>JustSupply Pro</span>
        <span>Evidence before conclusions.</span>
      </footer>
    </div>
  )
}

export default App
