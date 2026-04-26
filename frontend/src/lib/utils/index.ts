/**
 * Utility functions for the application.
 */

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes with clsx.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format time string (HH:MM:SS) to display format (HH:MM).
 */
export function formatTime(time: string | null): string {
  if (!time) return '--:--';
  return time.slice(0, 5);
}

/**
 * Format speed to display string.
 */
export function formatSpeed(speed: number | null, locale = 'en'): string {
  const unit = locale.startsWith('th') ? 'กม./ชม.' : 'km/h';
  if (speed === null) return `-- ${unit}`;
  return `${Math.round(speed)} ${unit}`;
}

/**
 * Format delay to display string.
 */
export function formatDelay(minutes: number, locale = 'en'): string {
  const unit = locale.startsWith('th') ? 'นาที' : 'min';
  if (minutes === 0) return `0 ${unit}`;
  return `${minutes > 0 ? '+' : ''}${minutes} ${unit}`;
}

/**
 * Get status color class based on train status.
 */
export function getStatusColor(status: string): string {
  switch (status) {
    case 'moving':
      return 'text-green-500';
    case 'at_station':
      return 'text-blue-500';
    case 'stopped':
      return 'text-yellow-500';
    case 'delayed':
      return 'text-red-500';
    default:
      return 'text-gray-500';
  }
}

/**
 * Brand colour for a train type. Mirrors the palette in
 * ``simulation/app/services/trajectory_service.py`` so badges on the map and
 * in info panels match the colour MapLibre uses for the vehicle icon.
 */
export function getTrainTypeColor(type: string | null | undefined): string {
  switch ((type ?? '').trim().toLowerCase()) {
    case 'special_express':
      return '#E53935';
    case 'express':
      return '#EF6C00';
    case 'rapid':
      return '#1E88E5';
    case 'ordinary':
      return '#43A047';
    case 'commuter':
      return '#8E24AA';
    default:
      return '#2196F3';
  }
}

/**
 * Get train type display name.
 */
export function getTrainTypeName(type: string): string {
  switch (type) {
    case 'special_express':
      return 'Special Express';
    case 'rapid':
      return 'Rapid';
    case 'ordinary':
      return 'Ordinary';
    default:
      return type;
  }
}

/**
 * Get route type display name.
 */
export function getRouteTypeName(type: string): string {
  switch (type) {
    case 'northern':
      return 'Northern Line';
    case 'northeastern':
      return 'Northeastern Line';
    case 'southern':
      return 'Southern Line';
    case 'eastern':
      return 'Eastern Line';
    default:
      return type;
  }
}

/**
 * Get route color.
 */
export function getRouteColor(type: string): string {
  switch (type) {
    case 'northern':
      return '#E53935';
    case 'northeastern':
      return '#1E88E5';
    case 'southern':
      return '#FB8C00';
    case 'eastern':
      return '#8E24AA';
    default:
      return '#666666';
  }
}

/**
 * Get day of week name.
 */
export function getDayName(day: number): string {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  return days[day] || '';
}

/**
 * Check if schedule is active today.
 */
export function isActiveToday(daysOfWeek: number[] | null): boolean {
  if (!daysOfWeek) return true;
  const today = new Date().getDay();
  // Convert Sunday=0 to Monday=0 format
  const dayIndex = today === 0 ? 6 : today - 1;
  return daysOfWeek.includes(dayIndex);
}

/**
 * Calculate bearing between two coordinates.
 */
export function calculateBearing(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const toDeg = (rad: number) => (rad * 180) / Math.PI;

  const dLon = toRad(lon2 - lon1);
  const y = Math.sin(dLon) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(dLon);

  let bearing = toDeg(Math.atan2(y, x));
  return (bearing + 360) % 360;
}
