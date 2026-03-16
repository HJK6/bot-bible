import { useState, useEffect, useCallback } from 'react';
import * as Notifications from 'expo-notifications';
import { type EventSubscription } from 'expo-modules-core';

const unreadAgentIds = new Set<string>();
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((fn) => fn());
}

export function markRead(agentId: string) {
  unreadAgentIds.delete(agentId);
  notify();
}

export default function useUnreadNotifications() {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const listener = () => forceUpdate((n) => n + 1);
    listeners.add(listener);

    // Listen for incoming notifications and track agent_id
    const sub: EventSubscription = Notifications.addNotificationReceivedListener(
      (notification) => {
        const agentId = notification.request.content.data?.agent_id as string | undefined;
        if (agentId) {
          unreadAgentIds.add(agentId);
          notify();
        }
      }
    );

    return () => {
      listeners.delete(listener);
      sub.remove();
    };
  }, []);

  const hasUnread = useCallback(
    (agentId: string) => unreadAgentIds.has(agentId),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recompute on state change
    [unreadAgentIds.size]
  );

  const hasUnreadUpdates = unreadAgentIds.has('system');
  const hasUnreadChats = Array.from(unreadAgentIds).some((id) => id !== 'system');

  return { hasUnread, hasUnreadUpdates, hasUnreadChats, unreadAgentIds };
}
