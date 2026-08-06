'use client';

import React, { useState } from 'react';
import { X, Calendar, User, Tag, ShieldCheck, CheckCircle2, Search, Power } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';

interface CreateEventModalProps {
  isOpen: boolean;
  onClose: () => void;
  onEventCreated: () => void;
}

export default function CreateEventModal({ isOpen, onClose, onEventCreated }: CreateEventModalProps) {
  const [eventName, setEventName] = useState('');
  const [clientName, setClientName] = useState('');
  const [eventDate, setEventDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [eventStatus, setEventStatus] = useState<'active' | 'inactive'>('active');
  const [searchStatus, setSearchStatus] = useState<'enabled' | 'disabled'>('enabled');
  
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!eventName.trim() || !clientName.trim()) {
      setError('Event Name and Client Name are required.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('studio_token');
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/v2/studio/events`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
        body: JSON.stringify({
          event_name: eventName.trim(),
          client_name: clientName.trim(),
          event_date: eventDate,
          event_status: eventStatus,
          search_status: searchStatus,
        }),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.message || 'Failed to create event');
      }

      setEventName('');
      setClientName('');
      onEventCreated();
      onClose();
    } catch (err: any) {
      console.error('Error creating event:', err);
      setError(err.message || 'Error creating event. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fadeIn">
      <div className="w-full max-w-lg bg-[#0f1523] border border-slate-800 rounded-3xl p-6 md:p-8 shadow-2xl relative overflow-hidden">
        {/* Top Decorative Glow */}
        <div className="absolute top-0 right-0 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        {/* Modal Header */}
        <div className="flex items-center justify-between pb-6 border-b border-slate-800/80">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center text-white shadow-lg shadow-emerald-500/20">
              <Tag className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">Create Studio Event</h2>
              <p className="text-xs text-slate-400">Register a new client photo collection & vector index</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mt-4 p-3 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center space-x-2">
            <span>{error}</span>
          </div>
        )}

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          {/* Event Name */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
              Event Name <span className="text-rose-400">*</span>
            </label>
            <div className="relative">
              <Tag className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={eventName}
                onChange={(e) => setEventName(e.target.value)}
                placeholder="e.g. Royal Wedding Reception 2026"
                required
                className="w-full pl-10 pr-4 py-3 rounded-2xl bg-slate-950/80 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
              />
            </div>
          </div>

          {/* Client Name */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
              Client Name <span className="text-rose-400">*</span>
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                placeholder="e.g. Mr. & Mrs. Sharma"
                required
                className="w-full pl-10 pr-4 py-3 rounded-2xl bg-slate-950/80 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
              />
            </div>
          </div>

          {/* Date Picker */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
              Event Date
            </label>
            <div className="relative">
              <Calendar className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
                className="w-full pl-10 pr-4 py-3 rounded-2xl bg-slate-950/80 border border-slate-800 text-white text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
              />
            </div>
          </div>

          {/* Status Toggles Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            {/* Event Status Toggle */}
            <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
              <div>
                <div className="text-xs font-bold text-white flex items-center space-x-1.5">
                  <Power className="w-3.5 h-3.5 text-slate-400" />
                  <span>Event Status</span>
                </div>
                <div className="text-[10px] text-slate-400">
                  {eventStatus === 'active' ? 'Active Collection' : 'Inactive'}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setEventStatus(eventStatus === 'active' ? 'inactive' : 'active')}
                className={`px-3 py-1.5 rounded-xl font-bold text-xs transition ${
                  eventStatus === 'active'
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                    : 'bg-slate-800 text-slate-400 border border-slate-700'
                }`}
              >
                {eventStatus === 'active' ? 'Active' : 'Inactive'}
              </button>
            </div>

            {/* Vector Search Status Toggle */}
            <div className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
              <div>
                <div className="text-xs font-bold text-white flex items-center space-x-1.5">
                  <Search className="w-3.5 h-3.5 text-slate-400" />
                  <span>Vector Search</span>
                </div>
                <div className="text-[10px] text-slate-400">
                  {searchStatus === 'enabled' ? 'Search Enabled' : 'Disabled'}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSearchStatus(searchStatus === 'enabled' ? 'disabled' : 'enabled')}
                className={`px-3 py-1.5 rounded-xl font-bold text-xs transition ${
                  searchStatus === 'enabled'
                    ? 'bg-teal-500/20 text-teal-400 border border-teal-500/40'
                    : 'bg-slate-800 text-slate-400 border border-slate-700'
                }`}
              >
                {searchStatus === 'enabled' ? 'Enabled' : 'Disabled'}
              </button>
            </div>
          </div>

          {/* Modal Action Footer */}
          <div className="flex items-center space-x-3 pt-4 border-t border-slate-800/80">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-3 rounded-2xl bg-slate-900 hover:bg-slate-800 text-slate-300 font-semibold text-xs transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="flex-1 py-3 rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold text-xs transition shadow-lg shadow-emerald-500/20 flex items-center justify-center space-x-2 disabled:opacity-50"
            >
              {isLoading ? (
                <span>Creating Event...</span>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Create Event</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
