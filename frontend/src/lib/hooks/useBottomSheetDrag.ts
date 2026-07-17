/**
 * Drag-to-resize hook for mobile bottom sheets.
 *
 * Three snap positions are measured from real DOM content:
 *   snap 1 (peek)  — visible area up to the snap1Ref sentinel
 *   snap 2 (mid)   — visible area up to the snap2Ref sentinel
 *   snap 3 (full)  — full scrollHeight of innerRef (no empty space)
 *
 * The current snap index is persisted to localStorage keyed by sheet type so
 * trains and stations remember their positions independently.
 *
 * Usage:
 *   const innerRef  = useRef<HTMLDivElement>(null);
 *   const snap1Ref  = useRef<HTMLDivElement>(null);
 *   const snap2Ref  = useRef<HTMLDivElement>(null);
 *   const { sheetStyle, handleBarProps } = useBottomSheetDrag('train', {
 *     innerRef, snap1Ref, snap2Ref,
 *   });
 *   // innerRef → scrollable inner div (must have className="... relative")
 *   // snap1Ref / snap2Ref → zero-height sentinel divs placed at section boundaries
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';

export type SheetType = 'train' | 'station';

const STORAGE_KEY: Record<SheetType, string> = {
  train: 'rt-sheet-snap-train',
  station: 'rt-sheet-snap-station',
};

/** Tailwind `sm` breakpoint — hook is a no-op on wider screens. */
const SM_PX = 640;
/**
 * Height of the drag-handle bar (h-1.5 = 6px + mt-2 = 8px + visual padding ≈ 20px).
 * Measured once rather than via a ref to keep the API simple.
 */
const HANDLE_H = 20;
/** Extra padding below the last visible element so content isn't flush. */
const SNAP_BOTTOM_PAD = 16;
/** Max fraction of viewport height the sheet can occupy. */
const MAX_RATIO = 0.82;

function viewportHeight(): number {
  return window.visualViewport?.height ?? window.innerHeight;
}

export interface BottomSheetRefs {
  /** The scrollable inner content div. Must be `position: relative`. */
  innerRef: RefObject<HTMLElement | null>;
  /** Zero-height sentinel placed at the bottom of snap-1 visible content. */
  snap1Ref: RefObject<HTMLElement | null>;
  /**
   * Zero-height sentinel placed at the bottom of snap-2 visible content.
   * May be null-ref if the content is conditional — snap 2 then equals snap 1.
   */
  snap2Ref: RefObject<HTMLElement | null>;
}

/**
 * Returns the pixel distance from `ancestor`'s top edge to the bottom edge of
 * `el` by walking up the offsetParent chain.  Works correctly even when `el`
 * is inside nested elements, as long as `ancestor` is `position: relative`.
 */
function getOffsetBottom(el: HTMLElement, ancestor: HTMLElement): number {
  let offset = el.offsetTop + el.offsetHeight;
  let curr: HTMLElement | null = el.offsetParent as HTMLElement | null;
  while (curr && curr !== ancestor) {
    offset += curr.offsetTop;
    curr = curr.offsetParent as HTMLElement | null;
  }
  return offset;
}

function nearestSnapIdx(
  height: number,
  snaps: [number, number, number]
): number {
  let best = 0;
  let bestDist = Infinity;
  for (let i = 0; i < snaps.length; i++) {
    const d = Math.abs(snaps[i] - height);
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  }
  return best;
}

function loadSnapIdx(type: SheetType): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY[type]);
    if (raw !== null) {
      const n = Number(raw);
      if (n === 0 || n === 1 || n === 2) return n;
    }
  } catch {
    /* localStorage unavailable */
  }
  return 1; // default: mid snap
}

function saveSnapIdx(type: SheetType, idx: number): void {
  try {
    localStorage.setItem(STORAGE_KEY[type], String(idx));
  } catch {
    /* ignore */
  }
}

export function useBottomSheetDrag(type: SheetType, refs: BottomSheetRefs) {
  const { innerRef, snap1Ref, snap2Ref } = refs;

  const snapsRef = useRef<[number, number, number]>([80, 250, 500]);
  const snapIdxRef = useRef<number>(loadSnapIdx(type));
  const dragRef = useRef({ active: false, startY: 0, startHeight: 0 });

  const [height, setHeight] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const measureSnaps = useCallback((): [number, number, number] => {
    if (typeof window === 'undefined') return [80, 250, 500];
    const inner = innerRef.current as HTMLElement | null;
    const s1 = snap1Ref.current as HTMLElement | null;
    const s2 = snap2Ref.current as HTMLElement | null;
    const maxH = Math.floor(viewportHeight() * MAX_RATIO);

    // Fallbacks when refs aren't yet mounted.
    let snap1 = HANDLE_H + 80;
    let snap2 = HANDLE_H + 200;
    let snap3 = HANDLE_H + 400;

    if (inner && s1) {
      snap1 = Math.min(
        HANDLE_H + getOffsetBottom(s1, inner) + SNAP_BOTTOM_PAD,
        maxH
      );
    }
    if (inner && s2) {
      snap2 = Math.min(
        HANDLE_H + getOffsetBottom(s2, inner) + SNAP_BOTTOM_PAD,
        maxH
      );
    }
    if (inner) {
      snap3 = Math.min(HANDLE_H + inner.scrollHeight, maxH);
    }

    // Guarantee strict ordering.
    snap1 = Math.max(snap1, HANDLE_H + 40);
    snap2 = Math.max(snap2, snap1 + 1);
    snap3 = Math.max(snap3, snap2 + 1);

    return [snap1, snap2, snap3];
  }, [innerRef, snap1Ref, snap2Ref]);

  // Initialise after first paint so DOM measurements are available.
  useEffect(() => {
    if (typeof window === 'undefined' || window.innerWidth >= SM_PX) {
      setHeight(null);
      return;
    }
    const raf = window.requestAnimationFrame(() => {
      const snaps = measureSnaps();
      snapsRef.current = snaps;
      snapIdxRef.current = loadSnapIdx(type);
      setHeight(snaps[snapIdxRef.current]);
    });
    return () => window.cancelAnimationFrame(raf);
  }, [type, measureSnaps]);

  // Re-measure when inner content resizes (e.g. async schedule data arrives).
  useEffect(() => {
    const inner = innerRef.current;
    if (!inner) return;
    const observer = new ResizeObserver(() => {
      if (typeof window !== 'undefined' && window.innerWidth < SM_PX) {
        const snaps = measureSnaps();
        snapsRef.current = snaps;
        // If we're at the full-content snap, follow the new content height.
        if (snapIdxRef.current === 2) setHeight(snaps[2]);
      }
    });
    observer.observe(inner);
    return () => observer.disconnect();
  }, [innerRef, measureSnaps]);

  // Recalculate on viewport resize (orientation change, etc.).
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= SM_PX) {
        setHeight(null);
        return;
      }
      const snaps = measureSnaps();
      snapsRef.current = snaps;
      setHeight(snaps[snapIdxRef.current]);
    };
    const viewport = window.visualViewport;
    window.addEventListener('resize', onResize, { passive: true });
    viewport?.addEventListener('resize', onResize, { passive: true });
    return () => {
      window.removeEventListener('resize', onResize);
      viewport?.removeEventListener('resize', onResize);
    };
  }, [measureSnaps]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (window.innerWidth >= SM_PX) return;
      e.preventDefault();
      const snaps = measureSnaps();
      snapsRef.current = snaps;
      dragRef.current = {
        active: true,
        startY: e.clientY,
        startHeight: snaps[snapIdxRef.current],
      };
      setIsDragging(true);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    },
    [measureSnaps]
  );

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current.active) return;
    const { startY, startHeight } = dragRef.current;
    const delta = startY - e.clientY; // drag up → positive → height grows
    const [min, , max] = snapsRef.current;
    setHeight(Math.max(min, Math.min(max, startHeight + delta)));
  }, []);

  const onPointerUp = useCallback(
    (e: React.PointerEvent) => {
      if (!dragRef.current.active) return;
      const { startY, startHeight } = dragRef.current;
      dragRef.current.active = false;
      setIsDragging(false);
      const delta = startY - e.clientY;
      const snaps = snapsRef.current;
      const [min, , max] = snaps;
      const clamped = Math.max(min, Math.min(max, startHeight + delta));
      const idx = nearestSnapIdx(clamped, snaps);
      snapIdxRef.current = idx;
      setHeight(snaps[idx]);
      saveSnapIdx(type, idx);
    },
    [type]
  );

  const onPointerCancel = useCallback(() => {
    if (!dragRef.current.active) return;
    dragRef.current.active = false;
    setIsDragging(false);
    setHeight(snapsRef.current[snapIdxRef.current]);
  }, []);

  /**
   * Apply to the outer sheet container `<div>`.
   * On desktop (≥ 640 px) height is unset so natural CSS sizing applies.
   */
  const sheetStyle: React.CSSProperties =
    height !== null
      ? {
          height: `${height}px`,
          transition: isDragging
            ? 'none'
            : 'height 0.28s cubic-bezier(0.32,0.72,0,1)',
        }
      : {};

  /**
   * Spread onto the drag-handle bar element.
   * `touchAction: 'none'` prevents the browser from intercepting the gesture.
   */
  const handleBarProps = {
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel,
    style: { touchAction: 'none', cursor: 'ns-resize' } as React.CSSProperties,
  };

  return { sheetStyle, handleBarProps };
}
