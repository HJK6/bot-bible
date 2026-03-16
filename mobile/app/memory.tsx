import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Platform, ActivityIndicator } from 'react-native';
import { Redirect } from 'expo-router';
import { marked } from 'marked';
import { callApi } from '../src/services/api';
import { Colors } from '@/constants/Colors';

interface LinkedFile {
  name: string;
  file: string;
  description: string;
}

interface IndexSection {
  id: string;
  title: string;
  summary: string;
  content: string;
  children: IndexSection[];
  linked_files?: LinkedFile[];
}

interface IndexData {
  sections: IndexSection[];
  files: { path: string; size: number; description: string }[];
  synced_at: string;
}

interface TreeNode {
  name: string;
  path?: string;
  type: 'file' | 'directory';
  children?: TreeNode[];
  size?: number;
  description?: string;
}

interface FileData {
  path: string;
  name: string;
  content: string;
  frontmatter: Record<string, any> | null;
  last_modified: string;
  size: number;
}

type SelectedItem =
  | { type: 'section'; id: string }
  | { type: 'file'; path: string };

const font: React.CSSProperties = {
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
};

const markdownStyles = `
  .memory-md {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: ${Colors.text};
    line-height: 1.6;
  }
  .memory-md h1, .memory-md h2, .memory-md h3, .memory-md h4, .memory-md h5, .memory-md h6 {
    color: ${Colors.text};
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: 600;
  }
  .memory-md h1 { font-size: 1.8em; border-bottom: 1px solid ${Colors.border}; padding-bottom: 0.3em; }
  .memory-md h2 { font-size: 1.4em; border-bottom: 1px solid ${Colors.border}; padding-bottom: 0.2em; }
  .memory-md h3 { font-size: 1.2em; }
  .memory-md p { margin: 0.8em 0; }
  .memory-md a { color: ${Colors.primary}; text-decoration: none; }
  .memory-md a:hover { text-decoration: underline; }
  .memory-md code {
    background: ${Colors.surfaceLight};
    padding: 0.2em 0.4em;
    border-radius: 4px;
    font-size: 0.9em;
    font-family: 'SF Mono', Menlo, monospace;
  }
  .memory-md pre {
    background: ${Colors.surface};
    border: 1px solid ${Colors.border};
    border-radius: 8px;
    padding: 1em;
    overflow-x: auto;
  }
  .memory-md pre code {
    background: none;
    padding: 0;
    font-size: 0.85em;
  }
  .memory-md table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
  }
  .memory-md th, .memory-md td {
    border: 1px solid ${Colors.border};
    padding: 0.6em 1em;
    text-align: left;
  }
  .memory-md th {
    background: ${Colors.surfaceLight};
    font-weight: 600;
  }
  .memory-md tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.02);
  }
  .memory-md blockquote {
    border-left: 3px solid ${Colors.primary};
    margin: 1em 0;
    padding: 0.5em 1em;
    color: ${Colors.textSecondary};
    background: rgba(99, 102, 241, 0.05);
    border-radius: 0 4px 4px 0;
  }
  .memory-md ul, .memory-md ol {
    padding-left: 1.5em;
    margin: 0.5em 0;
  }
  .memory-md li { margin: 0.3em 0; }
  .memory-md hr {
    border: none;
    border-top: 1px solid ${Colors.border};
    margin: 2em 0;
  }
  .memory-md img { max-width: 100%; border-radius: 8px; }

  .tree-item:hover {
    background: ${Colors.surfaceLight} !important;
  }
  .tree-item-selected {
    border-left: 3px solid ${Colors.primary} !important;
    background: rgba(99, 102, 241, 0.08) !important;
  }

  @media (max-width: 768px) {
    .memory-layout {
      flex-direction: column !important;
    }
    .memory-sidebar {
      width: 100% !important;
      max-height: 40vh !important;
      border-right: none !important;
      border-bottom: 1px solid ${Colors.border} !important;
    }
    .memory-content {
      min-height: 60vh !important;
    }
  }
`;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleString();
  } catch {
    return dateStr;
  }
}

// Category color dots for sections
const sectionColors: Record<string, string> = {
  environment: '#22c55e',
  preferences: '#f59e0b',
  architecture: '#6366f1',
  repos: '#3b82f6',
  coding: '#ec4899',
  monitoring: '#14b8a6',
  phone: '#8b5cf6',
  github: '#64748b',
  domain: '#f97316',
  personal: '#ef4444',
};

function getSectionColor(id: string): string {
  const lower = id.toLowerCase();
  for (const [key, color] of Object.entries(sectionColors)) {
    if (lower.includes(key)) return color;
  }
  return Colors.primary;
}

function SectionNode({
  section,
  depth,
  selectedItem,
  expandedNodes,
  onToggle,
  onSelectSection,
  onSelectFile,
}: {
  section: IndexSection;
  depth: number;
  selectedItem: SelectedItem | null;
  expandedNodes: Set<string>;
  onToggle: (id: string) => void;
  onSelectSection: (id: string) => void;
  onSelectFile: (path: string) => void;
}) {
  const isExpanded = expandedNodes.has(section.id);
  const isSelected = selectedItem?.type === 'section' && selectedItem.id === section.id;
  const hasChildren = (section.children && section.children.length > 0) || (section.linked_files && section.linked_files!.length > 0);

  return (
    <div>
      <div
        className={`tree-item ${isSelected ? 'tree-item-selected' : ''}`}
        onClick={() => {
          onSelectSection(section.id);
          if (hasChildren) onToggle(section.id);
        }}
        style={{
          padding: '8px 12px',
          paddingLeft: 12 + depth * 16,
          cursor: 'pointer',
          borderLeft: isSelected ? `3px solid ${Colors.primary}` : '3px solid transparent',
          transition: 'background 0.15s ease',
          display: 'flex',
          alignItems: 'flex-start',
          gap: 8,
        }}
      >
        {/* Expand chevron or dot */}
        <span style={{
          ...font,
          color: Colors.textMuted,
          fontSize: '0.7rem',
          width: 14,
          flexShrink: 0,
          marginTop: 4,
          userSelect: 'none',
        }}>
          {hasChildren ? (isExpanded ? '\u25BE' : '\u25B8') : ''}
        </span>
        {/* Color dot */}
        <span style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: getSectionColor(section.id),
          flexShrink: 0,
          marginTop: 6,
        }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            ...font,
            color: Colors.text,
            fontSize: '0.88rem',
            fontWeight: 500,
            lineHeight: 1.3,
          }}>
            {section.title}
          </div>
          {section.summary && (
            <div style={{
              ...font,
              color: Colors.textMuted,
              fontSize: '0.75rem',
              lineHeight: 1.3,
              marginTop: 2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {section.summary}
            </div>
          )}
        </div>
      </div>

      {/* Children and linked files */}
      {isExpanded && (
        <div style={{
          overflow: 'hidden',
          transition: 'max-height 0.2s ease',
        }}>
          {section.children?.map((child) => (
            <SectionNode
              key={child.id}
              section={child}
              depth={depth + 1}
              selectedItem={selectedItem}
              expandedNodes={expandedNodes}
              onToggle={onToggle}
              onSelectSection={onSelectSection}
              onSelectFile={onSelectFile}
            />
          ))}
          {section.linked_files?.map((lf) => {
            const isFileSelected = selectedItem?.type === 'file' && selectedItem.path === lf.file;
            return (
              <div
                key={lf.file}
                className={`tree-item ${isFileSelected ? 'tree-item-selected' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectFile(lf.file);
                }}
                style={{
                  padding: '6px 12px',
                  paddingLeft: 12 + (depth + 1) * 16 + 22,
                  cursor: 'pointer',
                  borderLeft: isFileSelected ? `3px solid ${Colors.primary}` : '3px solid transparent',
                  transition: 'background 0.15s ease',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                <span style={{ fontSize: '0.8rem', opacity: 0.6 }}>&#128196;</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{
                    ...font,
                    color: Colors.textSecondary,
                    fontSize: '0.82rem',
                  }}>
                    {lf.name}
                  </span>
                  <span style={{
                    ...font,
                    color: Colors.textMuted,
                    fontSize: '0.72rem',
                    marginLeft: 6,
                  }}>
                    {lf.file}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function FileTreeNode({
  node,
  depth,
  selectedItem,
  expandedNodes,
  onToggle,
  onSelectFile,
}: {
  node: TreeNode;
  depth: number;
  selectedItem: SelectedItem | null;
  expandedNodes: Set<string>;
  onToggle: (id: string) => void;
  onSelectFile: (path: string) => void;
}) {
  const nodeId = `tree:${node.path || node.name}`;
  const isExpanded = expandedNodes.has(nodeId);
  const isDir = node.type === 'directory';
  const isSelected = !isDir && node.path && selectedItem?.type === 'file' && selectedItem.path === node.path;

  return (
    <div>
      <div
        className={`tree-item ${isSelected ? 'tree-item-selected' : ''}`}
        onClick={() => {
          if (isDir) {
            onToggle(nodeId);
          } else if (node.path) {
            onSelectFile(node.path);
          }
        }}
        style={{
          padding: '5px 12px',
          paddingLeft: 12 + depth * 16,
          cursor: 'pointer',
          borderLeft: isSelected ? `3px solid ${Colors.primary}` : '3px solid transparent',
          transition: 'background 0.15s ease',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        {isDir && (
          <span style={{ ...font, color: Colors.textMuted, fontSize: '0.7rem', width: 14 }}>
            {isExpanded ? '\u25BE' : '\u25B8'}
          </span>
        )}
        {!isDir && <span style={{ width: 14 }} />}
        <span style={{ fontSize: '0.78rem', opacity: 0.5 }}>
          {isDir ? '\uD83D\uDCC1' : '\uD83D\uDCC4'}
        </span>
        <span style={{
          ...font,
          color: isDir ? Colors.text : Colors.textSecondary,
          fontSize: '0.82rem',
          fontWeight: isDir ? 500 : 400,
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {node.name}
        </span>
        {!isDir && node.size !== undefined && (
          <span style={{ ...font, color: Colors.textMuted, fontSize: '0.72rem', flexShrink: 0 }}>
            {formatSize(node.size)}
          </span>
        )}
      </div>
      {isDir && isExpanded && node.children?.map((child, i) => (
        <FileTreeNode
          key={child.path || `${node.name}-${i}`}
          node={child}
          depth={depth + 1}
          selectedItem={selectedItem}
          expandedNodes={expandedNodes}
          onToggle={onToggle}
          onSelectFile={onSelectFile}
        />
      ))}
    </div>
  );
}

export default function MemoryPage() {
  if (Platform.OS !== 'web') {
    return <Redirect href="/" />;
  }

  const [index, setIndex] = useState<IndexData | null>(null);
  const [fileTree, setFileTree] = useState<TreeNode[] | null>(null);
  const [selectedItem, setSelectedItem] = useState<SelectedItem | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [fileContent, setFileContent] = useState<Map<string, FileData>>(new Map());
  const [loading, setLoading] = useState(true);
  const [contentLoading, setContentLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allFilesExpanded, setAllFilesExpanded] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [indexRes, treeRes] = await Promise.all([
        callApi<IndexData>('dashGetMemoryIndex'),
        callApi<{ tree: TreeNode[] }>('dashGetMemoryTree'),
      ]);
      setIndex(indexRes);
      setFileTree(treeRes.tree);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load memory');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const fetchFileContent = useCallback(async (path: string) => {
    if (fileContent.has(path)) return;
    setContentLoading(true);
    try {
      const result = await callApi<FileData>('dashGetMemoryFile', { path });
      setFileContent((prev) => new Map(prev).set(path, result));
    } catch (err: any) {
      // store error as pseudo content
      setFileContent((prev) => new Map(prev).set(path, {
        path,
        name: path.split('/').pop() || path,
        content: `*Error loading file: ${err.message}*`,
        frontmatter: null,
        last_modified: '',
        size: 0,
      }));
    } finally {
      setContentLoading(false);
    }
  }, [fileContent]);

  const handleToggle = useCallback((id: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleSelectSection = useCallback((id: string) => {
    setSelectedItem({ type: 'section', id });
  }, []);

  const handleSelectFile = useCallback((path: string) => {
    setSelectedItem({ type: 'file', path });
    fetchFileContent(path);
  }, [fetchFileContent]);

  // Find section by id (recursive)
  const findSection = useCallback((sections: IndexSection[], id: string): IndexSection | null => {
    for (const s of sections) {
      if (s.id === id) return s;
      if (s.children) {
        const found = findSection(s.children, id);
        if (found) return found;
      }
    }
    return null;
  }, []);

  const totalFiles = index?.files?.length || 0;

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

  if (error && !index) {
    return (
      <div style={centered}>
        <div style={{ textAlign: 'center' }}>
          <p style={{ ...font, color: Colors.error, fontSize: '1rem' }}>{error}</p>
          <button onClick={() => { setLoading(true); fetchData(); }} style={{
            ...font, background: Colors.surfaceLight, color: Colors.text,
            border: `1px solid ${Colors.border}`, borderRadius: 6,
            padding: '0.4rem 1rem', cursor: 'pointer',
          }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Render content panel
  let contentPanel: React.ReactNode = null;

  if (!selectedItem) {
    contentPanel = (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        height: '100%', minHeight: 400,
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: 16, opacity: 0.3 }}>&#129504;</div>
          <p style={{ ...font, color: Colors.textMuted, fontSize: '0.95rem', margin: 0 }}>
            Select a section or file to view
          </p>
        </div>
      </div>
    );
  } else if (selectedItem.type === 'section' && index) {
    const section = findSection(index.sections, selectedItem.id);
    if (section) {
      const htmlContent = section.content ? marked.parse(section.content) as string : '';
      contentPanel = (
        <div style={{ padding: '2rem' }}>
          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <span style={{
                width: 10, height: 10, borderRadius: '50%',
                background: getSectionColor(section.id),
              }} />
              <h1 style={{
                ...font, color: Colors.text, fontSize: '1.6rem',
                margin: 0, fontWeight: 600,
              }}>
                {section.title}
              </h1>
            </div>
            {section.summary && (
              <div style={{
                ...font, display: 'inline-block',
                background: 'rgba(99, 102, 241, 0.1)',
                color: Colors.textSecondary,
                padding: '4px 12px',
                borderRadius: 20,
                fontSize: '0.82rem',
                marginTop: 4,
              }}>
                {section.summary}
              </div>
            )}
          </div>
          {section.linked_files && section.linked_files.length > 0 && (
            <div style={{
              marginBottom: '1.5rem',
              padding: '12px 16px',
              background: Colors.surface,
              borderRadius: 8,
              border: `1px solid ${Colors.border}`,
            }}>
              <div style={{
                ...font, color: Colors.textMuted, fontSize: '0.75rem',
                textTransform: 'uppercase', letterSpacing: '0.05em',
                marginBottom: 8, fontWeight: 600,
              }}>
                Linked Files
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {section.linked_files.map((lf) => (
                  <span
                    key={lf.file}
                    onClick={() => handleSelectFile(lf.file)}
                    style={{
                      ...font, cursor: 'pointer',
                      background: Colors.surfaceLight,
                      color: Colors.primary,
                      padding: '3px 10px',
                      borderRadius: 4,
                      fontSize: '0.8rem',
                      transition: 'background 0.15s',
                    }}
                  >
                    {lf.name}
                  </span>
                ))}
              </div>
            </div>
          )}
          {htmlContent && (
            <div className="memory-md" dangerouslySetInnerHTML={{ __html: htmlContent }} />
          )}
        </div>
      );
    }
  } else if (selectedItem.type === 'file') {
    const file = fileContent.get(selectedItem.path);
    if (contentLoading && !file) {
      contentPanel = (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', minHeight: 400 }}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </div>
      );
    } else if (file) {
      const htmlContent = file.content ? marked.parse(file.content) as string : '';
      contentPanel = (
        <div style={{ padding: '2rem' }}>
          {/* File header */}
          <div style={{
            marginBottom: '1.5rem',
            paddingBottom: '1rem',
            borderBottom: `1px solid ${Colors.border}`,
          }}>
            <h1 style={{
              ...font, color: Colors.text, fontSize: '1.5rem',
              margin: 0, fontWeight: 600,
            }}>
              {file.name}
            </h1>
            <div style={{
              display: 'flex', gap: 16, marginTop: 8, flexWrap: 'wrap',
            }}>
              <span style={{
                ...font, color: Colors.textMuted, fontSize: '0.8rem',
                display: 'flex', alignItems: 'center', gap: 4,
              }}>
                &#128195; {file.path}
              </span>
              {file.size > 0 && (
                <span style={{ ...font, color: Colors.textMuted, fontSize: '0.8rem' }}>
                  {formatSize(file.size)}
                </span>
              )}
              {file.last_modified && (
                <span style={{ ...font, color: Colors.textMuted, fontSize: '0.8rem' }}>
                  Modified {formatDate(file.last_modified)}
                </span>
              )}
            </div>
          </div>

          {/* Frontmatter */}
          {file.frontmatter && Object.keys(file.frontmatter).length > 0 && (
            <div style={{
              marginBottom: '1.5rem',
              padding: '12px 16px',
              background: Colors.surface,
              borderRadius: 8,
              border: `1px solid ${Colors.border}`,
            }}>
              <div style={{
                ...font, color: Colors.textMuted, fontSize: '0.75rem',
                textTransform: 'uppercase', letterSpacing: '0.05em',
                marginBottom: 8, fontWeight: 600,
              }}>
                Metadata
              </div>
              {Object.entries(file.frontmatter).map(([key, val]) => (
                <div key={key} style={{
                  display: 'flex', gap: 8, marginBottom: 4,
                }}>
                  <span style={{ ...font, color: Colors.textSecondary, fontSize: '0.82rem', fontWeight: 500 }}>
                    {key}:
                  </span>
                  <span style={{ ...font, color: Colors.text, fontSize: '0.82rem' }}>
                    {String(val)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Markdown body */}
          {htmlContent && (
            <div className="memory-md" dangerouslySetInnerHTML={{ __html: htmlContent }} />
          )}
        </div>
      );
    }
  }

  // @ts-ignore - web-only HTML elements
  return (
    <div style={{
      background: Colors.background,
      minHeight: '100vh',
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      display: 'flex',
      flexDirection: 'column',
    }}>
      <style dangerouslySetInnerHTML={{ __html: markdownStyles }} />

      {/* Header */}
      <div style={{
        padding: '16px 24px',
        borderBottom: `1px solid ${Colors.border}`,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: Colors.surface,
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h1 style={{
            ...font, color: Colors.text, fontSize: '1.3rem',
            margin: 0, fontWeight: 600,
          }}>
            Memory
          </h1>
          <span style={{
            ...font, background: Colors.surfaceLight,
            color: Colors.textSecondary,
            padding: '2px 10px',
            borderRadius: 12,
            fontSize: '0.78rem',
          }}>
            {totalFiles} files
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {index?.synced_at && (
            <span style={{ ...font, color: Colors.textMuted, fontSize: '0.8rem' }}>
              Synced {formatDate(index.synced_at)}
            </span>
          )}
          <button
            onClick={() => { setLoading(true); fetchData(); }}
            style={{
              ...font, background: Colors.surfaceLight, color: Colors.text,
              border: `1px solid ${Colors.border}`, borderRadius: 6,
              padding: '6px 14px', cursor: 'pointer', fontSize: '0.85rem',
              transition: 'background 0.15s',
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Main layout */}
      <div className="memory-layout" style={{
        display: 'flex',
        flex: 1,
        overflow: 'hidden',
      }}>
        {/* Left panel — Tree Navigator */}
        <div className="memory-sidebar" style={{
          width: 320,
          flexShrink: 0,
          borderRight: `1px solid ${Colors.border}`,
          overflowY: 'auto',
          background: Colors.background,
        }}>
          {/* Sections */}
          {index?.sections?.map((section) => (
            <SectionNode
              key={section.id}
              section={section}
              depth={0}
              selectedItem={selectedItem}
              expandedNodes={expandedNodes}
              onToggle={handleToggle}
              onSelectSection={handleSelectSection}
              onSelectFile={handleSelectFile}
            />
          ))}

          {/* Divider */}
          <div style={{
            margin: '12px 12px 0',
            borderTop: `1px solid ${Colors.border}`,
            paddingTop: 12,
          }}>
            <div
              className="tree-item"
              onClick={() => setAllFilesExpanded(!allFilesExpanded)}
              style={{
                padding: '8px 12px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                transition: 'background 0.15s ease',
              }}
            >
              <span style={{ ...font, color: Colors.textMuted, fontSize: '0.7rem', width: 14 }}>
                {allFilesExpanded ? '\u25BE' : '\u25B8'}
              </span>
              <span style={{
                ...font, color: Colors.textMuted, fontSize: '0.78rem',
                textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600,
              }}>
                All Files
              </span>
              <span style={{
                ...font, color: Colors.textMuted, fontSize: '0.72rem',
                marginLeft: 'auto',
              }}>
                {totalFiles}
              </span>
            </div>
          </div>

          {allFilesExpanded && fileTree && (
            <div style={{ paddingBottom: 24 }}>
              {fileTree.map((node) => (
                <FileTreeNode
                  key={node.path}
                  node={node}
                  depth={1}
                  selectedItem={selectedItem}
                  expandedNodes={expandedNodes}
                  onToggle={handleToggle}
                  onSelectFile={handleSelectFile}
                />
              ))}
            </div>
          )}

          {/* Bottom padding */}
          <div style={{ height: 24 }} />
        </div>

        {/* Right panel — Content Viewer */}
        <div className="memory-content" style={{
          flex: 1,
          overflowY: 'auto',
          background: Colors.background,
        }}>
          {contentPanel}
        </div>
      </div>
    </div>
  );
}
