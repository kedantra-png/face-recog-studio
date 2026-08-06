'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ShieldCheck, ArrowLeft, UploadCloud, Server, LogOut, UserCheck, Plus, Search, Calendar, Tag, Image as ImageIcon, Cpu, RefreshCw, Power, Key, QrCode } from 'lucide-react';
import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { VirtualizedQueue } from '@/components/upload/VirtualizedQueue';
import { DirectSearchDebugger } from '@/components/upload/DirectSearchDebugger';
import { MetricsOverview } from '@/components/upload/MetricsOverview';

import { ResumableUploader, UploadQueueItem } from '@/components/upload/ResumableUploader';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useStudioAuth } from '@/hooks/useStudioAuth';
import { getApiBaseUrl } from '@/lib/api';

import EventCard, { StudioEvent } from '@/components/studio/EventCard';
import CreateEventModal from '@/components/studio/CreateEventModal';
import PaginatedImageRegistry from '@/components/studio/PaginatedImageRegistry';
import ResetPasskeyModal from '@/components/studio/ResetPasskeyModal';
import StudioQrCodeModal from '@/components/studio/StudioQrCodeModal';

export default function StudioPage() {
  const { studioInfo, isAuthenticated, isLoading, logout } = useStudioAuth();
  const router = useRouter();

  // View state: selectedEvent (null = Events Grid view, non-null = Event Detail Upload view)
  const [selectedEvent, setSelectedEvent] = useState<StudioEvent | null>(null);

  // Events list state
  const [events, setEvents] = useState<StudioEvent[]>([]);
  const [eventSummary, setEventSummary] = useState<any>(null);
  const [eventSearchQuery, setEventSearchQuery] = useState('');
  const [isFetchingEvents, setIsFetchingEvents] = useState(false);

  // Modal states
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isResetPasskeyModalOpen, setIsResetPasskeyModalOpen] = useState(false);
  const [isQrCodeModalOpen, setIsQrCodeModalOpen] = useState(false);

  // Registry refresh trigger
  const [registryRefreshTrigger, setRegistryRefreshTrigger] = useState(0);

  // Queue & Hardware state
  const [queue, setQueue] = useState<UploadQueueItem[]>([]);
  const [systemMetrics, setSystemMetrics] = useState<any>(null);
  const uploaderRef = useRef<ResumableUploader | null>(null);

  // Redirect if unauthenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      window.location.href = '/studio/login';
    }
  }, [isLoading, isAuthenticated]);

  // Initialize Resumable Uploader Manager
  useEffect(() => {
    uploaderRef.current = new ResumableUploader((newQueue) => {
      setQueue(newQueue);
    });
  }, []);

  // Fetch Studio Events from backend
  const fetchStudioEvents = useCallback(async (query: string = '') => {
    if (!isAuthenticated) return;
    setIsFetchingEvents(true);

    try {
      const token = localStorage.getItem('studio_token');
      const baseUrl = getApiBaseUrl();
      const url = `${baseUrl}/api/v2/studio/events` + (query ? `?q=${encodeURIComponent(query)}` : '');

      const res = await fetch(url, {
        headers: {
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
      });

      const data = await res.json();
      if (res.ok && data.success) {
        setEvents(data.events || []);
        setEventSummary(data.summary || null);
      }
    } catch (err) {
      console.error('Error fetching studio events:', err);
    } finally {
      setIsFetchingEvents(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchStudioEvents(eventSearchQuery);
    }
  }, [isAuthenticated, fetchStudioEvents, eventSearchQuery]);

  // WebSocket event handler
  const handleWebSocketMessage = useCallback((event: any) => {
    if (event.event === 'system_metrics') {
      setSystemMetrics(event.data);
    } else if (event.event === 'embedding_completed') {
      const { image_id, job_id, detected_faces, quality_score } = event.data;
      setQueue((prevQueue) =>
        prevQueue.map((item) =>
          item.jobId === job_id || item.id === image_id || item.status === 'embedding_processing'
            ? { ...item, status: 'completed', progress: 100, detectedFaces: detected_faces, qualityScore: quality_score }
            : item
        )
      );
      setRegistryRefreshTrigger((prev) => prev + 1);
    } else if (event.event === 'embedding_processing') {
      const { image_id, job_id } = event.data;
      setQueue((prevQueue) =>
        prevQueue.map((item) =>
          item.jobId === job_id || item.id === image_id
            ? { ...item, status: 'embedding_processing', progress: 100 }
            : item
        )
      );
    }
  }, []);

  const { isConnected } = useWebSocket(handleWebSocketMessage);

  // File Upload Handlers bound to active event
  const handleFilesSelected = (files: File[]) => {
    if (!uploaderRef.current || !selectedEvent) return;
    const jobId = `job_${Math.random().toString(36).substring(2, 10)}`;
    uploaderRef.current.addFiles(files, jobId);
  };

  const handleZipSelected = async (zipFile: File) => {
    if (!uploaderRef.current || !selectedEvent) return;
    const jobId = `job_${Math.random().toString(36).substring(2, 10)}`;
    try {
      await uploaderRef.current.uploadZip(zipFile, jobId);
    } catch (err) {
      console.error('ZIP upload failed:', err);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col items-center justify-center space-y-4">
        <div className="w-12 h-12 rounded-full border-4 border-emerald-500/20 border-t-emerald-400 animate-spin" />
        <p className="text-sm text-slate-400 font-medium">Verifying Studio JWT Session Token...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col justify-between selection:bg-emerald-500 selection:text-white">
      {/* Header Navigation */}
      <header className="sticky top-0 z-40 w-full glass-panel border-b border-slate-800/80 bg-[#090d16]/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Left Title & Navigation */}
          <div className="flex items-center space-x-4">
            {selectedEvent ? (
              <button
                onClick={() => setSelectedEvent(null)}
                className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 transition border border-slate-700/60 flex items-center space-x-1.5 text-xs font-semibold"
                title="Back to All Events"
              >
                <ArrowLeft className="w-4 h-4" />
                <span className="hidden sm:inline">All Events</span>
              </button>
            ) : (
              <Link
                href="/"
                className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 transition border border-slate-700/60"
                title="Back to Main Scanner"
              >
                <ArrowLeft className="w-4 h-4" />
              </Link>
            )}

            <div className="flex items-center space-x-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 text-white shadow-lg shadow-emerald-500/20">
                <UploadCloud className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-emerald-400 bg-clip-text text-transparent">
                  {studioInfo?.studio_name || 'Studio'} Dashboard
                </h1>
                <p className="text-xs text-slate-400 font-medium flex items-center space-x-2">
                  <span>InsightFace 512-d Vector Indexing</span>
                  <span className="text-slate-600">•</span>
                  <span className="text-emerald-400 font-mono">ID: {studioInfo?.studio_id}</span>
                </p>
              </div>
            </div>
          </div>

          {/* Right Status & Auth Actions */}
          <div className="flex items-center space-x-2.5">
            {/* WebSocket Connection Badge */}
            <div className="hidden lg:flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-semibold border bg-emerald-950/40 text-emerald-400 border-emerald-500/30">
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-ping' : 'bg-amber-500'}`} />
              <Server className="w-3.5 h-3.5" />
              <span>{isConnected ? 'WebSocket Active' : 'Connecting...'}</span>
            </div>

            {/* Studio QR & Share Link Button */}
            <button
              onClick={() => setIsQrCodeModalOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-teal-500/10 hover:bg-teal-500/20 text-teal-400 hover:text-teal-300 font-bold text-xs transition border border-teal-500/30"
              title="View Persistent Studio Access Link & QR Code"
            >
              <QrCode className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">QR Pass</span>
            </button>

            {/* Reset Passkey Button */}
            <button
              onClick={() => setIsResetPasskeyModalOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 hover:text-amber-300 font-bold text-xs transition border border-amber-500/30"
              title="Reset Studio Passkey"
            >
              <Key className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Reset Passkey</span>
            </button>

            {/* Authenticated Studio Badge */}
            <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700 text-xs font-medium text-slate-200">
              <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span className="hidden md:inline">{studioInfo?.studio_name}</span>
            </div>

            {/* Logout Button */}
            <button
              onClick={logout}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 hover:text-rose-300 font-semibold text-xs transition border border-rose-500/30"
              title="Sign Out of Studio"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-8 flex-grow">
        {selectedEvent === null ? (
          /* MODE 1: STUDIO EVENTS OVERVIEW DASHBOARD */
          <div className="space-y-8">
            {/* Summary Statistics Bar */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-[#0b0f19]/90 border border-slate-800 p-5 rounded-3xl shadow-xl flex items-center space-x-4">
                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-bold">
                  <Tag className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-2xl font-black text-white">{eventSummary?.total_events || events.length}</div>
                  <div className="text-xs text-slate-400 font-medium">Registered Events</div>
                </div>
              </div>

              <div className="bg-[#0b0f19]/90 border border-slate-800 p-5 rounded-3xl shadow-xl flex items-center space-x-4">
                <div className="w-12 h-12 rounded-2xl bg-teal-500/10 text-teal-400 flex items-center justify-center font-bold">
                  <Power className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-2xl font-black text-white">{eventSummary?.enabled_events || 0}</div>
                  <div className="text-xs text-teal-400 font-semibold">Active Vector Searches</div>
                </div>
              </div>

              <div className="bg-[#0b0f19]/90 border border-slate-800 p-5 rounded-3xl shadow-xl flex items-center space-x-4">
                <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center font-bold">
                  <ImageIcon className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-2xl font-black text-white">{eventSummary?.total_images_all || 0}</div>
                  <div className="text-xs text-slate-400 font-medium">Total Event Photos</div>
                </div>
              </div>

              <div className="bg-[#0b0f19]/90 border border-slate-800 p-5 rounded-3xl shadow-xl flex items-center space-x-4">
                <div className="w-12 h-12 rounded-2xl bg-sky-500/10 text-sky-400 flex items-center justify-center font-bold">
                  <Cpu className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-2xl font-black text-white">{eventSummary?.total_vectors_all || 0}</div>
                  <div className="text-xs text-slate-400 font-medium">512-d Vectors Indexed</div>
                </div>
              </div>
            </div>

            {/* Action Bar: Search Events & Create Event Button */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 rounded-3xl bg-[#0b0f19]/90 border border-slate-800">
              <div className="relative w-full sm:w-80">
                <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={eventSearchQuery}
                  onChange={(e) => setEventSearchQuery(e.target.value)}
                  placeholder="Search events by name, client, or ID..."
                  className="w-full pl-10 pr-4 py-2.5 rounded-2xl bg-slate-950/80 border border-slate-800 text-white placeholder-slate-500 text-xs focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
                />
              </div>

              <div className="flex items-center space-x-3 w-full sm:w-auto">
                <button
                  onClick={() => fetchStudioEvents(eventSearchQuery)}
                  disabled={isFetchingEvents}
                  className="p-2.5 rounded-2xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 transition flex items-center justify-center"
                  title="Refresh Events"
                >
                  <RefreshCw className={`w-4 h-4 ${isFetchingEvents ? 'animate-spin' : ''}`} />
                </button>

                <button
                  onClick={() => setIsCreateModalOpen(true)}
                  className="flex-1 sm:flex-initial px-5 py-2.5 rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-extrabold text-xs transition shadow-lg shadow-emerald-500/25 flex items-center justify-center space-x-2"
                >
                  <Plus className="w-4 h-4" />
                  <span>Create New Event</span>
                </button>
              </div>
            </div>

            {/* Events Responsive Cards Grid */}
            {events.length === 0 ? (
              <div className="p-12 text-center bg-[#0b0f19]/60 border border-slate-800/80 rounded-3xl space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500 mx-auto">
                  <Tag className="w-6 h-6" />
                </div>
                <h3 className="text-sm font-bold text-white">No Studio Events Found</h3>
                <p className="text-xs text-slate-400 max-w-sm mx-auto">
                  Click "Create New Event" above to add your first photo collection and upload photos for vector indexing.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {events.map((evt) => (
                  <EventCard
                    key={evt.event_id}
                    event={evt}
                    onSelectEvent={(e) => setSelectedEvent(e)}
                    onStatusUpdated={() => fetchStudioEvents(eventSearchQuery)}
                    onEventDeleted={() => fetchStudioEvents(eventSearchQuery)}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          /* MODE 2: EVENT DETAIL WORKSPACE */
          <div className="space-y-8">
            {/* Active Event Banner */}
            <div className="p-6 rounded-3xl bg-gradient-to-r from-[#0f1523] via-[#11192b] to-[#0a1220] border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-2xl">
              <div>
                <div className="flex items-center space-x-2 mb-1">
                  <span className="px-2.5 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-400 font-mono text-[10px] font-bold border border-emerald-500/20">
                    {selectedEvent.event_id}
                  </span>
                  <span className="text-xs text-slate-400">• {selectedEvent.event_date}</span>
                </div>
                <h2 className="text-2xl font-black text-white tracking-tight">{selectedEvent.event_name}</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Client: <span className="text-slate-200 font-semibold">{selectedEvent.client_name}</span>
                </p>
              </div>

              {/* Status Indicator Badges */}
              <div className="flex items-center space-x-3">
                <div className="px-3.5 py-1.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold flex items-center space-x-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span>Active Collection</span>
                </div>
              </div>
            </div>

            {/* Hardware & Telemetry Overview */}
            <MetricsOverview metrics={systemMetrics} />

            {/* Universal Dropzone bound to Event */}
            <UploadDropzone
              onFilesSelected={handleFilesSelected}
              onZipSelected={handleZipSelected}
            />

            {/* Live Upload & Processing Queue */}
            <VirtualizedQueue
              queue={queue}
              onPause={(id) => uploaderRef.current?.pause(id)}
              onResume={(id) => uploaderRef.current?.resume(id)}
              onCancel={(id) => uploaderRef.current?.cancel(id)}
              onRetry={(id) => uploaderRef.current?.retry(id)}
            />

            {/* Direct Vector Search & Match Debugger */}
            <DirectSearchDebugger />

            {/* Paginated Image Registry for Event */}
            <PaginatedImageRegistry
              eventId={selectedEvent.event_id}
              refreshTrigger={registryRefreshTrigger}
            />
          </div>
        )}
      </main>

      {/* Create Event Modal */}
      <CreateEventModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onEventCreated={() => fetchStudioEvents(eventSearchQuery)}
      />

      {/* Reset Passkey Modal */}
      <ResetPasskeyModal
        isOpen={isResetPasskeyModalOpen}
        onClose={() => setIsResetPasskeyModalOpen(false)}
      />

      {/* Studio QR Code & Share Link Modal */}
      <StudioQrCodeModal
        isOpen={isQrCodeModalOpen}
        onClose={() => setIsQrCodeModalOpen(false)}
        studioName={studioInfo?.studio_name}
        studioId={studioInfo?.studio_id}
      />

      {/* Footer */}
      <footer className="w-full border-t border-slate-800/80 py-4 bg-[#070a11]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-2">
          <span>AuraFace Enterprise Studio ({studioInfo?.studio_id}) • InsightFace 512-d Qdrant Vector Index</span>
          <span>MongoDB: face_recog_db_v2 • Qdrant: faces_embed_v2</span>
        </div>
      </footer>
    </div>
  );
}
