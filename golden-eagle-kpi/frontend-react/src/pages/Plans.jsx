import React, { useState, useEffect, useCallback } from 'react'
import api from '../services/api'

const TABS = [{ key: 'wy', label: '金鹰PLAN' }, { key: 'patrol', label: '巡检任务' }, { key: 'maintain', label: '维保任务' }]
const WY_STATES = ['即将开始','进行中','即将到期','到期预警','逾期报警','已逾期','已完成','已暂停']

export default function Plans() {
  const [tab, setTab] = useState('wy')
  const [data, setData] = useState({ items: [], total: 0 })
  const [stats, setStats] = useState(null)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [stateFilter, setStateFilter] = useState('')
  const [selectedMonth, setSelectedMonth] = useState('')
  const [months, setMonths] = useState([])
  const [loading, setLoading] = useState(false)
  const projectId = localStorage.getItem('user_project_id') || ''

  useEffect(() => {
    api.get('/api/stats/months', { params: { projectId } }).then(r => setMonths(r.data.months || [])).catch(() => {})
  }, [projectId])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, page_size: pageSize, projectId }
      if (stateFilter) {
        if (tab === 'wy') params.plan_state = stateFilter
        else params.task_state_name = stateFilter
      }
      if (selectedMonth) params.month = selectedMonth
      if (tab === 'wy') {
        const [listRes, statsRes] = await Promise.all([
          api.get('/api/wy/plans', { params }),
          api.get('/api/wy/stats', { params: { projectId, ...(selectedMonth && { month: selectedMonth }) } }),
        ])
        setData(listRes.data)
        setStats(statsRes.data)
      } else {
        params.task_type = tab
        const [listRes, statsRes] = await Promise.all([
          api.get('/api/ipms/tasks', { params }),
          api.get('/api/ipms/stats', { params: { task_type: tab, projectId, ...(selectedMonth && { month: selectedMonth }) } }),
        ])
        setData(listRes.data)
        setStats(statsRes.data)
      }
    } catch (err) { console.error('Plans load error:', err) }
    setLoading(false)
  }, [tab, page, pageSize, projectId, stateFilter, selectedMonth])

  useEffect(() => { load() }, [load])
  const totalPages = Math.ceil(data.total / pageSize) || 1
  const ganttItems = (data.items || []).slice(0, 15)
  const today = new Date()

  // WY stats字段: total, in_progress, expiring, overdue, finished, paused
  // IPMS stats字段: total, in_progress, finished, overdue
  const renderStatsCards = () => {
    if (!stats) return null
    if (tab === 'wy') {
      return (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
          <StatCard label="总专项" value={stats.total || 0} />
          <StatCard label="进行中" value={stats.in_progress || 0} color="green" />
          <StatCard label="已逾期" value={stats.overdue || 0} color="red" />
          <StatCard label="已完成" value={stats.finished || 0} color="blue" />
        </div>
      )
    }
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
        <StatCard label="总任务" value={stats.total || 0} />
        <StatCard label="进行中" value={stats.in_progress || 0} color="green" />
        <StatCard label="已完成" value={stats.finished || 0} color="blue" />
        <StatCard label="已逾期" value={stats.overdue || 0} color="red" />
      </div>
    )
  }

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>计划管理</h2>

      <div className="config-tabs" style={{ marginBottom: 16 }}>
        {TABS.map(t => (
          <button key={t.key} className={`config-tab ${tab === t.key ? 'active' : ''}`} onClick={() => { setTab(t.key); setPage(1); setStateFilter('') }}>{t.label}</button>
        ))}
      </div>

      {renderStatsCards()}

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <select className="select" value={selectedMonth} onChange={e => { setSelectedMonth(e.target.value); setPage(1) }}>
          <option value="">全部月份</option>
          {months.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        {tab === 'wy' ? (
          <select className="select" value={stateFilter} onChange={e => { setStateFilter(e.target.value); setPage(1) }}>
            <option value="">全部状态</option>
            {WY_STATES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        ) : (
          <select className="select" value={stateFilter} onChange={e => { setStateFilter(e.target.value); setPage(1) }}>
            <option value="">全部状态</option>
            <option value="完成">完成</option>
            <option value="审核关闭">审核关闭</option>
            <option value="进行中">进行中</option>
            <option value="未开始">未开始</option>
          </select>
        )}
      </div>

      {/* WY 甘特图 */}
      {tab === 'wy' && ganttItems.length > 0 && (
        <div className="card" style={{ marginBottom: 16, overflow: 'hidden' }}>
          <div className="card-header"><span className="card-title">甘特图（前15条）</span></div>
          <div className="card-body" style={{ overflowX: 'auto' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 800 }}>
              {ganttItems.map((item, i) => {
                const start = item.plan_start_date ? new Date(item.plan_start_date) : null
                const end = item.plan_end_date ? new Date(item.plan_end_date) : null
                if (!start || !end) return <div key={i} style={{ fontSize: 12 }}>{item.special_name || '-'}: 日期无效</div>
                const leftPct = ((start.getMonth() + 1) / 12) * 50
                const widthPct = Math.max(5, ((end - start) / (1000 * 60 * 60 * 24 * 365)) * 50)
                const isOverdue = end < today && item.finish_flag !== 1
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 160, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0 }}>{item.special_name || '-'}</div>
                    <div style={{ flex: 1, position: 'relative', height: 20, background: 'var(--bg-hover)', borderRadius: 4 }}>
                      <div style={{ position: 'absolute', left: `${leftPct}%`, width: `${widthPct}%`, height: '100%', background: isOverdue ? 'var(--red)' : 'var(--blue)', borderRadius: 4, opacity: item.finish_flag === 1 ? 0.4 : 1 }} />
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-3)', flexShrink: 0 }}>{item.plan_end_date || ''}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* 表格 */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          {tab === 'wy' ? (
            <table className="table">
              <thead><tr><th>专项名称</th><th>项目</th><th>责任人</th><th>计划开始</th><th>计划完成</th><th>状态</th><th>完成</th></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>加载中...</td></tr>
                : data.items.length === 0 ? <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>无数据</td></tr>
                : data.items.map((item, i) => (
                  <tr key={i}>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.special_name || '-'}</td>
                    <td>{item.project_name || '-'}</td>
                    <td>{item.person_name || '-'}</td>
                    <td style={{ fontSize: 12 }}>{item.plan_start_date || '-'}</td>
                    <td style={{ fontSize: 12 }}>{item.plan_end_date || '-'}</td>
                    <td>{item.plan_state ? <span className={`badge ${item.plan_state.includes('逾期') ? 'badge-red' : item.plan_state === '已完成' ? 'badge-green' : 'badge-blue'}`}>{item.plan_state}</span> : '-'}</td>
                    <td>{item.finish_flag === 1 ? '✅' : '⬜'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            // IPMS字段: task_name, project_name, user_name, start_time, end_time, task_state_name
            <table className="table">
              <thead><tr><th>任务名称</th><th>项目</th><th>执行人</th><th>开始时间</th><th>结束时间</th><th>状态</th></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={6} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>加载中...</td></tr>
                : data.items.length === 0 ? <tr><td colSpan={6} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>无数据</td></tr>
                : data.items.map((item, i) => (
                  <tr key={i}>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.task_name || '-'}</td>
                    <td>{item.project_name || '-'}</td>
                    <td>{item.user_name || '-'}</td>
                    <td style={{ fontSize: 12 }}>{item.start_time ? String(item.start_time).substring(0, 16) : '-'}</td>
                    <td style={{ fontSize: 12 }}>{item.end_time ? String(item.end_time).substring(0, 16) : '-'}</td>
                    <td>{item.task_state_name ? <span className={`badge ${['完成','审核关闭'].includes(item.task_state_name) ? 'badge-green' : 'badge-blue'}`}>{item.task_state_name}</span> : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 20px', borderTop: '1px solid var(--border)' }}>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>共 {data.total} 条</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
            <span style={{ padding: '4px 10px', fontSize: 12, lineHeight: '20px' }}>{page} / {totalPages}</span>
            <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</button>
          </div>
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, color }) {
  const cv = color === 'red' ? 'var(--red)' : color === 'green' ? 'var(--green)' : color === 'blue' ? 'var(--blue)' : 'var(--text)'
  return <div className="card" style={{ padding: 16 }}><div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>{label}</div><div style={{ fontSize: 22, fontWeight: 700, color: cv }}>{value}</div></div>
}
