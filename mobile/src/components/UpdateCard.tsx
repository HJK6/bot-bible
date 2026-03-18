import React, { useCallback, useRef } from 'react';
import { View, Text, StyleSheet, Pressable, Animated } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Colors } from '@/constants/Colors';
import { AgentChatMessage } from '../types/agent';

interface Props {
  message: AgentChatMessage;
}

function formatRelativeTime(timestamp: number): string {
  const now = Date.now();
  const diff = now - timestamp;
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString();
}

export default function UpdateCard({ message }: Props) {
  const opacity = useRef(new Animated.Value(1)).current;

  const handleCopy = useCallback(() => {
    if (!message.message) return;
    Clipboard.setStringAsync(message.message);
    Animated.sequence([
      Animated.timing(opacity, { toValue: 0.4, duration: 100, useNativeDriver: true }),
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
    ]).start();
  }, [message.message, opacity]);

  return (
    <Pressable onLongPress={handleCopy}>
      <Animated.View style={[styles.card, { opacity }]}>
        <View style={styles.accent} />
        <View style={styles.content}>
          <View style={styles.header}>
            <Text style={styles.sender}>{message.sender || 'YOUR_BOT_NAME'}</Text>
            <Text style={styles.time}>{formatRelativeTime(message.timestamp)}</Text>
          </View>
          <Text selectable style={styles.body}>{message.message}</Text>
        </View>
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    borderRadius: 12,
    marginHorizontal: 16,
    marginVertical: 6,
    overflow: 'hidden',
  },
  accent: {
    width: 4,
    backgroundColor: Colors.primary,
  },
  content: {
    flex: 1,
    padding: 14,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  sender: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.textSecondary,
  },
  time: {
    fontSize: 12,
    color: Colors.textMuted,
  },
  body: {
    fontSize: 15,
    color: Colors.text,
    lineHeight: 22,
  },
});
