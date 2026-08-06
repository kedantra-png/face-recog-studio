'use client';

import React from 'react';
import { RecognitionResult } from '@/types';
import { getApiBaseUrl } from '@/lib/api';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ShieldAlert,
  UserCheck,
  Zap,
  Cpu,
  Database,
  Search,
  Activity,
  Layers,
  RotateCcw,
  Download
} from 'lucide-react';

interface RecognitionDashboardProps {
  result: RecognitionResult;
  onReset: () => void;
}

export const RecognitionDashboard: React.FC<RecognitionDashboardProps> = ({ result, onReset }) => {
  const {
    match_found,
    person_id,
    person_metadata,
    similarity_score,
    overall_confidence,
    anti_spoof_confidence,
    face_quality_score,
    processing_time_ms,
    top_matches = [],
    recognition_status,
    message,
    error,
  } = result;

  const getStatusHeader = () => {
    switch (recognition_status) {
      case 'MATCH_FOUND':
        return {
          title: 'MATCH FOUND',
          bg: 'bg-emerald-950/80 border-emerald-500/50 shadow-emerald-500/20',
          text: 'text-emerald-400',
          badgeBg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
          icon: <CheckCircle2 className="w-8 h-8 text-emerald-400 animate-bounce" />,
          desc: 'High-confidence facial match verified in Qdrant vector database.',
        };
      case 'SPOOF_DETECTED':
        return {
          title: 'SPOOF ATTACK REJECTED',
          bg: 'bg-rose-950/80 border-rose-500/50 shadow-rose-500/20',
          text: 'text-rose-400',
          badgeBg: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
          icon: <ShieldAlert className="w-8 h-8 text-rose-400" />,
          desc: 'Direct Landmark Liveness engine detected a 2D presentation attack attempt.',
        };
      case 'POOR_QUALITY':
        return {
          title: 'POOR FRAME QUALITY',
          bg: 'bg-amber-950/80 border-amber-500/50 shadow-amber-500/20',
          text: 'text-amber-400',
          badgeBg: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
          icon: <AlertTriangle className="w-8 h-8 text-amber-400" />,
          desc: message || 'Frame quality is blurry or lighting is insufficient. Please adjust camera position.',
        };
      case 'CHALLENGE_REQUIRED':
        return {
          title: 'ACTIVE LIVENESS CHALLENGE REQUIRED',
          bg: 'bg-amber-950/80 border-amber-500/50 shadow-amber-500/20',
          text: 'text-amber-400',
          badgeBg: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
          icon: <AlertTriangle className="w-8 h-8 text-amber-400 animate-pulse" />,
          desc: message || 'Liveness ambiguous. Please complete active challenge (eye blink or head turn).',
        };
      case 'NO_MATCH':
      default:
        return {
          title: 'NO MATCH FOUND',
          bg: 'bg-slate-900/90 border-slate-700 shadow-slate-900/50',
          text: 'text-slate-300',
          badgeBg: 'bg-slate-800 border-slate-700 text-slate-300',
          icon: <XCircle className="w-8 h-8 text-slate-400" />,
          desc: 'No face candidate matched the 42% similarity threshold in Qdrant database.',
        };
    }
  };

  const statusInfo = getStatusHeader();

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6">
      {/* Hero Result Banner */}
      <div className={`w-full p-6 rounded-3xl border shadow-2xl backdrop-blur-xl ${statusInfo.bg} flex flex-col md:flex-row items-center justify-between gap-6`}>
        <div className="flex items-center space-x-4">
          <div className="p-3 rounded-2xl bg-black/30 border border-white/10">{statusInfo.icon}</div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className={`text-xl font-bold tracking-wide ${statusInfo.text}`}>{statusInfo.title}</h2>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${statusInfo.badgeBg}`}>
                {recognition_status}
              </span>
            </div>
            <p className="text-sm text-slate-300 mt-1 max-w-xl">{statusInfo.desc}</p>
          </div>
        </div>

        <button
          onClick={onReset}
          className="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium text-sm transition-all border border-slate-600 shadow-lg flex items-center space-x-2 whitespace-nowrap"
        >
          <RotateCcw className="w-4 h-4" />
          <span>New Recognition Scan</span>
        </button>
      </div>

      {/* Detected Face & Matched Profile Cards Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Detected Face Image Card */}
        <div className="md:col-span-1 bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl flex flex-col items-center text-center space-y-4">
          <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center space-x-1">
            <UserCheck className="w-4 h-4" />
            <span>Detected Face Image</span>
          </span>
          <div className="relative w-32 h-32 rounded-2xl overflow-hidden border-2 border-cyan-500/50 shadow-cyan-500/20 shadow-lg bg-slate-950 flex items-center justify-center">
            {result.detected_face_b64 ? (
              <img
                src={result.detected_face_b64}
                alt="Detected Face"
                className="w-full h-full object-cover"
              />
            ) : (
              <UserCheck className="w-12 h-12 text-slate-500" />
            )}
          </div>
          <p className="text-xs text-slate-400">Aligned 112x112 Crop</p>
        </div>

        {/* Matched Person Profile Card */}
        {match_found && person_metadata ? (
          <div className="md:col-span-2 bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl flex flex-col sm:flex-row items-center justify-between gap-6">
            <div className="flex items-center space-x-4">
              <div className="relative w-28 h-28 rounded-2xl overflow-hidden border-2 border-emerald-500/50 shadow-emerald-500/20 shadow-lg bg-slate-950 flex items-center justify-center flex-shrink-0">
                {person_metadata.thumbnail_url ? (
                  <img
                    src={person_metadata.thumbnail_url}
                    alt={person_metadata.person_name || 'Matched Person'}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      const imgEl = e.currentTarget;
                      const rawSrc = imgEl.src;
                      if (!rawSrc.includes('/temp_uploads/') && person_metadata.person_name) {
                        const baseUrl = rawSrc.split('/api/')[0];
                        imgEl.src = `${baseUrl}/temp_uploads/${person_metadata.person_name}`;
                      }
                    }}
                  />
                ) : (
                  <UserCheck className="w-12 h-12 text-emerald-400" />
                )}
                <div className="absolute bottom-1 right-1 p-1 rounded-full bg-emerald-500 text-black">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                </div>
              </div>

              <div>
                <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">Database Match</span>
                <h3 className="text-xl font-bold text-slate-100">{person_metadata.person_name || person_id}</h3>
                <p className="text-xs font-mono text-emerald-400 mt-0.5">ID: {person_id || 'N/A'}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className="px-2.5 py-0.5 rounded-md text-[11px] bg-slate-800 text-slate-300 border border-slate-700">
                    {person_metadata.role || 'Verified Subject'}
                  </span>
                  <span className="px-2.5 py-0.5 rounded-md text-[11px] bg-slate-800 text-slate-300 border border-slate-700">
                    {person_metadata.department || 'Security Division'}
                  </span>
                  {person_id && (
                    <a
                      href={`${getApiBaseUrl()}/api/v2/images/${encodeURIComponent(person_id)}/download`}
                      download
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-0.5 rounded-md text-[11px] font-semibold bg-emerald-500 hover:bg-emerald-400 text-slate-950 flex items-center space-x-1 transition-all shadow-md shadow-emerald-500/20"
                    >
                      <Download className="w-3 h-3" />
                      <span>Download</span>
                    </a>
                  )}
                </div>
              </div>
            </div>

            <div className="flex flex-col items-center sm:items-end justify-center p-4 bg-slate-950/60 rounded-2xl border border-slate-800/80">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Confidence Score</span>
              <span className="text-3xl font-extrabold text-emerald-400">{overall_confidence}%</span>
              <span className="text-xs text-slate-400 mt-0.5">Cosine Sim: {Math.round(similarity_score * 100)}%</span>
            </div>
          </div>
        ) : (
          <div className="md:col-span-2 bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl flex items-center justify-center text-center">
            <div className="space-y-2">
              <XCircle className="w-10 h-10 text-slate-500 mx-auto" />
              <h4 className="text-sm font-semibold text-slate-300">No Person Profile Matched</h4>
              <p className="text-xs text-slate-400 max-w-sm">The detected face embedding was searched against Qdrant, but no enrolled person matched above the similarity threshold.</p>
            </div>
          </div>
        )}
      </div>

      {/* Metric Gauges Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Similarity Score */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Cosine Similarity</span>
            <Search className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="my-2">
            <span className="text-3xl font-extrabold text-cyan-400">{Math.round(similarity_score * 100)}%</span>
            <span className="text-xs text-slate-400 ml-1.5">(Threshold: 55%)</span>

          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-cyan-400 transition-all duration-500"
              style={{ width: `${Math.round(similarity_score * 100)}%` }}
            />
          </div>
        </div>

        {/* Overall Confidence */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Overall Confidence</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="my-2">
            <span className="text-3xl font-extrabold text-emerald-400">{overall_confidence}%</span>
            <span className="text-xs text-slate-400 ml-1.5">Re-ranked</span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-400 transition-all duration-500"
              style={{ width: `${overall_confidence}%` }}
            />
          </div>
        </div>

        {/* Anti-Spoof Confidence & Spoof Score */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Anti-Spoof Evaluation</span>
            <Zap className="w-4 h-4 text-purple-400" />
          </div>
          <div className="my-2 flex items-baseline justify-between">
            <div>
              <span className="text-2xl font-bold text-emerald-400">
                {anti_spoof_confidence !== undefined ? Math.round(anti_spoof_confidence * 100) : 95}%
              </span>
              <span className="text-xs text-emerald-400 font-semibold ml-1.5">REAL</span>
            </div>
            <div className="text-right">
              <span className={`text-xl font-bold ${result.spoof_confidence && result.spoof_confidence > 0.49 ? 'text-rose-500 font-extrabold' : 'text-rose-400/80'}`}>
                {result.spoof_confidence !== undefined ? Math.round(result.spoof_confidence * 100) : Math.max(0, 100 - Math.round((anti_spoof_confidence || 0.95) * 100))}%
              </span>
              <span className={`text-xs font-semibold ml-1.5 ${result.spoof_confidence && result.spoof_confidence > 0.49 ? 'text-rose-500' : 'text-rose-400/80'}`}>SPOOF</span>
            </div>
          </div>
          <div className="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden flex">
            <div
              className="h-full bg-emerald-400 transition-all duration-500"
              style={{ width: `${anti_spoof_confidence !== undefined ? Math.round(anti_spoof_confidence * 100) : 95}%` }}
              title={`Real Score: ${anti_spoof_confidence !== undefined ? Math.round(anti_spoof_confidence * 100) : 95}%`}
            />
            <div
              className="h-full bg-rose-500 transition-all duration-500"
              style={{ width: `${result.spoof_confidence !== undefined ? Math.round(result.spoof_confidence * 100) : Math.max(0, 100 - Math.round((anti_spoof_confidence || 0.95) * 100))}%` }}
              title={`Spoof Score: ${result.spoof_confidence !== undefined ? Math.round(result.spoof_confidence * 100) : Math.max(0, 100 - Math.round((anti_spoof_confidence || 0.95) * 100))}%`}
            />
          </div>
        </div>

        {/* Face Quality Score */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Quality Score</span>
            <Layers className="w-4 h-4 text-amber-400" />
          </div>
          <div className="my-2">
            <span className="text-2xl font-bold text-amber-400">
              {face_quality_score ? Math.round(face_quality_score * 100) : 85}%
            </span>
            <span className="text-xs text-slate-400 ml-1.5">Usable</span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-amber-400 transition-all duration-500"
              style={{ width: `${face_quality_score ? Math.round(face_quality_score * 100) : 85}%` }}
            />
          </div>
        </div>
      </div>

      {/* Latency Breakdown Table */}
      {processing_time_ms && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <span>Pipeline Latency Performance Breakdown</span>
            </h3>
            <span className="text-xs font-mono text-cyan-400 font-bold bg-cyan-500/10 border border-cyan-500/30 px-3 py-1 rounded-full">
              Total: {processing_time_ms.total_ms} ms
            </span>
          </div>

          <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-center">
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Security</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.security_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Quality</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.quality_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Anti-Spoof</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.anti_spoof_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Alignment</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.alignment_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Embedding</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.embedding_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Qdrant Search</span>
              <p className="text-sm font-bold text-cyan-400 mt-1">{processing_time_ms.qdrant_search_ms} ms</p>
            </div>
          </div>
        </div>
      )}

      {/* Top Vector Match Candidates Table */}
      {top_matches.length > 0 && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
          <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center space-x-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>Top Vector Candidates (Qdrant Nearest Neighbors)</span>
          </h3>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="text-[11px] uppercase bg-slate-950 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3">Rank</th>
                  <th className="p-3">Candidate Face</th>
                  <th className="p-3">Person / Vector ID</th>
                  <th className="p-3">Cosine Similarity</th>
                  <th className="p-3">Re-Ranked Score</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {top_matches.map((match, idx) => (
                  <tr key={match.image_id || idx} className="hover:bg-slate-800/40 transition-colors">
                    <td className="p-3 font-bold text-slate-400">#{idx + 1}</td>
                    <td className="p-3">
                      <div className="w-10 h-10 rounded-lg overflow-hidden border border-slate-700 bg-slate-950 flex items-center justify-center flex-shrink-0">
                        {(match.thumbnail_url || (match as any).face_thumbnail || (match as any).drive_url) ? (
                          <img
                            src={match.thumbnail_url || (match as any).face_thumbnail || (match as any).drive_url}
                            alt={match.person_name || 'Candidate'}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <UserCheck className="w-5 h-5 text-slate-500" />
                        )}

                      </div>
                    </td>
                    <td className="p-3 font-mono font-medium text-slate-100">{match.person_name || match.person_id}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold">
                        {Math.round(match.similarity_score * 100)}%
                      </span>
                    </td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">
                        {Math.round(match.re_ranked_confidence * 100)}%
                      </span>
                    </td>
                    <td className="p-3">
                      {match.similarity_score >= 0.45 ? (
                        <span className="text-emerald-400 font-semibold flex items-center space-x-1">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Matched</span>
                        </span>
                      ) : (
                        <span className="text-slate-500">Below Threshold</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

        </div>
      )}
    </div>
  );
};
