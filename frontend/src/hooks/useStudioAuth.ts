import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { getApiBaseUrl } from '@/lib/api';

export interface StudioInfo {
  studio_id: string;
  studio_name: string;
  role: string;
}

export function useStudioAuth() {
  const [studioInfo, setStudioInfo] = useState<StudioInfo | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const router = useRouter();

  const verifyToken = useCallback(async (): Promise<boolean> => {
    try {
      setIsLoading(true);
      const token = typeof window !== 'undefined' ? localStorage.getItem('studio_token') : null;
      const baseUrl = getApiBaseUrl();

      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(`${baseUrl}/api/v2/studio/me`, {
        method: 'GET',
        headers,
        credentials: 'include',
      });

      if (res.ok) {
        const data = await res.json();
        if (data.authenticated && data.studio) {
          setStudioInfo(data.studio);
          setIsAuthenticated(true);
          setIsLoading(false);
          return true;
        }
      }
    } catch (err) {
      console.warn('Studio authentication verification failed:', err);
    }

    // Clean up stale or invalid tokens to prevent redirect loops
    if (typeof window !== 'undefined') {
      localStorage.removeItem('studio_token');
      document.cookie = 'studio_access_token=; Max-Age=0; path=/;';
    }

    setIsAuthenticated(false);
    setStudioInfo(null);
    setIsLoading(false);
    return false;
  }, []);

  const login = useCallback((token: string, studio: StudioInfo) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('studio_token', token);
    }
    setStudioInfo(studio);
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(async () => {
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('studio_token') : null;
      const baseUrl = getApiBaseUrl();
      if (token) {
        await fetch(`${baseUrl}/api/v2/studio/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          credentials: 'include',
        });
      }
    } catch (err) {
      console.warn('Logout notification error:', err);
    }

    if (typeof window !== 'undefined') {
      localStorage.removeItem('studio_token');
      document.cookie = 'studio_access_token=; Max-Age=0; path=/;';
    }
    setStudioInfo(null);
    setIsAuthenticated(false);
    if (typeof window !== 'undefined') {
      window.location.href = '/studio/login';
    }
  }, []);

  useEffect(() => {
    verifyToken();
  }, [verifyToken]);

  return {
    studioInfo,
    isAuthenticated,
    isLoading,
    login,
    logout,
    verifyToken,
  };
}
