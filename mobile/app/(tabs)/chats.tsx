import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  Pressable,
  RefreshControl,
  ActivityIndicator,
  Alert,
  Modal,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { Swipeable } from 'react-native-gesture-handler';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import * as ImagePicker from 'expo-image-picker';
import { Colors } from '@/constants/Colors';
import useChats, { ChatPreview } from '../../src/hooks/useChats';
import useAutoRefresh from '../../src/hooks/useAutoRefresh';
import useCreateCommand from '../../src/hooks/useCreateCommand';
import useResponsive from '../../src/hooks/useResponsive';
import useUnreadNotifications from '../../src/hooks/useUnreadNotifications';
import { callApi } from '../../src/services/api';
import { uploadImage } from '../../src/services/upload';

function formatTime(ts: number): string {
  if (!ts) return '';
  const now = Date.now();
  const diff = now - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

const statusColors: Record<string, string> = {
  running: Colors.success,
  idle: Colors.warning,
  stale: Colors.textMuted,
  completed: Colors.textMuted,
  failed: Colors.error,
};

// --- Project tree for new chat seeded options ---
interface TreeNode {
  label: string;
  icon: string;
  children?: TreeNode[];
  /** If set, clicking this node auto-starts a chat with this prompt */
  autoPrompt?: string;
  /** Context prefix injected into every chat started under this node */
  contextPrefix?: string;
}

const PROJECT_TREE: TreeNode[] = [
  {
    label: 'Altum Realty',
    icon: 'building',
    contextPrefix: '[Altum Realty] ',
    children: [
      {
        label: 'Report Bug',
        icon: 'bug',
        contextPrefix: '[Altum Realty > Bug] ',
      },
      {
        label: 'Run Report',
        icon: 'bar-chart',
        contextPrefix: '[Altum Realty > Report] ',
        children: [
          {
            label: 'Call Days Report',
            icon: 'phone',
            autoPrompt: 'Run the Altum Realty call days report and send the results.',
          },
        ],
      },
    ],
  },
];

export default function ChatsScreen() {
  const router = useRouter();
  const { chats, loading, refetch } = useChats();
  const { createCommand, loading: commandLoading } = useCreateCommand();
  const { isDesktop, contentWidth } = useResponsive();
  const { hasUnread } = useUnreadNotifications();
  const [refreshing, setRefreshing] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [modalImageUri, setModalImageUri] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [showTrash, setShowTrash] = useState(false);
  const [trashedChats, setTrashedChats] = useState<ChatPreview[]>([]);
  const [trashedLoading, setTrashedLoading] = useState(false);
  // Tree navigation state: path of selected nodes
  const [treePath, setTreePath] = useState<TreeNode[]>([]);

  useAutoRefresh(refetch, { intervalMs: 10000 });

  const fetchTrashed = useCallback(async () => {
    try {
      setTrashedLoading(true);
      const agents = await callApi<any[]>('dashGetTrashedAgents');
      if (agents) {
        setTrashedChats(
          agents.map((a) => ({
            agent_id: a.agent_id,
            title: a.title || a.agent_name || a.agent_id.slice(0, 8),
            lastMessage: a.current_task || a.goal || '',
            lastTimestamp: a.trashed_at ? new Date(a.trashed_at).getTime() : 0,
            status: 'trashed',
          }))
        );
      }
    } catch {
      // ignore
    } finally {
      setTrashedLoading(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await refetch();
    if (showTrash) await fetchTrashed();
    setRefreshing(false);
  }, [refetch, showTrash, fetchTrashed]);

  const handleChatPress = useCallback(
    (chat: ChatPreview) => {
      router.push(`/agent/${chat.agent_id}`);
    },
    [router]
  );

  const handleDeleteChat = useCallback(
    async (chat: ChatPreview) => {
      try {
        await callApi('dashDeleteAgent', { agent_id: chat.agent_id });
        setTimeout(refetch, 1000);
      } catch (e: any) {
        Alert.alert('Delete Failed', e.message);
      }
    },
    [refetch]
  );

  const handleStopChat = useCallback(
    async (chat: ChatPreview) => {
      try {
        await createCommand('stop_agent', { agent_id: chat.agent_id });
        setTimeout(refetch, 2000);
      } catch (e: any) {
        Alert.alert('Stop Failed', e.message);
      }
    },
    [createCommand, refetch]
  );

  const handleToggleTrash = useCallback(async () => {
    const next = !showTrash;
    setShowTrash(next);
    if (next && trashedChats.length === 0) {
      await fetchTrashed();
    }
  }, [showTrash, trashedChats.length, fetchTrashed]);

  const handleRestoreChat = useCallback(
    async (chat: ChatPreview) => {
      try {
        await callApi('dashRestoreAgent', { agent_id: chat.agent_id });
        setTrashedChats((prev) => prev.filter((c) => c.agent_id !== chat.agent_id));
        setTimeout(refetch, 1000);
      } catch (e: any) {
        Alert.alert('Restore Failed', e.message);
      }
    },
    [refetch]
  );

  const handlePickFromLibrary = useCallback(async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission required', 'Please allow access to your photo library.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.7,
      allowsMultipleSelection: true,
      selectionLimit: 10,
    });
    if (!result.canceled && result.assets.length > 0) {
      setModalImageUri(result.assets[0].uri);
    }
  }, []);

  const handleTakeModalPhoto = useCallback(async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission required', 'Please allow camera access to take photos.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'],
      quality: 0.7,
    });
    if (!result.canceled && result.assets.length > 0) {
      setModalImageUri(result.assets[0].uri);
    }
  }, []);

  const handlePickModalImage = useCallback(() => {
    if (Platform.OS === 'web') {
      handlePickFromLibrary();
      return;
    }
    Alert.alert('Add Photo', undefined, [
      { text: 'Take Photo', onPress: handleTakeModalPhoto },
      { text: 'Choose from Library', onPress: handlePickFromLibrary },
      { text: 'Cancel', style: 'cancel' },
    ]);
  }, [handlePickFromLibrary, handleTakeModalPhoto]);

  const handleStartAgent = useCallback(async (overridePrompt?: string) => {
    const rawPrompt = overridePrompt ?? prompt;
    const trimmed = rawPrompt.trim();
    if (!trimmed && !modalImageUri) return;
    if (commandLoading || uploading) return;

    // Build final prompt with context prefix from tree path
    const contextPrefix = treePath.length > 0
      ? (treePath[treePath.length - 1].contextPrefix ?? '')
      : '';
    const finalPrompt = overridePrompt
      ? trimmed  // autoPrompt already has full context
      : contextPrefix + trimmed;

    try {
      let imageUrl: string | undefined;
      if (modalImageUri) {
        setUploading(true);
        try {
          imageUrl = await uploadImage(modalImageUri);
        } finally {
          setUploading(false);
        }
      }
      await createCommand('start_agent', { prompt: finalPrompt, image_url: imageUrl });
      setPrompt('');
      setModalImageUri(null);
      setModalVisible(false);
      setTreePath([]);
      setTimeout(refetch, 2000);
    } catch {
      // error in hook
    }
  }, [prompt, modalImageUri, commandLoading, uploading, createCommand, refetch, treePath]);

  const renderChatItem = useCallback(
    ({ item }: { item: ChatPreview }) => {
      const isActive = item.status === 'running' || item.status === 'idle';
      const dotColor = statusColors[item.status] || Colors.textMuted;
      const unread = hasUnread(item.agent_id);

      const renderRightActions = () => (
        <View style={styles.swipeActions}>
          {isActive && (
            <Pressable
              style={styles.stopAction}
              onPress={() => {
                Alert.alert('Stop Agent', `Stop "${item.title}"?`, [
                  { text: 'Cancel', style: 'cancel' },
                  { text: 'Stop', style: 'destructive', onPress: () => handleStopChat(item) },
                ]);
              }}
            >
              <FontAwesome name="stop-circle" size={20} color="#fff" />
            </Pressable>
          )}
          <Pressable
            style={styles.deleteAction}
            onPress={() => {
              Alert.alert('Delete Chat', `Delete "${item.title}"?`, [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Delete', style: 'destructive', onPress: () => handleDeleteChat(item) },
              ]);
            }}
          >
            <FontAwesome name="trash" size={20} color="#fff" />
          </Pressable>
        </View>
      );

      return (
        <Swipeable renderRightActions={renderRightActions} overshootRight={false} friction={2}>
          <Pressable
            style={({ pressed }) => [styles.chatItem, pressed && styles.chatItemPressed]}
            onPress={() => handleChatPress(item)}
          >
            <View style={styles.avatar}>
              <View style={[styles.avatarDot, { backgroundColor: dotColor }]} />
              <FontAwesome name="comment" size={20} color={Colors.textMuted} />
            </View>
            <View style={styles.chatContent}>
              <View style={styles.chatHeader}>
                <Text style={[styles.chatTitle, unread && styles.chatTitleUnread]} numberOfLines={1}>
                  {item.title}
                </Text>
                <Text style={styles.chatTime}>{formatTime(item.lastTimestamp)}</Text>
              </View>
              <View style={styles.chatPreview}>
                <Text style={[styles.chatLastMessage, unread && styles.chatLastMessageUnread]} numberOfLines={2}>
                  {item.lastMessage || 'No messages yet'}
                </Text>
                {unread && <View style={styles.unreadBadge} />}
              </View>
            </View>
          </Pressable>
        </Swipeable>
      );
    },
    [handleChatPress, handleDeleteChat, handleStopChat, hasUnread]
  );

  if (loading && chats.length === 0) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={styles.container}>
      <FlatList
        data={chats}
        keyExtractor={(item) => item.agent_id}
        renderItem={renderChatItem}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={Colors.primary} />
        }
        contentContainerStyle={[
          styles.listContent,
          isDesktop && { maxWidth: contentWidth, alignSelf: 'center', width: '100%' },
        ]}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <FontAwesome name="comments" size={48} color={Colors.textMuted} />
            <Text style={styles.emptyText}>No chats yet</Text>
            <Text style={styles.emptySubtext}>Start a new agent to begin chatting</Text>
          </View>
        }
        ListFooterComponent={
          <View>
            <Pressable style={styles.trashToggle} onPress={handleToggleTrash}>
              <FontAwesome
                name={showTrash ? 'chevron-down' : 'chevron-right'}
                size={12}
                color={Colors.textMuted}
              />
              <FontAwesome name="trash-o" size={14} color={Colors.textMuted} />
              <Text style={styles.trashToggleText}>
                Deleted{trashedChats.length > 0 ? ` (${trashedChats.length})` : ''}
              </Text>
            </Pressable>
            {showTrash && (
              trashedLoading ? (
                <ActivityIndicator size="small" color={Colors.textMuted} style={{ paddingVertical: 20 }} />
              ) : trashedChats.length === 0 ? (
                <Text style={styles.trashEmpty}>Trash is empty</Text>
              ) : (
                trashedChats.map((item) => (
                  <View key={item.agent_id} style={styles.trashedItem}>
                    <Pressable
                      style={styles.trashedContent}
                      onPress={() => router.push(`/agent/${item.agent_id}`)}
                    >
                      <View style={styles.avatar}>
                        <FontAwesome name="comment" size={20} color={Colors.textMuted} />
                      </View>
                      <View style={styles.chatContent}>
                        <Text style={styles.trashedTitle} numberOfLines={1}>{item.title}</Text>
                        <Text style={styles.trashedMeta}>
                          Deleted {formatTime(item.lastTimestamp)}
                        </Text>
                      </View>
                    </Pressable>
                    <Pressable
                      style={styles.restoreButton}
                      onPress={() => {
                        Alert.alert('Restore Chat', `Restore "${item.title}"?`, [
                          { text: 'Cancel', style: 'cancel' },
                          { text: 'Restore', onPress: () => handleRestoreChat(item) },
                        ]);
                      }}
                    >
                      <FontAwesome name="undo" size={16} color={Colors.primary} />
                    </Pressable>
                  </View>
                ))
              )
            )}
          </View>
        }
      />

      {/* FAB for new chat */}
      <Pressable style={styles.fab} onPress={() => { setTreePath([]); setPrompt(''); setModalImageUri(null); setModalVisible(true); }}>
        <FontAwesome name="plus" size={22} color="#fff" />
      </Pressable>

      {/* New Agent Modal with tree navigation */}
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
              {/* Header with back navigation */}
              <View style={styles.modalHeader}>
                {treePath.length > 0 && (
                  <Pressable
                    style={styles.backButton}
                    onPress={() => setTreePath((prev) => prev.slice(0, -1))}
                  >
                    <FontAwesome name="chevron-left" size={14} color={Colors.primary} />
                  </Pressable>
                )}
                <Text style={styles.modalTitle}>
                  {treePath.length === 0 ? 'New Chat' : treePath[treePath.length - 1].label}
                </Text>
              </View>

              {/* Breadcrumb when inside a project */}
              {treePath.length > 0 && (
                <View style={styles.breadcrumb}>
                  {treePath.map((node, i) => (
                    <React.Fragment key={i}>
                      {i > 0 && <FontAwesome name="chevron-right" size={8} color={Colors.textMuted} style={{ marginHorizontal: 6 }} />}
                      <Pressable onPress={() => setTreePath((prev) => prev.slice(0, i + 1))}>
                        <Text style={[styles.breadcrumbText, i === treePath.length - 1 && styles.breadcrumbActive]}>
                          {node.label}
                        </Text>
                      </Pressable>
                    </React.Fragment>
                  ))}
                </View>
              )}

              {/* Tree options for current level */}
              {(() => {
                const currentChildren = treePath.length === 0
                  ? PROJECT_TREE
                  : treePath[treePath.length - 1].children;
                if (currentChildren && currentChildren.length > 0) {
                  return (
                    <View style={styles.treeOptions}>
                      {currentChildren.map((node, i) => (
                        <Pressable
                          key={i}
                          style={({ pressed }) => [styles.treeOption, pressed && styles.treeOptionPressed]}
                          onPress={() => {
                            if (node.autoPrompt) {
                              handleStartAgent(node.autoPrompt);
                            } else if (node.children) {
                              setTreePath((prev) => [...prev, node]);
                            } else {
                              setTreePath((prev) => [...prev, node]);
                            }
                          }}
                        >
                          <View style={styles.treeOptionIcon}>
                            <FontAwesome name={node.icon as any} size={16} color={Colors.primary} />
                          </View>
                          <Text style={styles.treeOptionLabel}>{node.label}</Text>
                          {node.autoPrompt ? (
                            <FontAwesome name="bolt" size={12} color={Colors.warning} style={{ marginLeft: 'auto' }} />
                          ) : node.children ? (
                            <FontAwesome name="chevron-right" size={12} color={Colors.textMuted} style={{ marginLeft: 'auto' }} />
                          ) : null}
                        </Pressable>
                      ))}
                    </View>
                  );
                }
                return null;
              })()}

              {/* Divider */}
              <View style={styles.treeDivider}>
                <View style={styles.treeDividerLine} />
                <Text style={styles.treeDividerText}>or type a message</Text>
                <View style={styles.treeDividerLine} />
              </View>

              {/* Text input for custom prompt */}
              <TextInput
                style={styles.modalInput}
                value={prompt}
                onChangeText={setPrompt}
                placeholder={treePath.length > 0
                  ? `Message about ${treePath[treePath.length - 1].label}...`
                  : 'What should the agent do?'}
                placeholderTextColor={Colors.textMuted}
                multiline
                maxLength={2000}
              />
              {modalImageUri && (
                <View style={styles.modalImagePreview}>
                  <Image source={{ uri: modalImageUri }} style={styles.modalPreviewImage} />
                  <Pressable style={styles.modalRemoveImage} onPress={() => setModalImageUri(null)}>
                    <FontAwesome name="times-circle" size={20} color={Colors.textMuted} />
                  </Pressable>
                </View>
              )}
              <View style={styles.modalButtons}>
                <Pressable style={styles.imagePickerButton} onPress={handlePickModalImage}>
                  <FontAwesome name="image" size={18} color={Colors.primary} />
                </Pressable>
                <View style={{ flex: 1 }} />
                <Pressable style={styles.cancelButton} onPress={() => { setModalVisible(false); setModalImageUri(null); setTreePath([]); }}>
                  <Text style={styles.cancelText}>Cancel</Text>
                </Pressable>
                <Pressable
                  style={[styles.startButton, (!prompt.trim() && !modalImageUri || commandLoading || uploading) && styles.startButtonDisabled]}
                  onPress={() => handleStartAgent()}
                  disabled={(!prompt.trim() && !modalImageUri) || commandLoading || uploading}
                >
                  {commandLoading || uploading ? (
                    <ActivityIndicator size="small" color="#fff" />
                  ) : (
                    <Text style={styles.startText}>Start</Text>
                  )}
                </Pressable>
              </View>
            </Pressable>
          </Pressable>
        </KeyboardAvoidingView>
      </Modal>
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
  listContent: {
    flexGrow: 1,
  },
  chatItem: {
    flexDirection: 'row',
    padding: 14,
    paddingHorizontal: 16,
    backgroundColor: Colors.background,
  },
  chatItemPressed: {
    backgroundColor: Colors.surface,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  avatarDot: {
    position: 'absolute',
    top: 0,
    right: 0,
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: Colors.background,
  },
  chatContent: {
    flex: 1,
    justifyContent: 'center',
  },
  chatHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  chatTitle: {
    fontSize: 15,
    fontWeight: '500',
    color: Colors.text,
    flex: 1,
    marginRight: 8,
  },
  chatTitleUnread: {
    fontWeight: '700',
  },
  chatTime: {
    fontSize: 12,
    color: Colors.textMuted,
  },
  chatPreview: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  chatLastMessage: {
    fontSize: 13,
    color: Colors.textSecondary,
    flex: 1,
    lineHeight: 18,
  },
  chatLastMessageUnread: {
    color: Colors.text,
    fontWeight: '500',
  },
  unreadBadge: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: Colors.primary,
    marginLeft: 8,
  },
  separator: {
    height: 1,
    backgroundColor: Colors.border,
    marginLeft: 76,
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
    fontSize: 18,
    fontWeight: '600',
  },
  emptySubtext: {
    color: Colors.textMuted,
    fontSize: 14,
  },
  swipeActions: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  stopAction: {
    backgroundColor: Colors.warning,
    justifyContent: 'center',
    alignItems: 'center',
    width: 60,
  },
  deleteAction: {
    backgroundColor: Colors.error,
    justifyContent: 'center',
    alignItems: 'center',
    width: 60,
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
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
    gap: 10,
  },
  backButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: Colors.background,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: Colors.text,
  },
  breadcrumb: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
    paddingHorizontal: 2,
  },
  breadcrumbText: {
    fontSize: 12,
    color: Colors.textMuted,
    fontWeight: '500',
  },
  breadcrumbActive: {
    color: Colors.primary,
  },
  treeOptions: {
    gap: 6,
    marginBottom: 4,
  },
  treeOption: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 10,
    backgroundColor: Colors.background,
    borderWidth: 1,
    borderColor: Colors.border,
    gap: 12,
  },
  treeOptionPressed: {
    backgroundColor: Colors.surfaceLight,
    borderColor: Colors.primary,
  },
  treeOptionIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: Colors.primary + '18',
    justifyContent: 'center',
    alignItems: 'center',
  },
  treeOptionLabel: {
    fontSize: 15,
    fontWeight: '500',
    color: Colors.text,
  },
  treeDivider: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 12,
    gap: 10,
  },
  treeDividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: Colors.border,
  },
  treeDividerText: {
    fontSize: 12,
    color: Colors.textMuted,
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
  modalImagePreview: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 10,
  },
  modalPreviewImage: {
    width: 60,
    height: 60,
    borderRadius: 8,
    resizeMode: 'cover',
  },
  modalRemoveImage: {
    padding: 4,
  },
  imagePickerButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalButtons: {
    flexDirection: 'row',
    alignItems: 'center',
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
  trashToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    marginTop: 8,
  },
  trashToggleText: {
    fontSize: 13,
    color: Colors.textMuted,
    fontWeight: '500',
  },
  trashEmpty: {
    textAlign: 'center',
    color: Colors.textMuted,
    fontSize: 13,
    paddingVertical: 16,
  },
  trashedItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingRight: 16,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  trashedContent: {
    flex: 1,
    flexDirection: 'row',
    padding: 14,
    paddingHorizontal: 16,
    opacity: 0.5,
  },
  trashedTitle: {
    fontSize: 15,
    fontWeight: '500',
    color: Colors.textMuted,
  },
  trashedMeta: {
    fontSize: 12,
    color: Colors.textMuted,
    marginTop: 2,
  },
  restoreButton: {
    padding: 10,
  },
});
