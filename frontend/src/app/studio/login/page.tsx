'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ShieldCheck, Key, Lock, Eye, EyeOff, Sparkles, AlertCircle, ArrowRight, Server, CheckCircle2 } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';

export default function StudioLoginPage() {
  const [passkey, setPasskey] = useState<string>('');
  const [showPasskey, setShowPasskey] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [rateLimitMessage, setRateLimitMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const router = useRouter();

  // Redirect if already authenticated with valid token
  useEffect(() => {
    const verifyExistingSession = async () => {
      const existingToken = localStorage.getItem('studio_token');
      if (!existingToken) return;

      try {
        const baseUrl = getApiBaseUrl();
        const res = await fetch(`${baseUrl}/api/v2/studio/me`, {
          method: 'GET',
          headers: { Authorization: `Bearer ${existingToken}` },
          credentials: 'include',
        });
        if (res.ok) {
          const data = await res.json();
          if (data.authenticated) {
            window.location.href = '/studio';
            return;
          }
        }
      } catch {
        // network error or backend offline
      }

      // Clear invalid token if verification fails
      localStorage.removeItem('studio_token');
      document.cookie = 'studio_access_token=; Max-Age=0; path=/;';
    };

    verifyExistingSession();
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!passkey.trim()) {
      setError('Please enter your Studio Passkey.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setRateLimitMessage(null);
    setSuccessMessage(null);

    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/v2/studio/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          passkey: passkey.trim(),
        }),
      });

      const data = await res.json();

      if (res.status === 429) {
        setRateLimitMessage(data.detail || 'Too many login attempts. Please wait 60 seconds.');
        setIsLoading(false);
        return;
      }

      if (!res.ok) {
        throw new Error(data.detail || 'Authentication failed. Please verify your passkey.');
      }

      if (data.success && data.access_token) {
        localStorage.setItem('studio_token', data.access_token);
        setSuccessMessage('Authentication successful! Loading Studio Workspace...');
        setTimeout(() => {
          window.location.href = '/studio';
        }, 150);
      } else {
        throw new Error('Invalid response payload from authentication server.');
      }
    } catch (err: any) {
      console.error('Studio login error:', err);
      setError(err.message || 'Login failed. Please verify passkey.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col justify-between items-center selection:bg-emerald-500 selection:text-white relative overflow-hidden">
      {/* Background Ambient Glowing Orbs */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-emerald-500/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute bottom-10 right-10 w-[350px] h-[350px] bg-teal-500/10 rounded-full blur-[120px] pointer-events-none" />

      {/* Top Header Identity */}
      <header className="w-full max-w-7xl px-6 py-6 flex items-center justify-between z-10">
        <div className="flex items-center space-x-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 text-white shadow-lg shadow-emerald-500/20">
            <ShieldCheck className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-emerald-400 bg-clip-text text-transparent">
              AuraFace Studio
            </h1>
            <p className="text-xs text-slate-400">Enterprise AI Portal</p>
          </div>
        </div>

        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-semibold bg-slate-900/80 border border-slate-800 text-slate-300">
          <Server className="w-3.5 h-3.5 text-emerald-400" />
          <span>FastAPI Protected Gateway</span>
        </div>
      </header>

      {/* Main Login Card Section */}
      <main className="w-full max-w-md px-4 py-8 z-10 flex flex-col items-center">
        <div className="w-full bg-slate-900/60 backdrop-blur-2xl border border-slate-800/90 rounded-3xl p-8 shadow-2xl space-y-6 relative overflow-hidden">
          {/* Top Decorative Border Highlight */}
          <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-emerald-500 via-teal-400 to-emerald-600" />

          {/* Heading */}
          <div className="text-center space-y-2">
            <div className="inline-flex items-center justify-center p-3 rounded-2xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-2 shadow-inner">
              <Lock className="w-7 h-7" />
            </div>
            <h2 className="text-2xl font-bold text-white tracking-tight">Studio Access</h2>
            <p className="text-xs text-slate-400">
              Enter your secure Passkey to access the embedding studio workspace.
            </p>
          </div>

          {/* Rate Limit Notice Banner */}
          {rateLimitMessage && (
            <div className="p-4 rounded-2xl bg-amber-950/80 border border-amber-500/50 text-amber-200 text-xs flex items-start space-x-3 animate-fade-in">
              <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5 animate-pulse" />
              <div>
                <span className="font-bold">Rate Limit Advisory:</span> {rateLimitMessage}
              </div>
            </div>
          )}

          {/* Error Banner */}
          {error && (
            <div className="p-4 rounded-2xl bg-rose-950/80 border border-rose-500/50 text-rose-200 text-xs flex items-start space-x-3 animate-fade-in">
              <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-bold">Access Denied:</span> {error}
              </div>
            </div>
          )}

          {/* Success Banner */}
          {successMessage && (
            <div className="p-4 rounded-2xl bg-emerald-950/80 border border-emerald-500/50 text-emerald-200 text-xs flex items-center space-x-3 animate-fade-in">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 animate-bounce" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleLogin} className="space-y-5">
            {/* Passkey Only Input */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <Key className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Studio Passkey</span>
                </label>
              </div>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <Lock className="w-4 h-4 text-emerald-400" />
                </div>
                <input
                  type={showPasskey ? 'text' : 'password'}
                  value={passkey}
                  onChange={(e) => setPasskey(e.target.value)}
                  placeholder="Enter your studio passkey"
                  required
                  autoFocus
                  className="w-full pl-10 pr-10 py-3.5 rounded-2xl bg-slate-950/80 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowPasskey(!showPasskey)}
                  className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-white transition"
                >
                  {showPasskey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3.5 px-4 rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold text-sm transition-all shadow-lg shadow-emerald-500/25 flex items-center justify-center space-x-2 disabled:opacity-50"
            >
              {isLoading ? (
                <span>Authenticating Passkey...</span>
              ) : (
                <>
                  <span>Sign In to Studio</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
        </div>
      </main>

      {/* Footer Notice */}
      <footer className="py-6 text-center text-xs text-slate-500 z-10">
        <span>Protected by PBKDF2-HMAC-SHA256 & 24h JWT Tokens • AuraFace AI Platform</span>
      </footer>
    </div>
  );
}
