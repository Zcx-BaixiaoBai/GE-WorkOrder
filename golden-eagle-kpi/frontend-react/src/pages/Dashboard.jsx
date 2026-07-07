import React, { useState, useEffect, useCallback } from 'react'
import ReactECharts from 'echarts-for-react'
import api from '../services/api'

export default function Dashboard() {
  const [months, setMonths] = useState([])
  const [selectedMonth, setSelectedMonth] = useState('')
  const [dashboard, setDashboard] = useState(null)
  const [warnings, setWarnings] = useState([])
  const [initiation, setInitiation] = useState(null)
  const [wyStats, setWyStats] = useState(null)
  const [ipmsPatrol, setIpmsPatrol] = useState(null)
  const [ipmsMaintain, setIpmsMaintain] = useState(null)
  const [loading, setLoading] = useState(true)

  const projectId = localStorage.getItem('user_project_id') || ''

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const params = { projectId }
      if (selectedMonth) params.month = selectedMonth

      const [monthsRes, dashRes, warnRes, initRes, wyRes, patrolRes, maintainRes] = await Promise.all([
        api.get('/api/stats/months', { params: { projectId } }),
        api.get('/api/stats/dashboard', { params }),
        api.get('/api/stats/warnings', { params }),
        api.get('/api/stats/initiation', { params }),
        api.get('/api/wy/stats', { params: { projectId } }),
        api.get('/api/ipms/stats', { params: { task_type: 'patrol', projectId } }),
        api.get('/api/ipms/stats', { params: { task_type: 'maintain', projectId } }),
      ])

      setMonths(monthsRes.data.months || [])
      setDashboard(dashRes.data)
      setWarnings(warnRes.data.items || [])
      setInitiation(initRes.data)
      setWyStats(wyRes.data)
      setIpmsPatrol(patrolRes.data)
      setIpmsMaintain(maintainRes.data)
    } catch (err) {
      console.error('Dashboard load error:', err)
    }
    setLoading(false)
  }, [projectId, selectedMonth])

  useEffect(() => { loadData() }, [loadData])

  // KPI 卡片 - 字段映射: total/pending/completed/rate
  const kpiCards = dashboard ? [
    { label: '累计工单', value: dashboard.total?.toLocaleString() || 0 },
    { label: '待处理', value: dashboard.pending || 0 },
    { label: '已完成', value: dashboard.completed?.toLocaleString() || 0 },
    { label: '及时完成率', value: `${(dashboard.rate || 0).toFixed(1)}%` },
  ] : Array(4).fill({ label: '加载中', value: '...' })

  // 项目概览 - 从独立API获取
  const overviewCards = [
    { title: '金鹰PLAN', total: wyStats?.total || 0, items: [
      { label: '进行中', value: wyStats?.in_progress || 0 },
      { label: '即将到期', value: wyStats?.expiring || 0 },
      { label: '已逾期', value: wyStats?.overdue || 0 },
    ]},
    { title: '巡检任务', total: ipmsPatrol?.total || 0, items: [
      { label: '进行中', value: ipmsPatrol?.in_progress || 0 },
      { label: '已完成', value: ipmsPatrol?.finished || 0 },
      { label: '已逾期', value: ipmsPatrol?.overdue || 0 },
    ]},
    { title: '维保任务', total: ipmsMaintain?.maintain_count || ipmsMaintain?.total || 0, items: [
      { label: '进行中', value: ipmsMaintain?.in_progress || 0 },
      { label: '已完成', value: ipmsMaintain?.finished || 0 },
      { label: '已逾期', value: ipmsMaintain?.overdue || 0 },
    ]},
  ]

  // 工单趋势图 - 使用API返回的trend数据
  const trendData = dashboard?.trend || []
  const trendOption = {
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: trendData.map(t => t.month), axisLine: { lineStyle: { color: '#999' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#E5E5E5' } } },
    series: [{
      type: 'line',
      data: trendData.map(t => t.count),
      smooth: true,
      lineStyle: { color: '#1A5276', width: 2 },
      itemStyle: { color: '#1A5276' },
      areaStyle: { color: 'rgba(26,82,118,0.1)' },
    }],
    tooltip: { trigger: 'axis' },
  }

  // 角色分布图
  const roles = initiation?.levels || []
  const distOption = {
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: roles.map(r => r.level || ''), axisLine: { lineStyle: { color: '#999' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#E5E5E5' } } },
    series: [
      { name: '人数', type: 'bar', data: roles.map(r => r.count || 0), itemStyle: { color: '#1A5276' } },
      { name: '发起数', type: 'bar', data: roles.map(r => r.initiated || 0), itemStyle: { color: '#006400' } },
    ],
    legend: { data: ['人数', '发起数'], bottom: 0 },
    tooltip: { trigger: 'axis' },
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>概览驾驶舱</h2>
        <select className="select" value={selectedMonth} onChange={e => setSelectedMonth(e.target.value)}>
          <option value="">全部月份</option>
          {months.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>加载中...</div>
      ) : (
        <>
          <div className="kpi-grid">
            {kpiCards.map((card, i) => (
              <div key={i} className="kpi-card">
                <div className="kpi-label">{card.label}</div>
                <div className="kpi-value">{card.value}</div>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 20 }}>
            {overviewCards.map((card, i) => (
              <div key={i} className="card">
                <div className="card-header"><span className="card-title">{card.title}</span><span style={{ fontSize: 20, fontWeight: 700 }}>{card.total}</span></div>
                <div className="card-body" style={{ display: 'flex', gap: 16 }}>
                  {card.items.map((item, j) => (
                    <div key={j}>
                      <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{item.label}</div>
                      <div style={{ fontSize: 16, fontWeight: 600 }}>{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            <div className="card">
              <div className="card-header"><span className="card-title">工单趋势</span></div>
              <div className="card-body"><ReactECharts option={trendOption} style={{ height: 240 }} /></div>
            </div>
            <div className="card">
              <div className="card-header"><span className="card-title">角色分布</span></div>
              <div className="card-body"><ReactECharts option={distOption} style={{ height: 240 }} /></div>
            </div>
          </div>

          {/* 预警清单 - 字段: name/level/initiated/target/achievementRate/warningType */}
          <div className="card">
            <div className="card-header"><span className="card-title">预警清单</span><span style={{ fontSize: 12, color: 'var(--text-3)' }}>共 {warnings.length} 条 · 严重 {warnings.filter(w => w.warningType === 'severe').length}</span></div>
            <div style={{ overflowX: 'auto' }}>
              <table className="table">
                <thead><tr><th>姓名</th><th>层级</th><th>职务</th><th>已发起</th><th>目标</th><th>达成率</th><th>预警</th><th>排名</th></tr></thead>
                <tbody>
                  {warnings.slice(0, 20).map((w, i) => (
                    <tr key={i}>
                      <td>{w.name}</td>
                      <td>{w.level}</td>
                      <td>{w.position || '-'}</td>
                      <td>{w.initiated}</td>
                      <td>{w.target}</td>
                      <td>{w.achievementRate ? `${w.achievementRate}%` : '0%'}</td>
                      <td>{w.warningType === 'severe' ? <span className="badge badge-red">严重</span> : <span className="badge badge-yellow">一般</span>}</td>
                      <td>{w.projectRank || '-'}</td>
                    </tr>
                  ))}
                  {warnings.length === 0 && <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-3)' }}>暂无预警数据</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
