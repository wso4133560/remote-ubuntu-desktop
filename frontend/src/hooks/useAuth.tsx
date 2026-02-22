import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { apiClient } from '../services/api'

interface AuthContextType {
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    if (typeof window === 'undefined') {
      return false
    }
    return !!window.localStorage.getItem('access_token')
  })

  useEffect(() => {
    const onStorage = () => {
      setIsAuthenticated(!!window.localStorage.getItem('access_token'))
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const login = async (username: string, password: string) => {
    await apiClient.login(username, password)
    setIsAuthenticated(true)
  }

  const logout = async () => {
    await apiClient.logout()
    setIsAuthenticated(false)
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
