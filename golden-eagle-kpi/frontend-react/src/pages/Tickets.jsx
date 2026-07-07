import React, { useState, useEffect, useCallback } from 'react'
import api from '../services/api'

export default function Tickets() {
  const [data, setData] = useState({ items: [], total: 0 })
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [filters, setFilters] = useState({ keyword: '', status: '', month: '', ticketType: '' })
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [projects, setProjects] = useState([])
  const projectId = localStorage.getItem('user_project_id') || ''

  useEffect(() => { api.get('/api/config/projects').then(r => setProjects(r.data.items || [])).catch(() => {}) }, [])

  const loadTickets = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, pageSize, projectId }
      if (filters.keyword) params.keyword = filters.keyword
      if (filters.status) params.status = filters.status
      if (filters.month) params.month = filters.month
      if (filters.ticketType) params.ticketType = filters.ticketType
      const res = await api.get('/api/tickets/search', { params })
      setData(res.data)
    } catch (err) { console.error('Tickets load error:', err) }
    setLoading(false)
  }, [page, pageSize, projectId, filters])

  useEffect(() => { loadTickets() }, [loadTickets])
  const handleSearch = () => { setPage(1); loadTickets() }
  const totalPages = Math.ceil(data.total / pageSize) || 1

  // API字段: id, projectName, ticketType, creator, creatorId, createTime, deadline, status, statusText, statusClass, completeTime, handler, description
  const openDetail = (item) => { setDetail(item) }

  const exportExcel = () => {
    const params = new URLSearchParams({ projectId })
    if (filters.keyword) params.set('keyword', filters.keyword)
    if (filters.month) params.set('month', filters.month)
    const token = localStorage.getItem('auth_token')
    window.open(`/api/export/tickets?${params.toString()}`)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>工单管理</h2>
        <button className="btn btn-sm" onClick={exportExcel}>导出Excel</button>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <input className="input" placeholder="搜索工单号/姓名/工号" value={filters.keyword}
          onChange={e => setFilters({ ...filters, keyword: e.target.value })}
          onKeyDown={e => e.key === 'Enter' && handleSearch()} style={{ width: 200 }} />
        <select className="select" value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}>
          <option value="">全部状态</option><option value="pending">待处理</option><option value="processing">处理中</option>
          <option value="completed">已完成</option><option value="closed">已关闭</option>
        </select>
        <select className="select" value={filters.month} onChange={e => setFilters({ ...filters, month: e.target.value })}>
          <option value="">全部月份</option>
          {['2026-06','2026-05','2026-04','2026-03','2026-02','2026-01'].map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <select className="select" value={filters.ticketType} onChange={e => setFilters({ ...filters, ticketType: e.target.value })}>
          <option value="">全部类型</option><option value="物业维修">物业维修</option>
          <option value="保洁报修">保洁报修</option><option value="秩序报修">秩序报修</option>
        </select>
        <button className="btn btn-primary btn-sm" onClick={handleSearch}>搜索</button>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead><tr><th>工单号</th><th>项目</th><th>类型</th><th>描述</th><th>发起人</th><th>创建时间</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>加载中...</td></tr>
              : data.items.length === 0 ? <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>无数据</td></tr>
              : data.items.map((t, i) => (
                <tr key={i} style={{ cursor: 'pointer' }} onClick={() => openDetail(t)}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{t.id || '-'}</td>
                  <td>{t.projectName || '-'}</td>
                  <td>{t.ticketType || '-'}</td>
                  <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.description || '-'}</td>
                  <td>{t.creator || '-'}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-2)' }}>{t.createTime ? String(t.createTime).substring(0, 16) : '-'}</td>
                  <td>{renderStatus(t.statusText, t.statusClass)}</td>
                  <td><button className="btn btn-sm" onClick={e => { e.stopPropagation(); openDetail(t) }}>查看</button></td>
                </tr>
              ))}
            </tbody>
          </table>
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

      {detail && (
        <div style={{ position: 'fixed', top: 0, right: 0, width: 420, height: '100vh', background: 'var(--bg-card)', borderLeft: '1px solid var(--border)', boxShadow: '-4px 0 24px rgba(0,0,0,0.08)', zIndex: 500, overflowY: 'auto' }}>
          <style>{`@keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }`}</style>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>工单详情</span>
            <button className="btn btn-sm" onClick={() => setDetail(null)}>✕</button>
          </div>
          <div style={{ padding: 20 }}>
            <DetailRow label="工单号" value={detail.id} />
            <DetailRow label="项目" value={detail.projectName} />
            <DetailRow label="类型" value={detail.ticketType} />
            <DetailRow label="状态" value={detail.statusText} />
            <DetailRow label="发起人" value={`${detail.creator || ''} (${detail.creatorId || ''})`} />
            <DetailRow label="处理人" value={detail.handler} />
            <DetailRow label="创建时间" value={fmt(detail.createTime)} />
            <DetailRow label="截止时间" value={fmt(detail.deadline)} />
            <DetailRow label="完成时间" value={fmt(detail.completeTime)} />
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>描述</div>
              <div style={{ padding: 12, background: 'var(--bg-hover)', borderRadius: 'var(--radius)', fontSize: 13, lineHeight: 1.6 }}>{detail.description || '-'}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function renderStatus(text, cls) {
  if (!text) return <span className="badge" style={{ background: 'var(--text-3)', color: '#fff' }}>未知</span>
  if (['已完成','已关闭','已解决','已评分'].includes(text)) return <span className="badge badge-green">{text}</span>
  if (['待处理','未解决'].includes(text)) return <span className="badge badge-yellow">{text}</span>
  if (text === '处理中') return <span className="badge badge-blue">{text}</span>
  return <span className="badge" style={{ background: 'var(--text-3)', color: '#fff' }}>{text}</span>
}
function fmt(t) { return t ? String(t).substring(0, 19).replace('T', ' ') : '-' }
function DetailRow({ label, value }) {
  return <div style={{ display: 'flex', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
    <div style={{ width: 80, fontSize: 12, color: 'var(--text-3)', flexShrink: 0 }}>{label}</div>
    <div style={{ fontSize: 13, color: 'var(--text)', flex: 1, wordBreak: 'break-all' }}>{value || '-'}</div>
  </div>
}
