import { useState, type FormEvent } from 'react'
import type { Commodity, SupplierInput } from '../types/supplier'

interface SupplierFormProps {
  isSubmitting: boolean
  onSubmit: (payload: SupplierInput) => Promise<void>
}

interface FormValues {
  legalName: string
  countryCode: string
  website: string
  commodities: Commodity[]
}

const initialValues: FormValues = {
  legalName: '',
  countryCode: '',
  website: '',
  commodities: [],
}

export function SupplierForm({ isSubmitting, onSubmit }: SupplierFormProps) {
  const [values, setValues] = useState<FormValues>(initialValues)
  const [formError, setFormError] = useState<string | null>(null)

  function toggleCommodity(commodity: Commodity) {
    setValues((current) => ({
      ...current,
      commodities: current.commodities.includes(commodity)
        ? current.commodities.filter((item) => item !== commodity)
        : [...current.commodities, commodity],
    }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    if (values.commodities.length === 0) {
      setFormError('Select at least one commodity.')
      return
    }

    try {
      await onSubmit({
        legal_name: values.legalName.trim(),
        country_code: values.countryCode.toUpperCase(),
        website: values.website.trim() || null,
        commodities: values.commodities,
      })
      setValues(initialValues)
    } catch (error) {
      setFormError(
        error instanceof Error ? error.message : 'The supplier could not be saved.',
      )
    }
  }

  return (
    <aside className="panel form-panel">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">New record</p>
          <h2>Add a supplier</h2>
        </div>
        <span className="step-number" aria-hidden="true">
          01
        </span>
      </div>

      <p className="panel-intro">
        Start with identity and sourcing scope. Evidence and documents will be
        connected in the next milestones.
      </p>

      <form onSubmit={handleSubmit}>
        <label className="field">
          <span>Legal name</span>
          <input
            required
            minLength={2}
            maxLength={200}
            value={values.legalName}
            onChange={(event) =>
              setValues((current) => ({
                ...current,
                legalName: event.target.value,
              }))
            }
            placeholder="e.g. Cooperativa Cacau Justo"
          />
        </label>

        <div className="field-row">
          <label className="field country-field">
            <span>Country code</span>
            <input
              required
              minLength={2}
              maxLength={2}
              pattern="[A-Za-z]{2}"
              value={values.countryCode}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  countryCode: event.target.value.toUpperCase(),
                }))
              }
              placeholder="BR"
            />
          </label>

          <label className="field">
            <span>Website</span>
            <input
              type="url"
              value={values.website}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  website: event.target.value,
                }))
              }
              placeholder="https://example.org"
            />
          </label>
        </div>

        <fieldset>
          <legend>Commodities</legend>
          <div className="commodity-options">
            {(['cocoa', 'coffee'] as const).map((commodity) => (
              <label className="commodity-option" key={commodity}>
                <input
                  type="checkbox"
                  checked={values.commodities.includes(commodity)}
                  onChange={() => toggleCommodity(commodity)}
                />
                <span className="custom-checkbox" aria-hidden="true" />
                <span>{commodity}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {formError ? <p className="form-error">{formError}</p> : null}

        <button className="primary-button" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving supplier…' : 'Add supplier'}
          <span aria-hidden="true">→</span>
        </button>
      </form>
    </aside>
  )
}
