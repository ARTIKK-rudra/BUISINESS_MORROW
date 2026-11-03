'use client';

import { useEffect, useRef } from 'react';

const source = process.env.NEXT_PUBLIC_AMBIENT_VIDEO_SRC || '/media/fish-swimming.mp4';
const poster = process.env.NEXT_PUBLIC_AMBIENT_VIDEO_POSTER || '/media/fish-swimming-poster.jpg';

/** The ambient footage is deliberately behind the shared shell, across every route. */
export function AmbientBackground() {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (video) video.playbackRate = 0.5;
    const syncPlayback = () => {
      if (!video) return;
      if (reducedMotion.matches || document.hidden) {
        video.pause();
        return;
      }
      void video.play().catch(() => undefined);
    };

    syncPlayback();
    reducedMotion.addEventListener('change', syncPlayback);
    document.addEventListener('visibilitychange', syncPlayback);
    return () => {
      reducedMotion.removeEventListener('change', syncPlayback);
      document.removeEventListener('visibilitychange', syncPlayback);
      video?.pause();
    };
  }, []);

  return (
    <div className="site-ambient-background" aria-hidden="true">
      <video ref={videoRef} autoPlay muted loop playsInline preload="metadata" poster={poster}>
        <source src={source} type="video/mp4" />
      </video>
      <div className="site-ambient-wash" />
    </div>
  );
}
