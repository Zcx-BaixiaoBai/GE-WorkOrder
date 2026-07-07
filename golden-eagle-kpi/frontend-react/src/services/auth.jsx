import React, { createContext, useContext, useState, useCallback } from 'react'
import api from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    if (!localStorage.getItem('auth_token')) return null
    return {
      id: localStorage.getItem('user_id'),
      account: localStorage.getItem('user_account'),
      employeeId: localStorage.getItem('user_employee_id'),
      name: localStorage.getItem('user_name'),
      role: localStorage.getItem('user_role'),
      projectId: localStorage.getItem('user_project_id'),
      projectName: localStorage.getItem('user_project_name'),
      token: localStorage.getItem('auth_token'),
    }
  })

  const isLoggedIn = !!user

  const login = useCallback(async (account, password, employeeId, projectId) => {
    const res = await api.post('/api/auth/login', { account, password, employeeId, projectId })
    if (res.data.success) {
      const u = res.data.user
      localStorage.setItem('auth_token', res.data.token)
      localStorage.setItem('user_id', u.id)
      localStorage.setItem('user_account', u.account)
      localStorage.setItem('user_name', u.name)
      localStorage.setItem('user_role', u.role)
      localStorage.setItem('user_project_id', u.projectId || '')
      localStorage.setItem('user_project_name', u.projectName || '')
      setUser({ ...u, token: res.data.token })
    }
    return res.data
  }, [])

  const logout = useCallback(async () => {
    try { await api.post('/api/auth/logout') } catch {}
    localStorage.clear()
    setUser(null)
    window.location.href = '/login'
  }, [])

  // 权限判断
  const isAdmin = () => user?.role === '系统管理员' || user?.role === 'super_admin'
  const isProjectAdmin = () => ['系统管理员', 'super_admin', '项目负责人', 'project_admin'].includes(user?.role)
  const canManageConfig = () => isAdmin()
  const canTriggerSync = () => isAdmin()
  const canExport = () => ['系统管理员', '项目负责人', '部门管理'].includes(user?.role)

  return (
    <AuthContext.Provider value={{ user, isLoggedIn, login, logout, isAdmin, isProjectAdmin, canManageConfig, canTriggerSync, canExport }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
