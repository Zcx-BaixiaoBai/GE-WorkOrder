import React, { useState, useEffect, useCallback } from 'react'
import api from '../services/api'

export default function Personnel() {
  const [data, setData] = useState({ items: [], total: 0 })
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [roleFilter, setRoleFilter] = useState('')
  const [keyword, setKeyword] = useState('')
  const [selectedMonth, setSelectedMonth] = useState('')
  const [months, setMonths] = useState([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(null)
  const [showImport, setShowImport] = useState(false)
  const projectId = localStorage.getItem('user_project_id') || ''

  useEffect(() => {
    api.get('/api/stats/months', { params: { projectId } }).then(r => setMonths(r.data.months || [])).catch(() => {})
  }, [projectId])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, pageSize, projectId }
      if (keyword) params.keyword = keyword
      if (roleFilter) params.role = roleFilter
      if (selectedMonth) params.month = selectedMonth
      const res = await api.get('/api/personnel/list', { params })
      setData(res.data)
    } catch (err) { console.error('Personnel load error:', err) }
    setLoading(false)
  }, [page, pageSize, projectId, keyword, roleFilter, selectedMonth])

  useEffect(() => { load() }, [load])

  // API字段: id, name, position(职务), role(系统角色), projectId, projectName, count(发起数), target(目标), actual, deduction, isOutsourcing, status
  const handleDelete = async (id) => {
    if (!confirm('确认删除？')) return
    try { await api.delete(`/api/personnel/${id}`); load() } catch {}
  }

  const handleImport = async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      await api.post(`/api/personnel/import?mode=replace&project_id=${projectId}`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setShowImport(false); load(); alert('导入成功')
    } catch (err) { alert('导入失败: ' + (err.response?.data?.detail || err.message)) }
  }

  const handleExport = () => { window.open(`/api/export/personnel?projectId=${projectId}`) }
  const totalPages = Math.ceil(data.total / pageSize) || 1

  const roleBadge = (r) => {
    if (!r) return <span className="badge" style={{ background: 'var(--text-3)', color: '#fff' }}>未设置</span>
    if (r === '系统管理员' || r === '项目负责人') return <span className="badge badge-blue">{r}</span>
    if (r === '部门管理') return <span className="badge badge-green">{r}</span>
    if (r === '外包') return <span className="badge badge-yellow">{r}</span>
    return <span className="badge" style={{ background: 'var(--text-3)', color: '#fff' }}>{r}</span>
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>人力管理</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-sm" onClick={() => setEditing({})}>新增</button>
          <button className="btn btn-sm" onClick={() => setShowImport(true)}>导入</button>
          <button className="btn btn-sm" onClick={handleExport}>导出</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input className="input" placeholder="搜索姓名/工号" value={keyword}
          onChange={e => setKeyword(e.target.value)} onKeyDown={e => e.key === 'Enter' && setPage(1)} style={{ width: 200 }} />
        <select className="select" value={roleFilter} onChange={e => { setRoleFilter(e.target.value); setPage(1) }}>
          <option value="">全部角色</option><option value="项目负责人">项目负责人</option>
          <option value="部门管理">部门管理</option><option value="一线员工">一线员工</option><option value="外包">外包</option>
        </select>
        <select className="select" value={selectedMonth} onChange={e => { setSelectedMonth(e.target.value); setPage(1) }}>
          <option value="">全部月份</option>
          {months.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <button className="btn btn-primary btn-sm" onClick={() => { setPage(1); load() }}>搜索</button>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead><tr><th>工号</th><th>姓名</th><th>职务</th><th>系统角色</th><th>项目</th><th>发起数</th><th>目标</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={9} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>加载中...</td></tr>
              : data.items.length === 0 ? <tr><td colSpan={9} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>无数据</td></tr>
              : data.items.map((p, i) => (
                <tr key={i}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{p.id}</td>
                  <td>{p.name}</td>
                  <td>{p.position || '-'}</td>
                  <td>{roleBadge(p.role)}</td>
                  <td>{p.projectName || '-'}</td>
                  <td>{p.count ?? '-'}</td>
                  <td>{p.target ?? '-'}</td>
                  <td>{p.status === '在职' ? <span className="badge badge-green">在职</span> : <span className="badge badge-red">{p.status || '-'}</span>}</td>
                  <td>
                    <button className="btn btn-sm" onClick={() => setEditing(p)}>编辑</button>
                    <button className="btn btn-sm" style={{ marginLeft: 4 }} onClick={() => handleDelete(p.id)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 20px', borderTop: '1px solid var(--border)' }}>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>共 {data.total} 人</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
            <span style={{ padding: '4px 10px', fontSize: 12, lineHeight: '20px' }}>{page} / {totalPages}</span>
            <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</button>
          </div>
        </div>
      </div>

      {editing && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditing(null)}>
          <div className="card" style={{ width: 400, padding: 24 }} onClick={e => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>{editing.id ? '编辑人员' : '新增人员'}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input className="input" placeholder="工号" defaultValue={editing.id || ''} id="edit-emp-id" />
              <input className="input" placeholder="姓名" defaultValue={editing.name || ''} id="edit-name" />
              <input className="input" placeholder="职务" defaultValue={editing.position || ''} id="edit-position" />
              <select className="select" defaultValue={editing.status || '在职'} id="edit-status">
                <option value="在职">在职</option><option value="离职">离职</option>
              </select>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <button className="btn btn-primary" style={{ flex: 1 }} onClick={async () => {
                  const payload = { employee_id: document.getElementById('edit-emp-id').value, name: document.getElementById('edit-name').value, role: document.getElementById('edit-position').value, status: document.getElementById('edit-status').value, project_id: parseInt(projectId) || null }
                  try {
                    if (editing.id) await api.put(`/api/personnel/${editing.id}`, payload)
                    else await api.post('/api/personnel/create', payload)
                    setEditing(null); load()
                  } catch (err) { alert(err.response?.data?.detail || '保存失败') }
                }}>保存</button>
                <button className="btn" onClick={() => setEditing(null)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showImport && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowImport(false)}>
          <div className="card" style={{ width: 400, padding: 24 }} onClick={e => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>导入人力清单</h3>
            <p style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12 }}>选择Excel文件，将覆盖当前项目的人员数据</p>
            <input type="file" accept=".xlsx,.xls" onChange={e => e.target.files[0] && handleImport(e.target.files[0])} style={{ marginBottom: 12 }} />
            <button className="btn" onClick={() => setShowImport(false)}>取消</button>
          </div>
        </div>
      )}
    </div>
  )
}
