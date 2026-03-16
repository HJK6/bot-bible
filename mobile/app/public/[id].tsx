import React, { useState, useEffect, useCallback } from 'react';
import { Platform, ActivityIndicator } from 'react-native';
import { Redirect, useLocalSearchParams } from 'expo-router';
import { marked } from 'marked';
import { Colors } from '@/constants/Colors';

interface OutputData {
  title: string;
  content: string;
  updated_at: string;
}

const S3_BASE = 'https://bartimaeus-chat-media.s3.amazonaws.com/public';

const markdownStyles = `
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: ${Colors.text};
    line-height: 1.6;
    margin: 0;
    padding: 0;
  }
  h1, h2, h3, h4, h5, h6 {
    color: ${Colors.text};
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: 600;
  }
  h1 { font-size: 1.8em; border-bottom: 1px solid ${Colors.border}; padding-bottom: 0.3em; }
  h2 { font-size: 1.4em; border-bottom: 1px solid ${Colors.border}; padding-bottom: 0.2em; }
  h3 { font-size: 1.2em; }
  p { margin: 0.8em 0; }
  a { color: ${Colors.primary}; text-decoration: none; }
  a:hover { text-decoration: underline; }
  code {
    background: ${Colors.surfaceLight};
    padding: 0.2em 0.4em;
    border-radius: 4px;
    font-size: 0.9em;
    font-family: 'SF Mono', Menlo, monospace;
  }
  pre {
    background: ${Colors.surface};
    border: 1px solid ${Colors.border};
    border-radius: 8px;
    padding: 1em;
    overflow-x: auto;
  }
  pre code {
    background: none;
    padding: 0;
    font-size: 0.85em;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
  }
  th, td {
    border: 1px solid ${Colors.border};
    padding: 0.6em 1em;
    text-align: left;
  }
  th {
    background: ${Colors.surfaceLight};
    font-weight: 600;
  }
  tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.02);
  }
  blockquote {
    border-left: 3px solid ${Colors.primary};
    margin: 1em 0;
    padding: 0.5em 1em;
    color: ${Colors.textSecondary};
    background: rgba(99, 102, 241, 0.05);
    border-radius: 0 4px 4px 0;
  }
  ul, ol {
    padding-left: 1.5em;
    margin: 0.5em 0;
  }
  li { margin: 0.3em 0; }
  hr {
    border: none;
    border-top: 1px solid ${Colors.border};
    margin: 2em 0;
  }
  img { max-width: 100%; border-radius: 8px; }
`;

export default function PublicPage() {
  if (Platform.OS !== 'web') {
    return <Redirect href="/" />;
  }

  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<OutputData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchContent = useCallback(async () => {
    if (!id) return;
    try {
      const res = await fetch(`${S3_BASE}/${id}.json`);
      if (!res.ok) throw new Error('Page not found');
      const result = await res.json();
      setData(result);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load page');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchContent();
  }, [fetchContent]);

  const handleRefresh = () => {
    setLoading(true);
    fetchContent();
  };

  const centered: React.CSSProperties = {
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    minHeight: '100vh', background: Colors.background,
  };
  const font: React.CSSProperties = {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  };

  if (loading && !data) {
    return (
      <div style={centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div style={centered}>
        <div style={{ textAlign: 'center' }}>
          <p style={{ ...font, color: Colors.error, fontSize: '1rem' }}>{error}</p>
          <button onClick={handleRefresh} style={{ ...font, background: Colors.surfaceLight, color: Colors.text, border: `1px solid ${Colors.border}`, borderRadius: 6, padding: '0.4rem 1rem', cursor: 'pointer' }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data?.content) {
    return (
      <div style={centered}>
        <div style={{ textAlign: 'center' }}>
          <p style={{ ...font, color: Colors.textMuted, fontSize: '1rem' }}>Page not found</p>
        </div>
      </div>
    );
  }

  const htmlContent = marked.parse(data.content) as string;

  // @ts-ignore - web-only HTML elements
  return (
    <div style={{ background: Colors.background, minHeight: '100vh', overflow: 'auto', position: 'fixed', top: 0, left: 0, right: 0, bottom: 0 }}>
      <div style={{
        maxWidth: 960,
        margin: '0 auto',
        padding: '2rem 1.5rem',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.5rem',
          paddingBottom: '1rem',
          borderBottom: `1px solid ${Colors.border}`,
        }}>
          <div>
            {data.title && (
              <h1 style={{
                color: Colors.text,
                fontSize: '1.5rem',
                margin: 0,
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
              }}>
                {data.title}
              </h1>
            )}
            {data.updated_at && (
              <span style={{
                color: Colors.textMuted,
                fontSize: '0.85rem',
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
              }}>
                Updated {new Date(data.updated_at).toLocaleString()}
              </span>
            )}
          </div>
          <button
            onClick={handleRefresh}
            style={{
              background: Colors.surfaceLight,
              color: Colors.text,
              border: `1px solid ${Colors.border}`,
              borderRadius: 6,
              padding: '0.4rem 1rem',
              cursor: 'pointer',
              fontSize: '0.9rem',
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            }}
          >
            Refresh
          </button>
        </div>

        {/* Markdown Content */}
        <style dangerouslySetInnerHTML={{ __html: markdownStyles }} />
        <div dangerouslySetInnerHTML={{ __html: htmlContent }} />
      </div>
    </div>
  );
}
