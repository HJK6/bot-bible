import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Platform,
} from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { FontAwesome } from '@expo/vector-icons';
import { Colors } from '@/constants/Colors';
import { MOCK_AGENTS, getMockChat, getMockLogs } from '../../../../src/data/mockData';
import { Agent, AgentChatMessage } from '../../../../src/types/agent';
import StatusBadge from '../../../../src/components/StatusBadge';
import ChatBubble from '../../../../src/components/ChatBubble';
import ChatInput from '../../../../src/components/ChatInput';
import useResponsive from '../../../../src/hooks/useResponsive';

type TabName = 'info' | 'chat' | 'logs';

export default function V2AgentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [activeTab, setActiveTab] = useState<TabName>('info');

  const agent = MOCK_AGENTS.find((a) => a.agent_id === id);

  React.useLayoutEffect(() => {
    if (agent) {
      router.setParams({ title: agent.agent_name });
    }
  }, [agent]);

  if (!agent) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorText}>Agent not found</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Tabs */}
      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'info' && styles.tabActive]}
          onPress={() => setActiveTab('info')}
        >
          <Text style={[styles.tabText, activeTab === 'info' && styles.tabTextActive]}>Info</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'chat' && styles.tabActive]}
          onPress={() => setActiveTab('chat')}
        >
          <Text style={[styles.tabText, activeTab === 'chat' && styles.tabTextActive]}>Chat</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'logs' && styles.tabActive]}
          onPress={() => setActiveTab('logs')}
        >
          <Text style={[styles.tabText, activeTab === 'logs' && styles.tabTextActive]}>Logs</Text>
        </TouchableOpacity>
      </View>

      {/* Tab Content */}
      {activeTab === 'info' && <InfoTab agent={agent} />}
      {activeTab === 'chat' && <ChatTab agent={agent} />}
      {activeTab === 'logs' && <LogsTab agent={agent} />}
    </View>
  );
}

function InfoTab({ agent }: { agent: Agent }) {
  return (
    <ScrollView style={styles.tabContent} contentContainerStyle={styles.scrollContent}>
      {/* Hero Section */}
      <View style={styles.heroSection}>
        <View style={[styles.heroIcon, { backgroundColor: getAgentTypeColor(agent.agent_type) }]}>
          <FontAwesome name={getAgentTypeIcon(agent.agent_type)} size={24} color="#fff" />
        </View>
        <Text style={styles.heroTitle}>{agent.agent_name}</Text>
        <View style={styles.heroBadge}>
          {agent.status === 'running' && <PulseDot />}
          <StatusBadge status={agent.status} />
        </View>
      </View>

      {/* Progress Card */}
      {renderProgressCard(agent)}

      {/* Goal */}
      {agent.goal && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Goal</Text>
          <Text style={styles.goalText}>{agent.goal}</Text>
        </View>
      )}

      {/* Task Timeline */}
      {agent.metrics?.tasks && (agent.metrics.tasks as string[]).length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Tasks</Text>
          <TaskTimeline tasks={agent.metrics.tasks as string[]} />
        </View>
      )}

      {/* Metadata */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Details</Text>
        <View style={styles.metadataGrid}>
          <MetadataRow label="Agent Type" value={agent.agent_type} />
          <MetadataRow label="Status" value={agent.status} />
          <MetadataRow label="Interactive" value={agent.interactive ? 'Yes' : 'No'} />
          <MetadataRow label="Started" value={agent.started_at} />
          {agent.ended_at && <MetadataRow label="Completed" value={agent.ended_at} />}
          {agent.metrics && (
            <>
              {agent.metrics.parcels_scraped != null && (
                <MetadataRow label="Parcels Scraped" value={String(agent.metrics.parcels_scraped)} />
              )}
              {agent.metrics.files_reviewed != null && (
                <MetadataRow label="Files Reviewed" value={String(agent.metrics.files_reviewed)} />
              )}
              {agent.metrics.messages_processed != null && (
                <MetadataRow
                  label="Messages Processed"
                  value={String(agent.metrics.messages_processed)}
                />
              )}
              {agent.metrics.listings_found != null && (
                <MetadataRow label="Listings Found" value={String(agent.metrics.listings_found)} />
              )}
              {agent.metrics.sms_sent != null && (
                <MetadataRow label="SMS Sent" value={String(agent.metrics.sms_sent)} />
              )}
            </>
          )}
        </View>
      </View>

      {/* Actions */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Actions</Text>
        <View style={styles.actionButtons}>
          {agent.status === 'running' && (
            <TouchableOpacity style={styles.actionBtn} onPress={() => alert('Pause agent')}>
              <FontAwesome name="pause" size={16} color={Colors.text} />
              <Text style={styles.actionBtnText}>Pause</Text>
            </TouchableOpacity>
          )}
          {agent.status === 'running' && (
            <TouchableOpacity
              style={[styles.actionBtn, styles.actionBtnDanger]}
              onPress={() => alert('Stop agent')}
            >
              <FontAwesome name="stop" size={16} color={Colors.error} />
              <Text style={[styles.actionBtnText, styles.actionBtnTextDanger]}>Stop</Text>
            </TouchableOpacity>
          )}
          {agent.status === 'idle' && (
            <TouchableOpacity style={styles.actionBtn} onPress={() => alert('Resume agent')}>
              <FontAwesome name="play" size={16} color={Colors.text} />
              <Text style={styles.actionBtnText}>Resume</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity style={styles.actionBtn} onPress={() => alert('View logs')}>
            <FontAwesome name="file-text-o" size={16} color={Colors.text} />
            <Text style={styles.actionBtnText}>View Logs</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
}

function ChatTab({ agent }: { agent: Agent }) {
  const chat = getMockChat(agent.agent_id);
  const [messages, setMessages] = useState(chat);

  const handleSend = async (text: string, _imageUrl?: string) => {
    const newMsg: AgentChatMessage = {
      agent_id: agent.agent_id,
      timestamp: Date.now(),
      direction: 'inbound',
      message: text,
      sender: 'mobile',
    };
    setMessages([...messages, newMsg]);

    setTimeout(() => {
      const botMsg: AgentChatMessage = {
        agent_id: agent.agent_id,
        timestamp: Date.now() + 1,
        direction: 'outbound',
        message: 'This is a mock response. Real agent integration coming soon.',
        sender: agent.agent_name,
      };
      setMessages((prev) => [...prev, botMsg]);
    }, 1000);
  };

  if (!agent.interactive) {
    return (
      <View style={styles.tabContent}>
        <View style={styles.emptyState}>
          <FontAwesome name="comment-o" size={48} color={Colors.textMuted} />
          <Text style={styles.emptyStateText}>This agent is not interactive</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.tabContent}>
      <ScrollView style={styles.chatMessages} contentContainerStyle={styles.chatMessagesContent}>
        {messages.map((msg, idx) => (
          <ChatBubble key={idx} message={msg} />
        ))}
      </ScrollView>
      <ChatInput onSend={handleSend} />
    </View>
  );
}

function LogsTab({ agent }: { agent: Agent }) {
  const logs = getMockLogs(agent.agent_id);

  return (
    <ScrollView style={styles.tabContent} contentContainerStyle={styles.scrollContent}>
      {logs.map((log, idx) => (
        <View key={idx} style={styles.logEntry}>
          <View style={styles.logHeader}>
            <Text style={[styles.logLevel, { color: getLogLevelColor(log.level) }]}>
              {log.level.toUpperCase()}
            </Text>
            <Text style={styles.logTimestamp}>{log.timestamp}</Text>
          </View>
          <Text style={styles.logMessage}>{log.message}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

function renderProgressCard(agent: Agent) {
  const progress = getProgress(agent);
  if (!progress) return null;

  const { current, total, label } = progress;
  const percentage = total > 0 ? (current / total) * 100 : 0;

  return (
    <View style={styles.progressCard}>
      <Text style={styles.progressCardTitle}>Progress</Text>
      <View style={styles.progressCardMetrics}>
        <View style={styles.progressCardMetricItem}>
          <Text style={styles.progressCardMetricValue}>{current.toLocaleString()}</Text>
          <Text style={styles.progressCardMetricLabel}>Current</Text>
        </View>
        <Text style={styles.progressCardMetricSeparator}>/</Text>
        <View style={styles.progressCardMetricItem}>
          <Text style={styles.progressCardMetricValue}>{total.toLocaleString()}</Text>
          <Text style={styles.progressCardMetricLabel}>Total</Text>
        </View>
      </View>
      <View style={styles.progressCardBar}>
        <View
          style={[
            styles.progressCardBarFill,
            { width: `${percentage}%`, backgroundColor: getStatusColor(agent.status) },
          ]}
        />
      </View>
      <Text style={styles.progressCardPercentage}>{percentage.toFixed(1)}% complete</Text>
    </View>
  );
}

function TaskTimeline({ tasks }: { tasks: string[] }) {
  return (
    <View style={styles.timeline}>
      {tasks.map((task, idx) => {
        const isDone = task.startsWith('[done]');
        const isActive = task.startsWith('>>');
        const isFailed = task.includes('FAILED');
        const isPending = !isDone && !isActive && !isFailed;

        let taskText = task;
        if (isDone) taskText = task.replace('[done]', '').trim();
        if (isActive) taskText = task.replace('>>', '').trim();

        return (
          <View key={idx} style={styles.timelineItem}>
            <View style={styles.timelineDotContainer}>
              {idx < tasks.length - 1 && <View style={styles.timelineLine} />}
              {isDone && <View style={[styles.timelineDot, styles.timelineDotDone]} />}
              {isActive && <PulsingDot />}
              {isFailed && <View style={[styles.timelineDot, styles.timelineDotFailed]} />}
              {isPending && <View style={[styles.timelineDot, styles.timelineDotPending]} />}
            </View>
            <Text
              style={[
                styles.timelineText,
                isDone && styles.timelineTextDone,
                isFailed && styles.timelineTextFailed,
              ]}
            >
              {taskText}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

function PulsingDot() {
  const pulseAnim = React.useRef(new Animated.Value(1)).current;

  React.useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 0.4,
          duration: 800,
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 1,
          duration: 800,
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, []);

  return (
    <Animated.View
      style={[
        styles.timelineDot,
        styles.timelineDotActive,
        {
          opacity: pulseAnim,
        },
      ]}
    />
  );
}

function PulseDot() {
  const pulseAnim = React.useRef(new Animated.Value(1)).current;

  React.useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 0.4,
          duration: 1000,
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, []);

  return (
    <Animated.View
      style={[
        styles.pulseDot,
        {
          opacity: pulseAnim,
        },
      ]}
    />
  );
}

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metadataRow}>
      <Text style={styles.metadataLabel}>{label}</Text>
      <Text style={styles.metadataValue}>{value}</Text>
    </View>
  );
}

function getProgress(agent: Agent): { current: number; total: number; label: string } | null {
  const m = agent.metrics;
  if (!m) return null;
  if (m.parcels_scraped != null && m.parcels_total != null)
    return { current: m.parcels_scraped, total: m.parcels_total, label: 'parcels' };
  if (m.modules_completed != null && m.modules_total != null)
    return { current: m.modules_completed, total: m.modules_total, label: 'modules' };
  if (m.emails_sent != null && m.emails_total != null)
    return { current: m.emails_sent, total: m.emails_total, label: 'emails' };
  return null;
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'running':
      return Colors.success;
    case 'idle':
      return Colors.warning;
    case 'failed':
      return Colors.error;
    case 'completed':
      return Colors.textMuted;
    case 'stale':
      return Colors.textMuted;
    default:
      return Colors.border;
  }
}

function getAgentTypeIcon(agentType: string): any {
  switch (agentType) {
    case 'telegram-bot':
      return 'send';
    case 'aceable-bot':
      return 'graduation-cap';
    case 'claude-agent':
    case 'claude-code':
    default:
      return 'code';
  }
}

function getAgentTypeColor(agentType: string): string {
  switch (agentType) {
    case 'telegram-bot':
      return '#3b82f6';
    case 'aceable-bot':
      return Colors.warning;
    case 'claude-agent':
    case 'claude-code':
    default:
      return Colors.primary;
  }
}

function getLogLevelColor(level: string): string {
  switch (level.toLowerCase()) {
    case 'error':
      return Colors.error;
    case 'warn':
    case 'warning':
      return Colors.warning;
    case 'info':
      return Colors.primary;
    case 'debug':
      return Colors.textMuted;
    default:
      return Colors.text;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  tab: {
    flex: 1,
    paddingVertical: 14,
    alignItems: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: {
    borderBottomColor: Colors.primary,
  },
  tabText: {
    fontSize: 15,
    fontWeight: '500',
    color: Colors.textSecondary,
  },
  tabTextActive: {
    color: Colors.primary,
    fontWeight: '600',
  },
  tabContent: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
  },
  heroSection: {
    alignItems: 'center',
    paddingVertical: 24,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
    marginBottom: 20,
  },
  heroIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  heroTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: Colors.text,
    marginBottom: 8,
    textAlign: 'center',
  },
  heroBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  pulseDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.success,
  },
  progressCard: {
    backgroundColor: Colors.surface,
    borderRadius: 14,
    padding: 20,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  progressCardTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginBottom: 16,
  },
  progressCardMetrics: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  progressCardMetricItem: {
    alignItems: 'center',
  },
  progressCardMetricValue: {
    fontSize: 28,
    fontWeight: '700',
    color: Colors.text,
  },
  progressCardMetricLabel: {
    fontSize: 12,
    color: Colors.textSecondary,
    marginTop: 4,
  },
  progressCardMetricSeparator: {
    fontSize: 28,
    fontWeight: '300',
    color: Colors.textMuted,
    marginHorizontal: 20,
  },
  progressCardBar: {
    height: 10,
    backgroundColor: Colors.surfaceLight,
    borderRadius: 5,
    overflow: 'hidden',
    marginBottom: 8,
  },
  progressCardBarFill: {
    height: '100%',
    borderRadius: 5,
  },
  progressCardPercentage: {
    fontSize: 13,
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.text,
    marginBottom: 12,
  },
  goalText: {
    fontSize: 15,
    color: Colors.textSecondary,
    lineHeight: 22,
  },
  timeline: {
    marginTop: 8,
  },
  timelineItem: {
    flexDirection: 'row',
    marginBottom: 16,
  },
  timelineDotContainer: {
    alignItems: 'center',
    width: 24,
    marginRight: 12,
  },
  timelineLine: {
    position: 'absolute',
    top: 20,
    bottom: -16,
    width: 2,
    backgroundColor: Colors.border,
  },
  timelineDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginTop: 4,
  },
  timelineDotDone: {
    backgroundColor: Colors.success,
  },
  timelineDotActive: {
    backgroundColor: Colors.primary,
  },
  timelineDotFailed: {
    backgroundColor: Colors.error,
  },
  timelineDotPending: {
    backgroundColor: 'transparent',
    borderWidth: 2,
    borderColor: Colors.textMuted,
  },
  timelineText: {
    flex: 1,
    fontSize: 14,
    color: Colors.text,
    lineHeight: 20,
  },
  timelineTextDone: {
    color: Colors.textSecondary,
    textDecorationLine: 'line-through',
  },
  timelineTextFailed: {
    color: Colors.error,
  },
  metadataGrid: {
    gap: 12,
  },
  metadataRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  metadataLabel: {
    fontSize: 14,
    color: Colors.textSecondary,
  },
  metadataValue: {
    fontSize: 14,
    fontWeight: '500',
    color: Colors.text,
  },
  actionButtons: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: Colors.surfaceLight,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 10,
  },
  actionBtnDanger: {
    borderWidth: 1,
    borderColor: Colors.error,
    backgroundColor: 'transparent',
  },
  actionBtnText: {
    fontSize: 14,
    fontWeight: '500',
    color: Colors.text,
  },
  actionBtnTextDanger: {
    color: Colors.error,
  },
  chatMessages: {
    flex: 1,
  },
  chatMessagesContent: {
    padding: 16,
  },
  emptyState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 40,
  },
  emptyStateText: {
    fontSize: 16,
    color: Colors.textMuted,
    marginTop: 16,
  },
  logEntry: {
    backgroundColor: Colors.surface,
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
    borderLeftWidth: 3,
    borderLeftColor: Colors.border,
  },
  logHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  logLevel: {
    fontSize: 12,
    fontWeight: '700',
  },
  logTimestamp: {
    fontSize: 11,
    color: Colors.textMuted,
  },
  logMessage: {
    fontSize: 13,
    color: Colors.text,
    lineHeight: 18,
  },
  errorText: {
    fontSize: 16,
    color: Colors.error,
    textAlign: 'center',
    marginTop: 40,
  },
});
