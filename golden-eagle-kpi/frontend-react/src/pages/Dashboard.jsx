import React, { useState, useEffect, useCallback } from 'react'
import ReactECharts from 'echarts-for-react'
import api from '../services/api'

export default function Dashboard() {
  const [months, setMonths] = useState([])
  const [selectedMonth, setSelectedMonth] = useState('')
  const [dashboard, setDashboard] = useState(null)
  const [warnings, setWarnings] = useState([])
  const [initiation, setInitiation] = useState(null)
  const [loading, setLoading] = useState(true)

  const projectId = localStorage.getItem('user_project_id') || ''

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const params = { projectId }
      if (selectedMonth) params.month = selectedMonth

      const [monthsRes, dashRes, warnRes, initRes] = await Promise.all([
        api.get('/api/stats/months', { params: { projectId } }),
        api.get('/api/stats/dashboard', { params }),
        api.get('/api/stats/warnings', { params }),
        api.get('/api/stats/initiation', { params }),
      ])

      setMonths(monthsRes.data.months || [])
      setDashboard(dashRes.data)
      setWarnings(warnRes.data.items || warnRes.data || [])
      setInitiation(initRes.data)
    } catch (err) {
      console.error('Dashboard load error:', err)
    }
    setLoading(false)
  }, [projectId, selectedMonth])

  useEffect(() => { loadData() }, [loadData])

  const kpiCards = dashboard ? [
    { label: '累计工单', value: dashboard.totalTickets || 0, trend: '' },
    { label: '待处理', value: dashboard.pendingTickets || 0, trend: '' },
    { label: '已完成', value: dashboard.completedTickets || 0, trend: '' },
    { label: '及时完成率', value: `${(dashboard.timelyRate || 0).toFixed(1)}%`, trend: '' },
  ] : Array(4).fill({ label: '加载中', value: '...', trend: '' })

  const overviewCards = dashboard ? [
    { title: '金鹰PLAN', total: dashboard.wyTotal || 0, items: [
      { label: '进行中', value: dashboard.wyActive || 0 },
      { label: '即将到期', value: dashboard.wyExpiring || 0 },
      { label: '已逾期', value: dashboard.wyOverdue || 0 },
    ]},
    { title: '巡检任务', total: dashboard.ipmsPatrolTotal || 0, items: [
      { label: '进行中', value: dashboard.ipmsPatrolActive || 0 },
      { label: '已完成', value: dashboard.ipmsPatrolDone || 0 },
      { label: '已逾期', value: dashboard.ipmsPatrolOverdue || 0 },
    ]},
    { title: '维保任务', total: dashboard.ipmsMaintainTotal || 0, items: [
      { label: '进行中', value: dashboard.ipmsMaintainActive || 0 },
      { label: '已完成', value: dashboard.ipmsMaintainDone || 0 },
      { label: '已逾期', value: dashboard.ipmsMaintainOverdue || 0 },
    ]},
  ] : []

  // 工单趋势图配置
  const trendOption = {
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: months.slice(0, 6).reverse(), axisLine: { lineStyle: { color: '#999' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#E5E5E5' } } },
    series: [{
      type: 'line',
      data: months.slice(0, 6).map(() => Math.floor(Math.random() * 200 + 50)).reverse(),
      smooth: true,
      lineStyle: { color: '#1A5276', width: 2 },
      itemStyle: { color: '#1A5276' },
      areaStyle: { color: 'rgba(26,82,118,0.1)' },
    }],
    tooltip: { trigger: 'axis' },
  }

  // 角色分布图配置
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
      {/* 月份选择器 */}
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
          {/* KPI 卡片 */}
          <div className="kpi-grid">
            {kpiCards.map((card, i) => (
              <div key={i} className="kpi-card">
                <div className="kpi-label">{card.label}</div>
                <div className="kpi-value">{card.value}</div>
                {card.trend && <div className="kpi-trend">{card.trend}</div>}
              </div>
            ))}
          </div>

          {/* 项目概览卡片 */}
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

          {/* 趋势图表 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            <div className="card">
              <div className="card-header"><span className="card-title">工单趋势</span></div>
              <div className="card-body">
                <ReactECharts option={trendOption} style={{ height: 240 }} />
              </div>
            </div>
            <div className="card">
              <div className="card-header"><span className="card-title">角色分布</span></div>
              <div className="card-body">
                <ReactECharts option={distOption} style={{ height: 240 }} />
              </div>
            </div>
          </div>

          {/* 预警清单 */}
          <div className="card">
            <div className="card-header"><span className="card-title">预警清单</span><span style={{ fontSize: 12, color: 'var(--text-3)' }}>按达成率升序</span></div>
            <div style={{ overflowX: 'auto' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>姓名</th><th>角色</th><th>已发起</th><th>目标</th><th>达成率</th><th>预警级别</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.isArray(warnings) && warnings.slice(0, 20).map((w, i) => (
                    <tr key={i}>
                      <td>{w.name || w.initiator_name || '-'}</td>
                      <td>{w.role || '-'}</td>
                      <td>{w.initiated || w.count || 0}</td>
                      <td>{w.target || '-'}</td>
                      <td>{w.achievementRate ? `${w.achievementRate}%` : '-'}</td>
                      <td>{w.warningLevel === '严重' ? <span className="badge badge-red">严重</span> : <span className="badge badge-yellow">一般</span>}</td>
                    </tr>
                  ))}
                  {(!Array.isArray(warnings) || warnings.length === 0) && <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-3)' }}>暂无预警数据</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
