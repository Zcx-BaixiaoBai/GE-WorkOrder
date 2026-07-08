import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
})

// 请求拦截器：自动附加 token + 过滤空参数
api.interceptors.request.use(config => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // 过滤空字符串参数（如管理员projectId为空时不发送）
  if (config.params) {
    Object.keys(config.params).forEach(key => {
      if (config.params[key] === '' || config.params[key] === null || config.params[key] === undefined) {
        delete config.params[key]
      }
    })
  }
  return config
})

// 响应拦截器：401 跳登录
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.clear()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
