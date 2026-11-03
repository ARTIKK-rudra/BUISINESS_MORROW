# Site-wide ambient video

`fish-swimming.mp4` is the supplied 10-second, 1280 × 720 H.264 clip. It is enabled
behind the shared application shell, so it appears behind the dashboard and the other
workspace routes. A translucent wash and lightly translucent shell surfaces keep the
fish visible without putting video in front of text or controls.

To replace the clip, copy another MP4 into this directory and set its public path in
`frontend/.env.local`:

```env
NEXT_PUBLIC_AMBIENT_VIDEO_SRC=/media/your-background.mp4
```

Restart the Next.js server after changing the environment variable. Optionally set a
matching still poster with `NEXT_PUBLIC_AMBIENT_VIDEO_POSTER`. The supplied poster is
used by default. Playback is muted, looping, inline, pauses when the tab is hidden, and
is paused in reduced-motion mode (which shows the poster instead).
