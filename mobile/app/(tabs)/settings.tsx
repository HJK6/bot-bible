import React, { useState } from 'react';
import { View, Text, Pressable, StyleSheet, ActivityIndicator } from 'react-native';
import { useAuthenticator } from '@aws-amplify/ui-react-native';
import { Colors } from '@/constants/Colors';
import usePushNotifications from '../../src/hooks/usePushNotifications';
import useUsage from '../../src/hooks/useUsage';
import useAutoRefresh from '../../src/hooks/useAutoRefresh';

function UsageBar({ pct, color }: { pct: number; color: string }) {
  return (
    <View style={barStyles.track}>
      <View style={[barStyles.fill, { width: `${Math.min(pct, 100)}%`, backgroundColor: color }]} />
    </View>
  );
}

function getBarColor(pct: number): string {
  if (pct >= 80) return Colors.error;
  if (pct >= 50) return Colors.warning;
  return Colors.success;
}

function timeAgo(isoString: string): string {
  if (!isoString) return '';
  const now = new Date();
  const then = new Date(isoString);
  const diffMs = now.getTime() - then.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function SettingsScreen() {
  const { user, signOut } = useAuthenticator();
  const { expoPushToken, error: pushError } = usePushNotifications();
  const { usage, loading: usageLoading, refetch: refetchUsage } = useUsage();
  const [expanded, setExpanded] = useState(false);

  useAutoRefresh(refetchUsage, { intervalMs: 5 * 60 * 1000 }); // 5 min refresh

  const sessionPct = usage?.session_pct ?? 0;
  const sessionColor = getBarColor(sessionPct);

  return (
    <View style={styles.container}>
      {/* Usage Tracker - primary card */}
      <Pressable
        style={({ pressed }) => [styles.usageCard, pressed && styles.pressed]}
        onPress={() => setExpanded(!expanded)}
      >
        <View style={styles.usageHeader}>
          <Text style={styles.usageTitle}>Claude Code Usage</Text>
          {usageLoading && !usage ? (
            <ActivityIndicator size="small" color={Colors.textMuted} />
          ) : (
            <Text style={[styles.usagePct, { color: sessionColor }]}>
              {sessionPct}%
            </Text>
          )}
        </View>

        {usage && (
          <>
            <UsageBar pct={sessionPct} color={sessionColor} />
            <View style={styles.usageSubRow}>
              <Text style={styles.usageSubLabel}>Session (5h)</Text>
              <Text style={styles.usageSubValue}>
                Resets {usage.session_resets || 'N/A'}
              </Text>
            </View>
          </>
        )}

        {!usage && !usageLoading && (
          <Text style={styles.usageSubLabel}>No usage data yet</Text>
        )}

        {/* Expanded details */}
        {expanded && usage && (
          <View style={styles.expandedSection}>
            <View style={styles.divider} />

            {/* Week - all models */}
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Week (all models)</Text>
              <Text style={[styles.detailPct, { color: getBarColor(usage.week_all_pct) }]}>
                {usage.week_all_pct}%
              </Text>
            </View>
            <UsageBar pct={usage.week_all_pct} color={getBarColor(usage.week_all_pct)} />
            <Text style={styles.detailReset}>Resets {usage.week_all_resets || 'N/A'}</Text>

            {/* Week - sonnet */}
            <View style={[styles.detailRow, { marginTop: 12 }]}>
              <Text style={styles.detailLabel}>Week (Sonnet)</Text>
              <Text style={[styles.detailPct, { color: getBarColor(usage.week_sonnet_pct) }]}>
                {usage.week_sonnet_pct}%
              </Text>
            </View>
            <UsageBar pct={usage.week_sonnet_pct} color={getBarColor(usage.week_sonnet_pct)} />
            <Text style={styles.detailReset}>Resets {usage.week_sonnet_resets || 'N/A'}</Text>

            {/* Extra usage */}
            <View style={[styles.detailRow, { marginTop: 12 }]}>
              <Text style={styles.detailLabel}>Extra usage</Text>
              <Text style={styles.detailReset}>
                {usage.extra_usage === 'not_enabled' ? 'Not enabled' : usage.extra_usage}
              </Text>
            </View>

            {/* Last refreshed */}
            <View style={[styles.detailRow, { marginTop: 12 }]}>
              <Text style={styles.detailLabel}>Last refreshed</Text>
              <Text style={styles.detailReset}>
                {usage.last_heartbeat ? timeAgo(usage.last_heartbeat) : 'N/A'}
              </Text>
            </View>
          </View>
        )}

        <Text style={styles.expandHint}>
          {expanded ? 'Tap to collapse' : 'Tap for details'}
        </Text>
      </Pressable>

      <View style={styles.section}>
        <Text style={styles.label}>Signed in as</Text>
        <Text style={styles.value}>
          {user?.signInDetails?.loginId || 'Unknown'}
        </Text>
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>Push Notifications</Text>
        <Text style={styles.value}>
          {expoPushToken ? 'Enabled' : pushError || 'Not registered'}
        </Text>
        {expoPushToken && (
          <Text style={styles.tokenText} numberOfLines={1}>
            {expoPushToken}
          </Text>
        )}
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>Version</Text>
        <Text style={styles.value}>1.0.0</Text>
      </View>

      <Pressable
        style={({ pressed }) => [styles.signOutButton, pressed && styles.pressed]}
        onPress={signOut}
      >
        <Text style={styles.signOutText}>Sign Out</Text>
      </Pressable>
    </View>
  );
}

const barStyles = StyleSheet.create({
  track: {
    height: 8,
    backgroundColor: Colors.surfaceLight,
    borderRadius: 4,
    overflow: 'hidden',
    marginTop: 8,
  },
  fill: {
    height: '100%',
    borderRadius: 4,
  },
});

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    padding: 20,
  },
  usageCard: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  usageHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  usageTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.text,
  },
  usagePct: {
    fontSize: 18,
    fontWeight: '700',
  },
  usageSubRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 6,
  },
  usageSubLabel: {
    fontSize: 12,
    color: Colors.textMuted,
  },
  usageSubValue: {
    fontSize: 12,
    color: Colors.textSecondary,
  },
  expandHint: {
    fontSize: 11,
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: 10,
  },
  expandedSection: {
    marginTop: 4,
  },
  divider: {
    height: 1,
    backgroundColor: Colors.border,
    marginVertical: 12,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  detailLabel: {
    fontSize: 13,
    color: Colors.textSecondary,
  },
  detailPct: {
    fontSize: 15,
    fontWeight: '600',
  },
  detailReset: {
    fontSize: 11,
    color: Colors.textMuted,
    marginTop: 4,
  },
  section: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  label: {
    fontSize: 12,
    color: Colors.textMuted,
    marginBottom: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  value: {
    fontSize: 16,
    color: Colors.text,
  },
  tokenText: {
    fontSize: 10,
    color: Colors.textMuted,
    marginTop: 4,
  },
  signOutButton: {
    backgroundColor: Colors.error + '20',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginTop: 20,
    borderWidth: 1,
    borderColor: Colors.error + '40',
  },
  pressed: {
    opacity: 0.7,
  },
  signOutText: {
    color: Colors.error,
    fontSize: 16,
    fontWeight: '600',
  },
});
