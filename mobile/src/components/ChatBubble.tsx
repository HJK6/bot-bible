import React, { useCallback, useRef } from 'react';
import { View, Text, Image, StyleSheet, Pressable, Animated } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Colors } from '@/constants/Colors';
import { AgentChatMessageOptimistic } from '../types/agent';

interface Props {
  message: AgentChatMessageOptimistic;
}

export default function ChatBubble({ message }: Props) {
  const isInbound = message.direction === 'inbound';
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
    <View style={[styles.row, isInbound ? styles.rowRight : styles.rowLeft]}>
      <Pressable onLongPress={handleCopy}>
        <Animated.View
          style={[
            styles.bubble,
            isInbound ? styles.inbound : styles.outbound,
            message.pending && styles.pending,
            { opacity },
          ]}
        >
          <Text style={styles.sender}>{message.sender}</Text>
          {message.image_url && (
            <Image
              source={{ uri: message.image_url }}
              style={styles.image}
            />
          )}
          {message.message ? (
            <Text selectable style={styles.text}>{message.message}</Text>
          ) : null}
          <Text style={styles.time}>
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
            {message.pending ? ' · sending...' : ''}
          </Text>
        </Animated.View>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    marginVertical: 3,
    marginHorizontal: 12,
  },
  rowRight: {
    alignItems: 'flex-end',
  },
  rowLeft: {
    alignItems: 'flex-start',
  },
  bubble: {
    maxWidth: '80%',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  inbound: {
    backgroundColor: Colors.inboundBubble,
    borderBottomRightRadius: 4,
  },
  outbound: {
    backgroundColor: Colors.outboundBubble,
    borderBottomLeftRadius: 4,
  },
  pending: {
    opacity: 0.6,
  },
  sender: {
    fontSize: 11,
    color: Colors.textMuted,
    marginBottom: 2,
  },
  image: {
    width: 200,
    height: 200,
    borderRadius: 12,
    resizeMode: 'cover',
    marginBottom: 6,
  },
  text: {
    fontSize: 15,
    color: Colors.text,
    lineHeight: 21,
  },
  time: {
    fontSize: 10,
    color: Colors.textMuted,
    marginTop: 4,
    textAlign: 'right',
  },
});
