/** Client for a household's own family and what's happening in the house at
 *  the session's current moment. */

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
  role: 'parent' | 'child' | 'grandparent' | 'guest';
  occupation: string;
  room: number | null;
  status: 'home' | 'away' | 'asleep';
  home_now: boolean;
}

export interface RoomStatus {
  room: number;
  occupied: boolean;
  ac_on: boolean;
  ac_kw: number;
  ac_intensity: number;
}

export interface Family {
  house: HouseDesign;
  members: FamilyMember[];
  rooms: RoomStatus[];
  /** What each appliance group is drawing right now, kW. */
  appliance_kw: Record<string, number>;
}

export function fetchOwnFamily(accessToken: string, signal?: AbortSignal): Promise<Family> {
  return apiFetch<Family>('/households/me/family', accessToken, { signal });
}
