import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Platform, ActivityIndicator } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { callApi } from '../../src/services/api';
import { Colors } from '@/constants/Colors';

interface Trade {
  trade_id: string;
  strategy: string;
  ticker: string;
  stock_name?: string;
  news_type: string;
  headline?: string;
  event_id: string;
  shock_ratio: number;
  sector: string;
  sector_return: number;
  buy_date: string;
  buy_price: number;
  sell_date: string;
  sell_price: number;
  return_pct: number;
  status: string;
  created_at: string;
  closed_at?: string;
}

type SortKey = 'buy_date' | 'ticker' | 'strategy' | 'shock_ratio' | 'buy_price' | 'return_pct' | 'status' | 'sector' | 'news_type';
type SortDir = 'asc' | 'desc';

const font: React.CSSProperties = {
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
};

function fmtPrice(v: number | null | undefined): string {
  if (v == null || v === 0) return '-';
  return Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || v === 0) return '-';
  const n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
}

function fmtDate(d: string): string {
  if (!d) return '-';
  const parts = d.split('-');
  if (parts.length !== 3) return d;
  return `${parts[1]}/${parts[2]}`;
}

function returnColor(v: number | null | undefined): string {
  if (v == null || v === 0) return Colors.textMuted;
  return Number(v) >= 0 ? Colors.success : Colors.error;
}

function statusBadge(status: string): { bg: string; text: string; label: string } {
  if (status === 'closed') return { bg: 'rgba(34,197,94,0.15)', text: Colors.success, label: 'Closed' };
  return { bg: 'rgba(99,102,241,0.15)', text: Colors.primary, label: 'Open' };
}

function strategyLabel(s: string): string {
  if (s === 'fo_overnight') return 'F&O';
  if (s === 'midcap_swing') return 'Swing';
  return s;
}

function shockColor(ratio: number): string {
  if (ratio >= 10) return Colors.error;
  if (ratio >= 5) return '#facc15';
  return Colors.text;
}

// ─── Modal ───────────────────────────────────────────────

function TradeModal({ trade, onClose }: { trade: Trade; onClose: () => void }) {
  const badge = statusBadge(trade.status);

  return (
    <div
      className="trade-modal-overlay"
      onClick={onClose}
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
        overflow: 'auto', zIndex: 100, padding: '3vh 1rem',
      }}
    >
      <div
        className="trade-modal-card"
        onClick={e => e.stopPropagation()}
        style={{
          background: Colors.surface, borderRadius: 12, border: `1px solid ${Colors.border}`,
          width: '100%', maxWidth: 520, position: 'relative', padding: '1.5rem',
        }}
      >
        <button onClick={onClose} style={{
          position: 'absolute', top: 12, right: 14,
          background: 'none', border: 'none', color: Colors.textMuted,
          fontSize: '1.4rem', cursor: 'pointer', lineHeight: 1, padding: 4,
        }}>&times;</button>

        {/* Header */}
        <div style={{ marginBottom: '1.25rem', paddingRight: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem', flexWrap: 'wrap' }}>
            <h2 style={{ ...font, color: Colors.text, fontSize: '1.2rem', margin: 0 }}>
              {trade.stock_name || trade.ticker}
            </h2>
            <span style={{ ...font, color: Colors.primary, fontSize: '0.9rem', fontWeight: 600 }}>{trade.ticker}</span>
            <span style={{
              ...font, fontSize: '0.72rem', fontWeight: 600, padding: '2px 8px',
              borderRadius: 4, background: badge.bg, color: badge.text,
            }}>{badge.label}</span>
          </div>
          <div style={{ ...font, color: Colors.textMuted, fontSize: '0.8rem', marginTop: 4 }}>
            {trade.sector} &middot; {strategyLabel(trade.strategy)}
          </div>
        </div>

        {/* Return highlight */}
        {trade.status === 'closed' && (
          <div style={{
            background: Colors.surfaceLight, borderRadius: 8, padding: '1rem',
            marginBottom: '1.25rem', textAlign: 'center',
          }}>
            <div style={{ ...font, color: Colors.textMuted, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              Return
            </div>
            <div style={{ ...font, color: returnColor(trade.return_pct), fontSize: '1.8rem', fontWeight: 700 }}>
              {fmtPct(trade.return_pct)}
            </div>
          </div>
        )}

        {/* Info grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '1.25rem' }}>
          {[
            ['Buy Date', fmtDate(trade.buy_date), Colors.text],
            ['Sell Date', fmtDate(trade.sell_date), Colors.text],
            ['Buy Price', `\u20B9${fmtPrice(trade.buy_price)}`, Colors.text],
            ['Sell Price', trade.sell_price ? `\u20B9${fmtPrice(trade.sell_price)}` : 'Pending', trade.sell_price ? Colors.text : Colors.textMuted],
            ['Shock Ratio', `${trade.shock_ratio.toFixed(1)}x`, shockColor(trade.shock_ratio)],
            ['Sector Return', fmtPct(trade.sector_return), returnColor(trade.sector_return)],
            ['News Type', trade.news_type || '-', Colors.text],
            ['Strategy', strategyLabel(trade.strategy), Colors.text],
          ].map(([label, value, color]) => (
            <div key={label as string} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', borderBottom: `1px solid ${Colors.border}22` }}>
              <span style={{ ...font, color: Colors.textMuted, fontSize: '0.82rem' }}>{label}</span>
              <span style={{ ...font, color: color as string, fontSize: '0.82rem', fontWeight: 500 }}>{value}</span>
            </div>
          ))}
        </div>

        {/* Headline */}
        {trade.headline && (
          <div style={{ background: Colors.surfaceLight, borderRadius: 8, padding: '0.75rem 1rem' }}>
            <div style={{ ...font, color: Colors.textMuted, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              Trigger
            </div>
            <div style={{ ...font, color: Colors.textSecondary, fontSize: '0.82rem', lineHeight: 1.5 }}>
              {trade.headline}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Summary Stats ───────────────────────────────────────

function TradeStats({ trades }: { trades: Trade[] }) {
  const closed = trades.filter(t => t.status === 'closed');
  const open = trades.filter(t => t.status === 'open');
  const wins = closed.filter(t => t.return_pct > 0);
  const avgReturn = closed.length > 0
    ? closed.reduce((sum, t) => sum + (t.return_pct || 0), 0) / closed.length
    : 0;
  const totalReturn = closed.reduce((sum, t) => sum + (t.return_pct || 0), 0);

  const stats = [
    { label: 'Total', value: String(trades.length), color: Colors.text },
    { label: 'Open', value: String(open.length), color: Colors.primary },
    { label: 'Closed', value: String(closed.length), color: Colors.success },
    { label: 'Win Rate', value: closed.length > 0 ? `${((wins.length / closed.length) * 100).toFixed(0)}%` : '-', color: Colors.text },
    { label: 'Avg Return', value: closed.length > 0 ? fmtPct(avgReturn) : '-', color: returnColor(avgReturn) },
    { label: 'Total Return', value: closed.length > 0 ? fmtPct(totalReturn) : '-', color: returnColor(totalReturn) },
  ];

  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
      {stats.map(s => (
        <div key={s.label} style={{
          background: Colors.surface, border: `1px solid ${Colors.border}`, borderRadius: 8,
          padding: '8px 14px', flex: '1 1 auto', minWidth: 90, textAlign: 'center',
        }}>
          <div style={{ ...font, color: Colors.textMuted, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {s.label}
          </div>
          <div style={{ ...font, color: s.color, fontSize: '1.1rem', fontWeight: 700, marginTop: 2 }}>
            {s.value}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────

export default function TradesPage() {
  if (Platform.OS !== 'web') return <Redirect href="/" />;

  const router = useRouter();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'closed'>('all');
  const [sortKey, setSortKey] = useState<SortKey>('buy_date');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selected, setSelected] = useState<Trade | null>(null);

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    try {
      const data = await callApi<Trade[]>('stocksGetTrades', { from_date: '2026-03-10' });
      setTrades(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load trades');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTrades(); }, [fetchTrades]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelected(null); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const filtered = useMemo(() => {
    let list = trades;
    if (statusFilter !== 'all') {
      list = list.filter(t => t.status === statusFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(t =>
        t.ticker.toLowerCase().includes(q) ||
        (t.stock_name || '').toLowerCase().includes(q) ||
        (t.news_type || '').toLowerCase().includes(q)
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
  }, [trades, search, statusFilter, sortKey, sortDir]);

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

  const columns: { key: SortKey; label: string; align?: 'right' | 'left'; render: (t: Trade) => { text: string; color: string }; mobileVisible?: boolean }[] = [
    {
      key: 'buy_date', label: 'Date', mobileVisible: true,
      render: t => ({ text: fmtDate(t.buy_date), color: Colors.text }),
    },
    {
      key: 'ticker', label: 'Ticker', mobileVisible: true,
      render: t => ({ text: t.ticker, color: Colors.text }),
    },
    {
      key: 'strategy', label: 'Type',
      render: t => ({ text: strategyLabel(t.strategy), color: Colors.textSecondary }),
    },
    {
      key: 'news_type', label: 'Signal', mobileVisible: true,
      render: t => ({ text: t.news_type || '-', color: Colors.textSecondary }),
    },
    {
      key: 'shock_ratio', label: 'Shock', align: 'right',
      render: t => ({ text: t.shock_ratio.toFixed(1) + 'x', color: shockColor(t.shock_ratio) }),
    },
    {
      key: 'buy_price', label: 'Buy', align: 'right',
      render: t => ({ text: '\u20B9' + fmtPrice(t.buy_price), color: Colors.text }),
    },
    {
      key: 'return_pct', label: 'Return', align: 'right', mobileVisible: true,
      render: t => ({
        text: t.status === 'closed' ? fmtPct(t.return_pct) : '-',
        color: t.status === 'closed' ? returnColor(t.return_pct) : Colors.textMuted,
      }),
    },
    {
      key: 'status', label: 'Status', align: 'right', mobileVisible: true,
      render: t => {
        const b = statusBadge(t.status);
        return { text: b.label, color: b.text };
      },
    },
    {
      key: 'sector', label: 'Sector',
      render: t => ({ text: t.sector, color: Colors.textMuted }),
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
        .stocks-filters input, .stocks-filters select { min-width: 0; box-sizing: border-box; }
        .trade-row:hover { background: ${Colors.surfaceLight} !important; }
        .trade-modal-overlay { padding: 3vh 1rem; }
        .trade-modal-card { padding: 1.5rem; }
        @media (max-width: 640px) {
          .stocks-page { padding: 1rem 0.75rem; }
          .stocks-header { flex-direction: column; align-items: flex-start; }
          .stocks-header-left { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
          .stocks-filters { flex-direction: column; gap: 0.5rem; }
          .stocks-filters input, .stocks-filters select { width: 100% !important; max-width: 100% !important; }
          .desktop-only { display: none !important; }
          .trade-modal-overlay { padding: 0; }
          .trade-modal-card { border-radius: 0; max-width: 100%; min-height: 100vh; padding: 1.25rem 1rem; }
        }
      `}} />
      <div className="stocks-page">
        {/* Header */}
        <div className="stocks-header">
          <div className="stocks-header-left">
            <h1 style={{ ...font, color: Colors.text, fontSize: '1.4rem', margin: 0 }}>BSE Stocks</h1>
            <nav style={{ display: 'flex', gap: '4px' }}>
              <button style={navLinkStyle(false)} onClick={() => router.replace('/stocks/all')}>All Stocks</button>
              <button style={navLinkStyle(false)} onClick={() => router.replace('/stocks/volume-shocks')}>Volume Shocks</button>
              <button style={navLinkStyle(true)}>Trades</button>
            </nav>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ ...font, color: Colors.textMuted, fontSize: '0.85rem' }}>
              Showing <strong style={{ color: Colors.text }}>{filtered.length}</strong> trades
            </span>
            <button
              onClick={fetchTrades}
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

        {/* Stats */}
        {!loading && !error && trades.length > 0 && <TradeStats trades={trades} />}

        {/* Filters */}
        <div className="stocks-filters">
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as any)}
            style={{
              ...font, background: Colors.surface, color: Colors.text,
              border: `1px solid ${Colors.border}`, borderRadius: 6,
              padding: '8px 12px', fontSize: '0.85rem', outline: 'none',
              colorScheme: 'dark',
            }}
          >
            <option value="all">All Status</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
          <input
            type="text"
            placeholder="Search ticker, company, or signal..."
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
              <button onClick={fetchTrades}
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
                {filtered.map((trade, i) => (
                  <tr key={trade.trade_id} className="trade-row"
                    style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)', cursor: 'pointer' }}
                    onClick={() => setSelected(trade)}
                  >
                    {columns.map(col => {
                      const { text, color } = col.render(trade);
                      const isStatus = col.key === 'status';
                      return (
                        <td key={col.key} className={col.mobileVisible ? '' : 'desktop-only'} style={{ ...tdStyle(col), color }}>
                          {isStatus ? (
                            <span style={{
                              ...font, fontSize: '0.75rem', fontWeight: 600, padding: '2px 8px',
                              borderRadius: 4, background: statusBadge(trade.status).bg, color,
                            }}>{text}</span>
                          ) : text}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={columns.length} style={{ ...font, padding: '2rem', textAlign: 'center', color: Colors.textMuted }}>
                      No trades found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && <TradeModal trade={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
