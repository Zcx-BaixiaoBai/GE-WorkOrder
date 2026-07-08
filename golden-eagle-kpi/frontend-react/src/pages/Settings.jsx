import React, { useState, useEffect, useCallback } from 'react'
import api from '../services/api'
import { useAuth } from '../services/auth'
import SyncScheduleTab from '../components/SyncScheduleTab'
import AIConfigTab from '../components/AIConfigTab'

const TABS = [
  { key: 'import', label: '人力清单' },
  { key: 'role', label: '角色映射' },
  { key: 'area', label: '项目面积' },
  { key: 'kpi', label: 'KPI配置' },
  { key: 'dict', label: '数据字典' },
  { key: 'pm', label: '项目负责人' },
  { key: 'sync', label: '定时任务', adminOnly: true },
  { key: 'ai', label: 'AI配置', adminOnly: true },
]

export default function Settings() {
  const { isAdmin } = useAuth()
  const [tab, setTab] = useState('import')
  const visibleTabs = TABS.filter(t => !t.adminOnly || isAdmin())

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>系统配置</h2>
      <div className="config-tabs" style={{ marginBottom: 16 }}>
        {visibleTabs.map(t => (
          <button key={t.key} className={`config-tab ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'import' && <ImportTab />}
      {tab === 'role' && <RoleMappingTab />}
      {tab === 'area' && <ProjectAreaTab />}
      {tab === 'kpi' && <KpiTab />}
      {tab === 'dict' && <DictTab />}
      {tab === 'pm' && <PMTab />}
      {tab === 'sync' && isAdmin() && <SyncScheduleTab />}
      {tab === 'ai' && isAdmin() && <AIConfigTab />}
    </div>
  )
}

// ===== 人力清单导入 =====
function ImportTab() {
  const projectId = localStorage.getItem('user_project_id') || ''
  const [msg, setMsg] = useState('')
  const handleFile = async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      await api.post(`/api/personnel/import?mode=replace&project_id=${projectId}`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setMsg('导入成功')
    } catch (err) { setMsg('导入失败: ' + (err.response?.data?.detail || err.message)) }
  }
  return (
    <div className="card" style={{ padding: 24 }}>
      <h3 style={{ marginBottom: 12 }}>人力清单导入</h3>
      <p style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 16 }}>选择Excel文件，将覆盖当前项目的人员数据</p>
      <input type="file" accept=".xlsx,.xls" onChange={e => e.target.files[0] && handleFile(e.target.files[0])} style={{ marginBottom: 12 }} />
      {msg && <div style={{ fontSize: 13, color: msg.includes('成功') ? 'var(--green)' : 'var(--red)' }}>{msg}</div>}
    </div>
  )
}

// ===== 角色映射 =====
function RoleMappingTab() {
  const [items, setItems] = useState([])
  const [editing, setEditing] = useState(null)
  useEffect(() => { api.get('/api/config/role-mappings').then(r => setItems(r.data.items || [])) }, [])
  const save = async () => {
    if (!editing.sourceRole || !editing.targetRole) return
    if (editing.id) await api.put(`/api/config/role-mappings/${editing.id}`, editing)
    else await api.post('/api/config/role-mappings', editing)
    setEditing(null)
    api.get('/api/config/role-mappings').then(r => setItems(r.data.items || []))
  }
  const del = async (id) => { if (confirm('确认删除？')) { await api.delete(`/api/config/role-mappings/${id}`); api.get('/api/config/role-mappings').then(r => setItems(r.data.items || [])) } }
  return (
    <div>
      <div style={{ marginBottom: 12 }}><button className="btn btn-sm" onClick={() => setEditing({})}>新增映射</button></div>
      <table className="table">
        <thead><tr><th>原始职务</th><th>系统角色</th><th>操作</th></tr></thead>
        <tbody>
          {items.map((m, i) => <tr key={i}><td>{m.sourceRole}</td><td><span className="badge badge-blue">{m.targetRole}</span></td>
            <td><button className="btn btn-sm" onClick={() => setEditing(m)}>编辑</button><button className="btn btn-sm" style={{ marginLeft: 4 }} onClick={() => del(m.id)}>删除</button></td></tr>)}
        </tbody>
      </table>
      {editing && <EditModal title="角色映射" data={editing} fields={[{ key: 'sourceRole', label: '原始职务' }, { key: 'targetRole', label: '系统角色' }]} onSave={save} onClose={() => setEditing(null)} />}
    </div>
  )
}

// ===== 项目面积 =====
function ProjectAreaTab() {
  const [items, setItems] = useState([])
  const [editing, setEditing] = useState(null)
  useEffect(() => { api.get('/api/config/projects').then(r => setItems(r.data.items || [])) }, [])
  const save = async () => {
    await api.put(`/api/config/projects/${editing.id}`, editing)
    setEditing(null)
    api.get('/api/config/projects').then(r => setItems(r.data.items || []))
  }
  return (
    <div>
      <table className="table">
        <thead><tr><th>项目名称</th><th>面积(m²)</th><th>外包目标</th><th>操作</th></tr></thead>
        <tbody>
          {items.map((p, i) => <tr key={i}><td>{p.name}</td><td>{p.area?.toLocaleString() || '-'}</td><td>{p.outsourcingTarget || '-'}</td>
            <td><button className="btn btn-sm" onClick={() => setEditing(p)}>编辑</button></td></tr>)}
        </tbody>
      </table>
      {editing && <EditModal title="项目面积" data={editing} fields={[{ key: 'name', label: '名称', readonly: true }, { key: 'area', label: '面积(m²)', type: 'number' }, { key: 'outsourcingTarget', label: '外包目标', type: 'number' }]} onSave={save} onClose={() => setEditing(null)} />}
    </div>
  )
}

// ===== KPI配置 =====
function KpiTab() {
  const [items, setItems] = useState([])
  const [editing, setEditing] = useState(null)
  useEffect(() => { api.get('/api/config/projects').then(r => setItems(r.data.items || [])) }, [])
  const save = async () => {
    await api.put(`/api/config/projects/${editing.id}`, { kpiCompletionRate: editing.kpiCompletionRate, kpiTimelyRate: editing.kpiTimelyRate })
    setEditing(null)
    api.get('/api/config/projects').then(r => setItems(r.data.items || []))
  }
  return (
    <div>
      <table className="table">
        <thead><tr><th>项目</th><th>完成率目标(%)</th><th>及时率目标(%)</th><th>操作</th></tr></thead>
        <tbody>
          {items.map((p, i) => <tr key={i}><td>{p.name}</td><td>{p.kpiCompletionRate || '-'}</td><td>{p.kpiTimelyRate || '-'}</td>
            <td><button className="btn btn-sm" onClick={() => setEditing(p)}>编辑</button></td></tr>)}
        </tbody>
      </table>
      {editing && <EditModal title="KPI配置" data={editing} fields={[{ key: 'name', label: '项目', readonly: true }, { key: 'kpiCompletionRate', label: '完成率目标(%)', type: 'number' }, { key: 'kpiTimelyRate', label: '及时率目标(%)', type: 'number' }]} onSave={save} onClose={() => setEditing(null)} />}
    </div>
  )
}

// ===== 数据字典 =====
function DictTab() {
  return (
    <div className="card" style={{ padding: 24 }}>
      <h3 style={{ marginBottom: 12 }}>数据字典</h3>
      <p style={{ color: 'var(--text-3)' }}>工单类型、状态映射、角色分类等数据字典管理（待扩展）</p>
      <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <DictSection title="工单状态" items={['待处理', '处理中', '待审核', '已完成', '已关闭', '已解决', '已评分']} />
        <DictSection title="工单类型" items={['物业维修', '保洁报修', '秩序报修', '随手拍']} />
      </div>
    </div>
  )
}
function DictSection({ title, items }) {
  return (
    <div style={{ padding: 12, background: 'var(--bg-hover)', borderRadius: 'var(--radius)' }}>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>{title}</div>
      {items.map((item, i) => <div key={i} style={{ padding: '4px 0', fontSize: 12, color: 'var(--text-2)' }}>· {item}</div>)}
    </div>
  )
}

// ===== 项目负责人 =====
function PMTab() {
  const [items, setItems] = useState([])
  const [projects, setProjects] = useState([])
  const [editing, setEditing] = useState(null)
  useEffect(() => {
    api.get('/api/project-managers').then(r => setItems(r.data.items || []))
    api.get('/api/config/projects').then(r => setProjects(r.data.items || []))
  }, [])
  const save = async () => {
    if (!editing.project_id || !editing.manager_name) return
    if (editing.id) await api.put(`/api/project-managers/${editing.id}`, editing)
    else await api.post('/api/project-managers', editing)
    setEditing(null)
    api.get('/api/project-managers').then(r => setItems(r.data.items || []))
  }
  const del = async (id) => { if (confirm('确认删除？')) { await api.delete(`/api/project-managers/${id}`); api.get('/api/project-managers').then(r => setItems(r.data.items || [])) } }
  return (
    <div>
      <div style={{ marginBottom: 12 }}><button className="btn btn-sm" onClick={() => setEditing({})}>新增负责人</button></div>
      <table className="table">
        <thead><tr><th>项目</th><th>负责人</th><th>操作</th></tr></thead>
        <tbody>
          {items.map((m, i) => <tr key={i}><td>{m.project_name || '-'}</td><td>{m.manager_name}</td>
            <td><button className="btn btn-sm" onClick={() => setEditing(m)}>编辑</button><button className="btn btn-sm" style={{ marginLeft: 4 }} onClick={() => del(m.id)}>删除</button></td></tr>)}
        </tbody>
      </table>
      {editing && (
        <EditModal title="项目负责人" data={editing} fields={[{ key: 'project_id', label: '项目', type: 'select', options: projects.map(p => ({ value: p.id, label: p.name })) }, { key: 'manager_name', label: '负责人姓名' }]} onSave={save} onClose={() => setEditing(null)} />
      )}
    </div>
  )
}

// ===== 通用编辑弹窗 =====
function EditModal({ title, data, fields, onSave, onClose }) {
  const [form, setForm] = useState(data)
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', zIndex: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={onClose}>
      <div className="card" style={{ width: 400, padding: 24 }} onClick={e => e.stopPropagation()}>
        <h3 style={{ marginBottom: 16 }}>{title}</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {fields.map(f => {
            if (f.readonly) return <div key={f.key}><label style={{ fontSize: 12, color: 'var(--text-3)' }}>{f.label}</label><div style={{ padding: '8px 0', fontSize: 13 }}>{form[f.key] || '-'}</div></div>
            if (f.type === 'select') return (
              <div key={f.key}>
                <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>{f.label}</label>
                <select className="select" style={{ width: '100%' }} value={form[f.key] || ''} onChange={e => setForm({ ...form, [f.key]: parseInt(e.target.value) })}>
                  <option value="">选择{f.label}</option>
                  {f.options?.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            )
            return (
              <div key={f.key}>
                <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>{f.label}</label>
                <input className="input" style={{ width: '100%' }} type={f.type || 'text'} value={form[f.key] || ''} onChange={e => setForm({ ...form, [f.key]: f.type === 'number' ? parseFloat(e.target.value) : e.target.value })} />
              </div>
            )
          })}
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => onSave(form)}>保存</button>
            <button className="btn" onClick={onClose}>取消</button>
          </div>
        </div>
      </div>
    </div>
  )
}
