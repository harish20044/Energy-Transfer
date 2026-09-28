import { useContext } from 'react';

import { LiveDataContext, type LiveDataValue } from '@/live/context';

export function useLiveData(): LiveDataValue {
  const ctx = useContext(LiveDataContext);
  if (ctx === null) throw new Error('useLiveData must be used within a LiveDataProvider');
  return ctx;
}
