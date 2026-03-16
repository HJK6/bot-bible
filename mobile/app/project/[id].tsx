import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Platform,
} from 'react-native';
import { useLocalSearchParams, useNavigation } from 'expo-router';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Colors } from '@/constants/Colors';
import { callApi } from '../../src/services/api';
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

const STATUS_LABELS: Record<string, { color: string; label: string }> = {
  active: { color: Colors.success, label: 'Active' },
  paused: { color: Colors.warning, label: 'Paused' },
  archived: { color: Colors.textMuted, label: 'Archived' },
};

export default function ProjectDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const navigation = useNavigation();
  const { isDesktop, contentWidth } = useResponsive();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchProject = useCallback(async () => {
    try {
      const result = await callApi<Project>('dashGetProject', { project_id: id });
      if (result && !('status' in result && (result as any).status === 'error')) {
        setProject(result);
      }
    } catch {
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchProject();
  }, [fetchProject]);

  useEffect(() => {
    navigation.setOptions({
      title: project?.name || 'Project',
    });
  }, [navigation, project]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchProject();
    setRefreshing(false);
  }, [fetchProject]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.primary} />
      </View>
    );
  }

  if (!project) {
    return (
      <View style={styles.centered}>
        <FontAwesome name="exclamation-circle" size={48} color={Colors.textMuted} />
        <Text style={styles.emptyText}>Project not found</Text>
      </View>
    );
  }

  const statusInfo = STATUS_LABELS[project.status] || STATUS_LABELS.archived;
  const iconName = CATEGORY_ICONS[project.category] || 'code';

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[
        styles.content,
        isDesktop && { maxWidth: contentWidth, alignSelf: 'center', width: '100%' },
      ]}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={Colors.primary} />
      }
    >
      {/* Header */}
      <View style={styles.headerCard}>
        <View style={styles.headerRow}>
          <View style={[styles.iconContainer, { backgroundColor: Colors.primary + '20' }]}>
            <FontAwesome name={iconName as any} size={24} color={Colors.primary} />
          </View>
          <View style={styles.headerInfo}>
            <Text style={styles.projectName}>{project.name}</Text>
            <View style={styles.statusRow}>
              <View style={[styles.statusBadge, { backgroundColor: statusInfo.color + '20' }]}>
                <View style={[styles.statusDot, { backgroundColor: statusInfo.color }]} />
                <Text style={[styles.statusText, { color: statusInfo.color }]}>{statusInfo.label}</Text>
              </View>
              <Text style={styles.categoryText}>{project.category}</Text>
            </View>
          </View>
        </View>
        <Text style={styles.description}>{project.description}</Text>
      </View>

      {/* Tech Stack */}
      {project.tech_stack && project.tech_stack.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Tech Stack</Text>
          <View style={styles.techGrid}>
            {project.tech_stack.map((tech) => (
              <View key={tech} style={styles.techChip}>
                <Text style={styles.techChipText}>{tech}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Repo Path */}
      {project.repo_path && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Repository</Text>
          <View style={styles.repoRow}>
            <FontAwesome name="folder-o" size={14} color={Colors.textSecondary} />
            <Text selectable style={styles.repoPath}>{project.repo_path}</Text>
          </View>
        </View>
      )}

      {/* Recent Activity */}
      {project.recent_activity && project.recent_activity.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Recent Activity</Text>
          {project.recent_activity.map((activity, i) => (
            <View key={i} style={styles.activityItem}>
              <View style={styles.activityDot} />
              <Text style={styles.activityText}>{activity}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Metadata */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Details</Text>
        <View style={styles.metaGrid}>
          {project.created_at && (
            <MetaItem label="Created" value={new Date(project.created_at).toLocaleDateString()} />
          )}
          {project.updated_at && (
            <MetaItem label="Last Updated" value={new Date(project.updated_at).toLocaleDateString()} />
          )}
        </View>
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
    gap: 12,
  },
  content: {
    padding: 16,
    gap: 12,
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: 16,
  },
  headerCard: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    marginBottom: 12,
  },
  iconContainer: {
    width: 48,
    height: 48,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerInfo: {
    flex: 1,
  },
  projectName: {
    fontSize: 20,
    fontWeight: '700',
    color: Colors.text,
    marginBottom: 4,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '600',
  },
  categoryText: {
    fontSize: 12,
    color: Colors.textMuted,
  },
  description: {
    fontSize: 14,
    color: Colors.textSecondary,
    lineHeight: 21,
  },
  section: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: Colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 10,
  },
  techGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  techChip: {
    backgroundColor: Colors.primary + '15',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  techChipText: {
    fontSize: 13,
    color: Colors.primary,
    fontWeight: '500',
  },
  repoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  repoPath: {
    fontSize: 13,
    color: Colors.textSecondary,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  activityItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    paddingVertical: 6,
  },
  activityDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: Colors.primary,
    marginTop: 6,
  },
  activityText: {
    fontSize: 13,
    color: Colors.text,
    lineHeight: 19,
    flex: 1,
  },
  metaGrid: {
    gap: 8,
  },
  metaItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  metaLabel: {
    fontSize: 13,
    color: Colors.textMuted,
  },
  metaValue: {
    fontSize: 13,
    color: Colors.textSecondary,
  },
});
