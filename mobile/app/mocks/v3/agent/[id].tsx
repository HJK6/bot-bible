import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, TextInput } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons, FontAwesome } from '@expo/vector-icons';
import { Colors } from '@/constants/Colors';
import { MOCK_AGENTS, getMockChat, getMockLogs } from '../../../../src/data/mockData';
import { Agent, AgentChatMessageOptimistic, AgentLog } from '../../../../src/types/agent';
import StatusBadge from '../../../../src/components/StatusBadge';
import ChatBubble from '../../../../src/components/ChatBubble';
import ChatInput from '../../../../src/components/ChatInput';
import useResponsive from '../../../../src/hooks/useResponsive';

type Tab = 'info' | 'chat' | 'logs';

export default function AgentDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { isDesktop } = useResponsive();
  const [activeTab, setActiveTab] = useState<Tab>('info');
  const [chatMessages, setChatMessages] = useState<AgentChatMessageOptimistic[]>(getMockChat(id));
  const [logs, setLogs] = useState<AgentLog[]>(getMockLogs(id));

  const agent = MOCK_AGENTS.find(a => a.agent_id === id);

  if (!agent) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorText}>Agent not found</Text>
      </View>
    );
  }

  const handleSendMessage = async (message: string, _imageUrl?: string) => {
    const newMessage: AgentChatMessageOptimistic = {
      agent_id: agent.agent_id,
      timestamp: Date.now(),
      direction: 'inbound',
      message,
      sender: 'mobile',
      optimistic: true,
    };
    setChatMessages([...chatMessages, newMessage]);

    // Simulate agent response
    setTimeout(() => {
      const response: AgentChatMessageOptimistic = {
        agent_id: agent.agent_id,
        timestamp: Date.now() + 1,
        direction: 'outbound',
        message: 'This is a mock response. In production, this would come from the agent API.',
        sender: agent.agent_name,
      };
      setChatMessages(prev => [...prev, response]);
    }, 1000);
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

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const renderHeader = () => (
    <View style={styles.header}>
      <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
        <Ionicons name="arrow-back" size={24} color={Colors.text} />
      </TouchableOpacity>
      <Text style={styles.headerTitle} numberOfLines={1}>{agent.title}</Text>
      <StatusBadge status={agent.status} />
    </View>
  );

  const renderTabs = () => (
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
  );

  const renderInfoTab = () => {
    const statusColor = getStatusColor(agent.status);
    const metrics = agent.metrics;

    return (
      <ScrollView style={styles.tabContent}>
        {/* Status Strip */}
        <View style={[styles.statusStrip, { backgroundColor: statusColor }]} />

        {/* Key Metrics */}
        {metrics && (
          <View style={styles.metricsRow}>
            {metrics.parcels_processed !== undefined && (
              <View style={styles.metricCard}>
                <Text style={styles.metricValue}>{metrics.parcels_processed}</Text>
                <Text style={styles.metricLabel}>parcels</Text>
              </View>
            )}
            {metrics.skip_traced !== undefined && (
              <View style={styles.metricCard}>
                <Text style={styles.metricValue}>{metrics.skip_traced}</Text>
                <Text style={styles.metricLabel}>traced</Text>
              </View>
            )}
            {metrics.errors !== undefined && (
              <View style={styles.metricCard}>
                <Text style={styles.metricValue}>{metrics.errors}</Text>
                <Text style={styles.metricLabel}>errors</Text>
              </View>
            )}
            {metrics.leads_generated !== undefined && (
              <View style={styles.metricCard}>
                <Text style={styles.metricValue}>{metrics.leads_generated}</Text>
                <Text style={styles.metricLabel}>leads</Text>
              </View>
            )}
            {metrics.emails_sent !== undefined && (
              <View style={styles.metricCard}>
                <Text style={styles.metricValue}>{metrics.emails_sent}</Text>
                <Text style={styles.metricLabel}>emails</Text>
              </View>
            )}
            {metrics.tasks_completed !== undefined && (
              <View style={styles.metricCard}>
                <Text style={styles.metricValue}>{metrics.tasks_completed}</Text>
                <Text style={styles.metricLabel}>tasks done</Text>
              </View>
            )}
          </View>
        )}

        {/* Task Progress */}
        {metrics?.tasks && metrics.tasks.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>TASK PROGRESS</Text>
            {metrics.tasks.map((task: any, index: number) => {
              let icon;
              let iconColor;
              let textStyle;

              if (task.status === 'done') {
                icon = 'check-circle';
                iconColor = Colors.success;
                textStyle = [styles.taskText, styles.taskDone];
              } else if (task.status === 'active') {
                icon = 'play-circle';
                iconColor = Colors.primary;
                textStyle = [styles.taskText, styles.taskActive];
              } else if (task.status === 'failed') {
                icon = 'exclamation-circle';
                iconColor = Colors.error;
                textStyle = [styles.taskText, styles.taskFailed];
              } else {
                icon = 'circle-o';
                iconColor = Colors.textMuted;
                textStyle = [styles.taskText, styles.taskPending];
              }

              return (
                <View key={index} style={styles.taskRow}>
                  <FontAwesome name={icon as any} size={16} color={iconColor} style={styles.taskIcon} />
                  <Text style={textStyle}>{task.name}</Text>
                </View>
              );
            })}
          </View>
        )}

        {/* Details Grid */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>DETAILS</Text>
          <View style={styles.detailsGrid}>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Started</Text>
              <Text style={styles.detailValue}>{formatDate(agent.started_at)}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Heartbeat</Text>
              <Text style={styles.detailValue}>{formatDate(agent.last_heartbeat)}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Host</Text>
              <Text style={styles.detailValue}>{agent.host}</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>PID</Text>
              <Text style={styles.detailValue}>{agent.pid}</Text>
            </View>
            {(agent.metrics as any)?.model && (
              <View style={styles.detailRow}>
                <Text style={styles.detailLabel}>Model</Text>
                <Text style={styles.detailValue}>{(agent.metrics as any).model}</Text>
              </View>
            )}
          </View>
        </View>

        {/* Goal */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>GOAL</Text>
          <Text style={styles.goalText}>{agent.goal}</Text>
        </View>

        {/* Action Bar */}
        <View style={styles.actionBar}>
          {(agent.status === 'running' || agent.status === 'idle') && (
            <TouchableOpacity style={[styles.actionButton, styles.stopButton]}>
              <Text style={styles.actionButtonText}>Stop Agent</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity style={[styles.actionButton, styles.deleteButton]}>
            <Text style={styles.actionButtonText}>Delete Agent</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    );
  };

  const renderChatTab = () => (
    <View style={styles.chatContainer}>
      <ScrollView style={styles.chatScroll}>
        {chatMessages.map((msg) => (
          <ChatBubble key={msg.timestamp} message={msg} />
        ))}
      </ScrollView>
      <ChatInput onSend={handleSendMessage} />
    </View>
  );

  const renderLogsTab = () => {
    const getLevelColor = (level: string): string => {
      switch (level) {
        case 'error': return Colors.error;
        case 'warning': return Colors.warning;
        default: return Colors.primary;
      }
    };

    return (
      <ScrollView style={styles.tabContent}>
        {logs.map((log, index) => {
          const levelColor = getLevelColor(log.level);
          return (
            <View
              key={index}
              style={[styles.logItem, { borderLeftColor: levelColor }]}
            >
              <View style={styles.logHeader}>
                <Text style={[styles.logLevel, { color: levelColor }]}>
                  {log.level.toUpperCase()}
                </Text>
                <Text style={styles.logTimestamp}>{formatDate(String(log.timestamp))}</Text>
              </View>
              <Text style={styles.logMessage}>{log.message}</Text>
            </View>
          );
        })}
      </ScrollView>
    );
  };

  return (
    <View style={styles.container}>
      {renderHeader()}
      {renderTabs()}
      {activeTab === 'info' && renderInfoTab()}
      {activeTab === 'chat' && renderChatTab()}
      {activeTab === 'logs' && renderLogsTab()}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingTop: 60,
    paddingBottom: 16,
    backgroundColor: Colors.background,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  backButton: {
    marginRight: 12,
  },
  headerTitle: {
    flex: 1,
    fontSize: 16,
    fontWeight: 'bold',
    color: Colors.text,
  },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
    backgroundColor: Colors.surface,
  },
  tab: {
    flex: 1,
    paddingVertical: 16,
    alignItems: 'center',
  },
  tabActive: {
    borderBottomWidth: 2,
    borderBottomColor: Colors.primary,
  },
  tabText: {
    fontSize: 14,
    fontWeight: '500',
    color: Colors.textMuted,
  },
  tabTextActive: {
    color: Colors.primary,
  },
  tabContent: {
    flex: 1,
  },
  statusStrip: {
    height: 4,
    width: '100%',
  },
  metricsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 16,
    gap: 12,
  },
  metricCard: {
    backgroundColor: Colors.surfaceLight,
    borderRadius: 8,
    padding: 12,
    minWidth: 80,
    alignItems: 'center',
  },
  metricValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: Colors.text,
    marginBottom: 4,
  },
  metricLabel: {
    fontSize: 10,
    color: Colors.textMuted,
  },
  section: {
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'uppercase',
    color: Colors.textMuted,
    letterSpacing: 1,
    marginBottom: 12,
  },
  taskRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
  },
  taskIcon: {
    marginRight: 12,
  },
  taskText: {
    fontSize: 14,
    flex: 1,
  },
  taskDone: {
    color: Colors.textMuted,
    textDecorationLine: 'line-through',
  },
  taskActive: {
    color: Colors.primary,
    fontWeight: 'bold',
  },
  taskFailed: {
    color: Colors.error,
  },
  taskPending: {
    color: Colors.textMuted,
  },
  detailsGrid: {
    gap: 12,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  detailLabel: {
    fontSize: 13,
    color: Colors.textMuted,
  },
  detailValue: {
    fontSize: 13,
    color: Colors.text,
    fontWeight: '500',
  },
  goalText: {
    fontSize: 14,
    color: Colors.textSecondary,
    lineHeight: 20,
  },
  actionBar: {
    padding: 16,
    gap: 12,
  },
  actionButton: {
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  stopButton: {
    backgroundColor: Colors.warning,
  },
  deleteButton: {
    backgroundColor: Colors.error,
  },
  actionButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: Colors.text,
  },
  chatContainer: {
    flex: 1,
  },
  chatScroll: {
    flex: 1,
    padding: 16,
  },
  logItem: {
    padding: 12,
    marginHorizontal: 16,
    marginVertical: 6,
    borderLeftWidth: 3,
    backgroundColor: Colors.surface,
    borderRadius: 4,
  },
  logHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  logLevel: {
    fontSize: 11,
    fontWeight: 'bold',
    letterSpacing: 0.5,
  },
  logTimestamp: {
    fontSize: 11,
    color: Colors.textMuted,
  },
  logMessage: {
    fontSize: 13,
    color: Colors.textSecondary,
    lineHeight: 18,
  },
  errorText: {
    fontSize: 16,
    color: Colors.error,
    textAlign: 'center',
    marginTop: 100,
  },
});
