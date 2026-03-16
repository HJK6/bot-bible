import React, { useState, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  Pressable,
  Modal,
  TextInput,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Colors } from '@/constants/Colors';
import useResponsive from '../../src/hooks/useResponsive';
import AgentListItem from '../../src/components/AgentListItem';
import { Agent } from '../../src/types/agent';
import { MOCK_AGENTS } from '../../src/data/mockData';

const CLAUDE_TYPES = ['claude-agent', 'claude-code'];

export default function MockAgentsScreen() {
  const router = useRouter();
  const { isDesktop, isWide, contentWidth } = useResponsive();
  const [modalVisible, setModalVisible] = useState(false);
  const [prompt, setPrompt] = useState('');

  const agents = useMemo(() => {
    const order: Record<string, number> = { running: 0, idle: 1, stale: 2, completed: 3, failed: 4 };
    return [...MOCK_AGENTS].sort((a, b) => (order[a.status] ?? 5) - (order[b.status] ?? 5));
  }, []);

  const claudeAgents = useMemo(
    () => agents.filter((a) => CLAUDE_TYPES.includes(a.agent_type)),
    [agents]
  );
  const bots = useMemo(
    () => agents.filter((a) => !CLAUDE_TYPES.includes(a.agent_type)),
    [agents]
  );

  const handleAgentPress = useCallback(
    (agent: Agent) => {
      router.push(`/mocks/agent/${agent.agent_id}`);
    },
    [router]
  );

  const handleStartAgent = useCallback(() => {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    console.log('[MOCK] Start agent:', trimmed);
    setPrompt('');
    setModalVisible(false);
  }, [prompt]);

  const runningCount = agents.filter((a) => a.status === 'running').length;
  const idleCount = agents.filter((a) => a.status === 'idle').length;

  const numColumns = isWide ? 3 : isDesktop ? 2 : 1;

  const renderGrid = (data: Agent[]) => {
    if (numColumns === 1) {
      return data.map((agent) => (
        <AgentListItem key={agent.agent_id} agent={agent} onPress={() => handleAgentPress(agent)} />
      ));
    }
    const rows: Agent[][] = [];
    for (let i = 0; i < data.length; i += numColumns) {
      rows.push(data.slice(i, i + numColumns));
    }
    return rows.map((row, rowIdx) => (
      <View key={rowIdx} style={styles.gridRow}>
        {row.map((agent) => (
          <View key={agent.agent_id} style={{ flex: 1 }}>
            <AgentListItem agent={agent} onPress={() => handleAgentPress(agent)} />
          </View>
        ))}
        {row.length < numColumns &&
          Array.from({ length: numColumns - row.length }).map((_, i) => (
            <View key={`empty-${i}`} style={{ flex: 1 }} />
          ))}
      </View>
    ));
  };

  return (
    <View style={styles.container}>
      {/* Header with stats */}
      <View style={[styles.header, isDesktop && { paddingHorizontal: (Platform.OS === 'web' ? Math.max(0, (1440 - contentWidth) / 2) : 0) + 16 }]}>
        <View style={styles.statsBar}>
          <View style={styles.stat}>
            <View style={[styles.statDot, { backgroundColor: Colors.success }]} />
            <Text style={styles.statText}>{runningCount} running</Text>
          </View>
          <View style={styles.stat}>
            <View style={[styles.statDot, { backgroundColor: Colors.warning }]} />
            <Text style={styles.statText}>{idleCount} idle</Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statText}>{agents.length} total</Text>
          </View>
        </View>
        {isDesktop && (
          <Pressable style={styles.startButtonDesktop} onPress={() => setModalVisible(true)}>
            <FontAwesome name="plus" size={14} color="#fff" />
            <Text style={styles.startButtonDesktopText}>Start Agent</Text>
          </Pressable>
        )}
      </View>

      {/* Scrollable content */}
      <FlatList
        data={[1]}
        keyExtractor={() => 'content'}
        renderItem={() => (
          <View style={[styles.content, isDesktop && { maxWidth: contentWidth, alignSelf: 'center', width: '100%' }]}>
            {claudeAgents.length > 0 && (
              <>
                <View style={styles.sectionHeader}>
                  <Text style={styles.sectionTitle}>Claude Agents ({claudeAgents.length})</Text>
                </View>
                {renderGrid(claudeAgents)}
              </>
            )}
            {bots.length > 0 && (
              <>
                <View style={styles.sectionHeader}>
                  <Text style={styles.sectionTitle}>Bots ({bots.length})</Text>
                </View>
                {renderGrid(bots)}
              </>
            )}
          </View>
        )}
        contentContainerStyle={styles.listContent}
      />

      {/* FAB (mobile only) */}
      {!isDesktop && (
        <Pressable style={styles.fab} onPress={() => setModalVisible(true)}>
          <FontAwesome name="plus" size={22} color="#fff" />
        </Pressable>
      )}

      {/* New Agent Modal */}
      <Modal
        visible={modalVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setModalVisible(false)}
      >
        <KeyboardAvoidingView
          style={styles.modalOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <Pressable style={styles.modalOverlay} onPress={() => setModalVisible(false)}>
            <Pressable
              style={[styles.modalContent, isDesktop && styles.modalContentDesktop]}
              onPress={(e) => e.stopPropagation()}
            >
              <Text style={styles.modalTitle}>Start New Agent</Text>
              <TextInput
                style={styles.modalInput}
                value={prompt}
                onChangeText={setPrompt}
                placeholder="What should the agent do?"
                placeholderTextColor={Colors.textMuted}
                multiline
                maxLength={2000}
                autoFocus
              />
              <View style={styles.modalButtons}>
                <Pressable style={styles.cancelButton} onPress={() => setModalVisible(false)}>
                  <Text style={styles.cancelText}>Cancel</Text>
                </Pressable>
                <Pressable
                  style={[styles.startButton, !prompt.trim() && styles.startButtonDisabled]}
                  onPress={handleStartAgent}
                  disabled={!prompt.trim()}
                >
                  <Text style={styles.startText}>Start</Text>
                </Pressable>
              </View>
            </Pressable>
          </Pressable>
        </KeyboardAvoidingView>
      </Modal>
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
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  statsBar: {
    flexDirection: 'row',
    gap: 16,
  },
  stat: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  statDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statText: {
    fontSize: 13,
    color: Colors.textSecondary,
  },
  startButtonDesktop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: Colors.primary,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  startButtonDesktopText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  content: {
    paddingBottom: 80,
  },
  gridRow: {
    flexDirection: 'row',
  },
  sectionHeader: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 6,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: Colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  listContent: {
    flexGrow: 1,
  },
  fab: {
    position: 'absolute',
    right: 20,
    bottom: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: Colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
  },
  modalOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  modalContent: {
    backgroundColor: Colors.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    minHeight: 250,
    width: '100%',
    position: 'absolute',
    bottom: 0,
  },
  modalContentDesktop: {
    position: 'relative',
    bottom: undefined,
    borderRadius: 16,
    maxWidth: 520,
    width: '90%',
    minHeight: 200,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: Colors.text,
    marginBottom: 16,
  },
  modalInput: {
    backgroundColor: Colors.background,
    borderRadius: 12,
    padding: 14,
    fontSize: 15,
    color: Colors.text,
    minHeight: 100,
    textAlignVertical: 'top',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  modalButtons: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 12,
    marginTop: 16,
  },
  cancelButton: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  cancelText: {
    color: Colors.textSecondary,
    fontSize: 15,
    fontWeight: '600',
  },
  startButton: {
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: Colors.primary,
  },
  startButtonDisabled: {
    backgroundColor: Colors.primary + '40',
  },
  startText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
});
