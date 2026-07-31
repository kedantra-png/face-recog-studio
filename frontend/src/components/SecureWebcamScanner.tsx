'use client';

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Camera, ShieldCheck, Sparkles, AlertCircle, RefreshCw, Eye, Sun, Zap, CheckCircle2, Lock } from 'lucide-react';
import { FrameQualityMetrics, CandidateFrame } from '@/types';

interface SecureWebcamScannerProps {
  onAutoCaptureFrames: (frames: CandidateFrame[]) => void;
  isProcessing: boolean;
  stageMessage?: string;
  onReset?: () => void;
}

export const SecureWebcamScanner: React.FC<SecureWebcamScannerProps> = ({
  onAutoCaptureFrames,
  isProcessing,
  stageMessage,
  onReset,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const [stream, setStream] = useState<MediaStream | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [qualityMetrics, setQualityMetrics] = useState<FrameQualityMetrics>({
    blur_score: 0,
    brightness: 0,
    contrast: 0,
    face_size_ratio: 0,
    motion_stability: 0,
    overall_score: 0,
    usable: false,
    guidance_message: 'Position face inside the oval target',
  });

  const [candidateFrames, setCandidateFrames] = useState<CandidateFrame[]>([]);
  const [stableFrameCount, setStableFrameCount] = useState<number>(0);
  const [autoCaptured, setAutoCaptured] = useState<boolean>(false);

  const lastFrameDataRef = useRef<Uint8ClampedArray | null>(null);
  const hasFiredRef = useRef<boolean>(false);


  // Initialize camera
  const startCamera = useCallback(async () => {
    try {
      setCameraError(null);
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user',
        },
        audio: false,
      });
      setStream(mediaStream);
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }
    } catch (err: any) {
      console.error('Camera permission denied or camera unavailable:', err);
      setCameraError(err.message || 'Camera permission denied. Please allow camera access in browser settings.');
    }
  }, []);

  useEffect(() => {
    startCamera();
    return () => {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  // Client-side image quality & stability analyzer loop
  useEffect(() => {
    let animationFrameId: number;

    const analyzeFrame = () => {
      if (videoRef.current && canvasRef.current && videoRef.current.readyState === 4 && !autoCaptured && !isProcessing) {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');

        if (ctx) {
          canvas.width = video.videoWidth || 640;
          canvas.height = video.videoHeight || 480;
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const data = imageData.data;
          const len = data.length;

          // 1. Calculate Mean Brightness & Contrast
          let sumBrightness = 0;
          for (let i = 0; i < len; i += 16) {
            // step sampling for performance
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            sumBrightness += (r + g + b) / 3.0;
          }
          const samplesCount = len / 16;
          const brightness = sumBrightness / samplesCount;

          let sumSquareDiff = 0;
          for (let i = 0; i < len; i += 16) {
            const gray = (data[i] + data[i + 1] + data[i + 2]) / 3.0;
            sumSquareDiff += Math.pow(gray - brightness, 2);
          }
          const contrast = Math.sqrt(sumSquareDiff / samplesCount);

          // 2. Estimate Blur via Discrete Laplacian Variance approximation on center crop
          const cx = Math.floor(canvas.width / 4);
          const cy = Math.floor(canvas.height / 4);
          const cw = Math.floor(canvas.width / 2);
          const ch = Math.floor(canvas.height / 2);
          const centerData = ctx.getImageData(cx, cy, cw, ch).data;

          let laplacianSum = 0;
          const stride = cw * 4;
          for (let y = 1; y < ch - 1; y += 2) {
            for (let x = 1; x < cw - 1; x += 2) {
              const idx = (y * cw + x) * 4;
              const center = centerData[idx];
              const top = centerData[idx - stride];
              const bottom = centerData[idx + stride];
              const left = centerData[idx - 4];
              const right = centerData[idx + 4];
              const lap = Math.abs(4 * center - top - bottom - left - right);
              laplacianSum += lap;
            }
          }
          const blurScore = Math.min(100, (laplacianSum / ((cw * ch) / 4)) * 3.5);

          // 3. Motion Stability check comparing against last frame
          let motionDiff = 0;
          if (lastFrameDataRef.current && lastFrameDataRef.current.length === centerData.length) {
            let diffSum = 0;
            for (let i = 0; i < centerData.length; i += 32) {
              diffSum += Math.abs(centerData[i] - lastFrameDataRef.current[i]);
            }
            motionDiff = diffSum / (centerData.length / 32);
          }
          lastFrameDataRef.current = new Uint8ClampedArray(centerData);
          const motionStability = Math.max(0, Math.min(100, 100 - motionDiff * 8.0));

          // 4. Evaluate usability & guidance message
          let usable = true;
          let message = 'Hold still — Auto capturing best frames';

          if (brightness < 35) {
            usable = false;
            message = 'Lighting too dark — Move to a brighter area';
          } else if (brightness > 220) {
            usable = false;
            message = 'Lighting overexposed — Avoid direct glare';
          } else if (blurScore < 15) {
            usable = false;
            message = 'Image blurry — Please hold camera steady';
          } else if (motionStability < 40) {
            usable = false;
            message = 'Motion detected — Keep head completely still';
          }

          const overallScore = Math.round(
            0.4 * blurScore + 0.3 * motionStability + 0.15 * Math.min(100, contrast * 1.5) + 0.15 * Math.min(100, (1 - Math.abs(brightness - 128) / 128) * 100)
          );

          setQualityMetrics({
            blur_score: Math.round(blurScore),
            brightness: Math.round(brightness),
            contrast: Math.round(contrast),
            face_size_ratio: 35,
            motion_stability: Math.round(motionStability),
            overall_score: overallScore,
            usable,
            guidance_message: message,
          });

          // Accumulate candidate frames if usable
          if (usable) {
            setStableFrameCount((prev) => {
              const nextCount = prev + 1;
              const b64 = canvas.toDataURL('image/jpeg', 0.90);
              const frameObj: CandidateFrame = {
                frame_b64: b64,
                quality_score: overallScore,
                blur_score: Math.round(blurScore),
              };

              setCandidateFrames((prevFrames) => {
                const updated = [...prevFrames, frameObj];
                // Once 12 candidate frames collected over stable window -> select top 3 best frames
                if (updated.length >= 10 && !autoCaptured && !hasFiredRef.current) {
                  hasFiredRef.current = true;
                  setAutoCaptured(true);
                  const sorted = [...updated].sort((a, b) => b.quality_score - a.quality_score);
                  const best3 = sorted.slice(0, 3);
                  setTimeout(() => {
                    onAutoCaptureFrames(best3);
                  }, 50);
                }
                return updated;
              });


              return nextCount;
            });
          } else {
            setStableFrameCount(0);
          }
        }
      }

      animationFrameId = requestAnimationFrame(analyzeFrame);
    };

    animationFrameId = requestAnimationFrame(analyzeFrame);
    return () => cancelAnimationFrame(animationFrameId);
  }, [autoCaptured, isProcessing, onAutoCaptureFrames]);

  const handleResetScanner = () => {
    hasFiredRef.current = false;
    setAutoCaptured(false);
    setCandidateFrames([]);
    setStableFrameCount(0);
    lastFrameDataRef.current = null;
    if (onReset) onReset();
  };


  const getBorderColor = () => {
    if (isProcessing) return 'border-cyan-400 shadow-cyan-500/50';
    if (autoCaptured) return 'border-emerald-400 shadow-emerald-500/50';
    if (qualityMetrics.usable) return 'border-emerald-500 shadow-emerald-500/40';
    return 'border-amber-500/70 shadow-amber-500/20';
  };

  return (
    <div className="w-full flex flex-col items-center justify-center space-y-6">
      {/* Scanner Header Security Badge */}
      <div className="flex items-center space-x-3 px-4 py-1.5 rounded-full bg-slate-900/80 border border-slate-700/60 shadow-lg">
        <ShieldCheck className="w-4 h-4 text-emerald-400 animate-pulse" />
        <span className="text-xs font-medium text-slate-300">Enterprise Secure Webcam Gateway</span>
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          Auto Capture Enabled
        </span>
      </div>

      {/* Camera Viewport & Oval Guide Overlay */}
      <div className="relative w-full max-w-xl aspect-[4/3] rounded-3xl overflow-hidden bg-slate-950 border border-slate-800 shadow-2xl flex items-center justify-center">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={`w-full h-full object-cover transform -scale-x-100 transition-opacity duration-300 ${
            stream ? 'opacity-100' : 'opacity-0'
          }`}
        />
        <canvas ref={canvasRef} className="hidden" />

        {/* Camera Permission or Hardware Error */}
        {cameraError && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-slate-950/95 p-6 text-center space-y-4">
            <AlertCircle className="w-12 h-12 text-rose-400 animate-bounce" />
            <h3 className="text-lg font-semibold text-white">Camera Access Error</h3>
            <p className="text-sm text-slate-400 max-w-md">{cameraError}</p>
            <button
              onClick={startCamera}
              className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm transition-all shadow-lg flex items-center space-x-2"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Retry Camera Permission</span>
            </button>
          </div>
        )}

        {/* Dynamic Oval Target Face Guide */}
        {stream && !cameraError && (
          <div className="absolute inset-0 pointer-events-none flex flex-col items-center justify-center">
            {/* Outer Oval Target Box */}
            <div
              className={`w-56 h-72 rounded-[50%] border-4 ${getBorderColor()} shadow-2xl transition-all duration-300 relative flex items-center justify-center`}
            >
              {/* Corner Crosshairs */}
              <div className="absolute top-2 left-1/2 -translate-x-1/2 w-4 h-1 bg-white/40 rounded-full" />
              <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-4 h-1 bg-white/40 rounded-full" />
              <div className="absolute left-2 top-1/2 -translate-y-1/2 w-1 h-4 bg-white/40 rounded-full" />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 w-1 h-4 bg-white/40 rounded-full" />

              {/* Laser Scanning Animation when processing */}
              {isProcessing && (
                <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_15px_#22d3ee] animate-[scan_2s_infinite_linear]" />
              )}
            </div>

            {/* Live Position & Guidance Status Pill */}
            <div className="absolute bottom-6 px-5 py-2 rounded-2xl bg-slate-900/90 backdrop-blur-md border border-slate-700/80 shadow-xl flex items-center space-x-2.5 text-xs font-medium text-slate-200">
              {isProcessing ? (
                <>
                  <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />
                  <span className="text-cyan-300">{stageMessage || 'Analyzing top 3 candidate frames...'}</span>
                </>
              ) : autoCaptured ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="text-emerald-300">Frames Captured! Verifying Recognition...</span>
                </>
              ) : qualityMetrics.usable ? (
                <>
                  <Sparkles className="w-4 h-4 text-emerald-400 animate-pulse" />
                  <span className="text-emerald-300">Hold Still ({candidateFrames.length}/12 frames)</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4 text-amber-400" />
                  <span className="text-amber-300">{qualityMetrics.guidance_message}</span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Security Watermark */}
        <div className="absolute top-4 left-4 z-20 flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-black/60 backdrop-blur-md text-[11px] font-mono text-slate-300 border border-white/10">
          <Lock className="w-3 h-3 text-emerald-400" />
          <span>NO_UPLOAD_RESTRICTED</span>
        </div>
      </div>

      {/* Real-time Quality Telemetry Bar */}
      <div className="w-full max-w-xl bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-xl grid grid-cols-4 gap-3 text-center">
        <div className="flex flex-col items-center space-y-1">
          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center space-x-1">
            <Eye className="w-3 h-3 text-cyan-400" />
            <span>Blur Score</span>
          </span>
          <span className="text-sm font-semibold text-slate-100">{qualityMetrics.blur_score}</span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                qualityMetrics.blur_score > 30 ? 'bg-emerald-500' : 'bg-amber-500'
              }`}
              style={{ width: `${Math.min(100, qualityMetrics.blur_score)}%` }}
            />
          </div>
        </div>

        <div className="flex flex-col items-center space-y-1">
          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center space-x-1">
            <Sun className="w-3 h-3 text-amber-400" />
            <span>Brightness</span>
          </span>
          <span className="text-sm font-semibold text-slate-100">{qualityMetrics.brightness}</span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="h-full bg-amber-500 transition-all duration-300"
              style={{ width: `${Math.min(100, (qualityMetrics.brightness / 255) * 100)}%` }}
            />
          </div>
        </div>

        <div className="flex flex-col items-center space-y-1">
          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center space-x-1">
            <Zap className="w-3 h-3 text-purple-400" />
            <span>Stability</span>
          </span>
          <span className="text-sm font-semibold text-slate-100">{qualityMetrics.motion_stability}%</span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="h-full bg-purple-500 transition-all duration-300"
              style={{ width: `${qualityMetrics.motion_stability}%` }}
            />
          </div>
        </div>

        <div className="flex flex-col items-center space-y-1">
          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center space-x-1">
            <Sparkles className="w-3 h-3 text-emerald-400" />
            <span>Quality Score</span>
          </span>
          <span className="text-sm font-semibold text-emerald-400">{qualityMetrics.overall_score}%</span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all duration-300"
              style={{ width: `${qualityMetrics.overall_score}%` }}
            />
          </div>
        </div>
      </div>

      {/* Manual Reset Button if Auto-Captured */}
      {autoCaptured && !isProcessing && (
        <button
          onClick={handleResetScanner}
          className="px-6 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium transition-all shadow-md flex items-center space-x-2 border border-slate-700"
        >
          <RefreshCw className="w-4 h-4" />
          <span>Reset Scanner for Next Face</span>
        </button>
      )}
    </div>
  );
};
