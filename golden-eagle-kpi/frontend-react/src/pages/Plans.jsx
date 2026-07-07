import React, { useState, useEffect, useCallback } from 'react'
import api from '../services/api'

const TABS = [{ key: 'wy', label: '金鹰PLAN' }, { key: 'patrol', label: '巡检任务' }, { key: 'maintain', label: '维保任务' }]
const WY_STATES = ['即将开始','进行中','即将到期','到期预警','逾期报警','已逾期','已完成','已暂停']
const MONTHS = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']

// 过滤"None"字符串
const clean = (v) => (v && v !== 'None' && v !== 'null') ? v : '-'

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

  // ===== WY 统计卡片（6个）=====
  const renderWYStats = () => {
    if (!stats) return null
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10, marginBottom: 16 }}>
        <StatCard label="总专项" value={stats.total || 0} />
        <StatCard label="即将开始" value={stats.starting_soon || 0} color="blue" />
        <StatCard label="进行中" value={stats.in_progress || 0} color="green" />
        <StatCard label="即将到期" value={stats.expiring || 0} color="yellow" />
        <StatCard label="已逾期" value={stats.overdue || 0} color="red" />
        <StatCard label="已暂停" value={stats.paused || 0} />
      </div>
    )
  }

  // ===== IPMS 统计卡片（4个）=====
  const renderIPMSStats = () => {
    if (!stats) return null
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
        <StatCard label="总任务" value={stats.total || 0} />
        <StatCard label="进行中" value={stats.in_progress || 0} color="green" />
        <StatCard label="已完成" value={stats.finished || 0} color="blue" />
        <StatCard label="已逾期" value={stats.overdue || 0} color="red" />
      </div>
    )
  }

  // ===== 真正的甘特图（动态月份范围）=====
  const renderGantt = () => {
    const ganttItems = (data.items || []).slice(0, 20)
    if (ganttItems.length === 0) return null

    // 根据selectedMonth计算显示的12个月范围
    let baseYear = 2026, baseMonth = 0
    if (selectedMonth) {
      const [y, m] = selectedMonth.split('-')
      baseYear = parseInt(y)
      baseMonth = parseInt(m) - 1
    }
    // 生成12个月的标签和偏移
    const ganttMonths = []
    for (let i = 0; i < 12; i++) {
      const d = new Date(baseYear, baseMonth + i, 1)
      ganttMonths.push({ label: `${d.getMonth() + 1}月`, year: d.getFullYear(), month: d.getMonth() })
    }

    return (
      <div className="card" style={{ marginBottom: 16, overflow: 'hidden' }}>
        <div className="card-header"><span className="card-title">甘特图（前20条）{selectedMonth ? `· ${selectedMonth}起` : '· 全年'}</span></div>
        <div className="card-body" style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 900 }}>
            {/* 表头：任务名 + 12个月 */}
            <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', paddingBottom: 6, marginBottom: 6 }}>
              <div style={{ width: 180, flexShrink: 0, fontSize: 11, fontWeight: 600, color: 'var(--text-3)' }}>任务名称</div>
              <div style={{ flex: 1, display: 'flex' }}>
                {ganttMonths.map((m, i) => (
                  <div key={i} style={{ flex: 1, fontSize: 11, color: 'var(--text-3)', textAlign: 'center', borderLeft: '1px solid var(--border)' }}>
                    {m.label}{m.month === 0 ? <span style="color: 'var(--text-2)">'{String(m.year).slice(-2)}</span> : ''}
                  </div>
                ))}
              </div>
            </div>
            {/* 每行：任务名 + 甘特条 */}
            {ganttItems.map((item, idx) => {
              const start = item.plan_start_date ? new Date(item.plan_start_date) : null
              const end = item.plan_end_date ? new Date(item.plan_end_date) : null
              const state = item.computed_state || item.plan_state || ''
              const isOverdue = state.includes('逾期')
              const isPaused = state === '已暂停' || item.pause_flag === 1
              const isFinished = item.finish_flag === 1
              const isInProgress = state === '进行中'
              
              // 计算甘特条位置：相对于baseMonth的月份偏移
              let barLeft = 0, barWidth = 0
              if (start && end) {
                const startOffset = (start.getFullYear() - baseYear) * 12 + (start.getMonth() - baseMonth)
                const endOffset = (end.getFullYear() - baseYear) * 12 + (end.getMonth() - baseMonth) + 1
                barLeft = Math.max(0, (startOffset / 12) * 100)
                barWidth = Math.max(3, ((endOffset - startOffset) / 12) * 100)
                if (barLeft > 100) { barLeft = 0; barWidth = 0 } // 不在显示范围内
                if (barLeft + barWidth > 100) barWidth = 100 - barLeft
              }
              
              const barColor = isFinished ? 'var(--green)' : isPaused ? 'var(--text-3)' : isOverdue ? 'var(--red)' : isInProgress ? 'var(--blue)' : 'var(--yellow)'
              const barOpacity = isFinished ? 0.4 : isPaused ? 0.3 : 1
              
              return (
                <div key={idx} style={{ display: 'flex', alignItems: 'center', height: 28, borderBottom: '1px solid var(--border)' }}>
                  <div style={{ width: 180, flexShrink: 0, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingRight: 8 }} title={clean(item.special_name)}>
                    {clean(item.special_name)}
                  </div>
                  <div style={{ flex: 1, position: 'relative', height: '100%' }}>
                    {/* 月份网格线 */}
                    {ganttMonths.map((_, i) => (
                      <div key={i} style={{ position: 'absolute', left: `${(i / 12) * 100}%`, top: 0, bottom: 0, width: 1, background: 'var(--border)' }} />
                    ))}
                    {/* 甘特条 */}
                    {start && end && barWidth > 0 && (
                      <div style={{
                        position: 'absolute',
                        left: `${barLeft}%`,
                        width: `${barWidth}%`,
                        top: 4, bottom: 4,
                        background: barColor,
                        opacity: barOpacity,
                        borderRadius: 3,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 10,
                        color: '#fff',
                        overflow: 'hidden',
                        whiteSpace: 'nowrap',
                      }}>
                        {barWidth > 10 && (isFinished ? '✅' : isPaused ? '⏸' : isOverdue ? '⚠' : '')}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
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

      {tab === 'wy' ? renderWYStats() : renderIPMSStats()}

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
            <option value="未完成">未完成</option>
            <option value="进行中">进行中</option>
          </select>
        )}
      </div>

      {/* WY 甘特图 */}
      {tab === 'wy' && renderGantt()}

      {/* 表格 */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          {tab === 'wy' ? (
            <table className="table">
              <thead><tr><th>专项名称</th><th>任务事项</th><th>项目</th><th>责任人</th><th>计划开始</th><th>计划完成</th><th>状态</th><th>完成</th></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>加载中...</td></tr>
                : data.items.length === 0 ? <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>无数据</td></tr>
                : data.items.map((item, i) => {
                  const state = clean(item.computed_state || item.plan_state)
                  return (
                    <tr key={i}>
                      <td style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{clean(item.special_name)}</td>
                      <td style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{clean(item.plan_content)}</td>
                      <td>{clean(item.project_name)}</td>
                      <td>{clean(item.person_name)}</td>
                      <td style={{ fontSize: 12 }}>{item.plan_start_date ? item.plan_start_date.substring(0, 10) : '-'}</td>
                      <td style={{ fontSize: 12 }}>{item.plan_end_date ? item.plan_end_date.substring(0, 10) : '-'}</td>
                      <td>{state !== '-' ? <span className={`badge ${state.includes('逾期') ? 'badge-red' : state === '已完成' ? 'badge-green' : state === '已暂停' ? '' : 'badge-blue'}`} style={state === '已暂停' ? { background: 'var(--text-3)', color: '#fff' } : {}}>{state}</span> : '-'}</td>
                      <td>{item.finish_flag === 1 ? '✅' : '⬜'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            // IPMS: task_name, project_name, user_name, address_name, sys_name, start_time, end_time, task_state_name
            <table className="table">
              <thead><tr><th>任务名称</th><th>项目</th><th>区域</th><th>系统</th><th>执行人</th><th>开始时间</th><th>结束时间</th><th>状态</th></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>加载中...</td></tr>
                : data.items.length === 0 ? <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>无数据</td></tr>
                : data.items.map((item, i) => (
                  <tr key={i}>
                    <td style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{clean(item.task_name)}</td>
                    <td>{clean(item.project_name)}</td>
                    <td>{clean(item.address_name)}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-2)' }}>{clean(item.sys_name)}</td>
                    <td>{clean(item.user_name)}</td>
                    <td style={{ fontSize: 12 }}>{item.start_time ? String(item.start_time).substring(0, 10) : '-'}</td>
                    <td style={{ fontSize: 12 }}>{item.end_time ? String(item.end_time).substring(0, 10) : '-'}</td>
                    <td>{item.task_state_name && item.task_state_name !== 'None' ? <span className={`badge ${['完成','审核关闭'].includes(item.task_state_name) ? 'badge-green' : 'badge-blue'}`}>{item.task_state_name}</span> : '-'}</td>
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
  const cv = color === 'red' ? 'var(--red)' : color === 'green' ? 'var(--green)' : color === 'blue' ? 'var(--blue)' : color === 'yellow' ? 'var(--yellow)' : 'var(--text)'
  return <div className="card" style={{ padding: 12, textAlign: 'center' }}><div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>{label}</div><div style={{ fontSize: 20, fontWeight: 700, color: cv }}>{value}</div></div>
}
