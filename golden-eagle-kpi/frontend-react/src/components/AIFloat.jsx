import React, { useState, useRef, useEffect } from 'react'
import { useAuth } from '../services/auth'

export default function AIFloat() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(() => {
    const saved = localStorage.getItem('aiFloatPos')
    return saved ? JSON.parse(saved) : { x: window.innerWidth - 68, y: window.innerHeight - 68 }
  })
  const [messages, setMessages] = useState([{ role: 'bot', text: '您好！我是金鹰AI助手，可以帮您分析工单数据、KPI完成率、人员绩效等。' }])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const dragRef = useRef(null)
  const hasMoved = useRef(false)

  // 拖拽逻辑
  const onMouseDown = (e) => {
    hasMoved.current = false
    const startX = e.clientX - pos.x
    const startY = e.clientY - pos.y
    const onMove = (ev) => {
      hasMoved.current = true
      const x = Math.max(10, Math.min(window.innerWidth - 58, ev.clientX - startX))
      const y = Math.max(10, Math.min(window.innerHeight - 58, ev.clientY - startY))
      setPos({ x, y })
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      if (hasMoved.current) {
        localStorage.setItem('aiFloatPos', JSON.stringify(pos))
      }
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  const handleClick = () => {
    if (!hasMoved.current) setOpen(!open)
  }

  const send = async () => {
    if (!input.trim() || streaming) return
    const msg = input.trim()
    setMessages(prev => [...prev, { role: 'user', text: msg }])
    setInput('')
    setStreaming(true)
    setMessages(prev => [...prev, { role: 'bot', text: '' }])
    try {
      const res = await fetch('/api/ai/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('auth_token')}` },
        body: JSON.stringify({ message: msg, project_id: parseInt(user?.projectId) || null, user_name: user?.name, employee_id: user?.employeeId })
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') break
            try {
              const json = JSON.parse(data)
              if (json.content) {
                setMessages(prev => {
                  const copy = [...prev]
                  copy[copy.length - 1] = { role: 'bot', text: copy[copy.length - 1].text + json.content }
                  return copy
                })
              }
            } catch {}
          }
        }
      }
    } catch (e) {
      setMessages(prev => {
        const copy = [...prev]
        copy[copy.length - 1] = { role: 'bot', text: 'AI服务暂时不可用，请稍后重试。' }
        return copy
      })
    }
    setStreaming(false)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  // 弹窗方向
  const chatPos = pos.y > window.innerHeight / 2 ? { bottom: '70px' } : { top: '70px' }
  const chatSide = pos.x > window.innerWidth / 2 ? { right: '20px' } : { left: '20px' }

  return (
    <>
      <div
        className={`ai-float-btn ${hasMoved.current ? 'dragging' : ''}`}
        style={{ left: pos.x, top: pos.y }}
        onMouseDown={onMouseDown}
        onClick={handleClick}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5Z" fill="currentColor"/></svg>
      </div>
      {open && (
        <div className="ai-chat-overlay show" style={{ ...chatPos, ...chatSide }}>
          <div className="ai-chat-window">
            <div className="ai-chat-header">
              <div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>金鹰AI助手</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>基于本系统数据库 · 专注KPI分析</div>
              </div>
              <button className="btn btn-sm" onClick={() => setOpen(false)}>✕</button>
            </div>
            <div className="ai-chat-messages">
              {messages.map((m, i) => (
                <div key={i} className={m.role === 'user' ? 'ai-msg-user' : 'ai-msg-bot'}>
                  <div className="ai-msg-bubble" style={{ whiteSpace: 'pre-wrap' }}>{m.text || '...'}</div>
                </div>
              ))}
            </div>
            <div className="ai-chat-input-wrap">
              <textarea
                className="ai-chat-input"
                placeholder="输入问题，按Enter发送..."
                rows="1"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
              />
              <button className="btn btn-primary" onClick={send} disabled={streaming}>发送</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
