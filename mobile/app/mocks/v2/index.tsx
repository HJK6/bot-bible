import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Platform,
} from 'react-native';
import { router } from 'expo-router';
import { FontAwesome } from '@expo/vector-icons';
import { Colors } from '@/constants/Colors';
import { MOCK_AGENTS } from '../../../src/data/mockData';
import { Agent } from '../../../src/types/agent';
import StatusBadge from '../../../src/components/StatusBadge';
import useResponsive from '../../../src/hooks/useResponsive';

type FilterStatus = 'all' | 'running' | 'idle' | 'completed' | 'failed';

export default function V2IndexScreen() {
  const { isDesktop, isWide } = useResponsive();
  const isMobile = !isDesktop;
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');

  const filteredAgents = useMemo(() => {
    let agents = MOCK_AGENTS;

    // Filter by status
    if (filterStatus !== 'all') {
      agents = agents.filter((a) => a.status === filterStatus);
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      agents = agents.filter(
        (a) =>
          a.agent_name.toLowerCase().includes(query) ||
          (a.goal && a.goal.toLowerCase().includes(query)) ||
          (a.current_task && a.current_task.toLowerCase().includes(query))
      );
    }

    return agents;
  }, [searchQuery, filterStatus]);

  const numColumns = isMobile ? 1 : isWide ? 3 : 2;

  return (
    <View style={styles.container}>
      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <FontAwesome name="search" size={16} color={Colors.textMuted} style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          placeholder="Search agents..."
          placeholderTextColor={Colors.textMuted}
          value={searchQuery}
          onChangeText={setSearchQuery}
        />
      </View>

      {/* Filter Chips */}
      <View style={styles.filterContainer}>
        {(['all', 'running', 'idle', 'completed', 'failed'] as FilterStatus[]).map((status) => (
          <TouchableOpacity
            key={status}
            style={[styles.filterChip, filterStatus === status && styles.filterChipActive]}
            onPress={() => setFilterStatus(status)}
          >
            <Text
              style={[
                styles.filterChipText,
                filterStatus === status && styles.filterChipTextActive,
              ]}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Agent Cards */}
      <FlatList
        data={filteredAgents}
        keyExtractor={(item) => item.agent_id}
        key={numColumns}
        numColumns={numColumns}
        renderItem={({ item }) => <AgentCard agent={item} />}
        contentContainerStyle={styles.listContent}
        columnWrapperStyle={numColumns > 1 ? styles.columnWrapper : undefined}
      />

      {/* FAB */}
      {isMobile && (
        <TouchableOpacity style={styles.fab} onPress={() => alert('Create new agent')}>
          <FontAwesome name="plus" size={24} color="#fff" />
        </TouchableOpacity>
      )}
    </View>
  );
}

function AgentCard({ agent }: { agent: Agent }) {
  return (
    <TouchableOpacity
      style={[styles.card, { borderLeftColor: getStatusColor(agent.status) }]}
      onPress={() => router.push(`/mocks/v2/agent/${agent.agent_id}`)}
      activeOpacity={0.7}
    >
      {/* Top Row: Icon + Title + Status Badge */}
      <View style={styles.cardTopRow}>
        <View style={styles.cardTitleRow}>
          <View style={[styles.agentIcon, { backgroundColor: getAgentTypeColor(agent.agent_type) }]}>
            <FontAwesome name={getAgentTypeIcon(agent.agent_type)} size={14} color="#fff" />
          </View>
          <Text style={styles.cardTitle} numberOfLines={1}>
            {agent.agent_name}
          </Text>
        </View>
        <View style={styles.statusBadgeContainer}>
          {agent.status === 'running' && <PulseDot />}
          <StatusBadge status={agent.status} />
        </View>
      </View>

      {/* Goal */}
      {agent.goal && (
        <Text style={styles.cardGoal} numberOfLines={2}>
          {agent.goal}
        </Text>
      )}

      {/* Progress Section */}
      {agent.status === 'running' && renderProgress(agent)}

      {/* Current Task */}
      {agent.status === 'running' && agent.current_task && (
        <Text style={styles.currentTask} numberOfLines={1}>
          {agent.current_task}
        </Text>
      )}

      {/* Bottom Row: Quick Actions */}
      <View style={styles.cardBottomRow}>
        <View style={styles.quickActions}>
          {agent.interactive && (
            <TouchableOpacity
              style={[styles.quickActionBtn, styles.quickActionBtnPrimary]}
              onPress={(e) => {
                e.stopPropagation();
                router.push(`/mocks/v2/agent/${agent.agent_id}`);
              }}
            >
              <Text style={styles.quickActionTextPrimary}>Chat</Text>
            </TouchableOpacity>
          )}
          {agent.status === 'running' && (
            <TouchableOpacity
              style={[styles.quickActionBtn, styles.quickActionBtnWarning]}
              onPress={(e) => {
                e.stopPropagation();
                alert('Stop agent');
              }}
            >
              <Text style={styles.quickActionTextWarning}>Stop</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity
            style={[styles.quickActionBtn, styles.quickActionBtnDefault]}
            onPress={(e) => {
              e.stopPropagation();
              router.push(`/mocks/v2/agent/${agent.agent_id}`);
            }}
          >
            <Text style={styles.quickActionTextDefault}>View</Text>
          </TouchableOpacity>
        </View>
      </View>
    </TouchableOpacity>
  );
}

function renderProgress(agent: Agent) {
  const progress = getProgress(agent);
  if (!progress) return null;

  const { current, total, label } = progress;
  const percentage = total > 0 ? (current / total) * 100 : 0;

  return (
    <View style={styles.progressSection}>
      <View style={styles.progressBar}>
        <View
          style={[
            styles.progressFill,
            { width: `${percentage}%`, backgroundColor: getStatusColor(agent.status) },
          ]}
        />
      </View>
      <Text style={styles.progressText}>
        {current.toLocaleString()} / {total.toLocaleString()} {label}
      </Text>
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
      return '#3b82f6'; // blue
    case 'aceable-bot':
      return Colors.warning; // amber
    case 'claude-agent':
    case 'claude-code':
    default:
      return Colors.primary; // indigo
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surfaceLight,
    marginHorizontal: 16,
    marginTop: 16,
    paddingHorizontal: 12,
    paddingVertical: Platform.OS === 'ios' ? 10 : 8,
    borderRadius: 12,
  },
  searchIcon: {
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 15,
    color: Colors.text,
  },
  filterContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 8,
  },
  filterChip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: Colors.surfaceLight,
  },
  filterChipActive: {
    backgroundColor: Colors.primary,
  },
  filterChipText: {
    fontSize: 13,
    fontWeight: '500',
    color: Colors.textSecondary,
  },
  filterChipTextActive: {
    color: '#fff',
  },
  listContent: {
    padding: 16,
    paddingTop: 0,
  },
  columnWrapper: {
    gap: 12,
  },
  card: {
    flex: 1,
    backgroundColor: Colors.surface,
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    borderLeftWidth: 4,
  },
  cardTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  cardTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 8,
  },
  agentIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.text,
    flex: 1,
  },
  statusBadgeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  pulseDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.success,
  },
  cardGoal: {
    fontSize: 14,
    color: Colors.textSecondary,
    marginBottom: 12,
    lineHeight: 20,
  },
  progressSection: {
    marginBottom: 12,
  },
  progressBar: {
    height: 6,
    backgroundColor: Colors.surfaceLight,
    borderRadius: 3,
    overflow: 'hidden',
    marginBottom: 6,
  },
  progressFill: {
    height: '100%',
    borderRadius: 3,
  },
  progressText: {
    fontSize: 12,
    color: Colors.textSecondary,
  },
  currentTask: {
    fontSize: 13,
    fontStyle: 'italic',
    color: Colors.textMuted,
    marginBottom: 12,
  },
  cardBottomRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
  },
  quickActions: {
    flexDirection: 'row',
    gap: 8,
  },
  quickActionBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
  },
  quickActionBtnPrimary: {
    backgroundColor: Colors.primary,
  },
  quickActionBtnWarning: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: Colors.warning,
  },
  quickActionBtnDefault: {
    backgroundColor: Colors.surfaceLight,
  },
  quickActionTextPrimary: {
    fontSize: 13,
    fontWeight: '600',
    color: '#fff',
  },
  quickActionTextWarning: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.warning,
  },
  quickActionTextDefault: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.text,
  },
  fab: {
    position: 'absolute',
    right: 20,
    bottom: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: Colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
  },
});
