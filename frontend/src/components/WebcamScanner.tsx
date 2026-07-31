'use client';

import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Camera, CameraOff, Play, Pause, Scan, RefreshCw, AlertCircle } from 'lucide-react';
import { PredictionResult } from '@/types';

interface WebcamScannerProps {
  onAnalyzeFrame: (base64Image: string) => Promise<void>;
  isAnalyzing: boolean;
  activeResult: PredictionResult | null;
}

export const WebcamScanner: React.FC<WebcamScannerProps> = ({
  onAnalyzeFrame,
  isAnalyzing,
  activeResult,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  const [isCameraActive, setIsCameraActive] = useState<boolean>(false);
  const [isAutoScanActive, setIsAutoScanActive] = useState<boolean>(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  // Start Webcam Stream
  const startCamera = async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
        audio: false,
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
        setIsCameraActive(true);
      }
    } catch (err: any) {
      console.error('Camera access error:', err);
      setCameraError(err.message || 'Unable to access webcam. Please check browser permissions.');
    }
  };

  // Stop Webcam Stream
  const stopCamera = useCallback(() => {
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream;
      stream.getTracks().forEach((track) => track.stop());
      videoRef.current.srcObject = null;
    }
    setIsCameraActive(false);
    setIsAutoScanActive(false);
  }, []);

  // Capture Frame from Video
  const captureFrame = useCallback((): string | null => {
    if (!videoRef.current || !canvasRef.current) return null;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    
    if (video.videoWidth === 0 || video.videoHeight === 0) return null;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.85);
  }, []);

  // Manual Trigger
  const handleSingleCapture = async () => {
    const frame = captureFrame();
    if (frame) {
      await onAnalyzeFrame(frame);
    }
  };

  // Auto-scan interval loop
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    if (isCameraActive && isAutoScanActive && !isAnalyzing) {
      timer = setInterval(async () => {
        const frame = captureFrame();
        if (frame) {
          await onAnalyzeFrame(frame);
        }
      }, 800); // scan every 800ms
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isCameraActive, isAutoScanActive, isAnalyzing, captureFrame, onAnalyzeFrame]);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  return (
    <div className="glass-panel p-5 rounded-3xl border border-slate-800/80 shadow-2xl relative overflow-hidden flex flex-col justify-between h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <div className="p-2 rounded-xl bg-teal-500/10 text-teal-400 border border-teal-500/20">
            <Camera className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100">Live Webcam Feed</h2>
            <p className="text-xs text-slate-400">Real-time video liveness detection</p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-2">
          {isCameraActive ? (
            <>
              <button
                onClick={() => setIsAutoScanActive(!isAutoScanActive)}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition border ${
                  isAutoScanActive
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse'
                    : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
                }`}
              >
                {isAutoScanActive ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                <span>{isAutoScanActive ? 'Auto Scanning' : 'Enable Auto Scan'}</span>
              </button>
              <button
                onClick={stopCamera}
                className="p-2 rounded-xl bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 border border-rose-500/30 transition"
                title="Turn Off Camera"
              >
                <CameraOff className="w-4 h-4" />
              </button>
            </>
          ) : (
            <button
              onClick={startCamera}
              className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-semibold text-xs shadow-lg shadow-emerald-500/20 transition"
            >
              <Camera className="w-4 h-4" />
              <span>Start Camera</span>
            </button>
          )}
        </div>
      </div>

      {/* Video Stream Container */}
      <div className="relative aspect-[4/3] w-full rounded-2xl overflow-hidden bg-slate-950 border border-slate-800/80 flex items-center justify-center group">
        <video
          ref={videoRef}
          className={`w-full h-full object-cover ${isCameraActive ? 'block' : 'hidden'}`}
          playsInline
          muted
        />
        <canvas ref={canvasRef} className="hidden" />

        {/* Camera Off Placeholder */}
        {!isCameraActive && !cameraError && (
          <div className="flex flex-col items-center justify-center p-6 text-center space-y-3">
            <div className="p-4 rounded-full bg-slate-900 border border-slate-800 text-slate-500">
              <CameraOff className="w-10 h-10" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-300">Camera is Offline</p>
              <p className="text-xs text-slate-500 max-w-xs mt-1">
                Click 'Start Camera' above to initiate live webcam anti-spoofing scan.
              </p>
            </div>
            <button
              onClick={startCamera}
              className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs shadow-lg shadow-emerald-500/20 transition"
            >
              Turn On Webcam
            </button>
          </div>
        )}

        {/* Camera Error Display */}
        {cameraError && (
          <div className="flex flex-col items-center justify-center p-6 text-center space-y-3 text-rose-400">
            <AlertCircle className="w-10 h-10" />
            <p className="text-xs max-w-xs">{cameraError}</p>
            <button
              onClick={startCamera}
              className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 font-semibold text-xs border border-rose-500/30"
            >
              Retry Access
            </button>
          </div>
        )}

        {/* Scanning Overlay Animation */}
        {isCameraActive && isAutoScanActive && (
          <div className="absolute inset-0 pointer-events-none border-2 border-emerald-500/40 rounded-2xl overflow-hidden">
            <div className="w-full h-1 bg-gradient-to-r from-transparent via-emerald-400 to-transparent absolute left-0 animate-scan shadow-[0_0_15px_#10b981]" />
            <div className="absolute top-3 left-3 px-2 py-1 rounded bg-black/60 backdrop-blur text-[10px] font-mono text-emerald-400 flex items-center space-x-1 border border-emerald-500/30">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
              <span>LIVE AI SCANNING</span>
            </div>
          </div>
        )}

        {/* Analyzing Overlay Spinner */}
        {isAnalyzing && (
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-10">
            <div className="flex flex-col items-center space-y-2">
              <RefreshCw className="w-8 h-8 text-emerald-400 animate-spin" />
              <span className="text-xs font-semibold text-white tracking-wider uppercase">Processing Models...</span>
            </div>
          </div>
        )}
      </div>

      {/* Footer Capture Action */}
      {isCameraActive && (
        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            {isAutoScanActive ? 'Auto-evaluating live frames...' : 'Position face inside camera frame'}
          </span>
          <button
            onClick={handleSingleCapture}
            disabled={isAnalyzing}
            className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold text-xs shadow-lg shadow-emerald-500/25 transition disabled:opacity-50"
          >
            <Scan className="w-4 h-4" />
            <span>Capture & Analyze</span>
          </button>
        </div>
      )}
    </div>
  );
};
