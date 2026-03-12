import React, { createContext, useCallback, useEffect, useState } from 'react';
import * as authApi from '../api/auth';
import type { UserProfile } from '../types';

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: UserProfile | null;
  accessToken: string | null;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: !!localStorage.getItem('access_token'),
    isLoading: true,
    user: null,
    accessToken: localStorage.getItem('access_token'),
  });

  const loadUser = useCallback(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setState({
        isAuthenticated: false,
        isLoading: false,
        user: null,
        accessToken: null,
      });
      return;
    }

    try {
      const user = await authApi.getMe();
      setState({
        isAuthenticated: true,
        isLoading: false,
        user,
        accessToken: token,
      });
    } catch {
      // Token might be expired; the interceptor will handle refresh
      // If that fails too, we'll end up redirected to login
      setState({
        isAuthenticated: false,
        isLoading: false,
        user: null,
        accessToken: null,
      });
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await authApi.login(email, password);
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
    localStorage.setItem('user_id', tokens.user_id);
    localStorage.setItem('user_email', tokens.email);

    const user = await authApi.getMe();
    setState({
      isAuthenticated: true,
      isLoading: false,
      user,
      accessToken: tokens.access_token,
    });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_email');
    setState({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      accessToken: null,
    });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
