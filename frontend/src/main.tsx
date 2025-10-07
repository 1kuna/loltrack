import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import Dashboard from './routes/Dashboard'
import Live from './routes/Live'
import Matches from './routes/Matches'
import Targets from './routes/Targets'
import Settings from './routes/Settings'
import './styles/tailwind.css'

const router = createBrowserRouter([
  { path: '/', element: <Dashboard/> },
  { path: '/live', element: <Live/> },
  { path: '/matches', element: <Matches/> },
  { path: '/targets', element: <Targets/> },
  { path: '/settings', element: <Settings/> },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <div className="min-h-screen grid grid-cols-12 gap-4 p-4">
      <aside className="col-span-2 space-y-2">
        <div className="card text-xl font-bold">LoL Tracker</div>
        <nav className="card space-y-2">
          <a href="/" className="block hover:text-accent">Dashboard</a>
          <a href="/live" className="block hover:text-accent">Live Game</a>
          <a href="/matches" className="block hover:text-accent">Matches</a>
          <a href="/targets" className="block hover:text-accent">Targets</a>
          <a href="/settings" className="block hover:text-accent">Settings</a>
        </nav>
      </aside>
      <main className="col-span-10">
        <RouterProvider router={router} />
      </main>
    </div>
  </React.StrictMode>
)

