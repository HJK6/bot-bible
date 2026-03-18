import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import {
  View,
  Text,
  FlatList,
  ScrollView,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Alert,
  TextInput,
} from 'react-native';
import { useLocalSearchParams, useNavigation } from 'expo-router';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Colors } from '@/constants/Colors';
import useResponsive from '../../../src/hooks/useResponsive';
import ChatBubble from '../../../src/components/ChatBubble';
import ChatInput from '../../../src/components/ChatInput';
import StatusBadge from '../../../src/components/StatusBadge';
import { Agent, AgentChatMessageOptimistic, AgentLog } from '../../../src/types/agent';
import { MOCK_AGENTS, getMockChat, getMockLogs } from '../../../src/data/mockData';

type TabName = 'info' | 'chat' | 'logs';

export default function MockAgentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const navigation = useNavigation();
  const { isDesktop, contentWidth } = useResponsive();

  const agent = MOCK_AGENTS.find((a) => a.agent_id === id);
  const serverMessages = useMemo(() => getMockChat(id), [id]);
  const logs = useMemo(() => getMockLogs(id), [id]);

  const [optimisticMessages, setOptimisticMessages] = useState<AgentChatMessageOptimistic[]>([]);
  const [activeTab, setActiveTab] = useState<TabName>('info');

  useEffect(() => {
    navigation.setOptions({
      title: agent?.title || agent?.agent_name || id.slice(0, 8),
      headerRight: () => (agent ? <StatusBadge status={agent.status} /> : null),
    });
  }, [navigation, agent, id]);

  useEffect(() => {
    if (agent?.interactive) setActiveTab('chat');
  }, [agent?.interactive]);

  const allMessages = useMemo(() => {
    const pendingOptimistic = optimisticMessages.filter((opt) => {
      if (!opt.optimistic) return false;
      return !serverMessages.some(
        (srv) =>
          srv.direction === 'inbound' &&
          srv.message === opt.message &&
          Math.abs(srv.timestamp - opt.timestamp) < 30000
      );
    });
    return [...serverMessages, ...pendingOptimistic];
  }, [serverMessages, optimisticMessages]);

  const flatListRef = useRef<any>(null);

  const handleSend = useCallback(
    async (message: string) => {
      const optimisticMsg: AgentChatMessageOptimistic = {
        agent_id: id,
        timestamp: Date.now(),
        direction: 'inbound',
        message,
        sender: 'mobile',
        optimistic: true,
        pending: true,
      };
      setOptimisticMessages((prev) => [...prev, optimisticMsg]);
      // Simulate send delay
      await new Promise((r) => setTimeout(r, 500));
      setOptimisticMessages((prev) =>
        prev.map((m) => (m === optimisticMsg ? { ...m, pending: false } : m))
      );
    },
    [id]
  );

  const handleStop = useCallback(() => {
    Alert.alert('Stop Agent', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Stop', style: 'destructive', onPress: () => console.log('[MOCK] Stop agent', id) },
    ]);
  }, [id]);

  const handleDelete = useCallback(() => {
    Alert.alert('Delete Agent', 'This cannot be undone.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          console.log('[MOCK] Delete agent', id);
          navigation.goBack();
        },
      },
    ]);
  }, [id, navigation]);

  const tabs: { key: TabName; label: string; show: boolean }[] = [
    { key: 'info', label: 'Info', show: true },
    { key: 'chat', label: 'Chat', show: agent?.interactive === true },
    { key: 'logs', label: `Logs (${logs.length})`, show: true },
  ];

  const wrapDesktop = (children: React.ReactNode) =>
    isDesktop ? (
      <View style={{ maxWidth: contentWidth, alignSelf: 'center', width: '100%', flex: 1 }}>
        {children}
      </View>
    ) : (
      <>{children}</>
    );

  if (!agent) {
    return (
      <View style={[styles.container, { justifyContent: 'center', alignItems: 'center' }]}>
        <Text style={{ color: Colors.textMuted, fontSize: 16 }}>Agent not found</Text>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      {/* Tab bar */}
      <View style={[styles.tabBar, isDesktop && { maxWidth: contentWidth, alignSelf: 'center', width: '100%' }]}>
        {tabs
          .filter((t) => t.show)
          .map((tab) => (
            <Pressable
              key={tab.key}
              style={[styles.tab, activeTab === tab.key && styles.tabActive, isDesktop && styles.tabDesktop]}
              onPress={() => setActiveTab(tab.key)}
            >
              <Text style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}>
                {tab.label}
              </Text>
            </Pressable>
          ))}
      </View>

      {/* Tab content */}
      {activeTab === 'info' &&
        wrapDesktop(<InfoTab agent={agent} onStop={handleStop} onDelete={handleDelete} isDesktop={isDesktop} />)}
      {activeTab === 'chat' &&
        wrapDesktop(
          <>
            <FlatList
              ref={flatListRef}
              data={allMessages}
              keyExtractor={(item, idx) => `${item.timestamp}-${idx}`}
              renderItem={({ item }) => <ChatBubble message={item} />}
              contentContainerStyle={styles.chatContent}
              onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: false })}
              onLayout={() => flatListRef.current?.scrollToEnd({ animated: false })}
              ListEmptyComponent={
                <View style={styles.emptyChat}>
                  <Text style={styles.emptyChatText}>No messages yet. Send a message to start.</Text>
                </View>
              }
            />
            <ChatInput
              onSend={handleSend}
              disabled={!agent || (agent.status !== 'running' && agent.status !== 'idle')}
              placeholder={
                agent?.status === 'running'
                  ? 'Send a message...'
                  : agent?.status === 'idle'
                    ? 'Send a message to wake this agent...'
                    : 'Agent is not running'
              }
            />
          </>
        )}
      {activeTab === 'logs' && wrapDesktop(<LogsTab logs={logs} isDesktop={isDesktop} />)}
    </KeyboardAvoidingView>
  );
}

// --- Info Tab ---
function InfoTab({
  agent,
  onStop,
  onDelete,
  isDesktop,
}: {
  agent: Agent;
  onStop: () => void;
  onDelete: () => void;
  isDesktop: boolean;
}) {
  const [editingTitle, setEditingTitle] = useState(false);
  const [editingGoal, setEditingGoal] = useState(false);
  const [titleDraft, setTitleDraft] = useState(agent.title);
  const [goalDraft, setGoalDraft] = useState(agent.goal);

  const saveField = useCallback(
    async (field: 'title' | 'goal', value: string) => {
      console.log('[MOCK] Save', field, '=', value);
      if (field === 'title') setEditingTitle(false);
      else setEditingGoal(false);
    },
    []
  );

  const isActive = agent.status === 'running' || agent.status === 'idle';

  return (
    <ScrollView style={styles.infoContainer} contentContainerStyle={styles.infoContent}>
      {/* Title */}
      <View style={styles.field}>
        <View style={styles.fieldHeader}>
          <Text style={styles.fieldLabel}>Title</Text>
          <Pressable onPress={() => { setEditingTitle(!editingTitle); setTitleDraft(agent.title); }}>
            <FontAwesome name={editingTitle ? 'close' : 'pencil'} size={14} color={Colors.textMuted} />
          </Pressable>
        </View>
        {editingTitle ? (
          <View style={styles.editRow}>
            <TextInput style={styles.editInput} value={titleDraft} onChangeText={setTitleDraft} autoFocus />
            <Pressable style={styles.saveButton} onPress={() => saveField('title', titleDraft)}>
              <Text style={styles.saveText}>Save</Text>
            </Pressable>
          </View>
        ) : (
          <Text style={styles.fieldValue}>{agent.title || agent.agent_name || '—'}</Text>
        )}
      </View>

      {/* Status row */}
      <View style={styles.statusRow}>
        <StatusBadge status={agent.status} />
        <Text style={styles.typeBadge}>{agent.agent_type}</Text>
        {agent.interactive && <Text style={styles.interactiveBadge}>interactive</Text>}
        {agent.started_at && <Text style={styles.metaText}>{formatUptime(agent.started_at)}</Text>}
      </View>

      {/* Goal */}
      <View style={styles.field}>
        <View style={styles.fieldHeader}>
          <Text style={styles.fieldLabel}>Goal</Text>
          <Pressable onPress={() => { setEditingGoal(!editingGoal); setGoalDraft(agent.goal); }}>
            <FontAwesome name={editingGoal ? 'close' : 'pencil'} size={14} color={Colors.textMuted} />
          </Pressable>
        </View>
        {editingGoal ? (
          <View>
            <TextInput
              style={[styles.editInput, { minHeight: 80 }]}
              value={goalDraft}
              onChangeText={setGoalDraft}
              multiline
              autoFocus
            />
            <Pressable style={[styles.saveButton, { alignSelf: 'flex-end', marginTop: 8 }]} onPress={() => saveField('goal', goalDraft)}>
              <Text style={styles.saveText}>Save</Text>
            </Pressable>
          </View>
        ) : (
          <Text style={styles.fieldValue}>{agent.goal || 'No goal set'}</Text>
        )}
      </View>

      {/* Current task + Metrics */}
      <View style={isDesktop ? styles.twoColumn : undefined}>
        {agent.current_task ? (
          <View style={[styles.field, isDesktop && styles.columnHalf]}>
            <Text style={styles.fieldLabel}>Current Task</Text>
            <Text style={[styles.fieldValue, { fontStyle: 'italic' }]}>{agent.current_task}</Text>
          </View>
        ) : null}

        {agent.metrics && Object.keys(agent.metrics).length > 0 && (
          <View style={[styles.field, isDesktop && styles.columnHalf]}>
            <Text style={styles.fieldLabel}>Metrics</Text>
            <MetricsDisplay metrics={agent.metrics} isDesktop={isDesktop} />
          </View>
        )}
      </View>

      {/* Metadata */}
      <View style={styles.field}>
        <Text style={styles.fieldLabel}>Details</Text>
        <View style={[styles.metaGrid, isDesktop && styles.metaGridDesktop]}>
          {agent.started_at && <MetaItem label="Started" value={new Date(agent.started_at).toLocaleString()} />}
          {agent.ended_at && <MetaItem label="Ended" value={new Date(agent.ended_at).toLocaleString()} />}
          {agent.last_heartbeat && <MetaItem label="Last Heartbeat" value={new Date(agent.last_heartbeat).toLocaleString()} />}
          {agent.host && <MetaItem label="Host" value={agent.host} />}
          {agent.pid > 0 && <MetaItem label="PID" value={String(agent.pid)} />}
        </View>
      </View>

      {/* Actions */}
      <View style={styles.actions}>
        {isActive && (
          <Pressable style={styles.stopButton} onPress={onStop}>
            <FontAwesome name="stop" size={14} color={Colors.warning} />
            <Text style={styles.stopText}>Stop</Text>
          </Pressable>
        )}
        <Pressable style={styles.deleteButton} onPress={onDelete}>
          <FontAwesome name="trash" size={14} color={Colors.error} />
          <Text style={styles.deleteText}>Delete</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metaItem}>
      <Text style={styles.metaLabel}>{label}</Text>
      <Text style={styles.metaValue}>{value}</Text>
    </View>
  );
}

// --- Metrics Display ---
function MetricsDisplay({ metrics, isDesktop }: { metrics: Record<string, any>; isDesktop: boolean }) {
  const scalarEntries = Object.entries(metrics).filter(([, v]) => !Array.isArray(v) && typeof v !== 'object');
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

// --- Logs Tab ---
function LogsTab({ logs, isDesktop }: { logs: AgentLog[]; isDesktop: boolean }) {
  const LEVEL_COLORS: Record<string, string> = {
    info: Colors.primary,
    warning: Colors.warning,
    error: Colors.error,
  };

  return (
    <FlatList
      data={logs}
      keyExtractor={(item, idx) => `${item.timestamp}-${idx}`}
      renderItem={({ item }) => (
        <View style={[styles.logRow, { borderLeftColor: LEVEL_COLORS[item.level] || Colors.textMuted }]}>
          <View style={styles.logHeader}>
            <Text style={styles.logTime}>{new Date(item.timestamp).toLocaleTimeString()}</Text>
            <Text style={[styles.logLevel, { color: LEVEL_COLORS[item.level] || Colors.textMuted }]}>
              {item.level}
            </Text>
          </View>
          <Text style={styles.logMessage}>{item.message}</Text>
          {item.metadata && Object.keys(item.metadata).length > 0 && (
            <Text style={styles.logMeta}>{JSON.stringify(item.metadata, null, 2)}</Text>
          )}
        </View>
      )}
      contentContainerStyle={styles.logsContent}
      ListEmptyComponent={
        <View style={styles.emptyChat}>
          <Text style={styles.emptyChatText}>No logs available</Text>
        </View>
      }
    />
  );
}

// --- Helpers ---
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

// --- Styles ---
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
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
  field: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  fieldHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
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
  editRow: {
    flexDirection: 'row',
    gap: 8,
  },
  editInput: {
    flex: 1,
    backgroundColor: Colors.background,
    borderRadius: 8,
    padding: 10,
    fontSize: 15,
    color: Colors.text,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  saveButton: {
    backgroundColor: Colors.primary,
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
    justifyContent: 'center',
  },
  saveText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 14,
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
  interactiveBadge: {
    fontSize: 12,
    color: Colors.primary,
    backgroundColor: Colors.primary + '20',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
    overflow: 'hidden',
  },
  metaText: {
    fontSize: 12,
    color: Colors.textMuted,
  },
  twoColumn: {
    flexDirection: 'row',
    gap: 16,
  },
  columnHalf: {
    flex: 1,
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
  actions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  stopButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: Colors.warning + '15',
    borderWidth: 1,
    borderColor: Colors.warning + '40',
    borderRadius: 12,
    padding: 14,
  },
  stopText: {
    color: Colors.warning,
    fontSize: 15,
    fontWeight: '600',
  },
  deleteButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: Colors.error + '15',
    borderWidth: 1,
    borderColor: Colors.error + '40',
    borderRadius: 12,
    padding: 14,
  },
  deleteText: {
    color: Colors.error,
    fontSize: 15,
    fontWeight: '600',
  },
  chatContent: {
    paddingVertical: 8,
  },
  emptyChat: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
  },
  emptyChatText: {
    color: Colors.textMuted,
    fontSize: 15,
    textAlign: 'center',
  },
  logsContent: {
    padding: 8,
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
