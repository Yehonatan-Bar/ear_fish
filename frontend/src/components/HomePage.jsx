// Home page component for creating and joining chat rooms
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import QRCode from 'qrcode.react'

const HomePage = () => {
  // State for room management
  const [roomId, setRoomId] = useState('')
  const [showQR, setShowQR] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const navigate = useNavigate()

  // Create new chat room via API
  const createRoom = async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/rooms`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })
      
      if (response.ok) {
        const data = await response.json()
        setRoomId(data.room_id)
        setShowQR(true)
      } else {
        console.error('Failed to create room')
      }
    } catch (error) {
      console.error('Error creating room:', error)
    } finally {
      setIsLoading(false)
    }
  }

  // Navigate to chat room
  const joinRoom = () => {
    if (roomId) {
      navigate(`/room/${roomId}`)
    }
  }

  // Generate shareable room URL
  const getRoomUrl = () => {
    return `${window.location.origin}/room/${roomId}`
  }

  // Copy room URL to clipboard
  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(getRoomUrl())
      alert('Room URL copied to clipboard!')
    } catch (error) {
      console.error('Failed to copy:', error)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-900 to-purple-900">
      <div className="bg-white bg-opacity-10 backdrop-blur-md rounded-lg p-8 max-w-md w-full mx-4">
        <h1 className="text-3xl font-bold text-center mb-8 text-white">
          Translation Chat
        </h1>
        
        <div className="space-y-6">
          {!showQR ? (
            // Room creation button
            <div className="text-center">
              <button
                onClick={createRoom}
                disabled={isLoading}
                className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold py-3 px-6 rounded-lg transition-colors duration-200 w-full"
              >
                {isLoading ? 'Creating Room...' : 'Create New Room'}
              </button>
            </div>
          ) : (
            // Room created success state
            <div className="text-center space-y-4">
              <h2 className="text-xl font-semibold text-white">Room Created!</h2>
              
              {/* QR Code for easy sharing */}
              <div className="bg-white p-4 rounded-lg">
                <QRCode 
                  value={getRoomUrl()}
                  size={200}
                  className="mx-auto"
                />
              </div>
              
              {/* Room ID display */}
              <div className="space-y-2">
                <p className="text-gray-300 text-sm">Room ID:</p>
                <p className="text-white font-mono text-sm bg-gray-800 p-2 rounded break-all">
                  {roomId}
                </p>
              </div>
              
              {/* Action buttons */}
              <div className="space-y-2">
                <button
                  onClick={copyToClipboard}
                  className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition-colors duration-200 w-full"
                >
                  Copy Room URL
                </button>
                
                <button
                  onClick={joinRoom}
                  className="bg-purple-600 hover:bg-purple-700 text-white font-bold py-2 px-4 rounded transition-colors duration-200 w-full"
                >
                  Join Room
                </button>
              </div>
            </div>
          )}
        </div>
        
        <div className="mt-8 text-center">
          <p className="text-gray-400 text-sm">
            Share the QR code or room URL with others to start chatting with real-time translation!
          </p>
        </div>
      </div>
    </div>
  )
}

export default HomePage