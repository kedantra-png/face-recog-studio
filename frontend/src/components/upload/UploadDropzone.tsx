'use client';

import React, { useRef, useState } from 'react';
import { UploadCloud, FolderUp, FileArchive, Image as ImageIcon, Sparkles } from 'lucide-react';

interface UploadDropzoneProps {
  onFilesSelected: (files: File[]) => void;
  onZipSelected: (zipFile: File) => void;
}

export const UploadDropzone: React.FC<UploadDropzoneProps> = ({
  onFilesSelected,
  onZipSelected,
}) => {
  const [dragActive, setDragActive] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const zipInputRef = useRef<HTMLInputElement>(null);

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

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedFiles = Array.from(e.dataTransfer.files);
      const zipFile = droppedFiles.find((f) => f.name.endsWith('.zip') || f.type === 'application/zip');

      if (zipFile) {
        onZipSelected(zipFile);
      } else {
        onFilesSelected(droppedFiles);
      }
    }
  };

  return (
    <div className="glass-panel p-6 rounded-3xl border border-slate-800/80 shadow-2xl space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <UploadCloud className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100">Universal Upload Engine</h2>
            <p className="text-xs text-slate-400">
              High-resolution face embedding pipeline (5MB Resumable Chunks)
            </p>
          </div>
        </div>
      </div>

      {/* Main Drag & Drop Box */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative aspect-[21/9] sm:aspect-[24/8] w-full rounded-2xl border-2 border-dashed transition flex flex-col items-center justify-center cursor-pointer p-6 text-center ${
          dragActive
            ? 'border-emerald-400 bg-emerald-500/10 scale-[1.01]'
            : 'border-slate-800 bg-slate-950/60 hover:border-slate-700 hover:bg-slate-900/60'
        }`}
      >
        {/* Hidden inputs */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              const allFiles = Array.from(e.target.files);
              const validExts = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'];
              const filtered = allFiles.filter((file) => {
                const name = file.name.toLowerCase();
                if (name.startsWith('.') || name === 'thumbs.db' || name === 'desktop.ini') return false;
                return validExts.some((ext) => name.endsWith(ext));
              });
              if (filtered.length > 0) {
                onFilesSelected(filtered);
              }
            }
          }}
        />
        <input
          ref={folderInputRef}
          type="file"
          multiple
          //@ts-ignore
          webkitdirectory=""
          directory=""
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              const allFiles = Array.from(e.target.files);
              const validExts = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif'];
              const filtered = allFiles.filter((file) => {
                const name = file.name.toLowerCase();
                if (name.startsWith('.') || name === 'thumbs.db' || name === 'desktop.ini') return false;
                return validExts.some((ext) => name.endsWith(ext));
              });
              if (filtered.length > 0) {
                onFilesSelected(filtered);
              } else {
                alert('No supported image files (.jpg, .jpeg, .png, .webp, .bmp, .tiff) were found in the selected folder.');
              }
            }
          }}
        />
        <input
          ref={zipInputRef}
          type="file"
          accept=".zip,application/zip"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files[0]) {
              onZipSelected(e.target.files[0]);
            }
          }}
        />


        <div className="p-4 rounded-full bg-slate-900 border border-slate-800 text-emerald-400 mb-3 group-hover:scale-110 transition">
          <UploadCloud className="w-8 h-8" />
        </div>
        <h3 className="text-base font-bold text-slate-100">
          Drag & Drop Images, Folders, or ZIP Archives
        </h3>
        <p className="text-xs text-slate-400 mt-1 max-w-md">
          Supports JPG, PNG, WEBP, TIFF, BMP, and ZIP archives. Folder hierarchy will be preserved automatically.
        </p>

        {/* Quick Action Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-2 mt-4" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition"
          >
            <ImageIcon className="w-3.5 h-3.5 text-teal-400" />
            <span>Select Photos</span>
          </button>

          <button
            onClick={() => folderInputRef.current?.click()}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition"
          >
            <FolderUp className="w-3.5 h-3.5 text-indigo-400" />
            <span>Upload Folder</span>
          </button>

          <button
            onClick={() => zipInputRef.current?.click()}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition"
          >
            <FileArchive className="w-3.5 h-3.5 text-amber-400" />
            <span>Upload ZIP Archive</span>
          </button>
        </div>
      </div>
    </div>
  );
};
