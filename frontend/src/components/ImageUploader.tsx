'use client';

import React, { useState, useRef } from 'react';
import { UploadCloud, Image as ImageIcon, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';

interface ImageUploaderProps {
  onUploadFile: (file: File) => Promise<void>;
  isAnalyzing: boolean;
}

export const ImageUploader: React.FC<ImageUploaderProps> = ({
  onUploadFile,
  isAnalyzing,
}) => {
  const [dragActive, setDragActive] = useState<boolean>(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (file: File) => {
    if (!file.type.startsWith('image/')) {
      alert('Please upload a valid image file (JPG, PNG, WEBP).');
      return;
    }
    setSelectedFile(file);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    onUploadFile(file);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="glass-panel p-5 rounded-3xl border border-slate-800/80 shadow-2xl relative overflow-hidden flex flex-col justify-between h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <UploadCloud className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100">Upload Image File</h2>
            <p className="text-xs text-slate-400">Evaluate anti-spoofing on single photos</p>
          </div>
        </div>
      </div>

      {/* Drag and Drop Container */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative aspect-[4/3] w-full rounded-2xl overflow-hidden border-2 border-dashed transition flex flex-col items-center justify-center cursor-pointer p-4 ${
          dragActive
            ? 'border-cyan-400 bg-cyan-500/10'
            : 'border-slate-800 bg-slate-950/60 hover:border-slate-700 hover:bg-slate-900/60'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files[0]) {
              handleFileChange(e.target.files[0]);
            }
          }}
        />

        {previewUrl ? (
          <div className="relative w-full h-full rounded-xl overflow-hidden group">
            <img
              src={previewUrl}
              alt="Uploaded Preview"
              className="w-full h-full object-contain bg-slate-950"
            />
            <div className="absolute inset-0 bg-slate-950/40 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
              <span className="px-3 py-1.5 rounded-lg bg-black/70 text-xs font-semibold text-white backdrop-blur border border-white/10">
                Click to change image
              </span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center space-y-3 text-center">
            <div className="p-4 rounded-full bg-slate-900 border border-slate-800 text-cyan-400 group-hover:scale-110 transition">
              <UploadCloud className="w-8 h-8" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-200">
                Drag & Drop face image here
              </p>
              <p className="text-xs text-slate-500 mt-1">
                Supports JPG, PNG, WEBP formats (Max 10MB)
              </p>
            </div>
            <span className="px-3 py-1.5 rounded-lg bg-slate-800 text-xs font-medium text-slate-300 border border-slate-700">
              Browse Files
            </span>
          </div>
        )}

        {/* Loading Spinner */}
        {isAnalyzing && (
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-10">
            <div className="flex flex-col items-center space-y-2">
              <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin" />
              <span className="text-xs font-semibold text-white tracking-wider uppercase">Running Model Inference...</span>
            </div>
          </div>
        )}
      </div>

      {/* Selected File Details */}
      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-slate-400 truncate max-w-[200px]">
          {selectedFile ? selectedFile.name : 'No image uploaded yet'}
        </span>
        {selectedFile && (
          <button
            onClick={() => handleFileChange(selectedFile)}
            disabled={isAnalyzing}
            className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs shadow-lg shadow-cyan-500/20 transition disabled:opacity-50"
          >
            Re-evaluate
          </button>
        )}
      </div>
    </div>
  );
};
