import { useEffect, useState } from 'react';

/**
 * Counts down to the market gate closing, then rolls over to the next tick.
 *
 * Mirrors what the backend will push over WebSocket in P1; until then it keeps
 * the interface honestly *live* rather than showing a frozen number.
 */
export function useCountdown(initialSeconds: number, tickLengthSeconds = 900): number {
  const [seconds, setSeconds] = useState(initialSeconds);

  useEffect(() => {
    const timer = setInterval(() => {
      setSeconds((current) => (current <= 1 ? tickLengthSeconds : current - 1));
    }, 1000);

    return () => {
      clearInterval(timer);
    };
  }, [tickLengthSeconds]);

  return seconds;
}
