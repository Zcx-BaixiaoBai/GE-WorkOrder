import React, { useState, useEffect, useCallback } from 'react'
import api from '../services/api'
import { useAuth } from '../services/auth'

export default function Sync() {
  const { canTriggerSync } = useAuth()
  const [status, setStatus] = useState({ isSyncing: false, message: '', bi: null, wy: null, ipms: null })
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(false)
  const [showLogs, setShowLogs] = useState(false)
  const canSync = canTriggerSync()

  const loadStatus = useCallback(async () => {
    try {
      const [allRes, biRes, wyRes, ipmsRes] = await Promise.all([
        api.get('/api/sync_all/status'),
        api.get('/api/sync/status'),
        api.get('/api/sync_wy/status'),
        api.get('/api/sync_ipms/status'),
      ])
      setStatus({
        isSyncing: allRes.data.isSyncing || biRes.data.isSyncing || wyRes.data.is_syncing || ipms.data.is_syncing,
        message: allRes.data.message || '',
        bi: biRes.data,
        wy: wyRes.data,
        ipms: ipms.data,
      })
    } catch (err) { console.error('Sync status error:', err) }
  }, [])

  useEffect(() => {
    loadStatus()
    const interval = setInterval(loadStatus, 3000)
    return () => clearInterval(interval)
  }, [loadStatus])

  const startSync = async () => {
    if (!canSync) return
    setLoading(true)
    try {
      await api.post('/api/sync_all/start')
      loadStatus()
    } catch (err) {
      alert(err.response?.data?.error || '同步启动失败')
    }
    setLoading(false)
  }

  const loadLogs = async () => {
    try {
      const res = await api.get('/api/sync/logs')
      setLogs(res.data.items || res.data || [])
      setShowLogs(true)
    } catch {}
  }

  const channels = [
    { key: 'bi', label: 'BI 工单', data: status.bi, fields: ['progress', 'message', 'lastSyncTime', 'lastSyncResult'] },
    { key: 'wy', label: 'WY 筹建', data: status.wy, fields: ['progress', 'message', 'last_sync_time', 'last_result'] },
    { key: 'ipms', label: 'IPMS 设备', data: status.ipms, fields: ['progress', 'message', 'last_sync_time', 'last_result'] },
  ]

  const overallProgress = channels.reduce((sum, ch) => sum + (ch.data?.progress || 0), 0) / 3

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>数据同步</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-sm" onClick={loadLogs}>查看日志</button>
          {canSync && (
            <button className="btn btn-primary btn-sm" onClick={startSync} disabled={loading || status.isSyncing}>
              {status.isSyncing ? '同步中...' : '开始同步'}
            </button>
          )}
        </div>
      </div>

      {/* 整体进度 */}
      <div className="card" style={{ marginBottom: 16, padding: 24, textAlign: 'center' }}>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8 }}>整体进度</div>
        <div style={{ fontSize: 32, fontWeight: 700, color: status.isSyncing ? 'var(--blue)' : 'var(--text)' }}>
          {status.isSyncing ? `${Math.round(overallProgress)}%` : '就绪'}
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)' }}>{status.message || (status.isSyncing ? '同步进行中...' : '点击"开始同步"启动三通道并发同步')}</div>
      </div>

      {/* 三通道状态卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 16 }}>
        {channels.map(ch => {
          const d = ch.data || {}
          const isWorking = d.isSyncing || d.is_syncing
          const progress = d.progress || 0
          return (
            <div key={ch.key} className="card">
              <div className="card-header">
                <span className="card-title">{ch.label}</span>
                <span className={`badge ${isWorking ? 'badge-blue' : d.lastSyncResult === 'completed' || d.last_result === 'completed' ? 'badge-green' : d.lastSyncResult === 'failed' || d.last_result?.includes('fail') ? 'badge-red' : ''}`} style={{ background: isWorking ? 'var(--blue)' : '' }}>
                  {isWorking ? '同步中' : (d.lastSyncResult || d.last_result || '就绪')}
                </span>
              </div>
              <div className="card-body">
                {/* 进度条 */}
                <div style={{ height: 6, background: 'var(--bg-hover)', borderRadius: 3, marginBottom: 12, overflow: 'hidden' }}>
                  <div style={{ width: `${progress}%`, height: '100%', background: isWorking ? 'var(--blue)' : 'var(--green)', borderRadius: 3, transition: 'width 0.3s' }} />
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 4 }}>{d.message || d.message || '-'}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  上次: {d.lastSyncTime || d.last_sync_time ? (d.lastSyncTime || d.last_sync_time).toString().substring(0, 16).replace('T',' ') : '从未'}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* 日志面板 */}
      {showLogs && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">
            <span className="card-title">同步日志</span>
            <button className="btn btn-sm" onClick={() => setShowLogs(false)}>关闭</button>
          </div>
          <div style={{ maxHeight: 300, overflowY: 'auto', padding: '12px 20px' }}>
            {logs.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-3)', padding: 20 }}>暂无日志</div>
            ) : logs.slice(0, 50).map((log, i) => (
              <div key={i} style={{ padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 12 }}>
                <span style={{ color: 'var(--text-3)', marginRight: 8 }}>{log.started_at || log.created_at || ''}</span>
                <span style={{ color: log.status === 'completed' ? 'var(--green)' : log.status === 'failed' ? 'var(--red)' : 'var(--text-2)' }}>
                  [{log.status || '-'}]
                </span>
                <span style={{ marginLeft: 8, color: 'var(--text-2)' }}>{log.message || log.channel || '-'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!canSync && (
        <div style={{ padding: 16, background: 'var(--bg-hover)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-3)', textAlign: 'center' }}>
          仅系统管理员可触发同步
        </div>
      )}
    </div>
  )
}
