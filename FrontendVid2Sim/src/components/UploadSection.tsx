import { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  UploadCloud,
  FileVideo,
  X,
  ScanLine,
  Circle,
  Square,
  Video,
  VideoOff,
  RotateCcw,
  ArrowRight,
  AlertTriangle,
} from 'lucide-react';
import { StatusRibbon, CornerMark } from './SectionChrome';

interface UploadSectionProps {
  onUploadComplete: () => void;
}

type SourceMode = 'live' | 'upload';
type LiveState = 'init' | 'preview' | 'recording' | 'review' | 'error';

/**
 * Pick the highest-fidelity MediaRecorder mime type the browser actually
 * supports. Falls back to the empty string (browser picks its default).
 */
function pickRecorderMime(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  const candidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm;codecs=vp9',
    'video/webm;codecs=vp8',
    'video/webm',
    'video/mp4',
  ];
  for (const m of candidates) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return '';
}

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  const s = total % 60;
  const m = Math.floor(total / 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function captureFilename(): string {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, '0');
  return (
    `oak4_capture_${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
    `_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}.webm`
  );
}

export default function UploadSection({ onUploadComplete }: UploadSectionProps) {
  const [mode, setMode] = useState<SourceMode>('live');

  // --- upload tab state ---
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // --- live tab state ---
  const [liveState, setLiveState] = useState<LiveState>('init');
  const [mediaErr, setMediaErr] = useState<string | null>(null);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [recordedUrl, setRecordedUrl] = useState<string | null>(null);
  const [recordedName, setRecordedName] = useState<string>('');
  const [elapsed, setElapsed] = useState(0);
  const [devicePath, setDevicePath] = useState<string>('webcam·default');

  const livePreviewRef = useRef<HTMLVideoElement>(null);
  const playbackRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickStartRef = useRef<number>(0);
  const tickRafRef = useRef<number | null>(null);

  // ------------------------------------------------------------------
  // Camera lifecycle: start when mode=='live' and we're not reviewing.
  // ------------------------------------------------------------------
  const stopStream = useCallback(() => {
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) track.stop();
      streamRef.current = null;
    }
  }, []);

  const startCamera = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setLiveState('error');
      setMediaErr(
        'This browser does not expose the MediaDevices API. Use Chrome, Safari, or Firefox latest, served over HTTPS or localhost.',
      );
      return;
    }
    try {
      setLiveState('init');
      setMediaErr(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 30 },
        },
        audio: false,
      });
      streamRef.current = stream;
      const video = livePreviewRef.current;
      if (video) {
        video.srcObject = stream;
        video.muted = true;
        video.playsInline = true;
        await video.play().catch(() => {
          // Autoplay can be blocked; the user's gesture to start recording will resume it.
        });
      }
      const settings = stream.getVideoTracks()[0]?.getSettings();
      if (settings?.width && settings?.height) {
        setDevicePath(`webcam · ${settings.width}×${settings.height}@${Math.round(settings.frameRate ?? 30)}fps`);
      }
      setLiveState('preview');
    } catch (err) {
      console.error('[UploadSection] getUserMedia failed', err);
      setLiveState('error');
      setMediaErr(
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Camera access denied. Grant permission in your browser site settings and reload.'
          : err instanceof DOMException && err.name === 'NotFoundError'
            ? 'No camera detected. Plug in an OAK-4 or any webcam and retry.'
            : `Could not open camera: ${(err as Error).message ?? String(err)}`,
      );
    }
  }, []);

  useEffect(() => {
    if (mode !== 'live') {
      stopStream();
      return;
    }
    if (liveState === 'init' || liveState === 'preview') {
      if (!streamRef.current) {
        void startCamera();
      }
    }
  }, [mode, liveState, startCamera, stopStream]);

  // Cleanup on unmount: stop tracks + recorder + revoke URL.
  useEffect(() => {
    return () => {
      stopStream();
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        try { recorderRef.current.stop(); } catch { /* noop */ }
      }
      if (tickRafRef.current !== null) {
        cancelAnimationFrame(tickRafRef.current);
        tickRafRef.current = null;
      }
      if (recordedUrl) URL.revokeObjectURL(recordedUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------------------------------------------------------
  // Recording controls.
  // ------------------------------------------------------------------
  const tickLoop = useCallback(() => {
    const run = () => {
      setElapsed(Date.now() - tickStartRef.current);
      tickRafRef.current = requestAnimationFrame(run);
    };
    tickRafRef.current = requestAnimationFrame(run);
  }, []);

  const stopTickLoop = useCallback(() => {
    if (tickRafRef.current !== null) {
      cancelAnimationFrame(tickRafRef.current);
      tickRafRef.current = null;
    }
  }, []);

  const startRecording = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) {
      void startCamera();
      return;
    }
    const mime = pickRecorderMime();
    let recorder: MediaRecorder;
    try {
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    } catch (err) {
      console.error('[UploadSection] MediaRecorder construction failed', err);
      setLiveState('error');
      setMediaErr(`Recorder unavailable: ${(err as Error).message ?? String(err)}`);
      return;
    }
    chunksRef.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onerror = (e) => {
      console.error('[UploadSection] MediaRecorder error', e);
    };
    recorder.onstop = () => {
      const type = recorder.mimeType || 'video/webm';
      const blob = new Blob(chunksRef.current, { type });
      chunksRef.current = [];
      const url = URL.createObjectURL(blob);
      if (recordedUrl) URL.revokeObjectURL(recordedUrl);
      setRecordedBlob(blob);
      setRecordedUrl(url);
      setRecordedName(captureFilename());
      setLiveState('review');
      // We keep the live stream alive in case the user wants to re-record
      // immediately — no need to re-prompt for camera permission.
    };
    recorderRef.current = recorder;
    recorder.start(1000);
    tickStartRef.current = Date.now();
    setElapsed(0);
    tickLoop();
    setLiveState('recording');
  }, [recordedUrl, startCamera, tickLoop]);

  const stopRecording = useCallback(() => {
    stopTickLoop();
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
  }, [stopTickLoop]);

  const redoRecording = useCallback(() => {
    if (recordedUrl) URL.revokeObjectURL(recordedUrl);
    setRecordedBlob(null);
    setRecordedUrl(null);
    setRecordedName('');
    setElapsed(0);
    setLiveState('preview');
  }, [recordedUrl]);

  // ------------------------------------------------------------------
  // Commit paths — both tabs reach the same `onUploadComplete()`.
  // ------------------------------------------------------------------
  const commitLive = useCallback(() => {
    if (!recordedBlob) return;
    // Future: POST the blob to a pipeline endpoint. For now the static demo
    // flow hands off to ProcessingScreen → SimulationViewer which loads
    // Stream 03's assembled scene.json.
    stopTickLoop();
    stopStream();
    onUploadComplete();
  }, [onUploadComplete, recordedBlob, stopStream, stopTickLoop]);

  const commitUpload = useCallback(() => {
    if (!file) return;
    onUploadComplete();
  }, [file, onUploadComplete]);

  // ------------------------------------------------------------------
  // Drag & drop handlers (unchanged behavior, kept behind the Upload tab).
  // ------------------------------------------------------------------
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };
  const handlePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setFile(f);
    e.target.value = '';
  };

  const isRecording = liveState === 'recording';
  const isReview = liveState === 'review';

  return (
    <div className="w-full flex-1 flex flex-col items-center justify-center relative px-4 py-16">
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-2xl mb-6"
      >
        <StatusRibbon
          id="SYS·SCAN"
          label={
            mode === 'live'
              ? liveState === 'recording'
                ? 'live capture · recording'
                : liveState === 'review'
                  ? 'live capture · captured buffer ready'
                  : 'live capture · awaiting capture'
              : 'file upload · awaiting input'
          }
          right={
            <>
              <span>{mode === 'live' ? devicePath : 'max·2gb · codec·h264|h265'}</span>
              <span className={isRecording ? 'text-red-400' : 'text-primary'}>●</span>
            </>
          }
        />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="relative w-full max-w-2xl glass-panel p-8 flex flex-col overflow-hidden"
      >
        <CornerMark className="top-3 left-3" rot={0} size={14} />
        <CornerMark className="top-3 right-3" rot={90} size={14} />
        <CornerMark className="bottom-3 right-3" rot={180} size={14} />
        <CornerMark className="bottom-3 left-3" rot={270} size={14} />

        <div className="flex items-baseline gap-3 mb-5">
          <span className="text-xs font-mono text-primary/70">[01]</span>
          <div>
            <h2 className="text-3xl font-bold">Capture Footage</h2>
            <p className="text-textSecondary mt-1">
              Record a live scan from your OAK-4 (or any webcam) — or drop a recorded clip.
            </p>
          </div>
        </div>

        {/* Source-mode tabs */}
        <div className="grid grid-cols-2 gap-2 mb-5">
          <button
            onClick={() => setMode('live')}
            className={[
              'flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-mono transition-all',
              mode === 'live'
                ? 'bg-primary/15 border-primary/40 text-primary shadow-[0_0_18px_rgba(228,107,69,0.15)]'
                : 'bg-surfaceHover/40 border-border text-textSecondary hover:text-white hover:border-primary/30',
            ].join(' ')}
          >
            <Video className="w-4 h-4" />
            live capture
          </button>
          <button
            onClick={() => setMode('upload')}
            className={[
              'flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-mono transition-all',
              mode === 'upload'
                ? 'bg-primary/15 border-primary/40 text-primary shadow-[0_0_18px_rgba(228,107,69,0.15)]'
                : 'bg-surfaceHover/40 border-border text-textSecondary hover:text-white hover:border-primary/30',
            ].join(' ')}
          >
            <UploadCloud className="w-4 h-4" />
            drop file
          </button>
        </div>

        <AnimatePresence mode="wait">
          {mode === 'live' ? (
            <motion.div
              key="live"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
              className="relative w-full rounded-2xl border border-border bg-black/40 overflow-hidden"
            >
              {/* Live preview / playback stage */}
              <div className="relative aspect-video w-full bg-black">
                {/* Live preview video — always mounted when on live tab so srcObject sticks */}
                <video
                  ref={livePreviewRef}
                  className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-200 ${
                    isReview ? 'opacity-0 pointer-events-none' : 'opacity-100'
                  }`}
                  muted
                  playsInline
                  autoPlay
                />
                {/* Playback of the recorded clip */}
                {isReview && recordedUrl && (
                  <video
                    ref={playbackRef}
                    key={recordedUrl}
                    src={recordedUrl}
                    className="absolute inset-0 w-full h-full object-cover"
                    controls
                    playsInline
                  />
                )}

                {/* Scanner grid overlay */}
                <div
                  aria-hidden
                  className="absolute inset-0 opacity-[0.12] pointer-events-none"
                  style={{
                    backgroundImage:
                      'linear-gradient(to right, rgba(228,107,69,0.4) 1px, transparent 1px), linear-gradient(to bottom, rgba(228,107,69,0.4) 1px, transparent 1px)',
                    backgroundSize: '24px 24px',
                  }}
                />

                {/* Top-left telemetry */}
                <div className="absolute top-3 left-3 px-2 py-1 rounded bg-black/50 backdrop-blur-sm border border-border text-[10px] font-mono uppercase tracking-[0.2em] text-textSecondary flex items-center gap-2">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      isRecording
                        ? 'bg-red-500 animate-pulse'
                        : liveState === 'preview'
                          ? 'bg-emerald-400 animate-pulse'
                          : 'bg-yellow-400'
                    }`}
                  />
                  {isRecording ? 'rec' : liveState === 'preview' ? 'live' : liveState === 'review' ? 'buf' : 'init'}
                </div>

                {/* Elapsed timer */}
                {(isRecording || isReview) && (
                  <div className="absolute top-3 right-3 px-2.5 py-1 rounded bg-black/50 backdrop-blur-sm border border-border text-[11px] font-mono text-white tabular-nums">
                    {formatElapsed(elapsed)}
                  </div>
                )}

                {/* Recording pulse border */}
                {isRecording && (
                  <motion.div
                    aria-hidden
                    className="absolute inset-0 pointer-events-none rounded-2xl ring-2 ring-red-500/70"
                    animate={{ opacity: [0.3, 0.9, 0.3] }}
                    transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
                  />
                )}

                {/* Corner markers on the video stage */}
                <CornerMark className="top-2 left-2" rot={0} size={12} />
                <CornerMark className="top-2 right-2" rot={90} size={12} />
                <CornerMark className="bottom-2 right-2" rot={180} size={12} />
                <CornerMark className="bottom-2 left-2" rot={270} size={12} />

                {/* Init/error overlay */}
                {liveState === 'init' && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm text-center p-6">
                    <div className="flex flex-col items-center gap-3 text-textSecondary">
                      <Video className="w-8 h-8 text-primary animate-pulse" />
                      <span className="font-mono text-xs uppercase tracking-[0.2em]">requesting camera…</span>
                    </div>
                  </div>
                )}
                {liveState === 'error' && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/70 backdrop-blur-sm text-center p-6">
                    <div className="flex flex-col items-center gap-3 max-w-sm">
                      <VideoOff className="w-8 h-8 text-red-400" />
                      <div className="flex items-center gap-2 text-red-300 text-sm font-medium">
                        <AlertTriangle className="w-4 h-4" />
                        Camera unavailable
                      </div>
                      <p className="text-[11px] text-textSecondary leading-relaxed">
                        {mediaErr ?? 'Unknown media error.'}
                      </p>
                      <button
                        onClick={() => void startCamera()}
                        className="mt-1 px-4 py-1.5 rounded border border-primary/40 bg-primary/10 text-primary text-xs font-mono hover:bg-primary/20 transition-colors"
                      >
                        retry
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Control strip */}
              <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-border/70 bg-black/30">
                <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-textSecondary/70 flex items-center gap-2 min-w-0 truncate">
                  {liveState === 'review' ? (
                    <>
                      <FileVideo className="w-3 h-3 text-primary shrink-0" />
                      <span className="truncate">{recordedName}</span>
                      {recordedBlob && (
                        <span className="text-primary/70">
                          · {(recordedBlob.size / (1024 * 1024)).toFixed(2)} MB
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      <ScanLine className="w-3 h-3 text-primary shrink-0" />
                      <span>{devicePath}</span>
                    </>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {liveState === 'preview' && (
                    <motion.button
                      whileHover={{ scale: 1.04 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={startRecording}
                      className="flex items-center gap-2 px-4 py-2 rounded-full bg-red-500/15 border border-red-500/40 text-red-300 hover:bg-red-500/25 transition-colors font-mono text-xs uppercase tracking-[0.2em]"
                    >
                      <Circle className="w-3.5 h-3.5 fill-red-400 text-red-400" />
                      record
                    </motion.button>
                  )}
                  {liveState === 'recording' && (
                    <motion.button
                      whileHover={{ scale: 1.04 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={stopRecording}
                      className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/90 text-black hover:bg-white transition-colors font-mono text-xs uppercase tracking-[0.2em]"
                    >
                      <Square className="w-3.5 h-3.5 fill-black" />
                      stop
                    </motion.button>
                  )}
                  {liveState === 'review' && (
                    <>
                      <motion.button
                        whileHover={{ scale: 1.04 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={redoRecording}
                        className="flex items-center gap-2 px-3 py-2 rounded-full border border-border text-textSecondary hover:text-white hover:border-primary/40 transition-colors font-mono text-xs uppercase tracking-[0.2em]"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        re-record
                      </motion.button>
                      <motion.button
                        whileHover={{
                          scale: 1.05,
                          boxShadow: '0 0 20px rgba(228,107,69,0.3)',
                        }}
                        whileTap={{ scale: 0.95 }}
                        onClick={commitLive}
                        className="primary-button-solid text-xs px-4 py-2 font-mono flex items-center gap-2"
                      >
                        <span className="opacity-70">./</span>process_capture
                        <ArrowRight className="w-3.5 h-3.5" />
                      </motion.button>
                    </>
                  )}
                </div>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="upload"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
            >
              {!file ? (
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragging(true);
                  }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={handleDrop}
                  onClick={() => inputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
                  }}
                  className={`
                    relative w-full h-72 rounded-2xl border-2 border-dashed transition-all duration-300 flex flex-col items-center justify-center cursor-pointer overflow-hidden
                    ${isDragging
                      ? 'border-primary bg-primary/5 scale-[1.02]'
                      : 'border-border bg-surface/30 hover:border-textSecondary/50'
                    }
                  `}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={handlePick}
                  />
                  <div
                    aria-hidden
                    className="absolute inset-0 opacity-[0.08] pointer-events-none"
                    style={{
                      backgroundImage:
                        'linear-gradient(to right, rgba(228,107,69,0.5) 1px, transparent 1px), linear-gradient(to bottom, rgba(228,107,69,0.5) 1px, transparent 1px)',
                      backgroundSize: '20px 20px',
                    }}
                  />
                  <motion.div
                    aria-hidden
                    initial={{ y: '-100%' }}
                    animate={{ y: '100%' }}
                    transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
                    className="absolute left-0 w-full h-12 bg-gradient-to-b from-transparent via-primary/15 to-transparent pointer-events-none"
                  />

                  <CornerMark className="top-3 left-3" rot={0} size={10} />
                  <CornerMark className="top-3 right-3" rot={90} size={10} />
                  <CornerMark className="bottom-3 right-3" rot={180} size={10} />
                  <CornerMark className="bottom-3 left-3" rot={270} size={10} />

                  <div className="relative w-16 h-16 rounded-full bg-surface border border-border flex items-center justify-center mb-4 shadow-lg">
                    <UploadCloud className={`w-8 h-8 ${isDragging ? 'text-primary' : 'text-textSecondary'}`} />
                  </div>
                  <p className="relative font-medium mb-1">Click to browse or drag file here</p>
                  <p className="relative text-[10px] text-textSecondary uppercase tracking-[0.25em] font-mono flex items-center gap-2">
                    <ScanLine className="w-3 h-3" />
                    target zone · up to 2GB
                  </p>
                </div>
              ) : (
                <div className="relative w-full h-72 rounded-2xl border border-border bg-surface/30 flex flex-col items-center justify-center">
                  <motion.button
                    whileHover={{ scale: 1.1, rotate: 90 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={() => setFile(null)}
                    className="absolute top-4 right-4 p-2 rounded-full hover:bg-white/10 transition-colors"
                  >
                    <X className="w-5 h-5 text-textSecondary" />
                  </motion.button>

                  <CornerMark className="top-3 left-3" rot={0} size={10} />
                  <CornerMark className="top-3 right-3" rot={90} size={10} />
                  <CornerMark className="bottom-3 right-3" rot={180} size={10} />
                  <CornerMark className="bottom-3 left-3" rot={270} size={10} />

                  <div className="w-16 h-16 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center mb-4 text-primary shadow-[0_0_20px_rgba(228,107,69,0.15)]">
                    <FileVideo className="w-8 h-8" />
                  </div>
                  <p className="font-mono text-sm text-textSecondary mb-1">
                    <span className="text-primary">file·</span>
                    {file.name}
                  </p>
                  <p className="text-[10px] font-mono text-textSecondary/70 uppercase tracking-[0.2em] mb-6">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB · ready
                  </p>

                  <motion.button
                    whileHover={{
                      scale: 1.05,
                      boxShadow: '0 0 20px rgba(228,107,69,0.3)',
                    }}
                    whileTap={{ scale: 0.95 }}
                    onClick={commitUpload}
                    className="primary-button-solid text-sm px-7 py-3 font-mono"
                  >
                    <span className="opacity-70">./</span>process_video
                  </motion.button>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Bottom tech strip */}
        <div className="mt-5 pt-3 border-t border-dashed border-border/60 flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono uppercase tracking-[0.2em] text-textSecondary/60">
          <span>encoder·on-device</span>
          <span>pipeline·vid2sim-0.1</span>
          <span className="text-primary">●</span>
        </div>
      </motion.div>
    </div>
  );
}
