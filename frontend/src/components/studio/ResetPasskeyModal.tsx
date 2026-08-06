'use client';

import React, { useState } from 'react';
import { X, Key, Lock, Eye, EyeOff, CheckCircle2, ShieldAlert, AlertCircle } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';

interface ResetPasskeyModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function ResetPasskeyModal({ isOpen, onClose }: ResetPasskeyModalProps) {
  const [currentPasskey, setCurrentPasskey] = useState('');
  const [newPasskey, setNewPasskey] = useState('');
  const [confirmPasskey, setConfirmPasskey] = useState('');

  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  // Complexity Validation Rules
  const hasMinLength = newPasskey.length >= 8;
  const hasUpper = /[A-Z]/.test(newPasskey);
  const hasLower = /[a-z]/.test(newPasskey);
  const hasNumber = /[0-9]/.test(newPasskey);
  const hasSpecial = /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(newPasskey);
  const isMatch = newPasskey.length > 0 && newPasskey === confirmPasskey;

  const isStrong = hasMinLength && hasUpper && hasLower && hasNumber && hasSpecial && isMatch;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPasskey.trim() || !newPasskey.trim()) {
      setError('Please fill in all passkey fields.');
      return;
    }

    if (!isStrong) {
      setError('Please fulfill all passkey complexity requirements below.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const token = localStorage.getItem('studio_token');
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/v2/studio/reset-passkey`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
        body: JSON.stringify({
          current_passkey: currentPasskey.trim(),
          new_passkey: newPasskey.trim(),
        }),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.message || 'Passkey reset failed');
      }

      setSuccessMessage('Passkey updated successfully with PBKDF2-HMAC encryption!');
      setCurrentPasskey('');
      setNewPasskey('');
      setConfirmPasskey('');

      setTimeout(() => {
        onClose();
        setSuccessMessage(null);
      }, 1500);
    } catch (err: any) {
      console.error('Reset passkey error:', err);
      setError(err.message || 'Passkey reset failed. Please verify current passkey.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fadeIn">
      <div className="w-full max-w-md bg-[#0f1523] border border-slate-800 rounded-3xl p-6 md:p-8 shadow-2xl relative overflow-hidden">
        {/* Decorative Top Glow */}
        <div className="absolute top-0 left-0 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        {/* Modal Header */}
        <div className="flex items-center justify-between pb-5 border-b border-slate-800/80">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center text-white shadow-lg shadow-emerald-500/20">
              <Key className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">Reset Studio Passkey</h2>
              <p className="text-xs text-slate-400">Update passkey with PBKDF2-HMAC encryption</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Alert Messages */}
        {error && (
          <div className="mt-4 p-3 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {successMessage && (
          <div className="mt-4 p-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{successMessage}</span>
          </div>
        )}

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          {/* Current Passkey */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
              Current Passkey
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type={showCurrent ? 'text' : 'password'}
                value={currentPasskey}
                onChange={(e) => setCurrentPasskey(e.target.value)}
                placeholder="Enter current passkey"
                required
                className="w-full pl-10 pr-10 py-3 rounded-2xl bg-slate-950/80 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition font-mono"
              />
              <button
                type="button"
                onClick={() => setShowCurrent(!showCurrent)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition"
              >
                {showCurrent ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* New Passkey */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
              New Passkey
            </label>
            <div className="relative">
              <Key className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type={showNew ? 'text' : 'password'}
                value={newPasskey}
                onChange={(e) => setNewPasskey(e.target.value)}
                placeholder="Enter strong new passkey"
                required
                className="w-full pl-10 pr-10 py-3 rounded-2xl bg-slate-950/80 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition font-mono"
              />
              <button
                type="button"
                onClick={() => setShowNew(!showNew)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition"
              >
                {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Confirm Passkey */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
              Confirm New Passkey
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type={showConfirm ? 'text' : 'password'}
                value={confirmPasskey}
                onChange={(e) => setConfirmPasskey(e.target.value)}
                placeholder="Re-enter new passkey"
                required
                className="w-full pl-10 pr-10 py-3 rounded-2xl bg-slate-950/80 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition font-mono"
              />
              <button
                type="button"
                onClick={() => setShowConfirm(!showConfirm)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition"
              >
                {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Passkey Complexity Meter Checklist */}
          <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 space-y-1.5 text-[11px]">
            <div className="font-bold text-slate-300 uppercase tracking-wider text-[10px] mb-1">
              Passkey Complexity Requirements:
            </div>
            <div className={`flex items-center space-x-1.5 ${hasMinLength ? 'text-emerald-400 font-semibold' : 'text-slate-500'}`}>
              <span>{hasMinLength ? '✓' : '○'}</span>
              <span>At least 8 characters long</span>
            </div>
            <div className={`flex items-center space-x-1.5 ${hasUpper ? 'text-emerald-400 font-semibold' : 'text-slate-500'}`}>
              <span>{hasUpper ? '✓' : '○'}</span>
              <span>One uppercase letter (A-Z)</span>
            </div>
            <div className={`flex items-center space-x-1.5 ${hasLower ? 'text-emerald-400 font-semibold' : 'text-slate-500'}`}>
              <span>{hasLower ? '✓' : '○'}</span>
              <span>One lowercase letter (a-z)</span>
            </div>
            <div className={`flex items-center space-x-1.5 ${hasNumber ? 'text-emerald-400 font-semibold' : 'text-slate-500'}`}>
              <span>{hasNumber ? '✓' : '○'}</span>
              <span>One numeric digit (0-9)</span>
            </div>
            <div className={`flex items-center space-x-1.5 ${hasSpecial ? 'text-emerald-400 font-semibold' : 'text-slate-500'}`}>
              <span>{hasSpecial ? '✓' : '○'}</span>
              <span>One special character (!@#$%^&*...)</span>
            </div>
            <div className={`flex items-center space-x-1.5 ${isMatch ? 'text-emerald-400 font-semibold' : 'text-slate-500'}`}>
              <span>{isMatch ? '✓' : '○'}</span>
              <span>Passkeys match</span>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center space-x-3 pt-3 border-t border-slate-800/80">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-3 rounded-2xl bg-slate-900 hover:bg-slate-800 text-slate-300 font-semibold text-xs transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !isStrong}
              className="flex-1 py-3 rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold text-xs transition shadow-lg shadow-emerald-500/20 flex items-center justify-center space-x-2 disabled:opacity-40"
            >
              {isLoading ? <span>Updating...</span> : <span>Update Passkey</span>}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
