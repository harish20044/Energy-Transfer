/** Client for a household's own family composition and live room status. */

import { apiFetch } from '@/api/client';

export interface HouseDesign {
  bedrooms: number;
  washrooms: number;
  halls: number;
  ac_units: number;
}

export interface FamilyMember {
  index: number;
  age: number;
  role: 'parent' | 'child';
  room: number | null;
  home_now: boolean;
}

export interface RoomStatus {
  room: number;
  occupied: boolean;
  ac_intensity: number;
}

export interface Family {
  house: HouseDesign;
  members: FamilyMember[];
  rooms: RoomStatus[];
}

export function fetchOwnFamily(accessToken: string, signal?: AbortSignal): Promise<Family> {
  return apiFetch<Family>('/households/me/family', accessToken, { signal });
}
