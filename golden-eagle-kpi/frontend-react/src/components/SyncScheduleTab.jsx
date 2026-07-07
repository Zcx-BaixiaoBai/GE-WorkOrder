import React, { useState, useEffect, useRef } from 'react'
import api from '../services/api'

const CHANNELS = [
  { key: 'bi', label: 'BI 工单', tip: '需要浏览器环境，建议服务器有 Chrome 时启用' },
  { key: 'wy', label: 'WY 筹建专项', tip: 'HTTP API 同步，适合定时执行' },
  { key: 'ipms', label: 'IPMS 设备', tip: 'HTTP API 同步，适合定时执行' },
]

export default function SyncScheduleTab() {
  const [configs, setConfigs] = useState({})
  const [loaded, setLoaded] = useState(false)
  const [toast, setToast] = useState('')
  const timersRef = useRef({})

  useEffect(() => {
    if (loaded) return
    setLoaded(true)
    loadConfig()
  }, [loaded])

  const loadConfig = async () => {
    try {
      const res = await api.get('/api/config/sync-schedule')
      const map = {}
      ;(res.data.items || []).forEach(c => { map[c.channel] = c })
      setConfigs(map)
    } catch (err) { console.error('Load sync schedule error:', err) }
  }

  const showToast = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(''), 2500)
  }

  const handleSave = async (channel, field, value) => {
    const cfg = configs[channel] || {}
    const updated = { ...cfg, [field]: value }
    // 立即更新 UI
    setConfigs(prev => ({ ...prev, [channel]: updated }))
    // 防抖：500ms 后发送
    if (timersRef.current[channel]) clearTimeout(timersRef.current[channel])
    timersRef.current[channel] = setTimeout(async () => {
      try {
        await api.put(`/api/config/sync-schedule/${channel}`, {
          enabled: updated.enabled,
          cron_times: updated.cron_times,
        })
        showToast(`${channel.toUpperCase()} 定时配置已保存`)
        // 重新加载获取最新状态
        setTimeout(loadConfig, 500)
      } catch (err) {
        showToast(err.response?.status === 403 ? '需要系统管理员权限' : '保存失败')
        loadConfig()
      }
    }, 500)
  }

  const timeOptions = []
  for (let h = 0; h < 24; h++) {
    for (const m of [0, 30]) {
      timeOptions.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`)
    }
  }

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 16 }}>
        {CHANNELS.map(ch => {
          const cfg = configs[ch.key] || {}
          return (
            <div key={ch.key} className="card">
              <div className="card-header">
                <span className="card-title">{ch.label}</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={cfg.enabled || false}
                    onChange={e => handleSave(ch.key, 'enabled', e.target.checked)}
                    style={{ width: 16, height: 16, cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{cfg.enabled ? '已启用' : '已禁用'}</span>
                </label>
              </div>
              <div className="card-body">
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 6 }}>执行时间点（可多选）</div>
                <select
                  multiple
                  value={cfg.cron_times || []}
                  onChange={e => {
                    const selected = Array.from(e.target.selectedOptions).map(o => o.value)
                    handleSave(ch.key, 'cron_times', selected)
                  }}
                  style={{ width: '100%', minHeight: 120, border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 6, fontSize: 12, background: 'var(--bg-card)', color: 'var(--text)' }}
                >
                  {timeOptions.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-3)' }}>
                  <div>上次执行: <span style={{ color: 'var(--text-2)' }}>{cfg.last_run_time ? cfg.last_run_time.replace('T', ' ').substring(0, 16) : '-'}</span></div>
                  <div>执行结果: <span style={{ color: cfg.last_run_result?.includes('fail') ? 'var(--red)' : 'var(--green)' }}>{cfg.last_run_result || '-'}</span></div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-3)', padding: '8px 0' }}>
        提示：BI 工单同步需要浏览器环境，建议仅在服务器有 Chrome 时启用。WY/IPMS 通过 HTTP API 同步，适合定时执行。
      </div>
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
