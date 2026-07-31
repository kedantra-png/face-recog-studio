'use client';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB

export interface UploadQueueItem {
  id: string;
  jobId: string;
  file: File;
  relativePath: string;
  size: number;
  sha256?: string;
  totalChunks: number;
  uploadedChunks: number;
  progress: number; // 0 to 100
  speedBytesPerSec: number;
  status: 'queued' | 'uploading' | 'paused' | 'embedding_processing' | 'completed' | 'failed' | 'cancelled';
  detectedFaces?: number;
  qualityScore?: number;
  driveUrl?: string;
  error?: string;
}

export class ResumableUploader {
  private queue: UploadQueueItem[] = [];
  private activeUploads: Map<string, AbortController> = new Map();
  private concurrency: number = 4; // Adaptive concurrency (1 to 8)
  private onStateChangeCallback?: (queue: UploadQueueItem[]) => void;

  constructor(onStateChange?: (queue: UploadQueueItem[]) => void) {
    this.onStateChangeCallback = onStateChange;
  }

  public static async computeSHA256(file: File): Promise<string> {
    const buffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  public async addFiles(files: File[], jobId: string) {
    const newItems: UploadQueueItem[] = [];

    for (const file of files) {
      const relativePath = (file as any).webkitRelativePath || file.name;
      const totalChunks = Math.ceil(file.size / CHUNK_SIZE) || 1;
      let sha256 = '';

      try {
        sha256 = await ResumableUploader.computeSHA256(file);
      } catch (e) {
        console.warn('Failed to compute client-side SHA256 hash:', e);
      }

      // Client-side SHA-256 Duplicate Check against active queue
      if (
        sha256 &&
        this.queue.some(
          (item) => item.sha256 === sha256 && item.status !== 'cancelled' && item.status !== 'failed'
        )
      ) {
        console.log(`[SHA256 Duplicate Skipped]: ${file.name} (${sha256})`);
        continue;
      }

      newItems.push({
        id: `file_${Math.random().toString(36).substring(2, 10)}`,
        jobId,
        file,
        relativePath,
        size: file.size,
        sha256,
        totalChunks,
        uploadedChunks: 0,
        progress: 0,
        speedBytesPerSec: 0,
        status: 'queued',
      });
    }

    if (newItems.length === 0) return;

    this.queue = [...this.queue, ...newItems];
    this.notify();
    this.processQueue();
  }


  public async uploadZip(file: File, jobId: string): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('job_id', jobId);

    const res = await fetch(`${API_BASE_URL}/api/v2/upload/zip`, {
      method: 'POST',
      body: formData,
    });
    return await res.json();
  }

  public pause(id: string) {
    const item = this.queue.find((i) => i.id === id);
    if (item && item.status === 'uploading') {
      item.status = 'paused';
      const controller = this.activeUploads.get(id);
      if (controller) {
        controller.abort();
        this.activeUploads.delete(id);
      }
      this.notify();
    }
  }

  public resume(id: string) {
    const item = this.queue.find((i) => i.id === id);
    if (item && item.status === 'paused') {
      item.status = 'queued';
      this.notify();
      this.processQueue();
    }
  }

  public cancel(id: string) {
    const item = this.queue.find((i) => i.id === id);
    if (item) {
      item.status = 'cancelled';
      const controller = this.activeUploads.get(id);
      if (controller) {
        controller.abort();
        this.activeUploads.delete(id);
      }
      this.notify();
    }
  }

  public retry(id: string) {
    const item = this.queue.find((i) => i.id === id);
    if (item && item.status === 'failed') {
      item.status = 'queued';
      item.uploadedChunks = 0;
      item.progress = 0;
      item.error = undefined;
      this.notify();
      this.processQueue();
    }
  }

  private async processQueue() {
    const currentlyUploading = Array.from(this.activeUploads.keys()).length;
    if (currentlyUploading >= this.concurrency) return;

    const nextItem = this.queue.find((i) => i.status === 'queued');
    if (!nextItem) return;

    nextItem.status = 'uploading';
    this.notify();

    const controller = new AbortController();
    this.activeUploads.set(nextItem.id, controller);

    try {
      await this.uploadItemChunks(nextItem, controller.signal);
      nextItem.status = 'embedding_processing';
      nextItem.progress = 100;
      this.notify();
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        nextItem.status = 'failed';
        nextItem.error = err.message || 'Upload failed';
        this.notify();
      }
    } finally {
      this.activeUploads.delete(nextItem.id);
      this.processQueue();
    }
  }

  private async uploadItemChunks(item: UploadQueueItem, signal: AbortSignal) {
    const startTime = Date.now();
    let uploadedBytesTotal = item.uploadedChunks * CHUNK_SIZE;

    for (let index = item.uploadedChunks; index < item.totalChunks; index++) {
      if (signal.aborted) throw new Error('AbortError');

      const start = index * CHUNK_SIZE;
      const end = Math.min(item.size, start + CHUNK_SIZE);
      const chunkBlob = item.file.slice(start, end);

      const formData = new FormData();
      formData.append('job_id', item.jobId);
      formData.append('file_id', item.id);
      formData.append('chunk_index', index.toString());
      formData.append('total_chunks', item.totalChunks.toString());
      formData.append('relative_path', item.relativePath);
      formData.append('chunk', chunkBlob, item.file.name);

      const chunkStartTime = Date.now();
      const res = await fetch(`${API_BASE_URL}/api/v2/upload/chunk`, {
        method: 'POST',
        body: formData,
        signal,
      });

      if (!res.ok) {
        throw new Error(`Chunk ${index} upload failed with status ${res.status}`);
      }

      const chunkLatency = Date.now() - chunkStartTime;
      this.adaptConcurrency(chunkLatency);

      item.uploadedChunks = index + 1;
      uploadedBytesTotal += chunkBlob.size;
      item.progress = Math.round((item.uploadedChunks / item.totalChunks) * 100);

      const elapsedSec = (Date.now() - startTime) / 1000;
      item.speedBytesPerSec = elapsedSec > 0 ? Math.round(uploadedBytesTotal / elapsedSec) : 0;

      this.notify();
    }
  }

  private adaptConcurrency(latencyMs: number) {
    // Adaptive concurrency tuning (1 to 8 connections)
    if (latencyMs < 200 && this.concurrency < 8) {
      this.concurrency += 1;
    } else if (latencyMs > 1500 && this.concurrency > 1) {
      this.concurrency -= 1;
    }
  }

  private notify() {
    if (this.onStateChangeCallback) {
      this.onStateChangeCallback([...this.queue]);
    }
  }


  public getQueue(): UploadQueueItem[] {
    return [...this.queue];
  }
}
