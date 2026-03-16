import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Platform, ActivityIndicator } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { callApi } from '../../src/services/api';
import { Colors } from '@/constants/Colors';

interface Stock {
  ticker: string;
  stock_name: string;
  name_bse: string;
  sector: string;
  trust_score: number;
  close_price: number;
  market_cap: string;
  stock_pe: number | null;
  sector_pe: number | null;
  roce: number | null;
  roe: number | null;
  dividend_yield: number | null;
  pledge_pct: number;
  book_value: number | null;
  face_value: number | null;
  trade_date: string;
  bse_code: string;
  isin: string;
  prev_day_volume: number;
  net_sales_Q1: string;
  net_sales_Q2: string;
  net_sales_Q3: string;
  net_sales_Q4: string;
  net_profit_Q1: string;
  net_profit_Q2: string;
  net_profit_Q3: string;
  net_profit_Q4: string;
  governance_fy: string;
  auditor_name: string;
  auditor_fees_current: string;
  auditor_fees_previous: string;
  auditor_fees_pct_revenue: string;
  auditor_fees_breakdown: string;
  related_party_total: string;
  related_party_pct_profit: string;
  kmp_remuneration_total: string;
  kmp_remuneration_pct_profit: string;
  kmp_remuneration_breakdown: string;
}

type SortKey = keyof Stock;
type SortDir = 'asc' | 'desc';

const font: React.CSSProperties = {
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
};

function fmt(v: any, suffix = ''): string {
  if (v == null || v === '' || v === undefined) return '-';
  return String(v) + suffix;
}

function fmtNum(v: any, decimals = 1): string {
  if (v == null || v === '') return '-';
  return Number(v).toFixed(decimals);
}

function fmtPrice(v: any): string {
  if (v == null) return '-';
  return Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function fmtVol(v: any): string {
  if (v == null) return '-';
  return Number(v).toLocaleString('en-IN');
}

function fmtPct(v: any): string {
  if (v == null || v === '' || v === true || v === false) return '';
  const n = Number(v);
  if (isNaN(n)) return '';
  return (n < 1 ? (n * 100).toFixed(2) : Number(n).toFixed(2)) + '%';
}

function fmtAmtPct(amt: any, pct: any, unit = 'Cr'): string {
  const amtStr = (amt != null && amt !== '' && amt !== true) ? '\u20B9' + amt + ' ' + unit : '-';
  const pctStr = fmtPct(pct);
  if (pctStr && amtStr !== '-') return `${amtStr} (${pctStr} of revenue)`;
  if (pctStr) return pctStr;
  return amtStr;
}

function StockModal({ stock, onClose }: { stock: Stock; onClose: () => void }) {
  const trustColor = stock.trust_score >= 90 ? Colors.success : stock.trust_score >= 85 ? '#facc15' : Colors.text;

  const section = (title: string, rows: [string, string][]): React.ReactNode => (
    <div style={{ marginBottom: '1.25rem' }}>
      <h3 style={{ ...font, color: Colors.textSecondary, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 8px 0' }}>{title}</h3>
      <div className="stock-modal-grid">
        {rows.map(([label, value]) => (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: `1px solid ${Colors.border}22` }}>
            <span style={{ ...font, color: Colors.textMuted, fontSize: '0.82rem' }}>{label}</span>
            <span style={{ ...font, color: Colors.text, fontSize: '0.82rem', fontWeight: 500 }}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  );

  const quarterTable = (title: string, q1: string, q2: string, q3: string, q4: string): React.ReactNode => (
    <div style={{ marginBottom: '1.25rem' }}>
      <h3 style={{ ...font, color: Colors.textSecondary, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 8px 0' }}>{title}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '4px' }}>
        {['Q1', 'Q2', 'Q3', 'Q4'].map(q => (
          <div key={q} style={{ ...font, textAlign: 'center', color: Colors.textMuted, fontSize: '0.72rem', fontWeight: 600, padding: '4px' }}>{q}</div>
        ))}
        {[q1, q2, q3, q4].map((v, i) => (
          <div key={i} style={{ ...font, textAlign: 'center', color: Colors.text, fontSize: '0.82rem', padding: '6px', background: Colors.surfaceLight, borderRadius: 4 }}>{fmt(v)}</div>
        ))}
      </div>
    </div>
  );

  return (
    <div
      className="stock-modal-overlay"
      onClick={onClose}
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
        overflow: 'auto', zIndex: 100,
      }}
    >
      <div
        className="stock-modal-card"
        onClick={e => e.stopPropagation()}
        style={{
          background: Colors.surface, borderRadius: 12, border: `1px solid ${Colors.border}`,
          width: '100%', maxWidth: 640, position: 'relative',
        }}
      >
        {/* Close */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 12, right: 14,
            background: 'none', border: 'none', color: Colors.textMuted,
            fontSize: '1.4rem', cursor: 'pointer', lineHeight: 1, padding: 4,
          }}
        >
          &times;
        </button>

        {/* Header */}
        <div style={{ marginBottom: '1.25rem', paddingRight: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem', flexWrap: 'wrap' }}>
            <h2 style={{ ...font, color: Colors.text, fontSize: '1.2rem', margin: 0 }}>{stock.stock_name}</h2>
            <span style={{ ...font, color: Colors.primary, fontSize: '0.9rem', fontWeight: 600 }}>{stock.ticker}</span>
          </div>
          <div style={{ ...font, color: Colors.textMuted, fontSize: '0.8rem', marginTop: 4 }}>
            {stock.sector} &middot; BSE: {stock.bse_code} &middot; ISIN: {stock.isin}
          </div>
        </div>

        {/* Trust score badge */}
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
          background: Colors.surfaceLight, borderRadius: 8, padding: '8px 14px', marginBottom: '1.25rem',
        }}>
          <span style={{ ...font, color: Colors.textMuted, fontSize: '0.8rem' }}>Trust Score</span>
          <span style={{ ...font, color: trustColor, fontSize: '1.3rem', fontWeight: 700 }}>{stock.trust_score}</span>
        </div>

        {section('Price & Valuation', [
          ['Close Price', '\u20B9' + fmtPrice(stock.close_price)],
          ['Market Cap', '\u20B9' + fmt(stock.market_cap) + ' Cr'],
          ['Stock PE', fmtNum(stock.stock_pe)],
          ['Sector PE', fmtNum(stock.sector_pe)],
          ['Book Value', '\u20B9' + fmtNum(stock.book_value, 0)],
          ['Face Value', '\u20B9' + fmtNum(stock.face_value, 0)],
        ])}

        {section('Performance', [
          ['ROCE', fmtNum(stock.roce) + '%'],
          ['ROE', fmtNum(stock.roe) + '%'],
          ['Dividend Yield', fmtNum(stock.dividend_yield, 2) + '%'],
          ['Pledge %', fmtNum(stock.pledge_pct) + '%'],
          ['Prev Day Volume', fmtVol(stock.prev_day_volume)],
          ['Trade Date', fmt(stock.trade_date)],
        ])}

        {quarterTable('Net Sales (Cr)', stock.net_sales_Q1, stock.net_sales_Q2, stock.net_sales_Q3, stock.net_sales_Q4)}
        {quarterTable('Net Profit (Cr)', stock.net_profit_Q1, stock.net_profit_Q2, stock.net_profit_Q3, stock.net_profit_Q4)}

        {(stock.auditor_name || stock.governance_fy) && section('Governance' + (stock.governance_fy ? ` (FY ${stock.governance_fy})` : ''), [
          ...(stock.auditor_name ? [['Auditor', stock.auditor_name] as [string, string]] : []),
          ...(stock.auditor_fees_current ? [['Audit Fees (Current)', fmtAmtPct(stock.auditor_fees_current, stock.auditor_fees_pct_revenue)] as [string, string]] : []),
          ...(stock.auditor_fees_previous ? [['Audit Fees (Previous)', '\u20B9' + stock.auditor_fees_previous + ' Cr'] as [string, string]] : []),
          ...(stock.related_party_total && stock.related_party_total !== '0' ? [['Related Party Total', (() => {
            const pct = fmtPct(stock.related_party_pct_profit);
            const base = '\u20B9' + stock.related_party_total + ' Cr';
            return pct ? `${base} (${pct} of profit)` : base;
          })()] as [string, string]] : []),
          ...(stock.kmp_remuneration_total && fmtPct(stock.kmp_remuneration_total) !== '' ? [['KMP Remuneration', (() => {
            const amt = '\u20B9' + stock.kmp_remuneration_total + ' Cr';
            const pct = fmtPct(stock.kmp_remuneration_pct_profit);
            return pct ? `${amt} (${pct} of profit)` : amt;
          })()] as [string, string]] : []),
        ])}

        {stock.auditor_fees_breakdown && (
          <div style={{ marginBottom: '1.25rem' }}>
            <h3 style={{ ...font, color: Colors.textSecondary, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 6px 0' }}>Audit Fee Breakdown</h3>
            <p style={{ ...font, color: Colors.text, fontSize: '0.82rem', margin: 0, lineHeight: 1.5 }}>{stock.auditor_fees_breakdown}</p>
          </div>
        )}

        {stock.kmp_remuneration_breakdown && (
          <div style={{ marginBottom: '0.5rem' }}>
            <h3 style={{ ...font, color: Colors.textSecondary, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 6px 0' }}>KMP Remuneration Breakdown</h3>
            <p style={{ ...font, color: Colors.text, fontSize: '0.82rem', margin: 0, lineHeight: 1.5 }}>{stock.kmp_remuneration_breakdown}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function StocksAllPage() {
  if (Platform.OS !== 'web') return <Redirect href="/" />;

  const router = useRouter();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Stock | null>(null);

  const [search, setSearch] = useState('');
  const [sectorFilter, setSectorFilter] = useState('All Sectors');
  const [sortKey, setSortKey] = useState<SortKey>('trust_score');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const fetchStocks = useCallback(async () => {
    try {
      const data = await callApi<Stock[]>('stocksGetAll');
      setStocks(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load stocks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStocks(); }, [fetchStocks]);

  // Close modal on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelected(null); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const sectors = useMemo(() => {
    const unique = [...new Set(stocks.map(s => s.sector).filter(Boolean))].sort();
    return ['All Sectors', ...unique];
  }, [stocks]);

  const filtered = useMemo(() => {
    let list = stocks;
    if (sectorFilter !== 'All Sectors') {
      list = list.filter(s => s.sector === sectorFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(s =>
        s.stock_name.toLowerCase().includes(q) ||
        s.ticker.toLowerCase().includes(q)
      );
    }
    list = [...list].sort((a, b) => {
      const av = a[sortKey] ?? -Infinity;
      const bv = b[sortKey] ?? -Infinity;
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return list;
  }, [stocks, sectorFilter, search, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'trust_score' || key === 'roce' || key === 'roe' ? 'desc' : 'asc');
    }
  };

  const sortArrow = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' \u25B2' : ' \u25BC') : '';

  const centered: React.CSSProperties = {
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    minHeight: '100vh', background: Colors.background,
  };

  if (loading) {
    return (
      <div style={centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={centered}>
        <div style={{ textAlign: 'center' }}>
          <p style={{ ...font, color: Colors.error, fontSize: '1rem' }}>{error}</p>
          <button onClick={() => { setLoading(true); fetchStocks(); }}
            style={{ ...font, background: Colors.surfaceLight, color: Colors.text, border: `1px solid ${Colors.border}`, borderRadius: 6, padding: '0.4rem 1rem', cursor: 'pointer' }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  const columns: { key: SortKey; label: string; align?: 'right' | 'left'; fmt?: (v: any) => string; mobileVisible?: boolean }[] = [
    { key: 'trust_score', label: 'Trust', align: 'right', fmt: v => v != null ? String(v) : '-', mobileVisible: true },
    { key: 'ticker', label: 'Ticker', mobileVisible: true },
    { key: 'stock_name', label: 'Company' },
    { key: 'sector', label: 'Sector', mobileVisible: true },
    { key: 'close_price', label: 'Price', align: 'right', fmt: v => v != null ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '-' },
    { key: 'market_cap', label: 'Mkt Cap', align: 'right' },
    { key: 'stock_pe', label: 'PE', align: 'right', fmt: v => v != null ? Number(v).toFixed(1) : '-' },
    { key: 'roce', label: 'ROCE%', align: 'right', fmt: v => v != null ? Number(v).toFixed(1) : '-' },
    { key: 'roe', label: 'ROE%', align: 'right', fmt: v => v != null ? Number(v).toFixed(1) : '-' },
    { key: 'dividend_yield', label: 'Div%', align: 'right', fmt: v => v != null ? Number(v).toFixed(2) : '-' },
    { key: 'pledge_pct', label: 'Pledge%', align: 'right', fmt: v => v != null ? Number(v).toFixed(1) : '-' },
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
    color: Colors.text,
    borderBottom: `1px solid ${Colors.border}`,
    whiteSpace: 'nowrap',
  });

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

  return (
    <div style={{ background: Colors.background, minHeight: '100vh', position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, overflow: 'auto' }}>
      <style dangerouslySetInnerHTML={{ __html: `
        .stocks-page { max-width: 1400px; margin: 0 auto; padding: 1.5rem 1rem; box-sizing: border-box; }
        .stocks-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem; }
        .stocks-header-left { display: flex; align-items: center; gap: 1rem; }
        .stocks-filters { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: center; }
        .stocks-filters input, .stocks-filters select { min-width: 0; box-sizing: border-box; }
        .stock-modal-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; }
        .stock-modal-overlay { padding: 3vh 1rem; }
        .stock-modal-card { padding: 1.5rem; }
        @media (max-width: 640px) {
          .stocks-page { padding: 1rem 0.75rem; }
          .stocks-header { flex-direction: column; align-items: flex-start; }
          .stocks-header-left { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
          .stocks-filters { flex-direction: column; gap: 0.5rem; }
          .stocks-filters input, .stocks-filters select { width: 100% !important; max-width: 100% !important; }
          .stock-modal-grid { grid-template-columns: 1fr; }
          .desktop-only { display: none !important; }
          .stock-modal-overlay { padding: 0; }
          .stock-modal-card { border-radius: 0; max-width: 100%; min-height: 100vh; padding: 1.25rem 1rem; }
        }
      `}} />
      <div className="stocks-page">
        {/* Header */}
        <div className="stocks-header">
          <div className="stocks-header-left">
            <h1 style={{ ...font, color: Colors.text, fontSize: '1.4rem', margin: 0 }}>BSE Stocks</h1>
            <nav style={{ display: 'flex', gap: '4px' }}>
              <button style={navLinkStyle(true)}>All Stocks</button>
              <button style={navLinkStyle(false)} onClick={() => router.replace('/stocks/volume-shocks')}>Volume Shocks</button>
              <button style={navLinkStyle(false)} onClick={() => router.replace('/stocks/trades')}>Trades</button>
            </nav>
          </div>
          <span style={{ ...font, color: Colors.textMuted, fontSize: '0.85rem' }}>
            Showing <strong style={{ color: Colors.text }}>{filtered.length}</strong> of {stocks.length} stocks
          </span>
        </div>

        {/* Filters */}
        <div className="stocks-filters">
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
          <select
            value={sectorFilter}
            onChange={e => setSectorFilter(e.target.value)}
            style={{
              ...font, background: Colors.surface, color: Colors.text,
              border: `1px solid ${Colors.border}`, borderRadius: 6,
              padding: '8px 12px', fontSize: '0.85rem', outline: 'none', cursor: 'pointer',
            }}
          >
            {sectors.map(s => (
              <option key={s} value={s}>
                {s === 'All Sectors' ? s : `${s} (${stocks.filter(st => st.sector === s).length})`}
              </option>
            ))}
          </select>
        </div>

        {/* Table */}
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
              {filtered.map((stock, i) => (
                <tr
                  key={stock.ticker}
                  onClick={() => setSelected(stock)}
                  style={{
                    background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)',
                    cursor: 'pointer',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = Colors.surfaceLight)}
                  onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)')}
                >
                  {columns.map(col => {
                    const val = stock[col.key];
                    const display = col.fmt ? col.fmt(val) : (val != null ? String(val) : '-');
                    let cellColor = Colors.text;
                    if (col.key === 'trust_score') {
                      const ts = Number(val);
                      cellColor = ts >= 90 ? Colors.success : ts >= 85 ? '#facc15' : Colors.text;
                    }
                    return (
                      <td key={col.key} className={col.mobileVisible ? '' : 'desktop-only'} style={{ ...tdStyle(col), color: cellColor }}>
                        {display}
                      </td>
                    );
                  })}
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={columns.length} style={{ ...font, padding: '2rem', textAlign: 'center', color: Colors.textMuted }}>
                    No stocks match your filters
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && <StockModal stock={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
