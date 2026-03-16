import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  Pressable,
  Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Colors } from '@/constants/Colors';
import useProjects from '../../src/hooks/useProjects';
import useResponsive from '../../src/hooks/useResponsive';
import { Project } from '../../src/types/agent';

const CATEGORY_ICONS: Record<string, string> = {
  'Infrastructure': 'server',
  'Trading': 'line-chart',
  'Real Estate': 'home',
  'Automation': 'bolt',
  'AI': 'magic',
  'Frontend': 'desktop',
  'Data': 'database',
};

const STATUS_COLORS: Record<string, string> = {
  active: Colors.success,
  paused: Colors.warning,
  archived: Colors.textMuted,
};

export default function ProjectsScreen() {
  const { projects, loading, refetch } = useProjects();
  const { isDesktop, contentWidth } = useResponsive();
  const [refreshing, setRefreshing] = useState(false);
  const router = useRouter();

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  }, [refetch]);

  if (loading && projects.length === 0) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  const activeCount = projects.filter((p) => p.status === 'active').length;

  return (
    <View style={styles.container}>
      <View style={[styles.header, isDesktop && { paddingHorizontal: (Platform.OS === 'web' ? Math.max(0, (1440 - contentWidth) / 2) : 0) + 16 }]}>
        <Text style={styles.headerCount}>{activeCount} active projects</Text>
      </View>
      <FlatList
        data={projects}
        keyExtractor={(item) => item.project_id}
        renderItem={({ item }) => (
          <ProjectCard
            project={item}
            onPress={() => router.push(`/project/${item.project_id}` as any)}
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
            <FontAwesome name="folder-open-o" size={48} color={Colors.textMuted} />
            <Text style={styles.emptyText}>No projects found</Text>
          </View>
        }
      />
    </View>
  );
}

function ProjectCard({ project, onPress }: { project: Project; onPress: () => void }) {
  const iconName = CATEGORY_ICONS[project.category] || 'code';
  const statusColor = STATUS_COLORS[project.status] || Colors.textMuted;

  return (
    <Pressable
      style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
      onPress={onPress}
    >
      <View style={styles.cardHeader}>
        <View style={[styles.iconContainer, { backgroundColor: Colors.primary + '20' }]}>
          <FontAwesome name={iconName as any} size={18} color={Colors.primary} />
        </View>
        <View style={styles.cardTitleRow}>
          <Text style={styles.cardTitle} numberOfLines={1}>{project.name}</Text>
          <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
        </View>
      </View>
      <Text style={styles.cardDescription} numberOfLines={2}>
        {project.description}
      </Text>
      {project.tech_stack && project.tech_stack.length > 0 && (
        <View style={styles.techRow}>
          {project.tech_stack.slice(0, 4).map((tech) => (
            <Text key={tech} style={styles.techBadge}>{tech}</Text>
          ))}
          {project.tech_stack.length > 4 && (
            <Text style={styles.techMore}>+{project.tech_stack.length - 4}</Text>
          )}
        </View>
      )}
      {project.recent_activity && project.recent_activity.length > 0 && (
        <Text style={styles.recentActivity} numberOfLines={1}>
          {project.recent_activity[0]}
        </Text>
      )}
    </Pressable>
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
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  headerCount: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  listContent: {
    flexGrow: 1,
    paddingTop: 8,
    paddingBottom: 20,
    paddingHorizontal: 12,
  },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    marginVertical: 4,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardPressed: {
    opacity: 0.7,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 8,
  },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  cardTitleRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.text,
    flex: 1,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginLeft: 8,
  },
  cardDescription: {
    fontSize: 13,
    color: Colors.textSecondary,
    lineHeight: 19,
    marginBottom: 8,
  },
  techRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 8,
  },
  techBadge: {
    fontSize: 11,
    color: Colors.primary,
    backgroundColor: Colors.primary + '15',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    overflow: 'hidden',
    fontWeight: '500',
  },
  techMore: {
    fontSize: 11,
    color: Colors.textMuted,
    paddingVertical: 3,
  },
  recentActivity: {
    fontSize: 12,
    color: Colors.textMuted,
    fontStyle: 'italic',
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
