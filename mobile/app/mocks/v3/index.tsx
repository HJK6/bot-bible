import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, Dimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { Colors } from '@/constants/Colors';
import { MOCK_AGENTS, getMockLogs } from '../../../src/data/mockData';
import { Agent, AgentLog } from '../../../src/types/agent';
import useResponsive from '../../../src/hooks/useResponsive';
import { Ionicons, FontAwesome } from '@expo/vector-icons';

type StatusCounts = {
  running: number;
  idle: number;
  failed: number;
  total: number;
};

type ActivityItem = {
  agentName: string;
  timestamp: number;
  level: 'info' | 'warning' | 'error';
  message: string;
};

export default function CommandCenterHome() {
  const router = useRouter();
  const { isDesktop } = useResponsive();
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 60000);
    return () => clearInterval(timer);
  }, []);

  // Calculate status counts
  const statusCounts: StatusCounts = MOCK_AGENTS.reduce((acc, agent) => {
    if (agent.status === 'running') acc.running++;
    if (agent.status === 'idle') acc.idle++;
    if (agent.status === 'failed') acc.failed++;
    acc.total++;
    return acc;
  }, { running: 0, idle: 0, failed: 0, total: 0 });

  // Get activity feed
  const getActivityFeed = (): ActivityItem[] => {
    const allLogs: Array<{ agent: Agent; log: AgentLog }> = [];

    MOCK_AGENTS.forEach(agent => {
      const logs = getMockLogs(agent.agent_id);
      logs.slice(-3).forEach(log => {
        allLogs.push({ agent, log });
      });
    });

    return allLogs
      .sort((a, b) => new Date(b.log.timestamp).getTime() - new Date(a.log.timestamp).getTime())
      .slice(0, 10)
      .map(({ agent, log }) => ({
        agentName: agent.title,
        timestamp: log.timestamp,
        level: log.level,
        message: log.message
      }));
  };

  const activityFeed = getActivityFeed();

  const formatUptime = (agent: Agent): string => {
    if (agent.status === 'completed' || agent.status === 'failed') {
      const ended = new Date(agent.last_heartbeat);
      const now = new Date();
      const diffMs = now.getTime() - ended.getTime();
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      return `ended ${diffHours}h ago`;
    }

    const started = new Date(agent.started_at);
    const now = new Date();
    const diffMs = now.getTime() - started.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    return `${diffHours}h ${diffMins}m`;
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'running': return Colors.success;
      case 'idle': return Colors.warning;
      case 'failed': return Colors.error;
      case 'stale': return Colors.error;
      case 'completed': return Colors.textMuted;
      default: return Colors.textSecondary;
    }
  };

  const getLevelColor = (level: string): string => {
    switch (level) {
      case 'error': return Colors.error;
      case 'warning': return Colors.warning;
      default: return Colors.primary;
    }
  };

  const formatTimestamp = (timestamp: number | string): string => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  };

  const renderStatCard = (value: number, label: string, color: string) => (
    <View style={[styles.statCard, { borderColor: Colors.border }]} key={label}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );

  const renderAgentRow = (agent: Agent) => {
    const statusColor = getStatusColor(agent.status);
    const currentTask = agent.metrics?.current_task || agent.goal;
    const isActive = agent.status === 'running';

    return (
      <TouchableOpacity
        key={agent.agent_id}
        style={styles.agentRow}
        onPress={() => router.push(`/mocks/v3/agent/${agent.agent_id}`)}
      >
        <View style={styles.agentLeft}>
          <View style={[
            styles.statusDot,
            { backgroundColor: statusColor },
            isActive && { shadowColor: statusColor, shadowRadius: 4, shadowOpacity: 0.6 }
          ]} />
        </View>

        <View style={styles.agentCenter}>
          <Text style={styles.agentTitle}>{agent.title}</Text>
          <Text style={styles.agentTask} numberOfLines={1}>{currentTask}</Text>
        </View>

        <View style={styles.agentRight}>
          <Text style={styles.agentUptime}>{formatUptime(agent)}</Text>
          {isActive && (
            <FontAwesome name="refresh" size={12} color={Colors.primary} style={styles.activityIcon} />
          )}
        </View>
      </TouchableOpacity>
    );
  };

  const renderActivityItem = (item: ActivityItem, index: number) => {
    const levelColor = getLevelColor(item.level);

    return (
      <View key={index} style={[styles.activityItem, { borderLeftColor: levelColor }]}>
        <View style={[styles.activityDot, { backgroundColor: levelColor }]} />
        <View style={styles.activityContent}>
          <View style={styles.activityHeader}>
            <Text style={styles.activityAgent}>{item.agentName}</Text>
            <Text style={styles.activityTime}>{formatTimestamp(item.timestamp)}</Text>
          </View>
          <Text style={styles.activityMessage} numberOfLines={2}>{item.message}</Text>
        </View>
      </View>
    );
  };

  const renderMobileLayout = () => (
    <ScrollView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Command Center</Text>
        <Text style={styles.headerTime}>
          {currentTime.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
        </Text>
      </View>

      {/* Stats */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.statsRow}>
        {renderStatCard(statusCounts.running, 'RUNNING', Colors.success)}
        {renderStatCard(statusCounts.idle, 'IDLE', Colors.warning)}
        {renderStatCard(statusCounts.failed, 'FAILED', Colors.error)}
        {renderStatCard(statusCounts.total, 'TOTAL', Colors.text)}
      </ScrollView>

      {/* Agent List */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>AGENTS</Text>
        {MOCK_AGENTS.map(renderAgentRow)}
      </View>

      {/* Activity Feed */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>RECENT ACTIVITY</Text>
        {activityFeed.map(renderActivityItem)}
      </View>
    </ScrollView>
  );

  const renderDesktopLayout = () => (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Command Center</Text>
        <Text style={styles.headerTime}>
          {currentTime.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
        </Text>
      </View>

      <View style={styles.desktopContent}>
        {/* Left Column */}
        <ScrollView style={styles.desktopLeft}>
          {/* Stats */}
          <View style={styles.statsRow}>
            {renderStatCard(statusCounts.running, 'RUNNING', Colors.success)}
            {renderStatCard(statusCounts.idle, 'IDLE', Colors.warning)}
            {renderStatCard(statusCounts.failed, 'FAILED', Colors.error)}
            {renderStatCard(statusCounts.total, 'TOTAL', Colors.text)}
          </View>

          {/* Activity Feed */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>RECENT ACTIVITY</Text>
            {activityFeed.map(renderActivityItem)}
          </View>
        </ScrollView>

        {/* Right Column - Agent List */}
        <ScrollView style={styles.desktopRight}>
          <Text style={styles.sectionTitle}>AGENTS</Text>
          {MOCK_AGENTS.map(renderAgentRow)}
        </ScrollView>
      </View>
    </View>
  );

  return isDesktop ? renderDesktopLayout() : renderMobileLayout();
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 60,
    paddingBottom: 20,
    backgroundColor: Colors.background,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: Colors.text,
  },
  headerTime: {
    fontSize: 14,
    color: Colors.textMuted,
  },
  statsRow: {
    paddingHorizontal: 20,
    paddingVertical: 16,
    flexDirection: 'row',
    gap: 12,
  },
  statCard: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    minWidth: 100,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  statLabel: {
    fontSize: 11,
    textTransform: 'uppercase',
    color: Colors.textMuted,
    letterSpacing: 0.5,
  },
  section: {
    paddingHorizontal: 20,
    paddingTop: 24,
    paddingBottom: 16,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'uppercase',
    color: Colors.textMuted,
    letterSpacing: 1,
    marginBottom: 16,
  },
  agentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  agentLeft: {
    marginRight: 12,
  },
  statusDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  agentCenter: {
    flex: 1,
    marginRight: 12,
  },
  agentTitle: {
    fontSize: 15,
    fontWeight: 'bold',
    color: Colors.text,
    marginBottom: 4,
  },
  agentTask: {
    fontSize: 12,
    fontStyle: 'italic',
    color: Colors.textMuted,
  },
  agentRight: {
    alignItems: 'flex-end',
  },
  agentUptime: {
    fontSize: 12,
    color: Colors.textMuted,
    marginBottom: 4,
  },
  activityIcon: {
    opacity: 0.6,
  },
  activityItem: {
    flexDirection: 'row',
    paddingVertical: 12,
    borderLeftWidth: 3,
    paddingLeft: 12,
    marginBottom: 8,
  },
  activityDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginTop: 4,
    marginRight: 12,
  },
  activityContent: {
    flex: 1,
  },
  activityHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  activityAgent: {
    fontSize: 12,
    fontWeight: 'bold',
    color: Colors.text,
  },
  activityTime: {
    fontSize: 11,
    color: Colors.textMuted,
  },
  activityMessage: {
    fontSize: 13,
    color: Colors.textSecondary,
    lineHeight: 18,
  },
  desktopContent: {
    flex: 1,
    flexDirection: 'row',
  },
  desktopLeft: {
    flex: 0.6,
    borderRightWidth: 1,
    borderRightColor: Colors.border,
  },
  desktopRight: {
    flex: 0.4,
    paddingHorizontal: 20,
    paddingTop: 24,
  },
});
