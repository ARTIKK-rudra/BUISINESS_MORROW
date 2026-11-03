import type { Metadata } from 'next';
import './globals.css';
import './reference.css';
import { Shell } from '@/components/shell';
import { AmbientBackground } from '@/components/ambient-background';
export const metadata: Metadata = { title: 'Morrow — Business Command Center', description: 'An intelligent workspace for understanding business performance, demand, and inventory.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: `try{var t=localStorage.getItem('morrow-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}` }}/></head><body><AmbientBackground/><Shell>{children}</Shell></body></html>; }
