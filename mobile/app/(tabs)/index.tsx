import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  SectionList,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  Pressable,
  Platform,
} from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { Colors } from '@/constants/Colors';
import useBots from '../../src/hooks/useBots';
import useScheduledJobs from '../../src/hooks/useScheduledJobs';
import useAutoRefresh from '../../src/hooks/useAutoRefresh';
import useCreateCommand from '../../src/hooks/useCreateCommand';
import useResponsive from '../../src/hooks/useResponsive';
import BotListItem from '../../src/components/BotListItem';
import ScheduledJobItem from '../../src/components/ScheduledJobItem';
import { Bot, ScheduledJob } from '../../src/types/agent';
import FontAwesome from '@expo/vector-icons/FontAwesome';

type Tab = 'bots' | 'scheduled';

type ScheduledSection = { title: string; data: ScheduledJob[] };

export default function BotsScreen() {
  const { bots, loading: botsLoading, refetch: refetchBots } = useBots();
  const { jobs, syncedAt, loading: jobsLoading, refetch: refetchJobs } = useScheduledJobs();
  const { createCommand } = useCreateCommand();
  const { isDesktop, contentWidth } = useResponsive();
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<Tab>('bots');

  const refetchAll = useCallback(async () => {
    await Promise.all([refetchBots(), refetchJobs()]);
  }, [refetchBots, refetchJobs]);

  useAutoRefresh(refetchBots, { intervalMs: 10000 });

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await refetchAll();
    setRefreshing(false);
  }, [refetchAll]);

  const handleRestartBot = useCallback(
    async (botType: string) => {
      try {
        await createCommand('restart_bot', { bot_type: botType });
        setTimeout(refetchBots, 5000);
      } catch {}
    },
    [createCommand, refetchBots]
  );

  const runningCount = bots.filter((b) => b.status === 'running').length;
  const activeJobCount = jobs.filter((j) => j.active).length;
  const loading = botsLoading && bots.length === 0;

  // Group jobs by category for scheduled view
  const categoryOrder = ['Stocks', 'Trading', 'Land', 'Aceable', 'System', 'Other', 'Stale'];
  const jobsByCategory = jobs.reduce<Record<string, ScheduledJob[]>>((acc, job) => {
    const cat = job.category;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(job);
    return acc;
  }, {});

  const scheduledSections: ScheduledSection[] = categoryOrder
    .filter((cat) => jobsByCategory[cat]?.length)
    .map((cat) => ({ title: cat, data: jobsByCategory[cat] }));

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={styles.container}>
      <View style={[styles.header, isDesktop && { paddingHorizontal: (Platform.OS === 'web' ? Math.max(0, (1440 - contentWidth) / 2) : 0) + 16 }]}>
        <View style={styles.tabBar}>
          <Pressable
            style={[styles.tab, tab === 'bots' && styles.tabActive]}
            onPress={() => setTab('bots')}
          >
            <View style={[styles.tabDot, { backgroundColor: tab === 'bots' ? Colors.success : Colors.textMuted }]} />
            <Text style={[styles.tabText, tab === 'bots' && styles.tabTextActive]}>
              {runningCount} running
            </Text>
          </Pressable>
          <Pressable
            style={[styles.tab, tab === 'scheduled' && styles.tabActive]}
            onPress={() => setTab('scheduled')}
          >
            <FontAwesome
              name="clock-o"
              size={11}
              color={tab === 'scheduled' ? Colors.primary : Colors.textMuted}
            />
            <Text style={[styles.tabText, tab === 'scheduled' && styles.tabTextActive]}>
              {activeJobCount} scheduled
            </Text>
          </Pressable>
        </View>
      </View>

      {tab === 'bots' ? (
        <FlatList
          data={bots}
          keyExtractor={(item) => item.bot_id}
          renderItem={({ item }: { item: Bot }) => (
            <BotListItem
              bot={item}
              onRestart={() => handleRestartBot(item.bot_type)}
            />
          )}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={Colors.primary} />
          }
          contentContainerStyle={[
            styles.listContent,
            isDesktop && { maxWidth: contentWidth, alignSelf: 'center', width: '100%' },
          ]}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <FontAwesome name="cogs" size={48} color={Colors.textMuted} />
              <Text style={styles.emptyText}>No bots running</Text>
            </View>
          }
        />
      ) : (
        <SectionList
          sections={scheduledSections}
          keyExtractor={(item) => `job-${item.tag}`}
          renderItem={({ item }: { item: ScheduledJob }) => (
            <ScheduledJobItem job={item} />
          )}
          renderSectionHeader={({ section }) => (
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>{section.title}</Text>
            </View>
          )}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={Colors.primary} />
          }
          contentContainerStyle={[
            styles.listContent,
            isDesktop && { maxWidth: contentWidth, alignSelf: 'center', width: '100%' },
          ]}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <FontAwesome name="clock-o" size={48} color={Colors.textMuted} />
              <Text style={styles.emptyText}>No scheduled jobs</Text>
            </View>
          }
          stickySectionHeadersEnabled={false}
        />
      )}
    </GestureHandlerRootView>
  );
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
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    borderRadius: 10,
    padding: 3,
    gap: 2,
  },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 8,
  },
  tabActive: {
    backgroundColor: Colors.background,
  },
  tabDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  tabText: {
    fontSize: 13,
    fontWeight: '500',
    color: Colors.textMuted,
  },
  tabTextActive: {
    color: Colors.text,
  },
  listContent: {
    flexGrow: 1,
    paddingTop: 8,
    paddingBottom: 20,
  },
  sectionHeader: {
    paddingHorizontal: 20,
    paddingTop: 10,
    paddingBottom: 4,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: '700',
    color: Colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 80,
    gap: 12,
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: 16,
  },
});
