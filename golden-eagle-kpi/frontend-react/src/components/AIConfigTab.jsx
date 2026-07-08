import React, { useState, useEffect } from 'react'
import api from '../services/api'

export default function AIConfigTab() {
  const [config, setConfig] = useState({ model: '', apiKey: '', invokeUrl: '', maxTokens: 16384, temperature: 0.6 })
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/api/config/ai').then(r => setConfig(r.data)).catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaved(false)
    setError('')
    try {
      await api.put('/api/config/ai', config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(err.response?.data?.detail || '保存失败')
    }
  }

  return (
    <div>
      <div className="card" style={{ padding: 24, maxWidth: 600 }}>
        <h3 style={{ marginBottom: 16 }}>AI 对话配置</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>模型名称</label>
            <input className="input" style={{ width: '100%' }} value={config.model} onChange={e => setConfig({ ...config, model: e.target.value })} placeholder="如 qwen/qwen3.5-122b-a10b" />
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>API Key</label>
            <input className="input" style={{ width: '100%' }} type="password" value={config.apiKey} onChange={e => setConfig({ ...config, apiKey: e.target.value })} placeholder="nvapi-..." />
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>API 地址</label>
            <input className="input" style={{ width: '100%' }} value={config.invokeUrl} onChange={e => setConfig({ ...config, invokeUrl: e.target.value })} placeholder="https://integrate.api.nvidia.com/v1/chat/completions" />
          </div>
          <div style={{ display: 'flex', gap: 14 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Max Tokens</label>
              <input className="input" style={{ width: '100%' }} type="number" value={config.maxTokens} onChange={e => setConfig({ ...config, maxTokens: parseInt(e.target.value) || 16384 })} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Temperature</label>
              <input className="input" style={{ width: '100%' }} type="number" step="0.1" value={config.temperature} onChange={e => setConfig({ ...config, temperature: parseFloat(e.target.value) || 0.6 })} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <button className="btn btn-primary" onClick={handleSave}>保存配置</button>
            {saved && <span style={{ color: 'var(--green)', fontSize: 13, lineHeight: '34px' }}>✅ 已保存并生效</span>}
            {error && <span style={{ color: 'var(--red)', fontSize: 13, lineHeight: '34px' }}>{error}</span>}
          </div>
        </div>
      </div>
      <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-3)', padding: '8px 0' }}>
        提示：保存后立即生效，无需重启。API Key 加密存储在 .env 文件中。
      </div>
    </div>
  )
}
