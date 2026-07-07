import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../services/auth'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [projects, setProjects] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  React.useEffect(() => {
    fetch('/api/config/projects').then(r => r.json()).then(data => {
      setProjects(data.items || [])
    }).catch(() => {})
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const result = await login(account, password, employeeId, projectId)
      if (result.success) {
        navigate('/')
      } else {
        setError(result.error || '登录失败')
      }
    } catch (err) {
      setError(err.response?.data?.detail || '网络错误')
    }
    setLoading(false)
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <h1 className="login-title">工单KPI</h1>
        <p className="login-subtitle">金鹰物业工单评价系统 v1.1.0</p>
        <form className="login-form" onSubmit={handleSubmit}>
          <input className="login-input" placeholder="OA账号" value={account} onChange={e => setAccount(e.target.value)} required />
          <input className="login-input" type="password" placeholder="密码" value={password} onChange={e => setPassword(e.target.value)} required />
          <input className="login-input" placeholder="工号" value={employeeId} onChange={e => setEmployeeId(e.target.value)} required />
          <select className="login-input" value={projectId} onChange={e => setProjectId(e.target.value)} required>
            <option value="">选择项目</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          {error && <div style={{ color: 'var(--red)', fontSize: 13 }}>{error}</div>}
          <button className="login-btn" type="submit" disabled={loading}>{loading ? '登录中...' : '登录'}</button>
        </form>
        <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-3)', textAlign: 'center' }}>
          首次登录请使用OA账号密码<br />工号用于系统识别您的角色权限
        </div>
      </div>
    </div>
  )
}
