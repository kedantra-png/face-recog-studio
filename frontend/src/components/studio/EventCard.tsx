'use client';

import React, { useState } from 'react';
import { Calendar, User, Image, Cpu, Search, Power, Trash2, ArrowRight } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';

export interface StudioEvent {
  event_id: string;
  studio_id: string;
  event_name: string;
  client_name: string;
  event_date: string;
  event_status: 'active' | 'inactive';
  search_status: 'enabled' | 'disabled';
  total_images: number;
  total_vectors: number;
  total_faces?: number;
  created_at: number;
}

interface EventCardProps {
  event: StudioEvent;
  onSelectEvent: (event: StudioEvent) => void;
  onStatusUpdated: () => void;
  onEventDeleted?: () => void;
}

export default function EventCard({ event, onSelectEvent, onStatusUpdated, onEventDeleted }: EventCardProps) {
  const [eventStatus, setEventStatus] = useState<'active' | 'inactive'>(event.event_status || 'active');
  const [searchStatus, setSearchStatus] = useState<'enabled' | 'disabled'>(event.search_status || 'enabled');
  const [isUpdating, setIsUpdating] = useState(false);

  const handleToggleEventStatus = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const nextStatus = eventStatus === 'active' ? 'inactive' : 'active';
    setEventStatus(nextStatus);
    setIsUpdating(true);

    try {
      const token = localStorage.getItem('studio_token');
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/api/v2/studio/events/${event.event_id}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
        body: JSON.stringify({ event_status: nextStatus }),
      });
      onStatusUpdated();
    } catch (err) {
      console.error('Error toggling event status:', err);
      setEventStatus(eventStatus); // revert on failure
    } finally {
      setIsUpdating(false);
    }
  };

  const handleToggleSearchStatus = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const nextStatus = searchStatus === 'enabled' ? 'disabled' : 'enabled';
    setSearchStatus(nextStatus);
    setIsUpdating(true);

    try {
      const token = localStorage.getItem('studio_token');
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/api/v2/studio/events/${event.event_id}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
        body: JSON.stringify({ search_status: nextStatus }),
      });
      onStatusUpdated();
    } catch (err) {
      console.error('Error toggling search status:', err);
      setSearchStatus(searchStatus); // revert on failure
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Are you sure you want to delete event '${event.event_name}'?`)) return;

    try {
      const token = localStorage.getItem('studio_token');
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/api/v2/studio/events/${event.event_id}`, {
        method: 'DELETE',
        headers: {
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
      });
      if (onEventDeleted) onEventDeleted();
    } catch (err) {
      console.error('Error deleting event:', err);
    }
  };

  return (
    <div
      onClick={() => onSelectEvent(event)}
      className="group relative bg-[#0f1523]/90 hover:bg-[#131b2d] border border-slate-800/80 hover:border-emerald-500/50 rounded-3xl p-6 transition-all duration-300 shadow-xl hover:shadow-2xl hover:shadow-emerald-500/10 cursor-pointer flex flex-col justify-between overflow-hidden"
    >
      {/* Top Background Gradient Glow */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 group-hover:bg-emerald-500/10 rounded-full blur-2xl transition pointer-events-none" />

      {/* Card Header: Event Title & Client Info */}
      <div>
        <div className="flex items-start justify-between">
          <div>
            <span className="inline-block px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-[10px] font-mono text-emerald-400 font-bold mb-2">
              {event.event_id}
            </span>
            <h3 className="text-base font-extrabold text-white group-hover:text-emerald-400 transition tracking-tight line-clamp-1">
              {event.event_name}
            </h3>
          </div>

          {/* Delete Action */}
          <button
            type="button"
            onClick={handleDelete}
            title="Delete Event"
            className="text-slate-600 hover:text-rose-400 p-1.5 rounded-xl hover:bg-rose-500/10 transition opacity-0 group-hover:opacity-100"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        {/* Client & Date Metadata */}
        <div className="mt-3 space-y-1.5 text-xs text-slate-400">
          <div className="flex items-center space-x-2">
            <User className="w-3.5 h-3.5 text-slate-500 shrink-0" />
            <span className="truncate font-medium text-slate-300">{event.client_name}</span>
          </div>
          <div className="flex items-center space-x-2">
            <Calendar className="w-3.5 h-3.5 text-slate-500 shrink-0" />
            <span>{event.event_date || 'Date not specified'}</span>
          </div>
        </div>

        {/* Telemetry Stats Grid */}
        <div className="mt-5 grid grid-cols-2 gap-2.5 p-3 rounded-2xl bg-slate-950/60 border border-slate-800/80">
          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-400">
              <Image className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="text-xs font-black text-white">{event.total_images || 0}</div>
              <div className="text-[9px] text-slate-500 font-semibold uppercase">Photos</div>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-xl bg-teal-500/10 flex items-center justify-center text-teal-400">
              <Cpu className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="text-xs font-black text-white">{event.total_vectors || 0}</div>
              <div className="text-[9px] text-slate-500 font-semibold uppercase">Vectors</div>
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Status Toggles & Open Button */}
      <div className="mt-6 pt-4 border-t border-slate-800/80 flex items-center justify-between gap-2">
        {/* Status Toggles Container */}
        <div className="flex items-center space-x-2">
          {/* Event Status Toggle */}
          <button
            type="button"
            onClick={handleToggleEventStatus}
            disabled={isUpdating}
            title="Toggle Event Active/Inactive"
            className={`px-2.5 py-1.5 rounded-xl font-bold text-[10px] transition flex items-center space-x-1 border ${
              eventStatus === 'active'
                ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/25'
                : 'bg-slate-900 text-slate-500 border-slate-800 hover:bg-slate-800 hover:text-slate-300'
            }`}
          >
            <Power className="w-3 h-3" />
            <span>{eventStatus === 'active' ? 'Active' : 'Inactive'}</span>
          </button>

          {/* Search Status Toggle */}
          <button
            type="button"
            onClick={handleToggleSearchStatus}
            disabled={isUpdating}
            title="Toggle Vector Search Status"
            className={`px-2.5 py-1.5 rounded-xl font-bold text-[10px] transition flex items-center space-x-1 border ${
              searchStatus === 'enabled'
                ? 'bg-teal-500/15 text-teal-400 border-teal-500/30 hover:bg-teal-500/25'
                : 'bg-slate-900 text-slate-500 border-slate-800 hover:bg-slate-800 hover:text-slate-300'
            }`}
          >
            <Search className="w-3 h-3" />
            <span>{searchStatus === 'enabled' ? 'Search On' : 'Search Off'}</span>
          </button>
        </div>

        {/* Action Button */}
        <div className="flex items-center text-xs font-bold text-emerald-400 group-hover:translate-x-1 transition">
          <span>Open</span>
          <ArrowRight className="w-3.5 h-3.5 ml-1" />
        </div>
      </div>
    </div>
  );
}
