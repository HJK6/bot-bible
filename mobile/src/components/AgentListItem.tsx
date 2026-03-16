import React, { useRef, useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, Animated, Alert } from 'react-native';
import { Swipeable } from 'react-native-gesture-handler';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Colors } from '@/constants/Colors';
import { Agent } from '../types/agent';
import StatusBadge from './StatusBadge';

interface Props {
  agent: Agent;
  onPress: () => void;
  onStop?: () => void;
  onDelete?: () => void;
  hasUnread?: boolean;
}

export default function AgentListItem({ agent, onPress, onStop, onDelete, hasUnread }: Props) {
  const swipeableRef = useRef<Swipeable>(null);
  const isActive = agent.status === 'running' || agent.status === 'idle';

  const handleStop = useCallback(() => {
    swipeableRef.current?.close();
    Alert.alert('Stop Agent', `Stop "${agent.title || agent.agent_name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Stop', style: 'destructive', onPress: onStop },
    ]);
  }, [agent.title, agent.agent_name, onStop]);

  const handleDelete = useCallback(() => {
    swipeableRef.current?.close();
    Alert.alert('Delete Agent', `Delete "${agent.title || agent.agent_name}"? This cannot be undone.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: onDelete },
    ]);
  }, [agent.title, agent.agent_name, onDelete]);

  const renderRightActions = useCallback(
    (progress: Animated.AnimatedInterpolation<number>) => {
      const translateX = progress.interpolate({
        inputRange: [0, 1],
        outputRange: [isActive ? 140 : 70, 0],
      });

      return (
        <Animated.View style={[styles.actionsContainer, { transform: [{ translateX }] }]}>
          {isActive && (
            <Pressable style={styles.stopAction} onPress={handleStop}>
              <FontAwesome name="stop-circle" size={22} color="#fff" />
              <Text style={styles.actionText}>Stop</Text>
            </Pressable>
          )}
          <Pressable style={styles.deleteAction} onPress={handleDelete}>
            <FontAwesome name="trash" size={22} color="#fff" />
            <Text style={styles.actionText}>Delete</Text>
          </Pressable>
        </Animated.View>
      );
    },
    [isActive, handleStop, handleDelete]
  );

  return (
    <Swipeable
      ref={swipeableRef}
      renderRightActions={renderRightActions}
      overshootRight={false}
      friction={2}
    >
      <Pressable
        style={({ pressed }) => [styles.container, pressed && styles.pressed]}
        onPress={onPress}
      >
        <View style={styles.header}>
          <View style={styles.titleRow}>
            {hasUnread && <View style={styles.unreadDot} />}
            <Text style={styles.title} numberOfLines={1}>
              {agent.title || agent.agent_name || agent.agent_id.slice(0, 8)}
            </Text>
          </View>
          <View style={styles.badges}>
            <StatusBadge status={agent.status} />
            {agent.interactive && (
              <FontAwesome name="comment" size={14} color={Colors.primary} />
            )}
          </View>
        </View>
        {agent.goal ? (
          <Text style={styles.goal} numberOfLines={2}>
            {agent.goal}
          </Text>
        ) : null}
        <View style={styles.footer}>
          <View style={styles.footerLeft}>
            <Text style={styles.meta}>
              {agent.agent_type}
            </Text>
            {agent.tmux_session ? (
              <View style={styles.tmuxBadge}>
                <FontAwesome name="terminal" size={9} color="#22c55e" />
                <Text style={styles.tmuxText}>
                  {agent.tmux_session}:{agent.tmux_window}
                </Text>
              </View>
            ) : null}
          </View>
          {agent.last_heartbeat ? (
            <Text style={styles.meta}>
              {formatTimeAgo(agent.last_heartbeat)}
            </Text>
          ) : null}
        </View>
      </Pressable>
    </Swipeable>
  );
}

function formatTimeAgo(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    marginHorizontal: 16,
    marginVertical: 5,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  pressed: {
    opacity: 0.7,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  badges: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 8,
    gap: 8,
  },
  unreadDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: Colors.primary,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.text,
    flex: 1,
  },
  goal: {
    fontSize: 13,
    color: Colors.textSecondary,
    marginBottom: 8,
    lineHeight: 18,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  footerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  meta: {
    fontSize: 11,
    color: Colors.textMuted,
  },
  tmuxBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#22c55e18',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
  },
  tmuxText: {
    fontSize: 10,
    color: '#22c55e',
    fontWeight: '600',
  },
  actionsContainer: {
    flexDirection: 'row',
    alignItems: 'stretch',
    marginVertical: 5,
  },
  stopAction: {
    backgroundColor: Colors.warning,
    justifyContent: 'center',
    alignItems: 'center',
    width: 70,
    borderTopLeftRadius: 12,
    borderBottomLeftRadius: 12,
  },
  deleteAction: {
    backgroundColor: Colors.error,
    justifyContent: 'center',
    alignItems: 'center',
    width: 70,
    borderTopRightRadius: 12,
    borderBottomRightRadius: 12,
  },
  actionText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '600',
    marginTop: 4,
  },
});
