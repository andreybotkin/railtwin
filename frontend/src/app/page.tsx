'use client';

import dynamic from 'next/dynamic';

import TrainInfoSheet from '@/components/TrainInfo/TrainInfoSheet';

const RailMap = dynamic(() => import('@/components/Map/RailMap'), { ssr: false });

export default function HomePage() {
  return (
    <main className="relative h-dvh w-full overflow-hidden bg-zinc-900">
      <RailMap />
      <div className="pointer-events-none absolute left-4 top-4 z-20 rounded-xl bg-black/40 px-3 py-2 text-xs text-white backdrop-blur">
        Thailand Railway Digital Twin
      </div>
      <div className="pointer-events-none absolute bottom-4 left-4 z-20 rounded-xl bg-black/40 px-3 py-2 text-xs text-white backdrop-blur">
        Northern / Northeastern / Southern / Eastern
      </div>
      <TrainInfoSheet />
    </main>
  );
}
