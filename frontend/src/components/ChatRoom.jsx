// Chat room component with real-time translation
import React, { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'

// Supported languages for translation
const LANGUAGES = {
  'en': 'English',
  'es': 'Spanish',
  'fr': 'French',
  'de': 'German',
  'it': 'Italian',
  'pt': 'Portuguese',
  'ru': 'Russian',
  'ja': 'Japanese',
  'ko': 'Korean',
  'zh': 'Chinese',
  'ar': 'Arabic',
  'hi': 'Hindi',
  'he': 'Hebrew',
  'th': 'Thai',
  'vi': 'Vietnamese',
  'tr': 'Turkish',
  'pl': 'Polish',
  'nl': 'Dutch',
  'sv': 'Swedish',
  'da': 'Danish',
  'no': 'Norwegian',
  'fi': 'Finnish'
}

const ChatRoom = () => {
  // Get room ID from URL parameters
  const { roomId } = useParams()
  
  // Chat state management
  const [messages, setMessages] = useState([])
  const [newMessage, setNewMessage] = useState('')
  const [username, setUsername] = useState('')
  const [language, setLanguage] = useState('en')
  const [isConnected, setIsConnected] = useState(false)
  const [showOriginal, setShowOriginal] = useState({})  // Track which messages show original text
  const [showSetup, setShowSetup] = useState(true)  // Show setup form initially
  const [typingUsers, setTypingUsers] = useState(new Set())  // Users currently typing
  const [isTyping, setIsTyping] = useState(false)  // Current user typing state
  
  // Refs for WebSocket and DOM elements
  const websocket = useRef(null)
  const messagesEndRef = useRef(null)
  const clientId = useRef(crypto.randomUUID())  // Unique client identifier
  const typingTimeoutRef = useRef(null)

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  // Scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Establish WebSocket connection to chat room
  const connectWebSocket = () => {
    // Determine WebSocket URL based on current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = import.meta.env.VITE_API_URL 
      ? import.meta.env.VITE_API_URL.replace(/^https?:\/\//, '') 
      : window.location.host
    const wsUrl = `${protocol}//${host}/ws/${roomId}?client_id=${clientId.current}&language=${language}&username=${encodeURIComponent(username)}`
    
    console.log('Connecting to WebSocket:', wsUrl)
    websocket.current = new WebSocket(wsUrl)
    
    // Handle connection open
    websocket.current.onopen = () => {
      setIsConnected(true)
      console.log('Connected to WebSocket')
    }
    
    // Handle incoming messages
    websocket.current.onmessage = (event) => {
      const data = JSON.parse(event.data)
      
      if (data.type === 'message') {
        // Add translated message to chat
        setMessages(prev => [...prev, data])
      } else if (data.type === 'user_joined') {
        // Show user joined notification
        setMessages(prev => [...prev, {
          type: 'system',
          message: `${data.client_id} joined the chat`,
          timestamp: data.timestamp
        }])
      } else if (data.type === 'user_left') {
        // Show user left notification
        setMessages(prev => [...prev, {
          type: 'system',
          message: `${data.username} left the chat`,
          timestamp: data.timestamp
        }])
      } else if (data.type === 'typing') {
        // Update typing indicators
        setTypingUsers(prev => {
          const newSet = new Set(prev)
          if (data.is_typing && data.client_id !== clientId.current) {
            newSet.add(data.username)
          } else {
            newSet.delete(data.username)
          }
          return newSet
        })
      }
    }
    
    // Handle connection close
    websocket.current.onclose = () => {
      setIsConnected(false)
      console.log('Disconnected from WebSocket')
    }
    
    // Handle connection errors
    websocket.current.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }

  // Complete setup and join chat room
  const handleSetup = () => {
    if (username.trim()) {
      setShowSetup(false)
      connectWebSocket()
    }
  }

  // Send message to chat room
  const sendMessage = () => {
    if (newMessage.trim() && websocket.current && isConnected) {
      websocket.current.send(JSON.stringify({
        type: 'message',
        text: newMessage.trim()
      }))
      setNewMessage('')
      handleTyping(false)  // Stop typing indicator
    }
  }

  // Handle typing indicator logic
  const handleTyping = (typing) => {
    if (typing !== isTyping) {
      setIsTyping(typing)
      // Send typing status to other users
      if (websocket.current && isConnected) {
        websocket.current.send(JSON.stringify({
          type: 'typing',
          is_typing: typing
        }))
      }
    }
    
    // Auto-stop typing after 1 second of inactivity
    if (typing) {
      clearTimeout(typingTimeoutRef.current)
      typingTimeoutRef.current = setTimeout(() => {
        handleTyping(false)
      }, 1000)
    }
  }

  // Handle keyboard input in message field
  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      sendMessage()
    } else {
      handleTyping(true)  // Start typing indicator
    }
  }

  // Toggle between original and translated text
  const toggleOriginal = (messageId) => {
    setShowOriginal(prev => ({
      ...prev,
      [messageId]: !prev[messageId]
    }))
  }

  // Get appropriate text to display for a message
  const getMessageText = (message) => {
    // Show original if toggled
    if (showOriginal[message.timestamp]) {
      return message.original_text
    }
    
    // Show original if sender uses same language
    if (message.sender_language === language) {
      return message.original_text
    }
    
    // Show translation or fallback to original
    return message.translations[language] || message.original_text
  }

  // Format timestamp for display
  const formatTime = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    })
  }

  // Show setup form before entering chat
  if (showSetup) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-900 to-purple-900">
        <div className="bg-white bg-opacity-10 backdrop-blur-md rounded-lg p-8 max-w-md w-full mx-4">
          <h1 className="text-2xl font-bold text-center mb-6 text-white">
            Join Chat Room
          </h1>
          
          <div className="space-y-4">
            {/* Username input */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Your Name
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full p-3 rounded-lg bg-gray-800 text-white border border-gray-600 focus:border-blue-500 focus:outline-none"
                placeholder="Enter your name"
              />
            </div>
            
            {/* Language selection */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Your Language
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full p-3 rounded-lg bg-gray-800 text-white border border-gray-600 focus:border-blue-500 focus:outline-none"
              >
                {Object.entries(LANGUAGES).map(([code, name]) => (
                  <option key={code} value={code}>{name}</option>
                ))}
              </select>
            </div>
            
            {/* Join button */}
            <button
              onClick={handleSetup}
              disabled={!username.trim()}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold py-3 px-6 rounded-lg transition-colors duration-200"
            >
              Join Chat
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col">
      {/* Chat header with user info and connection status */}
      <div className="bg-gray-800 p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-white">
            Translation Chat
          </h1>
          <div className="flex items-center space-x-4">
            <span className="text-sm text-gray-400">
              {username} ({LANGUAGES[language]})
            </span>
            {/* Connection status indicator */}
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
          </div>
        </div>
      </div>
      
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message, index) => (
          <div key={index} className={`flex ${message.client_id === clientId.current ? 'justify-end' : 'justify-start'}`}>
            {message.type === 'system' ? (
              // System notifications (user joined/left)
              <div className="text-center text-gray-400 text-sm py-2">
                {message.message}
              </div>
            ) : (
              // Chat messages with translation
              <div className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                message.client_id === clientId.current 
                  ? 'bg-blue-600 text-white' 
                  : 'bg-gray-700 text-white'
              }`}>
                {/* Message header */}
                <div className="text-xs opacity-75 mb-1">
                  {message.username} • {formatTime(message.timestamp)}
                </div>
                {/* Message content */}
                <div className="text-sm">
                  {getMessageText(message)}
                </div>
                {/* Toggle button for original/translated text */}
                {message.sender_language !== language && message.translations[language] && (
                  <button
                    onClick={() => toggleOriginal(message.timestamp)}
                    className="text-xs opacity-75 hover:opacity-100 mt-1 underline"
                  >
                    {showOriginal[message.timestamp] ? 'Show Translation' : 'Show Original'}
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
        
        {/* Typing indicators */}
        {typingUsers.size > 0 && (
          <div className="text-gray-400 text-sm italic">
            {Array.from(typingUsers).join(', ')} {typingUsers.size === 1 ? 'is' : 'are'} typing...
          </div>
        )}
        
        {/* Scroll anchor */}
        <div ref={messagesEndRef} />
      </div>
      
      {/* Message input area */}
      <div className="p-4 bg-gray-800 border-t border-gray-700">
        <div className="flex space-x-2">
          <input
            type="text"
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            className="flex-1 p-3 rounded-lg bg-gray-700 text-white border border-gray-600 focus:border-blue-500 focus:outline-none"
            placeholder="Type your message..."
            disabled={!isConnected}
          />
          <button
            onClick={sendMessage}
            disabled={!newMessage.trim() || !isConnected}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold py-3 px-6 rounded-lg transition-colors duration-200"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

export default ChatRoom