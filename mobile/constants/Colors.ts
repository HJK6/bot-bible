export const Colors = {
  primary: '#6366f1',
  primaryDark: '#4f46e5',
  background: '#0f0f23',
  surface: '#1a1a2e',
  surfaceLight: '#252540',
  text: '#e2e8f0',
  textSecondary: '#94a3b8',
  textMuted: '#64748b',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
  border: '#334155',
  inboundBubble: '#4f46e5',
  outboundBubble: '#1e293b',
};

export default {
  light: {
    text: '#000',
    background: '#fff',
    tint: Colors.primary,
    tabIconDefault: '#ccc',
    tabIconSelected: Colors.primary,
  },
  dark: {
    text: Colors.text,
    background: Colors.background,
    tint: Colors.primary,
    tabIconDefault: Colors.textMuted,
    tabIconSelected: Colors.primary,
  },
};
