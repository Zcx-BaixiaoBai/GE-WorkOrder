import React, { createContext, useContext, useState, useCallback } from 'react'

const ToastContext = createContext(null)

export function ToastProvider({ children }) {
  const [message, setMessage] = useState('')
  const [visible, setVisible] = useState(false)

  const showToast = useCallback((msg, duration = 2500) => {
    setMessage(msg)
    setVisible(true)
    setTimeout(() => setVisible(false), duration)
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {visible && <div className="toast">{message}</div>}
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    // 降级：返回一个空函数，避免在没有Provider时报错
    return { showToast: () => {} }
  }
  return ctx
}
