import axios, { AxiosInstance } from 'axios'

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: '/api/v1',
      timeout: 10000,
    })

    this.client.interceptors.request.use((config) => {
      const token = localStorage.getItem('access_token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    })

    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401) {
          await this.refreshToken()
          return this.client.request(error.config)
        }
        return Promise.reject(error)
      }
    )
  }

  async login(username: string, password: string) {
    const response = await this.client.post('/auth/login', {
      username,
      password,
    })
    localStorage.setItem('access_token', response.data.access_token)
    localStorage.setItem('refresh_token', response.data.refresh_token)
    return response.data
  }

  async refreshToken() {
    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) {
      throw new Error('No refresh token')
    }

    const response = await this.client.post('/auth/refresh', {
      refresh_token: refreshToken,
    })
    localStorage.setItem('access_token', response.data.access_token)
    localStorage.setItem('refresh_token', response.data.refresh_token)
    return response.data
  }

  async logout() {
    const refreshToken = localStorage.getItem('refresh_token')
    if (refreshToken) {
      await this.client.post('/auth/logout', {
        refresh_token: refreshToken,
      })
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  async getDevices(status?: string) {
    const response = await this.client.get('/devices', {
      params: { status },
    })
    return response.data
  }

  async getDevice(deviceId: string) {
    const response = await this.client.get(`/devices/${deviceId}`)
    return response.data
  }

  async deleteDevice(deviceId: string) {
    const response = await this.client.delete(`/devices/${deviceId}`)
    return response.data
  }

  async getDeviceHistory(deviceId: string, limit: number = 50) {
    const response = await this.client.get(`/devices/${deviceId}/history`, {
      params: { limit },
    })
    return response.data
  }

  async getSessionMetrics(sessionId: string, hours: number = 1) {
    const response = await this.client.get(`/metrics/${sessionId}`, {
      params: { hours },
    })
    return response.data
  }
}

export const apiClient = new ApiClient()
