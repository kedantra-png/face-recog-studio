'use client';

import React, { useRef, useEffect, useState, useCallback } from 'react';
import {
  RotateCcw,
  Play,
  Pause,
  Maximize2,
  Sparkles,
  MoveHorizontal,
  Compass,
  SlidersHorizontal,
  ShieldCheck
} from 'lucide-react';

const TOTAL_FRAMES = 56;

// Generate 56 frame image URLs from public/ezgif-split directory
const FRAME_PATHS: string[] = Array.from({ length: TOTAL_FRAMES }, (_, i) => {
  const padIndex = i.toString().padStart(2, '0');
  return `/ezgif-split/frame_${padIndex}_delay-0.2s.webp`;
});

export const DesktopFrameScrubber: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Loaded images cache
  const imagesRef = useRef<HTMLImageElement[]>([]);
  const [imagesLoaded, setImagesLoaded] = useState<boolean>(false);
  const [loadProgress, setLoadProgress] = useState<number>(0);

  // Playback & Interaction States
  const [currentFrame, setCurrentFrame] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [sensitivity, setSensitivity] = useState<number>(12); // px per frame change
  const [isUserInteracting, setIsUserInteracting] = useState<boolean>(false);

  const startXRef = useRef<number>(0);
  const startFrameRef = useRef<number>(0);
  const animationFrameIdRef = useRef<number | null>(null);
  const idleTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastTimeRef = useRef<number>(0);

  // Pre-load all 56 WebP frame images into memory
  useEffect(() => {
    let isMounted = true;
    let loadedCount = 0;
    const loadedImages: HTMLImageElement[] = [];

    FRAME_PATHS.forEach((path, index) => {
      const img = new Image();
      img.src = path;
      img.onload = () => {
        if (!isMounted) return;
        loadedCount += 1;
        loadedImages[index] = img;
        setLoadProgress(Math.round((loadedCount / TOTAL_FRAMES) * 100));

        if (loadedCount === TOTAL_FRAMES) {
          imagesRef.current = loadedImages;
          setImagesLoaded(true);
        }
      };
      img.onerror = () => {
        if (!isMounted) return;
        loadedCount += 1;
        setLoadProgress(Math.round((loadedCount / TOTAL_FRAMES) * 100));
        if (loadedCount === TOTAL_FRAMES) {
          imagesRef.current = loadedImages;
          setImagesLoaded(true);
        }
      };
    });

    return () => {
      isMounted = false;
    };
  }, []);

  // Draw target frame onto HTML5 Canvas
  const drawFrame = useCallback((frameIndex: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const images = imagesRef.current;
    const img = images[frameIndex];
    if (!img || !img.complete || img.naturalWidth === 0) return;

    // Handle High-DPI Canvas Scaling
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    
    if (canvas.width !== rect.width * dpr || canvas.height !== rect.height * dpr) {
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    // Calculate aspect ratio cover / contain fit
    const imgAspect = img.naturalWidth / img.naturalHeight;
    const canvasAspect = rect.width / rect.height;

    let drawW = rect.width;
    let drawH = rect.height;
    let drawX = 0;
    let drawY = 0;

    if (imgAspect > canvasAspect) {
      drawH = rect.width / imgAspect;
      drawY = (rect.height - drawH) / 2;
    } else {
      drawW = rect.height * imgAspect;
      drawX = (rect.width - drawW) / 2;
    }

    ctx.drawImage(img, drawX, drawY, drawW, drawH);
    ctx.restore();
  }, []);

  // Auto-play animation loop (30 FPS)
  useEffect(() => {
    if (!imagesLoaded || !isPlaying || isDragging) return;

    const fps = 24;
    const interval = 1000 / fps;

    const loop = (timestamp: number) => {
      if (!lastTimeRef.current) lastTimeRef.current = timestamp;
      const delta = timestamp - lastTimeRef.current;

      if (delta >= interval) {
        lastTimeRef.current = timestamp - (delta % interval);
        setCurrentFrame((prev) => (prev + 1) % TOTAL_FRAMES);
      }

      animationFrameIdRef.current = requestAnimationFrame(loop);
    };

    animationFrameIdRef.current = requestAnimationFrame(loop);

    return () => {
      if (animationFrameIdRef.current) {
        cancelAnimationFrame(animationFrameIdRef.current);
      }
    };
  }, [imagesLoaded, isPlaying, isDragging]);

  // Redraw canvas whenever currentFrame changes
  useEffect(() => {
    if (imagesLoaded) {
      drawFrame(currentFrame);
    }
  }, [currentFrame, imagesLoaded, drawFrame]);

  // Window resize handler
  useEffect(() => {
    const handleResize = () => {
      if (imagesLoaded) {
        drawFrame(currentFrame);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [imagesLoaded, currentFrame, drawFrame]);

  // Idle auto-resume timer setup
  const resetIdleTimer = useCallback(() => {
    setIsUserInteracting(true);
    setIsPlaying(false);

    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current);
    }

    idleTimerRef.current = setTimeout(() => {
      setIsUserInteracting(false);
      setIsPlaying(true);
    }, 2500); // Resume auto-rotation after 2.5s of inactivity
  }, []);

  // Pointer & Touch Drag Handlers
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
    startXRef.current = e.clientX;
    startFrameRef.current = currentFrame;
    resetIdleTimer();
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    e.preventDefault();

    const deltaX = e.clientX - startXRef.current;
    const frameShift = Math.floor(deltaX / sensitivity);

    let nextFrame = (startFrameRef.current + frameShift) % TOTAL_FRAMES;
    if (nextFrame < 0) nextFrame += TOTAL_FRAMES;

    setCurrentFrame(nextFrame);
    resetIdleTimer();
  };

  const handlePointerUp = () => {
    setIsDragging(false);
  };

  const togglePlayPause = () => {
    setIsPlaying(!isPlaying);
    setIsUserInteracting(true);
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
  };

  const handleReset = () => {
    setCurrentFrame(0);
    setIsPlaying(true);
    setIsUserInteracting(false);
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
  };

  return (
    <div className="w-full max-w-5xl mx-auto flex flex-col items-center">
      {/* Header Badge */}
      <div className="flex items-center space-x-2 px-4 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-4 shadow-sm">
        <Sparkles className="w-3.5 h-3.5 animate-pulse" />
        <span>360° Interactive 3D Video Frame Viewer</span>
      </div>

      {/* Main Glassmorphic Showcase Container */}
      <div
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        className={`relative w-full aspect-[16/9] md:aspect-[21/9] rounded-3xl bg-gradient-to-b from-slate-900/90 via-[#0b1220]/90 to-slate-950/95 border border-slate-800/80 shadow-2xl overflow-hidden select-none touch-none group cursor-grab active:cursor-grabbing backdrop-blur-2xl transition-all duration-300 ${
          isDragging ? 'border-emerald-500/60 shadow-emerald-500/10' : 'hover:border-slate-700'
        }`}
      >
        {/* Loading Overlay State */}
        {!imagesLoaded && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-slate-950/90 backdrop-blur-md p-6 text-center space-y-4">
            <div className="relative flex items-center justify-center w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <Compass className="w-8 h-8 animate-spin" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-100">Loading 3D Frame Sequence</h3>
              <p className="text-xs text-slate-400 mt-1">Pre-caching 56 WebP Desktop Video Frames for 60FPS Drag Scrubbing...</p>
            </div>
            <div className="w-64 bg-slate-800 h-2 rounded-full overflow-hidden border border-slate-700">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-300"
                style={{ width: `${loadProgress}%` }}
              />
            </div>
            <span className="text-xs font-mono font-bold text-emerald-400">{loadProgress}% Loaded</span>
          </div>
        )}

        {/* HTML5 Render Canvas */}
        <canvas
          ref={canvasRef}
          className="w-full h-full object-contain pointer-events-none transition-transform duration-200"
        />

        {/* Interactive Gesture Overlay Hint */}
        {imagesLoaded && (
          <div className={`absolute top-4 left-4 z-20 flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-slate-900/80 border border-slate-700/60 text-slate-300 text-xs font-medium backdrop-blur-md transition-opacity duration-300 ${
            isDragging ? 'opacity-100 border-emerald-500/50 text-emerald-300' : 'opacity-80 group-hover:opacity-100'
          }`}>
            <MoveHorizontal className={`w-4 h-4 text-emerald-400 ${isDragging ? 'animate-bounce' : ''}`} />
            <span>{isDragging ? 'Scrubbing Video Frames...' : '◄ Drag Left / Right to Rotate 360° ►'}</span>
          </div>
        )}

        {/* Idle Auto-Resume Indicator Badge */}
        {imagesLoaded && isPlaying && !isDragging && (
          <div className="absolute top-4 right-4 z-20 flex items-center space-x-2 px-3 py-1.5 rounded-full bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 text-xs font-semibold backdrop-blur-md">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <span>Auto Rotation Active</span>
          </div>
        )}

        {/* Floating Controls Bar */}
        {imagesLoaded && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex items-center space-x-3 px-4 py-2 rounded-2xl bg-slate-950/80 border border-slate-800/90 shadow-2xl backdrop-blur-xl transition-all duration-300 group-hover:border-slate-700">
            {/* Play/Pause Button */}
            <button
              onClick={togglePlayPause}
              className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-200 hover:text-white transition border border-slate-700/60"
              title={isPlaying ? 'Pause Auto Rotation' : 'Play Auto Rotation'}
            >
              {isPlaying ? <Pause className="w-4 h-4 text-amber-400" /> : <Play className="w-4 h-4 text-emerald-400" />}
            </button>

            {/* Reset Button */}
            <button
              onClick={handleReset}
              className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-200 hover:text-white transition border border-slate-700/60"
              title="Reset to Frame 0"
            >
              <RotateCcw className="w-4 h-4 text-slate-300" />
            </button>

            {/* Frame Indicator Pill */}
            <div className="px-3 py-1 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 text-xs font-mono font-semibold flex items-center space-x-1.5">
              <span className="text-slate-400">Frame:</span>
              <span className="text-emerald-400 font-bold">{currentFrame + 1}</span>
              <span className="text-slate-500">/ {TOTAL_FRAMES}</span>
            </div>

            {/* Sensitivity Cycle Button */}
            <button
              onClick={() => setSensitivity((prev) => (prev === 8 ? 16 : prev === 16 ? 24 : 8))}
              className="px-2.5 py-1 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 text-xs font-medium transition border border-slate-700/60 flex items-center space-x-1"
              title="Drag Scrubbing Sensitivity"
            >
              <SlidersHorizontal className="w-3.5 h-3.5 text-teal-400" />
              <span>{sensitivity === 8 ? 'Fast' : sensitivity === 16 ? 'Slow' : 'Normal'}</span>
            </button>
          </div>
        )}
      </div>

      {/* Frame Timeline Thumbnail Scrubber */}
      {imagesLoaded && (
        <div className="w-full mt-4 px-2 flex items-center space-x-3">
          <span className="text-xs font-semibold text-slate-400 tracking-wider uppercase font-mono">Scrub:</span>
          <input
            type="range"
            min={0}
            max={TOTAL_FRAMES - 1}
            value={currentFrame}
            onChange={(e) => {
              setCurrentFrame(parseInt(e.target.value, 10));
              resetIdleTimer();
            }}
            className="w-full accent-emerald-500 bg-slate-800 rounded-lg cursor-pointer h-2 border border-slate-700/50"
          />
          <span className="text-xs font-mono font-bold text-teal-400 w-12 text-right">{Math.round(((currentFrame + 1) / TOTAL_FRAMES) * 100)}%</span>
        </div>
      )}
    </div>
  );
};
