import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { Colors } from '@/constants/Colors';
import useUpdates from '../../src/hooks/useUpdates';
import useAutoRefresh from '../../src/hooks/useAutoRefresh';
import UpdateCard from '../../src/components/UpdateCard';
import { AgentChatMessage } from '../../src/types/agent';

export default function UpdatesScreen() {
  const { updates, loading, refetch } = useUpdates();
  const [refreshing, setRefreshing] = useState(false);

  useAutoRefresh(refetch, { intervalMs: 10000 });

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  }, [refetch]);

  const renderItem = useCallback(
    ({ item }: { item: AgentChatMessage }) => <UpdateCard message={item} />,
    []
  );

  const keyExtractor = useCallback(
    (item: AgentChatMessage) => `${item.agent_id}-${item.timestamp}`,
    []
  );

  if (loading && updates.length === 0) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={updates}
        renderItem={renderItem}
        keyExtractor={keyExtractor}
        contentContainerStyle={updates.length === 0 ? styles.emptyList : styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor={Colors.primary}
          />
        }
        ListEmptyComponent={
          <View style={styles.centered}>
            <Text style={styles.emptyText}>No updates yet</Text>
          </View>
        }
      />
    </View>
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
  list: {
    paddingVertical: 8,
  },
  emptyList: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: 16,
  },
});
