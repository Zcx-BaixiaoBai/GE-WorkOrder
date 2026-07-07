import React, { useState, useEffect, useCallback } from 'react'
import api from '../services/api'

export default function Personnel() {
  const [data, setData] = useState({ items: [], total: 0 })
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [roleFilter, setRoleFilter] = useState('')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(null)
  const [showImport, setShowImport] = useState(false)
  const projectId = localStorage.getItem('user_project_id') || ''

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, pageSize, projectId }
      if (keyword) params.keyword = keyword
      if (roleFilter) params.role = roleFilter
      const res = await api.get('/api/personnel/list', { params })
      setData(res.data)
    } catch (err) { console.error('Personnel load error:', err) }
    setLoading(false)
  }, [page, pageSize, projectId, keyword, roleFilter])

  useEffect(() => { load() }, [load])

  const handleSave = async () => {
    if (!editing?.name || !editing?.employee_id) return
    try {
      if (editing.id) {
        await api.put(`/api/personnel/${editing.id}`, editing)
      } else {
        await api.post('/api/personnel/create', { ...editing, project_id: parseInt(projectId) || null })
      }
      setEditing(null)
      load()
    } catch (err) { alert(err.response?.data?.detail || '保存失败') }
  }

  const handleDelete = async (id) => {
    if (!confirm('确认删除？')) return
    try { await api.delete(`/api/personnel/${id}`); load() } catch {}
  }

  const handleImport = async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      await api.post(`/api/personnel/import?mode=replace&project_id=${projectId}`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setShowImport(false)
      load()
      alert('导入成功')
    } catch (err) { alert('导入失败: ' + (err.response?.data?.detail || err.message)) }
  }

  const handleExport = () => {
    window.open(`/api/export/personnel?projectId=${projectId}`)
  }

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

      {/* 筛选栏 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input className="input" placeholder="搜索姓名/工号" value={keyword}
          onChange={e => setKeyword(e.target.value)} onKeyDown={e => e.key === 'Enter' && setPage(1)}
          style={{ width: 200 }} />
        <select className="select" value={roleFilter} onChange={e => { setRoleFilter(e.target.value); setPage(1) }}>
          <option value="">全部角色</option>
          <option value="项目负责人">项目负责人</option>
          <option value="部门管理">部门管理</option>
          <option value="一线员工">一线员工</option>
          <option value="外包">外包</option>
        </select>
        <button className="btn btn-primary btn-sm" onClick={() => { setPage(1); load() }}>搜索</button>
      </div>

      {/* 表格 */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr><th>工号</th><th>姓名</th><th>职务</th><th>系统角色</th><th>项目</th><th>状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>加载中...</td></tr>
              ) : data.items.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>无数据</td></tr>
              ) : data.items.map((p, i) => (
                <tr key={i}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{p.employee_id}</td>
                  <td>{p.name}</td>
                  <td>{p.role || '-'}</td>
                  <td>{roleBadge(p.system_role || p.role)}</td>
                  <td>{p.project_name || p.project_id || '-'}</td>
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
        {/* 分页 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 20px', borderTop: '1px solid var(--border)' }}>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>共 {data.total} 人</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
            <span style={{ padding: '4px 10px', fontSize: 12, lineHeight: '20px' }}>{page} / {totalPages}</span>
            <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</button>
          </div>
        </div>
      </div>

      {/* 编辑弹窗 */}
      {editing && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={() => setEditing(null)}>
          <div className="card" style={{ width: 400, padding: 24 }} onClick={e => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>{editing.id ? '编辑人员' : '新增人员'}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input className="input" placeholder="工号" value={editing.employee_id || ''} onChange={e => setEditing({ ...editing, employee_id: e.target.value })} />
              <input className="input" placeholder="姓名" value={editing.name || ''} onChange={e => setEditing({ ...editing, name: e.target.value })} />
              <input className="input" placeholder="职务" value={editing.role || ''} onChange={e => setEditing({ ...editing, role: e.target.value })} />
              <select className="select" value={editing.status || '在职'} onChange={e => setEditing({ ...editing, status: e.target.value })}>
                <option value="在职">在职</option>
                <option value="离职">离职</option>
              </select>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <button className="btn btn-primary" style={{ flex: 1 }} onClick={handleSave}>保存</button>
                <button className="btn" onClick={() => setEditing(null)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 导入弹窗 */}
      {showImport && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={() => setShowImport(false)}>
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
