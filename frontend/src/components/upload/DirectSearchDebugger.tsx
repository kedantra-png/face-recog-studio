'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Search, Camera, CheckCircle2, AlertTriangle, Cpu, RefreshCw, CircleDot, Upload, Video } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';

interface SearchDebugResult {
  success: boolean;
  error?: string;
  match_found?: boolean;
  person_id?: string;
  person_metadata?: any;
  similarity_score?: number;
  overall_confidence?: number;
  detected_face_b64?: string;
  top_matches?: any[];
  latency_ms?: {
    extract_ms: number;
    qdrant_ms: number;
    total_ms: number;
  };
}

export const DirectSearchDebugger: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [result, setResult] = useState<SearchDebugResult | null>(null);
  const [isCameraActive, setIsCameraActive] = useState<boolean>(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const startCamera = useCallback(async () => {
    try {
      setResult(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setIsCameraActive(true);
    } catch (err) {
      console.warn('Webcam camera access failed:', err);
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream;
      stream.getTracks().forEach((track) => track.stop());
      videoRef.current.srcObject = null;
    }
    setIsCameraActive(false);
  }, []);

  // Auto-start camera feed on mount
  useEffect(() => {
    startCamera();
    return () => {
      stopCamera();
    };
  }, [startCamera, stopCamera]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      stopCamera();
      const file = e.target.files[0];
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      setResult(null);
    }
  };

  const captureAndSearchCamera = async () => {
    let imageFile: File | null = selectedFile;

    if (isCameraActive && videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
        setPreviewUrl(dataUrl);

        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.95));
        if (blob) {
          imageFile = new File([blob], `camera_snap_${Date.now()}.jpg`, { type: 'image/jpeg' });
          setSelectedFile(imageFile);
        }
      }
    }

    if (!imageFile) return;

    setIsSearching(true);
    setResult(null);

    const t0 = performance.now();
    console.group(`[FRONTEND CAMERA FACE SEARCH] ${new Date().toLocaleTimeString()}`);
    console.log(`[FRONTEND STEP 1/4] Snap Video Canvas Frame created: ${imageFile.name} (${Math.round(imageFile.size/1024)} KB)`);

    try {
      const formData = new FormData();
      formData.append('file', imageFile);

      const t1 = performance.now();
      console.log(`[FRONTEND STEP 2/4] Transmitting image to POST /api/v2/upload/search-debug...`);

      const baseUrl = getApiBaseUrl();
      const response = await fetch(`${baseUrl}/api/v2/upload/search-debug`, {
        method: 'POST',
        body: formData,
      });

      const t2 = performance.now();
      console.log(`[FRONTEND STEP 3/4] Received HTTP ${response.status} backend response in ${Math.round(t2 - t1)}ms`);

      const data: SearchDebugResult = await response.json();
      setResult(data);

      const t3 = performance.now();
      console.log(`[FRONTEND STEP 4/4] Processed Search Results: match_found=${data.match_found}, person=${data.person_id || 'None'}, similarity=${Math.round((data.similarity_score||0)*100)}%`);
      console.log(`[FRONTEND SEARCH COMPLETE] Total Frontend Latency: ${Math.round(t3 - t0)}ms`);
      console.groupEnd();
    } catch (err: any) {
      console.error(`[FRONTEND SEARCH ERROR]:`, err);
      console.groupEnd();
      setResult({
        success: false,
        error: err.message || 'Camera vector search failed',
      });
    } finally {
      setIsSearching(false);
    }
  };


  return (
    <div className="glass-panel p-6 rounded-3xl border border-slate-800/80 shadow-2xl space-y-6">
      {/* Hidden Canvas */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <Camera className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100">Pure Camera-Based Face Detection & Vector Match</h2>
            <p className="text-xs text-slate-400">
              Live webcam camera feed • Instant 512-d ArcFace embedding extraction & Qdrant vector search
            </p>
          </div>
        </div>

        {/* Camera Control & File Switcher */}
        <div className="flex items-center space-x-2">
          {!isCameraActive ? (
            <button
              onClick={startCamera}
              className="px-3 py-1.5 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 text-xs font-semibold border border-cyan-500/30 flex items-center space-x-1.5 transition-all"
            >
              <Video className="w-3.5 h-3.5" />
              <span>Start Camera Stream</span>
            </button>
          ) : (
            <button
              onClick={stopCamera}
              className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 flex items-center space-x-1.5 transition-all"
            >
              <span>Pause Camera</span>
            </button>
          )}

          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 flex items-center space-x-1.5 transition-all"
          >
            <Upload className="w-3.5 h-3.5 text-cyan-400" />
            <span>File Upload Mode</span>
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileChange}
        className="hidden"
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Pure Camera Feed Box */}
        <div className="space-y-4">
          <div className="relative border-2 border-cyan-500/30 bg-slate-950 rounded-2xl p-2 text-center flex flex-col items-center justify-center min-h-[200px] overflow-hidden shadow-inner">
            {/* Live Camera Stream */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className={`w-full h-44 object-cover rounded-xl border border-slate-800 ${!isCameraActive ? 'hidden' : 'block'}`}
            />

            {/* Target Reticle Overlay */}
            {isCameraActive && (
              <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                <div className="w-32 h-36 border-2 border-dashed border-cyan-400/60 rounded-full animate-pulse flex items-center justify-center">
                  <span className="text-[10px] uppercase font-bold text-cyan-400/80 bg-slate-950/70 px-2 py-0.5 rounded-full">
                    Position Face
                  </span>
                </div>
              </div>
            )}

            {/* Photo Preview Mode */}
            {!isCameraActive && previewUrl && (
              <img src={previewUrl} alt="Captured Face" className="h-44 object-contain rounded-xl border border-slate-800" />
            )}

            {!isCameraActive && !previewUrl && (
              <div className="py-8 flex flex-col items-center justify-center space-y-2">
                <Camera className="w-8 h-8 text-cyan-400/60" />
                <p className="text-xs font-semibold text-slate-300">Camera Feed Paused</p>
                <button
                  onClick={startCamera}
                  className="px-3 py-1 rounded-lg bg-cyan-500/20 text-cyan-400 text-xs font-bold border border-cyan-500/30"
                >
                  Start Camera
                </button>
              </div>
            )}
          </div>

          <button
            onClick={captureAndSearchCamera}
            disabled={isSearching}
            className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-extrabold text-xs tracking-wide shadow-lg shadow-cyan-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center space-x-2"
          >
            {isSearching ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Detecting Face & Searching Qdrant...</span>
              </>
            ) : (
              <>
                <CircleDot className="w-4 h-4 text-cyan-200 animate-ping" />
                <span>Snap Camera & Search 512-d Vector Match</span>
              </>
            )}
          </button>
        </div>

        {/* Results Card */}
        <div className="md:col-span-2 space-y-4">
          {result ? (
            result.success ? (
              <div className="space-y-4">
                {/* Status Banner */}
                <div
                  className={`p-4 rounded-2xl border flex items-center justify-between ${
                    result.match_found
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                      : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                  }`}
                >
                  <div className="flex items-center space-x-3">
                    {result.match_found ? (
                      <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
                    ) : (
                      <AlertTriangle className="w-6 h-6 text-amber-400 shrink-0" />
                    )}
                    <div>
                      <h3 className="text-sm font-bold">
                        {result.match_found ? `Match Found: ${result.person_id}` : 'No Enrolled Person Matched Above Threshold'}
                      </h3>
                      <p className="text-xs opacity-80">
                        Cosine Similarity: {Math.round((result.similarity_score || 0) * 100)}% • Overall Confidence: {result.overall_confidence}%
                      </p>
                    </div>
                  </div>

                  {result.latency_ms && (
                    <div className="text-right text-[11px] font-mono opacity-80">
                      <div>Extract: {result.latency_ms.extract_ms}ms</div>
                      <div>Qdrant: {result.latency_ms.qdrant_ms}ms</div>
                      <div className="font-bold text-cyan-300">Total: {result.latency_ms.total_ms}ms</div>
                    </div>
                  )}
                </div>

                {/* Face Crop & Nearest Matches Table */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {/* Aligned Crop */}
                  <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 text-center">
                    <span className="text-[11px] font-semibold text-slate-400 block mb-2">Detected 112x112 Crop</span>
                    {result.detected_face_b64 ? (
                      <img src={result.detected_face_b64} alt="Aligned Face" className="w-24 h-24 mx-auto rounded-xl border border-cyan-500/40 object-cover" />
                    ) : (
                      <div className="w-24 h-24 mx-auto rounded-xl border border-slate-800 bg-slate-950 flex items-center justify-center text-xs text-slate-600">
                        No Crop
                      </div>
                    )}
                  </div>

                  {/* Nearest Matches Table */}
                  <div className="sm:col-span-2 bg-slate-900/80 border border-slate-800 rounded-2xl p-4 overflow-x-auto">
                    <span className="text-[11px] font-semibold text-slate-400 block mb-2">Top Qdrant Nearest Matches</span>
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400">
                          <th className="pb-1">Candidate</th>
                          <th className="pb-1">Person ID</th>
                          <th className="pb-1 text-right">Similarity</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/50">
                        {result.top_matches && result.top_matches.length > 0 ? (
                          result.top_matches.slice(0, 4).map((m: any, idx: number) => (
                            <tr key={idx} className="hover:bg-slate-800/40">
                              <td className="py-1.5">
                                {(m.thumbnail_url || m.face_thumbnail || m.drive_url) ? (
                                  <img
                                    src={m.thumbnail_url || m.face_thumbnail || m.drive_url}
                                    alt="Candidate Face"
                                    className="w-8 h-8 rounded-full object-cover border border-cyan-500/40 shadow-sm"
                                  />
                                ) : (
                                  <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] text-slate-500">
                                    N/A
                                  </div>
                                )}
                              </td>

                              <td className="py-1.5 font-mono text-slate-200">{m.person_id}</td>
                              <td className="py-1.5 text-right font-bold text-cyan-400">
                                {Math.round((m.similarity_score || 0) * 100)}%
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={3} className="py-3 text-center text-slate-500 text-[11px]">
                              No candidates returned from Qdrant index.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-semibold">
                {result.error || 'Vector search error occurred'}
              </div>
            )
          ) : (
            <div className="h-full border border-slate-800/80 rounded-2xl bg-slate-900/30 p-6 flex flex-col items-center justify-center text-center space-y-2 min-h-[200px]">
              <Cpu className="w-8 h-8 text-cyan-400/60" />
              <p className="text-xs font-semibold text-slate-200">Pure Camera Face Detection Active</p>
              <p className="text-[11px] text-slate-400 max-w-sm">
                Position your face inside the target frame and click "Snap Camera & Search 512-d Vector Match" to run instant InsightFace & Qdrant matching.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
