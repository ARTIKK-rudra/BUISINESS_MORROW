'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Mic, MicOff, Volume2, VolumeX } from 'lucide-react';
import { PageHeading } from '@/components/ui';
import { api, ApiError, type AssistantResponse } from '@/lib/api';

type VoicePhase = 'idle' | 'listening' | 'processing' | 'speaking' | 'error';
type SpeechResult = { transcript: string };
type SpeechAlternativeList = ArrayLike<SpeechResult>;
type SpeechResultList = ArrayLike<SpeechAlternativeList & { isFinal?: boolean }>;
type SpeechResultEvent = Event & { resultIndex?: number; results: SpeechResultList };
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onerror: ((event: Event & { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
};
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type BrowserWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

const phaseCopy: Record<VoicePhase, string> = {
  idle: 'Ask your business a question.',
  listening: 'Listening…',
  processing: 'Processing your question…',
  speaking: 'Speaking the verified response…',
  error: 'Voice assistant needs your attention.',
};
const historyStorageKey = 'morrow.voice-assistant-history';
const sessionStorageKey = 'morrow.voice-assistant-session';

export default function VoiceAssistantPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [recognitionSupported, setRecognitionSupported] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [recording, setRecording] = useState(false);
  const [phase, setPhase] = useState<VoicePhase>('idle');
  const [transcript, setTranscript] = useState('');
  const [answer, setAnswer] = useState<AssistantResponse | null>(null);
  const [error, setError] = useState('');
  const [playbackNotice, setPlaybackNotice] = useState('');
  const [consent, setConsent] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const recognition = useRef<SpeechRecognitionLike | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const recordingStream = useRef<MediaStream | null>(null);
  const recordingChunks = useRef<Blob[]>([]);
  const finalTranscript = useRef('');
  const submissionInFlight = useRef(false);

  const isListening = phase === 'listening';
  const isBusy = phase === 'processing' || phase === 'speaking';

  useEffect(() => {
    const browser = window as BrowserWindow;
    setRecognitionSupported(Boolean(browser.SpeechRecognition || browser.webkitSpeechRecognition));
    setSpeechSupported('speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined');
    const synth = 'speechSynthesis' in window ? window.speechSynthesis : undefined;
    const refreshVoices = () => synth?.getVoices();
    synth?.addEventListener?.('voiceschanged', refreshVoices);
    return () => {
      recognition.current?.abort();
      recorder.current?.state === 'recording' && recorder.current.stop();
      recordingStream.current?.getTracks().forEach(track => track.stop());
      synth?.cancel();
      synth?.removeEventListener?.('voiceschanged', refreshVoices);
    };
  }, []);

  useEffect(() => {
    const stored = window.sessionStorage.getItem(historyStorageKey);
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.every(item => typeof item === 'string')) setHistory(parsed.slice(-6));
    } catch { window.sessionStorage.removeItem(historyStorageKey); }
  }, []);

  function updateHistory(question: string) {
    setHistory(previous => {
      const next = [...previous, question].slice(-6);
      window.sessionStorage.setItem(historyStorageKey, JSON.stringify(next));
      return next;
    });
  }

  function conversationSession() {
    let id = window.sessionStorage.getItem(sessionStorageKey);
    if (!id) {
      id = crypto.randomUUID().replaceAll('-', '');
      window.sessionStorage.setItem(sessionStorageKey, id);
    }
    return id;
  }

  function stopRecognition() {
    recognition.current?.stop();
    recognition.current = null;
  }

  function cancelSpeech() {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  }

  function stop() {
    stopRecognition();
    if (isListening) setPhase('idle');
  }

  function releaseRecording() {
    recordingStream.current?.getTracks().forEach(track => track.stop());
    recordingStream.current = null;
    recorder.current = null;
    setRecording(false);
  }

  async function transcribeRecording(audio: Blob) {
    setPhase('processing');
    setError('');
    try {
      const result = await api.transcribeVoiceAudio(audio);
      setTranscript(result.transcript);
      await submit(result.transcript);
    } catch (caught) {
      setPhase('error');
      setError(caught instanceof ApiError ? caught.message : 'Could not transcribe this recording. Type your question instead.');
    }
  }

  async function startGeminiRecording() {
    if (!('MediaRecorder' in window)) {
      setPhase('error');
      setError('Audio recording is unsupported in this browser. Type your question instead.');
      return;
    }
    cancelSpeech();
    stopRecognition();
    setError('');
    setPlaybackNotice('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordingStream.current = stream;
      recordingChunks.current = [];
      const engine = new MediaRecorder(stream);
      recorder.current = engine;
      engine.ondataavailable = event => {
        if (event.data.size > 0) recordingChunks.current.push(event.data);
      };
      engine.onstop = () => {
        const audio = new Blob(recordingChunks.current, { type: engine.mimeType || 'audio/webm' });
        releaseRecording();
        if (audio.size > 0) void transcribeRecording(audio);
        else {
          setPhase('error');
          setError('No audio was recorded. Try again or type your question.');
        }
      };
      engine.start();
      setRecording(true);
      setPhase('listening');
    } catch {
      setPhase('error');
      setError('Microphone permission is required to record with Gemini. Allow microphone access, then try again.');
    }
  }

  function stopGeminiRecording() {
    if (recorder.current?.state === 'recording') recorder.current.stop();
  }

  function retrySpeechRecognition() {
    setError('');
    setPhase('idle');
    void start();
  }

  async function speak(response: string) {
    if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
      setPlaybackNotice('Speaker playback is not supported in this browser. The verified response is shown below.');
      setPhase('idle');
      return;
    }

    try {
      cancelSpeech();
      setPlaybackNotice('');
      setPhase('speaking');
      await new Promise<void>((resolve) => {
        const utterance = new SpeechSynthesisUtterance(response);
        utterance.rate = 1;
        utterance.pitch = 1;
        utterance.onend = () => resolve();
        utterance.onerror = () => {
          setPlaybackNotice('The response was received, but your browser could not play it aloud. Read the verified response below.');
          resolve();
        };
        window.speechSynthesis.speak(utterance);
      });
      setPhase('idle');
    } catch {
      setPlaybackNotice('The response was received, but speaker playback could not start. Read the verified response below.');
      setPhase('idle');
    }
  }

  async function submit(text: string) {
    const question = text.trim();
    if (!question || submissionInFlight.current) return;
    submissionInFlight.current = true;
    stopRecognition();
    setPhase('processing');
    setError('');
    setPlaybackNotice('');
    setAnswer(null);
    try {
      const value = await api.askByVoice(question, consent, pathname, history, conversationSession());
      if (!value.answer?.trim()) throw new ApiError('The server returned an empty voice response. Please try again.');
      setAnswer(value);
      updateHistory(question);
      await speak(value.answer);
      if (value.navigation_path) router.push(value.navigation_path);
    } catch (caught) {
      cancelSpeech();
      setPhase('error');
      setError(caught instanceof ApiError ? caught.message : 'Could not retrieve a business response. Please retry or type your question.');
    } finally {
      submissionInFlight.current = false;
    }
  }

  async function requestMicrophonePermission(): Promise<boolean> {
    if (!navigator.mediaDevices?.getUserMedia) return true;
    try {
      // SpeechRecognition implementations do not consistently show the browser
      // permission prompt themselves. Request and immediately release a stream
      // so the user has a clear, user-initiated permission flow.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(track => track.stop());
      return true;
    } catch (caught) {
      const name = caught instanceof DOMException ? caught.name : '';
      setPhase('error');
      setError(
        name === 'NotFoundError'
          ? 'No microphone was found. Connect a microphone, select it in your system sound settings, then try again.'
          : name === 'NotReadableError'
            ? 'Your microphone is being used by another app. Close that app, then try again.'
            : 'Microphone permission was denied. In Chrome, select the icon beside the address bar, set Microphone to Allow, then reload this page.',
      );
      return false;
    }
  }

  async function start() {
    const browser = window as BrowserWindow;
    const Constructor = browser.SpeechRecognition || browser.webkitSpeechRecognition;
    if (!Constructor) {
      setPhase('error');
      setError('Speech recognition is unavailable in this browser. Type a command below instead.');
      return;
    }

    if (!(await requestMicrophonePermission())) return;

    cancelSpeech();
    stopRecognition();
    finalTranscript.current = '';
    setError('');
    setPlaybackNotice('');
    setTranscript('');
    const engine = new Constructor();
    recognition.current = engine;
    engine.lang = navigator.language || 'en-US';
    engine.continuous = false;
    engine.interimResults = true;
    engine.onresult = (event) => {
      let latestInterim = '';
      for (let index = event.resultIndex ?? 0; index < event.results.length; index += 1) {
        const result = event.results[index];
        const spoken = result?.[0]?.transcript?.trim() ?? '';
        if (!spoken) continue;
        if (result.isFinal) finalTranscript.current = `${finalTranscript.current} ${spoken}`.trim();
        else latestInterim = spoken;
      }
      setTranscript(`${finalTranscript.current} ${latestInterim}`.trim());
      if (finalTranscript.current) void submit(finalTranscript.current);
    };
    engine.onerror = (event) => {
      if (event.error === 'aborted') return;
      // Web Speech implementations can report a late audio/network error while
      // shutting down after they already delivered a final transcript. The
      // question is then safely on its way to FastAPI; do not overwrite the
      // verified answer with a stale microphone error.
      if (submissionInFlight.current || finalTranscript.current) return;
      const message = event.error === 'not-allowed' || event.error === 'service-not-allowed'
        ? 'Microphone permission was denied. Allow microphone access in your browser settings, then try again.'
        : event.error === 'no-speech'
          ? 'No speech was detected. Try again or type your command below.'
          : event.error === 'audio-capture'
            ? 'The browser cannot access an input microphone. Confirm the correct input is selected in macOS System Settings → Sound → Input, then try again.'
            : event.error === 'network'
              ? 'Browser speech recognition could not reach its speech service. Check your internet connection, then retry or use the text command fallback.'
          : 'The browser could not capture speech. Check microphone permission or type your command.';
      setPhase('error');
      setError(message);
    };
    engine.onend = () => {
      if (!submissionInFlight.current && !finalTranscript.current) {
        setPhase(current => current === 'listening' ? 'idle' : current);
      }
    };
    try {
      engine.start();
      setPhase('listening');
    } catch {
      setPhase('error');
      setError('Could not start speech recognition. Check microphone permission and try again.');
    }
  }

  return <>
    <PageHeading eyebrow="SPEECH TO BUSINESS DATA" title="Voice assistant" description="Speak a read-only business question. Your browser transcribes it, FastAPI returns a verified answer, and your device reads it aloud when supported."/>
    <section className="panel voice-interaction-panel" aria-busy={isBusy}>
      <div className={`voice-orb ${isListening || phase === 'speaking' ? 'voice-orb-active' : ''}`}><span/></div>
      <p className="voice-state" role="status" aria-live="polite">{phaseCopy[phase]}</p>
      <h2>{phaseCopy[phase]}</h2>
      <p>Try “Show today’s sales”, “How much rice should I order?”, or “What products are low?”</p>
      <button type="button" className={`button ${isListening && !recording ? 'button-danger' : 'button-primary'}`} onClick={isListening && !recording ? stop : () => void start()} disabled={isBusy || !recognitionSupported || recording}>
        {isListening ? <><MicOff size={15}/> Stop listening</> : <><Mic size={15}/> Start voice input</>}
      </button>
      <button type="button" className={`button ${recording ? 'button-danger' : 'button-secondary'} voice-gemini-record`} onClick={recording ? stopGeminiRecording : () => void startGeminiRecording()} disabled={isBusy || isListening && !recording}>
        {recording ? <><MicOff size={15}/> Stop and transcribe</> : <><Mic size={15}/> Record with Gemini</>}
      </button>
      {!recognitionSupported && <p className="assistant-error" role="status">Speech recognition is unsupported here. You can still type a command below.</p>}
      <form className="voice-typed-form" onSubmit={event => { event.preventDefault(); void submit(transcript); }}>
        <label htmlFor="voice-command">Recognized speech or typed command</label>
        <div><input id="voice-command" value={transcript} onChange={event => setTranscript(event.target.value)} placeholder="Show today’s sales" maxLength={1000} disabled={isBusy}/><button className="button button-secondary" disabled={isBusy || !transcript.trim()}>Ask</button></div>
      </form>
      <label className="voice-consent"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} disabled={isBusy}/> Store this transcript in my voice interaction history. Off by default.</label>
      <p className="assistant-capability-note">The microphone stops before the request and speaker playback begin. This prevents your computer from transcribing its own response. “Record with Gemini” uploads only the recording you explicitly stop and requires a configured Gemini API key. {speechSupported ? 'Speaker playback is available in this browser.' : 'Speaker playback is unavailable here; the response remains visible as text.'}</p>
      {error && <div className="assistant-error voice-error" role="alert"><span>{error}</span>{error.includes('speech service') && <button type="button" className="button button-secondary" onClick={retrySpeechRecognition}>Retry voice input</button>}</div>}
      {playbackNotice && <div className="assistant-playback-fallback" role="status"><VolumeX size={15}/>{playbackNotice}</div>}
      {answer && <article className="assistant-answer" aria-live="polite"><div className="assistant-answer-label"><Volume2 size={14}/> VERIFIED RESPONSE</div><p>{answer.answer}</p>{answer.sources.length > 0 && <div className="assistant-sources"><strong>Records checked</strong>{answer.sources.map(source => <span key={source}>{source}</span>)}</div>}</article>}
    </section>
  </>;
}
