// Main React app component with routing
import React from 'react'
import { Routes, Route } from 'react-router-dom'
import HomePage from './components/HomePage'
import ChatRoom from './components/ChatRoom'

// Main application component with routing setup
function App() {
  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <Routes>
        {/* Home page for creating/joining rooms */}
        <Route path="/" element={<HomePage />} />
        {/* Chat room page with translation functionality */}
        <Route path="/room/:roomId" element={<ChatRoom />} />
      </Routes>
    </div>
  )
}

export default App