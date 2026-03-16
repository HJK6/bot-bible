import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Platform, ActivityIndicator } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { callApi } from '../../src/services/api';
import { Colors } from '@/constants/Colors';

interface Snapshot {
  time: string;
  minutes_elapsed: number;
  current_volume: number;
  expected_volume: number;
  shock_ratio: number;
  ltp: number | null;
  change_pct: number | null;
  sector_hot: boolean;
  has_large_deal?: boolean;
  large_deal_direction?: string;
}

interface VolumeShock {
  trade_date: string;
  ticker: string;
  bse_code: string;
  stock_name: string;
  sector: string;
  trust_score: number | null;
  prev_day_volume: number;
  first_detected_at: string;
  last_snapshot_at: string;
  peak_shock_ratio: number;
  peak_shock_time: string;
  latest_shock_ratio: number;
  latest_ltp: number | null;
  latest_change_pct: number | null;
  snapshot_count: number;
  snapshots: Snapshot[];
}

type SortKey = 'peak_shock_ratio' | 'ticker' | 'stock_name' | 'sector' | 'latest_ltp' | 'latest_change_pct' | 'prev_day_volume' | 'trust_score' | 'first_detected_at' | 'snapshot_count';
type SortDir = 'asc' | 'desc';

const font: React.CSSProperties = {
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
};

function todayIST(): string {
  const now = new Date();
  const ist = new Date(now.getTime() + (5.5 * 60 * 60 * 1000));
  return ist.toISOString().slice(0, 10);
}

function fmtVol(v: number | null | undefined): string {
  if (v == null) return '-';
  return Number(v).toLocaleString('en-IN');
}

function fmtLtp(v: number | null | undefined): string {
  if (v == null) return '-';
  return Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function fmtChg(v: number | null | undefined): string {
  if (v == null) return '-';
  const n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
}

function chgColor(v: number | null | undefined): string {
  if (v == null) return Colors.text;
  return Number(v) >= 0 ? Colors.success : Colors.error;
}

function shockColor(ratio: number): string {
  if (ratio >= 5) return Colors.error;
  if (ratio >= 3) return '#facc15';
  return Colors.success;
}

function trustColor(v: number | null): string {
  if (v == null) return Colors.text;
  if (v >= 90) return Colors.success;
  if (v >= 85) return '#facc15';
  return Colors.text;
}

// ─── SVG Chart ───────────────────────────────────────────

function ShockChart({ snapshots }: { snapshots: Snapshot[] }) {
  if (!snapshots || snapshots.length === 0) return null;

  const W = 560, H = 200;
  const padL = 45, padR = 20, padT = 20, padB = 40;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  const ratios = snapshots.map(s => s.shock_ratio);
  const maxR = Math.max(...ratios, 2.5);
  const minR = Math.min(...ratios, 0);
  const yRange = maxR - minR || 1;

  const toX = (i: number) => padL + (i / Math.max(snapshots.length - 1, 1)) * chartW;
  const toY = (r: number) => padT + chartH - ((r - minR) / yRange) * chartH;

  const points = snapshots.map((s, i) => `${toX(i)},${toY(s.shock_ratio)}`).join(' ');

  // Y-axis ticks
  const yTicks: number[] = [];
  const yStep = yRange <= 2 ? 0.5 : yRange <= 5 ? 1 : yRange <= 15 ? 2 : 5;
  for (let v = Math.ceil(minR / yStep) * yStep; v <= maxR; v += yStep) {
    yTicks.push(Math.round(v * 100) / 100);
  }

  // Threshold line at 2.0
  const thresholdY = toY(2.0);
  const showThreshold = 2.0 >= minR && 2.0 <= maxR;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: W, height: 'auto' }}>
      {/* Grid lines */}
      {yTicks.map(v => (
        <line key={v} x1={padL} x2={W - padR} y1={toY(v)} y2={toY(v)}
          stroke={Colors.border} strokeWidth={0.5} />
      ))}

      {/* Threshold line */}
      {showThreshold && (
        <>
          <line x1={padL} x2={W - padR} y1={thresholdY} y2={thresholdY}
            stroke={Colors.error} strokeWidth={1} strokeDasharray="6,4" opacity={0.6} />
          <text x={W - padR + 4} y={thresholdY + 4}
            fill={Colors.error} fontSize={10} opacity={0.7}>2x</text>
        </>
      )}

      {/* Line */}
      <polyline points={points} fill="none" stroke={Colors.primary} strokeWidth={2} />

      {/* Dots */}
      {snapshots.map((s, i) => (
        <circle key={i} cx={toX(i)} cy={toY(s.shock_ratio)} r={4}
          fill={shockColor(s.shock_ratio)} stroke={Colors.surface} strokeWidth={1.5} />
      ))}

      {/* Y-axis labels */}
      {yTicks.map(v => (
        <text key={v} x={padL - 8} y={toY(v) + 4}
          fill={Colors.textMuted} fontSize={10} textAnchor="end">{v}x</text>
      ))}

      {/* X-axis labels */}
      {snapshots.map((s, i) => {
        // Show every label if <= 8 snapshots, otherwise every other
        if (snapshots.length > 8 && i % 2 !== 0 && i !== snapshots.length - 1) return null;
        return (
          <text key={i} x={toX(i)} y={H - padB + 18}
            fill={Colors.textMuted} fontSize={10} textAnchor="middle">{s.time}</text>
        );
      })}
    </svg>
  );
}

// ─── Modal ───────────────────────────────────────────────

function ShockModal({ shock, onClose }: { shock: VolumeShock; onClose: () => void }) {
  const latestSnap = shock.snapshots?.[shock.snapshots.length - 1];

  return (
    <div
      className="shock-modal-overlay"
      onClick={onClose}
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
        overflow: 'auto', zIndex: 100, padding: '3vh 1rem',
      }}
    >
      <div
        className="shock-modal-card"
        onClick={e => e.stopPropagation()}
        style={{
          background: Colors.surface, borderRadius: 12, border: `1px solid ${Colors.border}`,
          width: '100%', maxWidth: 640, position: 'relative', padding: '1.5rem',
        }}
      >
        {/* Close */}
        <button onClick={onClose} style={{
          position: 'absolute', top: 12, right: 14,
          background: 'none', border: 'none', color: Colors.textMuted,
          fontSize: '1.4rem', cursor: 'pointer', lineHeight: 1, padding: 4,
        }}>&times;</button>

        {/* Header */}
        <div style={{ marginBottom: '1rem', paddingRight: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem', flexWrap: 'wrap' }}>
            <h2 style={{ ...font, color: Colors.text, fontSize: '1.2rem', margin: 0 }}>{shock.stock_name}</h2>
            <span style={{ ...font, color: Colors.primary, fontSize: '0.9rem', fontWeight: 600 }}>{shock.ticker}</span>
            {shock.trust_score != null && (
              <span style={{
                ...font, fontSize: '0.75rem', fontWeight: 600, padding: '2px 8px',
                borderRadius: 4, background: Colors.surfaceLight, color: trustColor(shock.trust_score),
              }}>Trust {shock.trust_score}</span>
            )}
          </div>
          <div style={{ ...font, color: Colors.textMuted, fontSize: '0.8rem', marginTop: 4 }}>
            {shock.sector} &middot; BSE: {shock.bse_code}
          </div>
        </div>

        {/* Chart */}
        {shock.snapshots && shock.snapshots.length > 0 && (
          <div style={{ marginBottom: '1.25rem', background: Colors.surfaceLight, borderRadius: 8, padding: '12px 8px' }}>
            <h3 style={{ ...font, color: Colors.textSecondary, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 8px 8px' }}>
              Shock Ratio Over Day
            </h3>
            <ShockChart snapshots={shock.snapshots} />
          </div>
        )}

        {/* Info grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '1.25rem' }}>
          {[
            ['Peak Shock', `${shock.peak_shock_ratio.toFixed(1)}x at ${shock.peak_shock_time}`, shockColor(shock.peak_shock_ratio)],
            ['Latest Shock', `${shock.latest_shock_ratio.toFixed(1)}x`, shockColor(shock.latest_shock_ratio)],
            ['First Detected', shock.first_detected_at, Colors.text],
            ['Last Snapshot', shock.last_snapshot_at, Colors.text],
            ['Price', fmtLtp(shock.latest_ltp), Colors.text],
            ['Change %', fmtChg(shock.latest_change_pct), chgColor(shock.latest_change_pct)],
            ['NSE Prev Volume', fmtVol(shock.prev_day_volume), Colors.text],
            ['Snapshots', String(shock.snapshot_count), Colors.text],
          ].map(([label, value, color]) => (
            <div key={label as string} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', borderBottom: `1px solid ${Colors.border}22` }}>
              <span style={{ ...font, color: Colors.textMuted, fontSize: '0.82rem' }}>{label}</span>
              <span style={{ ...font, color: color as string, fontSize: '0.82rem', fontWeight: 500 }}>{value}</span>
            </div>
          ))}
        </div>

        {/* Snapshots table */}
        {shock.snapshots && shock.snapshots.length > 0 && (
          <div>
            <h3 style={{ ...font, color: Colors.textSecondary, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 8px 0' }}>
              Intraday Snapshots
            </h3>
            <div style={{ overflowX: 'auto', borderRadius: 6, border: `1px solid ${Colors.border}` }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
                <thead>
                  <tr>
                    {['Time', 'Ratio', 'Volume', 'Expected', 'Price', 'Chg%'].map(h => (
                      <th key={h} style={{
                        ...font, padding: '6px 8px', textAlign: h === 'Time' ? 'left' : 'right',
                        fontWeight: 600, color: Colors.textSecondary, borderBottom: `1px solid ${Colors.border}`,
                        background: Colors.surfaceLight, whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shock.snapshots.map((snap, i) => {
                    const isShock = snap.shock_ratio >= 2.0;
                    return (
                      <tr key={i} style={{ background: isShock ? 'rgba(239,68,68,0.06)' : 'transparent' }}>
                        <td style={{ ...font, padding: '5px 8px', color: Colors.text, borderBottom: `1px solid ${Colors.border}22` }}>{snap.time}</td>
                        <td style={{ ...font, padding: '5px 8px', textAlign: 'right', color: shockColor(snap.shock_ratio), fontWeight: 600, borderBottom: `1px solid ${Colors.border}22` }}>{snap.shock_ratio.toFixed(1)}x</td>
                        <td style={{ ...font, padding: '5px 8px', textAlign: 'right', color: Colors.text, borderBottom: `1px solid ${Colors.border}22` }}>{fmtVol(snap.current_volume)}</td>
                        <td style={{ ...font, padding: '5px 8px', textAlign: 'right', color: Colors.textMuted, borderBottom: `1px solid ${Colors.border}22` }}>{fmtVol(snap.expected_volume)}</td>
                        <td style={{ ...font, padding: '5px 8px', textAlign: 'right', color: Colors.text, borderBottom: `1px solid ${Colors.border}22` }}>{fmtLtp(snap.ltp)}</td>
                        <td style={{ ...font, padding: '5px 8px', textAlign: 'right', color: chgColor(snap.change_pct), borderBottom: `1px solid ${Colors.border}22` }}>{fmtChg(snap.change_pct)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────

export default function VolumeShocksPage() {
  if (Platform.OS !== 'web') return <Redirect href="/" />;

  const router = useRouter();
  const [shocks, setShocks] = useState<VolumeShock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState(todayIST());
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('peak_shock_ratio');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selected, setSelected] = useState<VolumeShock | null>(null);

  const fetchShocks = useCallback(async (d: string) => {
    setLoading(true);
    try {
      const data = await callApi<VolumeShock[]>('stocksGetVolumeShocks', { trade_date: d });
      setShocks(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load volume shocks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchShocks(date); }, [date, fetchShocks]);

  // Close modal on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelected(null); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const filtered = useMemo(() => {
    let list = shocks;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(s =>
        s.stock_name.toLowerCase().includes(q) ||
        s.ticker.toLowerCase().includes(q)
      );
    }
    list = [...list].sort((a, b) => {
      const av = (a as any)[sortKey] ?? -Infinity;
      const bv = (b as any)[sortKey] ?? -Infinity;
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return list;
  }, [shocks, search, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const sortArrow = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' \u25B2' : ' \u25BC') : '';

  const centered: React.CSSProperties = {
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    minHeight: '100vh', background: Colors.background,
  };

  const navLinkStyle = (active: boolean): React.CSSProperties => ({
    ...font,
    color: active ? Colors.primary : Colors.textSecondary,
    textDecoration: 'none',
    fontSize: '0.9rem',
    fontWeight: active ? 600 : 400,
    padding: '6px 14px',
    borderRadius: 6,
    background: active ? Colors.surfaceLight : 'transparent',
    cursor: 'pointer',
    border: 'none',
  });

  const columns: { key: SortKey; label: string; align?: 'right' | 'left'; render: (s: VolumeShock) => { text: string; color: string }; mobileVisible?: boolean }[] = [
    {
      key: 'peak_shock_ratio', label: 'Shock', align: 'right', mobileVisible: true,
      render: s => ({ text: s.peak_shock_ratio.toFixed(1) + 'x', color: shockColor(s.peak_shock_ratio) }),
    },
    {
      key: 'ticker', label: 'Ticker', mobileVisible: true,
      render: s => ({ text: s.ticker, color: Colors.text }),
    },
    {
      key: 'stock_name', label: 'Company',
      render: s => ({ text: s.stock_name, color: Colors.text }),
    },
    {
      key: 'sector', label: 'Sector', mobileVisible: true,
      render: s => ({ text: s.sector, color: Colors.text }),
    },
    {
      key: 'latest_ltp', label: 'Price', align: 'right',
      render: s => ({ text: fmtLtp(s.latest_ltp), color: Colors.text }),
    },
    {
      key: 'latest_change_pct', label: 'Chg%', align: 'right',
      render: s => ({ text: fmtChg(s.latest_change_pct), color: chgColor(s.latest_change_pct) }),
    },
    {
      key: 'first_detected_at', label: 'Detected', align: 'right',
      render: s => ({ text: s.first_detected_at || '-', color: Colors.textMuted }),
    },
    {
      key: 'snapshot_count', label: 'Snaps', align: 'right',
      render: s => ({ text: String(s.snapshot_count || 0), color: Colors.textMuted }),
    },
    {
      key: 'prev_day_volume', label: 'NSE Vol', align: 'right',
      render: s => ({ text: fmtVol(s.prev_day_volume), color: Colors.text }),
    },
    {
      key: 'trust_score', label: 'Trust', align: 'right',
      render: s => ({ text: s.trust_score != null ? String(s.trust_score) : '-', color: trustColor(s.trust_score) }),
    },
  ];

  const thStyle = (col: typeof columns[0]): React.CSSProperties => ({
    ...font,
    padding: '10px 12px',
    textAlign: col.align || 'left',
    cursor: 'pointer',
    userSelect: 'none',
    whiteSpace: 'nowrap',
    fontWeight: 600,
    fontSize: '0.8rem',
    color: sortKey === col.key ? Colors.primary : Colors.textSecondary,
    borderBottom: `2px solid ${Colors.border}`,
    position: 'sticky',
    top: 0,
    background: Colors.surface,
    zIndex: 1,
  });

  const tdStyle = (col: typeof columns[0]): React.CSSProperties => ({
    ...font,
    padding: '8px 12px',
    textAlign: col.align || 'left',
    fontSize: '0.85rem',
    borderBottom: `1px solid ${Colors.border}`,
    whiteSpace: 'nowrap',
  });

  return (
    <div style={{ background: Colors.background, minHeight: '100vh', position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, overflow: 'auto' }}>
      <style dangerouslySetInnerHTML={{ __html: `
        .stocks-page { max-width: 1400px; margin: 0 auto; padding: 1.5rem 1rem; box-sizing: border-box; }
        .stocks-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem; }
        .stocks-header-left { display: flex; align-items: center; gap: 1rem; }
        .stocks-filters { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; }
        .stocks-filters input { min-width: 0; box-sizing: border-box; }
        .shock-row:hover { background: ${Colors.surfaceLight} !important; }
        .shock-modal-overlay { padding: 3vh 1rem; }
        .shock-modal-card { padding: 1.5rem; }
        @media (max-width: 640px) {
          .stocks-page { padding: 1rem 0.75rem; }
          .stocks-header { flex-direction: column; align-items: flex-start; }
          .stocks-header-left { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
          .stocks-filters { flex-direction: column; gap: 0.5rem; }
          .stocks-filters input { width: 100% !important; max-width: 100% !important; }
          .desktop-only { display: none !important; }
          .shock-modal-overlay { padding: 0; }
          .shock-modal-card { border-radius: 0; max-width: 100%; min-height: 100vh; padding: 1.25rem 1rem; }
        }
      `}} />
      <div className="stocks-page">
        {/* Header */}
        <div className="stocks-header">
          <div className="stocks-header-left">
            <h1 style={{ ...font, color: Colors.text, fontSize: '1.4rem', margin: 0 }}>BSE Stocks</h1>
            <nav style={{ display: 'flex', gap: '4px' }}>
              <button style={navLinkStyle(false)} onClick={() => router.replace('/stocks/all')}>All Stocks</button>
              <button style={navLinkStyle(true)}>Volume Shocks</button>
              <button style={navLinkStyle(false)} onClick={() => router.replace('/stocks/trades')}>Trades</button>
            </nav>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ ...font, color: Colors.textMuted, fontSize: '0.85rem' }}>
              Showing <strong style={{ color: Colors.text }}>{filtered.length}</strong> shocks
            </span>
            <button
              onClick={() => fetchShocks(date)}
              disabled={loading}
              style={{
                ...font, background: Colors.surfaceLight, color: loading ? Colors.textMuted : Colors.primary,
                border: `1px solid ${Colors.border}`, borderRadius: 6,
                padding: '4px 12px', fontSize: '0.82rem', fontWeight: 500,
                cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.6 : 1,
              }}
            >
              {loading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="stocks-filters">
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            style={{
              ...font, background: Colors.surface, color: Colors.text,
              border: `1px solid ${Colors.border}`, borderRadius: 6,
              padding: '8px 12px', fontSize: '0.85rem', outline: 'none',
              colorScheme: 'dark',
            }}
          />
          <input
            type="text"
            placeholder="Search ticker or company..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              ...font, background: Colors.surface, color: Colors.text,
              border: `1px solid ${Colors.border}`, borderRadius: 6,
              padding: '8px 12px', fontSize: '0.85rem', width: 260, outline: 'none',
            }}
          />
        </div>

        {/* Content */}
        {loading ? (
          <div style={{ ...centered, minHeight: '40vh' }}>
            <ActivityIndicator size="large" color={Colors.primary} />
          </div>
        ) : error ? (
          <div style={{ ...centered, minHeight: '40vh' }}>
            <div style={{ textAlign: 'center' }}>
              <p style={{ ...font, color: Colors.error, fontSize: '1rem' }}>{error}</p>
              <button onClick={() => fetchShocks(date)}
                style={{ ...font, background: Colors.surfaceLight, color: Colors.text, border: `1px solid ${Colors.border}`, borderRadius: 6, padding: '0.4rem 1rem', cursor: 'pointer' }}>
                Retry
              </button>
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto', borderRadius: 8, border: `1px solid ${Colors.border}` }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {columns.map(col => (
                    <th key={col.key} className={col.mobileVisible ? '' : 'desktop-only'} style={thStyle(col)} onClick={() => handleSort(col.key)}>
                      {col.label}{sortArrow(col.key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((shock, i) => (
                  <tr key={shock.ticker} className="shock-row"
                    style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)', cursor: 'pointer' }}
                    onClick={() => setSelected(shock)}
                  >
                    {columns.map(col => {
                      const { text, color } = col.render(shock);
                      return (
                        <td key={col.key} className={col.mobileVisible ? '' : 'desktop-only'} style={{ ...tdStyle(col), color }}>
                          {text}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={columns.length} style={{ ...font, padding: '2rem', textAlign: 'center', color: Colors.textMuted }}>
                      No volume shocks for {date}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && <ShockModal shock={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
