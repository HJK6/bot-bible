import React, { useRef, useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, Animated, Alert } from 'react-native';
import { Swipeable } from 'react-native-gesture-handler';
import { useRouter } from 'expo-router';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Colors } from '@/constants/Colors';
import { Bot } from '../types/agent';
import StatusBadge from './StatusBadge';

interface Props {
  bot: Bot;
  onRestart?: () => void;
}

export default function BotListItem({ bot, onRestart }: Props) {
  const swipeableRef = useRef<Swipeable>(null);
  const router = useRouter();

  const handlePress = useCallback(() => {
    router.push(`/bot/${bot.bot_id}`);
  }, [bot.bot_id, router]);

  const handleRestart = useCallback(() => {
    swipeableRef.current?.close();
    Alert.alert('Restart', `Restart "${bot.title || bot.bot_name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Restart', onPress: onRestart },
    ]);
  }, [bot.title, bot.bot_name, onRestart]);

  const renderRightActions = useCallback(
    (progress: Animated.AnimatedInterpolation<number>) => {
      const translateX = progress.interpolate({
        inputRange: [0, 1],
        outputRange: [70, 0],
      });
      return (
        <Animated.View style={[styles.actionsContainer, { transform: [{ translateX }] }]}>
          <Pressable style={styles.restartAction} onPress={handleRestart}>
            <FontAwesome name="refresh" size={22} color="#fff" />
            <Text style={styles.actionText}>Restart</Text>
          </Pressable>
        </Animated.View>
      );
    },
    [handleRestart]
  );

  return (
    <Swipeable
      ref={swipeableRef}
      renderRightActions={renderRightActions}
      overshootRight={false}
      friction={2}
    >
      <Pressable style={styles.container} onPress={handlePress}>
        <View style={styles.header}>
          <View style={styles.titleRow}>
            <FontAwesome name="cog" size={14} color={Colors.textMuted} />
            <Text style={styles.title} numberOfLines={1}>
              {bot.title || bot.bot_name}
            </Text>
          </View>
          <StatusBadge status={bot.status} />
        </View>
        {bot.current_task ? (
          <Text style={styles.task} numberOfLines={1}>
            {bot.current_task}
          </Text>
        ) : null}
        <View style={styles.footer}>
          <Text style={styles.meta}>{bot.bot_type}</Text>
          {bot.last_heartbeat ? (
            <Text style={styles.meta}>{formatTimeAgo(bot.last_heartbeat)}</Text>
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 8,
    gap: 8,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.text,
    flex: 1,
  },
  task: {
    fontSize: 13,
    color: Colors.textSecondary,
    marginBottom: 6,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  meta: {
    fontSize: 11,
    color: Colors.textMuted,
  },
  actionsContainer: {
    flexDirection: 'row',
    alignItems: 'stretch',
    marginVertical: 5,
  },
  restartAction: {
    backgroundColor: Colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    width: 70,
    borderRadius: 12,
  },
  actionText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '600',
    marginTop: 4,
  },
});
