import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Colors } from '@/constants/Colors';
import { ScheduledJob } from '../types/agent';

interface Props {
  job: ScheduledJob;
}

export default function ScheduledJobItem({ job }: Props) {
  const statusColor = job.stale
    ? Colors.textMuted
    : job.active
    ? Colors.success
    : Colors.warning;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <FontAwesome name="clock-o" size={13} color={Colors.textMuted} />
          <Text style={styles.title} numberOfLines={1}>
            {job.tag}
          </Text>
        </View>
        <View style={[styles.badge, { backgroundColor: statusColor + '20' }]}>
          <View style={[styles.dot, { backgroundColor: statusColor }]} />
          <Text style={[styles.badgeText, { color: statusColor }]}>
            {job.stale ? 'stale' : job.active ? 'active' : 'off'}
          </Text>
        </View>
      </View>
      <View style={styles.footer}>
        <Text style={styles.schedule}>
          {job.time} {job.days}
        </Text>
        {job.last_run ? (
          <Text style={styles.meta}>{formatTimeAgo(job.last_run)}</Text>
        ) : null}
      </View>
    </View>
  );
}

function formatTimeAgo(dateString: string): string {
  const diff = Date.now() - new Date(dateString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.surface,
    borderRadius: 10,
    padding: 12,
    marginHorizontal: 16,
    marginVertical: 3,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 8,
    gap: 7,
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.text,
    flex: 1,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    gap: 4,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: '600',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  schedule: {
    fontSize: 12,
    color: Colors.textSecondary,
  },
  meta: {
    fontSize: 11,
    color: Colors.textMuted,
  },
});
