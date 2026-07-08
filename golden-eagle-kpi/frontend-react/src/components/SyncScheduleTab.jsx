import React, { useState, useEffect } from 'react'
import api from '../services/api'

const CHANNELS = [
  { key: 'bi', label: 'BI 工单' },
  { key: 'wy', label: 'WY 筹建' },
  { key: 'ipms', label: 'IPMS 设备' },
]

const TIME_OPTIONS = []
for (let h = 0; h < 24; h++) {
  for (const m of [0, 30]) {
    TIME_OPTIONS.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`)
  }
}

export default function SyncScheduleTab() {
  const [tasks, setTasks] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [toast, setToast] = useState('')
  const [editing, setEditing] = useState(null) // null=列表, {}=新建, {id}=编辑

  useEffect(() => {
    if (loaded) return
    setLoaded(true)
    loadTasks()
  }, [loaded])

  const loadTasks = async () => {
    try {
      const res = await api.get('/api/config/sync-schedule')
      setTasks(res.data.items || [])
    } catch (err) { console.error('Load tasks error:', err) }
  }

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 2500) }

  const handleSave = async () => {
    const t = editing
    if (!t.channels || t.channels.length === 0) { showToast('请至少选择一个通道'); return }
    if (!t.cron_times || t.cron_times.length === 0) { showToast('请至少选择一个时间'); return }
    try {
      if (t.id) {
        await api.put(`/api/config/sync-schedule/${t.id}`, { name: t.name, channels: t.channels, cron_times: t.cron_times, enabled: t.enabled })
      } else {
        await api.post('/api/config/sync-schedule', { name: t.name || '', channels: t.channels, cron_times: t.cron_times, enabled: t.enabled !== false })
      }
      setEditing(null)
      loadTasks()
      showToast('任务已保存，调度器已重载')
    } catch (err) { showToast(err.response?.data?.detail || '保存失败') }
  }

  const handleDelete = async (id) => {
    if (!confirm('确认删除此任务？')) return
    try {
      await api.delete(`/api/config/sync-schedule/${id}`)
      loadTasks()
      showToast('任务已删除')
    } catch { showToast('删除失败') }
  }

  const toggleChannel = (ch) => {
    const current = editing.channels || []
    const updated = current.includes(ch) ? current.filter(c => c !== ch) : [...current, ch]
    setEditing({ ...editing, channels: updated })
  }

  const toggleTime = (time) => {
    const current = editing.cron_times || []
    const updated = current.includes(time) ? current.filter(t => t !== time) : [...current, time]
    setEditing({ ...editing, cron_times: updated })
  }

  // ===== 编辑/新建表单 =====
  if (editing) {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600 }}>{editing.id ? '编辑任务' : '新建任务'}</h3>
          <button className="btn btn-sm" onClick={() => setEditing(null)}>返回列表</button>
        </div>

        <div className="card" style={{ padding: 24, maxWidth: 600 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* 任务名称 */}
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>任务名称</label>
              <input className="input" style={{ width: '100%' }} placeholder="如：每日全量同步" value={editing.name || ''} onChange={e => setEditing({ ...editing, name: e.target.value })} />
            </div>

            {/* 通道选择 */}
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>同步通道（可多选）</label>
              <div style={{ display: 'flex', gap: 12 }}>
                {CHANNELS.map(ch => (
                  <label key={ch.key} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', padding: '8px 14px', border: '1px solid var(--border)', borderRadius: 'var(--radius)', background: (editing.channels || []).includes(ch.key) ? 'var(--bg-active)' : 'var(--bg-card)' }}>
                    <input type="checkbox" checked={(editing.channels || []).includes(ch.key)} onChange={() => toggleChannel(ch.key)} style={{ width: 16, height: 16 }} />
                    <span style={{ fontSize: 13 }}>{ch.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* 时间选择 */}
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>执行时间（可多选）</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, maxHeight: 120, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 8 }}>
                {TIME_OPTIONS.map(t => (
                  <label key={t} style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer', padding: '2px 8px', borderRadius: 'var(--radius-sm)', background: (editing.cron_times || []).includes(t) ? 'var(--blue)' : 'var(--bg-hover)', color: (editing.cron_times || []).includes(t) ? '#fff' : 'var(--text)', fontSize: 11 }}>
                    <input type="checkbox" checked={(editing.cron_times || []).includes(t)} onChange={() => toggleTime(t)} style={{ display: 'none' }} />
                    {t}
                  </label>
                ))}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>已选 {(editing.cron_times || []).length} 个时间点</div>
            </div>

            {/* 启用开关 */}
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" checked={editing.enabled !== false} onChange={e => setEditing({ ...editing, enabled: e.target.checked })} style={{ width: 16, height: 16 }} />
              <span style={{ fontSize: 13 }}>启用此任务</span>
            </label>

            {/* 按钮 */}
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" onClick={handleSave}>保存</button>
              <button className="btn" onClick={() => setEditing(null)}>取消</button>
            </div>
          </div>
        </div>
        {toast && <div className="toast">{toast}</div>}
      </div>
    )
  }

  // ===== 任务列表 =====
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600 }}>定时同步任务</h3>
        <button className="btn btn-primary btn-sm" onClick={() => setEditing({ channels: [], cron_times: [], enabled: true, name: '' })}>+ 新增任务</button>
      </div>

      {tasks.length === 0 ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)' }}>
          暂无定时任务，点击「新增任务」创建
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {tasks.map(task => (
            <div key={task.id} className="card" style={{ padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span className={`badge ${task.enabled ? 'badge-green' : ''}`} style={task.enabled ? {} : { background: 'var(--text-3)', color: '#fff' }}>
                    {task.enabled ? '启用' : '禁用'}
                  </span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{task.name}</span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-sm" onClick={() => setEditing(task)}>编辑</button>
                  <button className="btn btn-sm" onClick={() => handleDelete(task.id)}>删除</button>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 20, marginTop: 12, fontSize: 12 }}>
                <div>
                  <span style={{ color: 'var(--text-3)' }}>通道: </span>
                  {(task.channels || []).map(ch => {
                    const c = CHANNELS.find(x => x.key === ch)
                    return <span key={ch} className="badge badge-blue" style={{ marginRight: 4 }}>{c?.label || ch}</span>
                  })}
                </div>
                <div>
                  <span style={{ color: 'var(--text-3)' }}>时间: </span>
                  <span style={{ color: 'var(--text)' }}>{(task.cron_times || []).join(', ')}</span>
                </div>
              </div>
              {task.last_run_time && (
                <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-3)' }}>
                  上次执行: {task.last_run_time.replace('T', ' ').substring(0, 16)} · 结果: {task.last_run_result || '-'}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
