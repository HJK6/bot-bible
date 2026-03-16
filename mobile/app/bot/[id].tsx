import React, { useCallback, useRef } from 'react';
import {
  View,
  Text,
  ScrollView,
  FlatList,
  StyleSheet,
  Platform,
  Pressable,
  RefreshControl,
  Animated,
  Alert,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { useLocalSearchParams, useNavigation } from 'expo-router';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Colors } from '@/constants/Colors';
import useBots from '../../src/hooks/useBots';
import useAgentLogs from '../../src/hooks/useAgentLogs';
import useAutoRefresh from '../../src/hooks/useAutoRefresh';
import useResponsive from '../../src/hooks/useResponsive';
import useCreateCommand from '../../src/hooks/useCreateCommand';
import StatusBadge from '../../src/components/StatusBadge';
import { AgentLog } from '../../src/types/agent';

type TabName = 'info' | 'logs';

export default function BotDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const navigation = useNavigation();
  const { bots, refetch: refetchBots } = useBots();
  const { logs, refetch: refetchLogs } = useAgentLogs(id);
  const { createCommand } = useCreateCommand();
  const { isDesktop, contentWidth } = useResponsive();
  const [activeTab, setActiveTab] = React.useState<TabName>('info');
  const [refreshing, setRefreshing] = React.useState(false);

  const bot = bots.find((b) => b.bot_id === id);

  React.useEffect(() => {
    navigation.setOptions({
      title: bot?.title || bot?.bot_name || id?.slice(0, 8),
      headerRight: () => (bot ? <StatusBadge status={bot.status} /> : null),
    });
  }, [navigation, bot, id]);

  useAutoRefresh(refetchBots, { intervalMs: 10000 });
  useAutoRefresh(refetchLogs, { intervalMs: 10000, enabled: activeTab === 'logs' });

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([refetchBots(), refetchLogs()]);
    setRefreshing(false);
  }, [refetchBots, refetchLogs]);

  const handleRestart = useCallback(() => {
    if (!bot) return;
    Alert.alert('Restart', `Restart "${bot.title || bot.bot_name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Restart',
        onPress: async () => {
          await createCommand('restart_bot', { bot_type: bot.bot_type });
          setTimeout(refetchBots, 5000);
        },
      },
    ]);
  }, [bot, createCommand, refetchBots]);

  const wrapDesktop = (children: React.ReactNode) =>
    isDesktop ? (
      <View style={{ maxWidth: contentWidth, alignSelf: 'center', width: '100%', flex: 1 }}>
        {children}
      </View>
    ) : (
      <>{children}</>
    );

  if (!bot) {
    return (
      <View style={styles.centered}>
        <Text style={styles.emptyText}>Bot not found</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Tab bar */}
      <View style={[styles.tabBar, isDesktop && { maxWidth: contentWidth, alignSelf: 'center', width: '100%' }]}>
        {(['info', 'logs'] as TabName[]).map((tab) => (
          <Pressable
            key={tab}
            style={[styles.tab, activeTab === tab && styles.tabActive, isDesktop && styles.tabDesktop]}
            onPress={() => setActiveTab(tab)}
          >
            <Text style={[styles.tabText, activeTab === tab && styles.tabTextActive]}>
              {tab === 'info' ? 'Info' : `Logs (${logs.length})`}
            </Text>
          </Pressable>
        ))}
      </View>

      {activeTab === 'info' &&
        wrapDesktop(
          <ScrollView
            style={styles.infoContainer}
            contentContainerStyle={styles.infoContent}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={Colors.primary} />
            }
          >
            {/* Status row */}
            <View style={styles.statusRow}>
              <StatusBadge status={bot.status} />
              <Text style={styles.typeBadge}>{bot.bot_type}</Text>
              {bot.started_at && <Text style={styles.metaText}>{formatUptime(bot.started_at)}</Text>}
            </View>

            {/* Current task */}
            {bot.current_task ? (
              <View style={styles.field}>
                <Text style={styles.fieldLabel}>Current Task</Text>
                <Text selectable style={[styles.fieldValue, { fontStyle: 'italic' }]}>{bot.current_task}</Text>
              </View>
            ) : null}

            {/* Metrics */}
            {bot.metrics && Object.keys(bot.metrics).length > 0 && (
              <View style={styles.field}>
                <Text style={styles.fieldLabel}>Metrics</Text>
                <MetricsDisplay metrics={bot.metrics} isDesktop={isDesktop} />
              </View>
            )}

            {/* Details */}
            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Details</Text>
              <View style={[styles.metaGrid, isDesktop && styles.metaGridDesktop]}>
                {bot.started_at && <MetaItem label="Started" value={new Date(bot.started_at).toLocaleString()} />}
                {bot.last_heartbeat && <MetaItem label="Last Heartbeat" value={new Date(bot.last_heartbeat).toLocaleString()} />}
                {bot.host && <MetaItem label="Host" value={bot.host} />}
                {bot.pid > 0 && <MetaItem label="PID" value={String(bot.pid)} />}
              </View>
            </View>

            {/* Restart action */}
            <Pressable style={styles.restartButton} onPress={handleRestart}>
              <FontAwesome name="refresh" size={14} color={Colors.primary} />
              <Text style={styles.restartText}>Restart</Text>
            </Pressable>
          </ScrollView>
        )}

      {activeTab === 'logs' && wrapDesktop(<LogsTab logs={logs} />)}
    </View>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metaItem}>
      <Text style={styles.metaLabel}>{label}</Text>
      <Text selectable style={styles.metaValue}>{value}</Text>
    </View>
  );
}

function MetricsDisplay({ metrics, isDesktop }: { metrics: Record<string, any>; isDesktop: boolean }) {
  const scalarEntries = Object.entries(metrics).filter(([, v]) => !Array.isArray(v));
  const listEntries = Object.entries(metrics).filter(([, v]) => Array.isArray(v));

  return (
    <View style={styles.metricsContainer}>
      {scalarEntries.length > 0 && (
        <View style={[styles.metricScalarGrid, isDesktop && styles.metricScalarGridDesktop]}>
          {scalarEntries.map(([key, value]) => (
            <View key={key} style={styles.metricCard}>
              <Text style={styles.metricLabel}>{key.replace(/_/g, ' ')}</Text>
              <Text style={styles.metricValue}>{String(value)}</Text>
            </View>
          ))}
        </View>
      )}
      {listEntries.map(([key, value]) => (
        <TaskList key={key} label={key} items={value as string[]} />
      ))}
    </View>
  );
}

function TaskList({ label, items }: { label: string; items: string[] }) {
  return (
    <View style={styles.taskList}>
      <Text style={styles.metricLabel}>{label.replace(/_/g, ' ')}</Text>
      {items.map((item, i) => {
        const isDone = item.startsWith('[done]');
        const isActive = item.startsWith('>>');
        const isFailed = item.includes('FAILED');
        const displayText = item.replace(/^\[done\]\s*|^\[pending\]\s*|^>>\s*/g, '');
        return (
          <View key={i} style={[styles.taskItem, isActive && styles.taskItemActive]}>
            <FontAwesome
              name={isDone ? 'check-circle' : isActive ? 'play-circle' : isFailed ? 'exclamation-circle' : 'circle-o'}
              size={12}
              color={isDone ? Colors.success : isActive ? Colors.primary : isFailed ? Colors.error : Colors.textMuted}
            />
            <Text
              style={[
                styles.taskText,
                isDone && styles.taskDone,
                isActive && styles.taskActiveText,
                isFailed && styles.taskFailed,
              ]}
              numberOfLines={2}
            >
              {displayText}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

function LogsTab({ logs }: { logs: AgentLog[] }) {
  const LEVEL_COLORS: Record<string, string> = {
    info: Colors.primary,
    warning: Colors.warning,
    error: Colors.error,
  };

  return (
    <FlatList
      data={logs}
      keyExtractor={(item, idx) => `${item.timestamp}-${idx}`}
      renderItem={({ item }) => <LogRow item={item} levelColors={LEVEL_COLORS} />}
      contentContainerStyle={styles.logsContent}
      ListEmptyComponent={
        <View style={styles.centered}>
          <Text style={styles.emptyText}>No logs available</Text>
        </View>
      }
    />
  );
}

function LogRow({ item, levelColors }: { item: AgentLog; levelColors: Record<string, string> }) {
  const opacity = useRef(new Animated.Value(1)).current;

  const handleCopy = useCallback(() => {
    let text = item.message;
    if (item.metadata && Object.keys(item.metadata).length > 0) {
      text += '\n' + JSON.stringify(item.metadata, null, 2);
    }
    Clipboard.setStringAsync(text);
    Animated.sequence([
      Animated.timing(opacity, { toValue: 0.4, duration: 100, useNativeDriver: true }),
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
    ]).start();
  }, [item, opacity]);

  return (
    <Pressable onLongPress={handleCopy}>
      <Animated.View style={[styles.logRow, { borderLeftColor: levelColors[item.level] || Colors.textMuted, opacity }]}>
        <View style={styles.logHeader}>
          <Text style={styles.logTime}>{new Date(item.timestamp).toLocaleTimeString()}</Text>
          <Text style={[styles.logLevel, { color: levelColors[item.level] || Colors.textMuted }]}>
            {item.level}
          </Text>
        </View>
        <Text selectable style={styles.logMessage}>{item.message}</Text>
        {item.metadata && Object.keys(item.metadata).length > 0 && (
          <Text selectable style={styles.logMeta}>{JSON.stringify(item.metadata, null, 2)}</Text>
        )}
      </Animated.View>
    </Pressable>
  );
}

function formatUptime(startedAt: string): string {
  const diff = Date.now() - new Date(startedAt).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  const remainMins = mins % 60;
  if (hours < 24) return `${hours}h ${remainMins}m`;
  const days = Math.floor(hours / 24);
  const remainHours = hours % 24;
  return `${days}d ${remainHours}h`;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: 15,
  },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  tab: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
  },
  tabDesktop: {
    flex: 0,
    paddingHorizontal: 24,
  },
  tabActive: {
    borderBottomWidth: 2,
    borderBottomColor: Colors.primary,
  },
  tabText: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.textMuted,
  },
  tabTextActive: {
    color: Colors.primary,
  },
  infoContainer: {
    flex: 1,
  },
  infoContent: {
    padding: 16,
    gap: 16,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  typeBadge: {
    fontSize: 12,
    color: Colors.textSecondary,
    backgroundColor: Colors.surfaceLight,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
    overflow: 'hidden',
  },
  metaText: {
    fontSize: 12,
    color: Colors.textMuted,
  },
  field: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  fieldLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: Colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  fieldValue: {
    fontSize: 15,
    color: Colors.text,
    lineHeight: 22,
  },
  metaGrid: {
    gap: 8,
  },
  metaGridDesktop: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
  },
  metaItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    minWidth: 200,
  },
  metaLabel: {
    fontSize: 13,
    color: Colors.textMuted,
  },
  metaValue: {
    fontSize: 13,
    color: Colors.textSecondary,
  },
  metricsContainer: {
    gap: 8,
  },
  metricScalarGrid: {
    gap: 8,
  },
  metricScalarGridDesktop: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  metricCard: {
    backgroundColor: Colors.surfaceLight,
    borderRadius: 8,
    padding: 10,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    minWidth: 140,
  },
  metricLabel: {
    fontSize: 12,
    color: Colors.textSecondary,
    textTransform: 'capitalize',
  },
  metricValue: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.text,
  },
  taskList: {
    gap: 4,
    marginTop: 4,
  },
  taskItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 3,
    paddingHorizontal: 4,
  },
  taskItemActive: {
    borderLeftWidth: 2,
    borderLeftColor: Colors.primary,
    paddingLeft: 8,
  },
  taskText: {
    fontSize: 13,
    color: Colors.textSecondary,
    flex: 1,
  },
  taskDone: {
    textDecorationLine: 'line-through',
    color: Colors.textMuted,
  },
  taskActiveText: {
    fontWeight: '700',
    color: Colors.primary,
  },
  taskFailed: {
    color: Colors.error,
  },
  restartButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: Colors.primary + '15',
    borderWidth: 1,
    borderColor: Colors.primary + '40',
    borderRadius: 12,
    padding: 14,
  },
  restartText: {
    color: Colors.primary,
    fontSize: 15,
    fontWeight: '600',
  },
  logsContent: {
    padding: 8,
    flexGrow: 1,
  },
  logRow: {
    backgroundColor: Colors.surface,
    borderRadius: 8,
    padding: 10,
    marginVertical: 2,
    borderLeftWidth: 3,
  },
  logHeader: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 4,
  },
  logTime: {
    fontSize: 11,
    color: Colors.textMuted,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  logLevel: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  logMessage: {
    fontSize: 13,
    color: Colors.text,
    lineHeight: 19,
  },
  logMeta: {
    fontSize: 11,
    color: Colors.textMuted,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginTop: 4,
  },
});
