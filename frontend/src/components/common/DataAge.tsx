/**
 * Shows how stale data is: "5s ago", "2m ago", "offline"
 */
import { useState, useEffect } from 'react';

interface DataAgeProps {
  timestamp: string | null;  // ISO datetime string
}

function formatAge(ms: number): string {
  const sec = Math.floor(ms / 1000);
  if (sec < 5) return 'just now';
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  return `${hr}h ${min % 60}m ago`;
}

export default function DataAge({ timestamp }: DataAgeProps) {
  const [age, setAge] = useState<string>('--');

  useEffect(() => {
    if (!timestamp) {
      setAge('--');
      return;
    }

    const update = () => {
      const ms = Date.now() - new Date(timestamp).getTime();
      setAge(ms >= 0 ? formatAge(ms) : '--');
    };

    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [timestamp]);

  const isStale = timestamp
    ? Date.now() - new Date(timestamp).getTime() > 60000
    : true;

  return (
    <span style={{
      fontSize: '11px',
      fontFamily: 'var(--font-mono)',
      color: isStale ? 'var(--color-warning)' : 'var(--color-text-muted)',
      transition: 'color 0.3s ease',
    }}>
      {age}
    </span>
  );
}
