import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
} from 'react-router-dom'
import { ConsumerSearchPage } from './pages/ConsumerSearchPage'
import { EvidenceWorkspacePage } from './pages/EvidenceWorkspacePage'
import { SupplierWorkspacePage } from './pages/SupplierWorkspacePage'

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <header className="site-header">
          <Link className="brand" to="/" aria-label="JustSupply home">
            <span className="brand-mark" aria-hidden="true">JS</span>
            <span>JustSupply</span>
          </Link>

          <nav className="top-navigation" aria-label="Primary navigation">
            <NavLink to="/" end>Consumer</NavLink>
            <NavLink to="/pro/evidence">Evidence review</NavLink>
            <NavLink to="/pro/suppliers">Suppliers</NavLink>
          </nav>
        </header>

        <Routes>
          <Route path="/" element={<ConsumerSearchPage />} />
          <Route path="/pro/evidence" element={<EvidenceWorkspacePage />} />
          <Route path="/pro/suppliers" element={<SupplierWorkspacePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>

        <footer>
          <span>JustSupply</span>
          <span>Evidence before conclusions.</span>
        </footer>
      </div>
    </BrowserRouter>
  )
}

export default App
