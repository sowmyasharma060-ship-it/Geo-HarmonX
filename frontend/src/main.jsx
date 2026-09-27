import React from 'react'
import ReactDOM from 'react-dom/client'
import Dashboard from './dashboard'
import 'leaflet/dist/leaflet.css'
import './dashboard.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Dashboard />
  </React.StrictMode>
)
