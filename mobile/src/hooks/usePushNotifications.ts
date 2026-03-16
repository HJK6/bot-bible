import { useState, useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { router } from 'expo-router';
import { type EventSubscription } from 'expo-modules-core';
import { callApi } from '../services/api';

// Show notifications even when app is foregrounded
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

interface PushNotificationState {
  expoPushToken: string | null;
  error: string | null;
}

export default function usePushNotifications(): PushNotificationState {
  const [expoPushToken, setExpoPushToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const responseListener = useRef<EventSubscription | null>(null);

  useEffect(() => {
    // Push notifications only work on physical devices, not web
    if (!Device.isDevice || Platform.OS === 'web') {
      return;
    }

    registerForPushNotifications()
      .then((token) => {
        if (token) {
          setExpoPushToken(token);
          registerTokenWithBackend(token);
        }
      })
      .catch((e) => setError(e.message));

    // Handle notification taps — navigate to agent chat or updates
    responseListener.current =
      Notifications.addNotificationResponseReceivedListener((response) => {
        const data = response.notification.request.content.data;
        if (data?.agent_id === 'system') {
          router.push('/updates' as any);
        } else if (data?.agent_id) {
          router.push({ pathname: `/agent/[id]`, params: { id: data.agent_id, tab: 'chat' } } as any);
        }
      });

    // Handle cold start — app was closed when notification was tapped
    Notifications.getLastNotificationResponseAsync().then((response) => {
      if (response) {
        const data = response.notification.request.content.data;
        if (data?.agent_id === 'system') {
          setTimeout(() => {
            router.push('/updates' as any);
          }, 500);
        } else if (data?.agent_id) {
          setTimeout(() => {
            router.push({ pathname: `/agent/[id]`, params: { id: data.agent_id, tab: 'chat' } } as any);
          }, 500);
        }
      }
    });

    return () => {
      if (responseListener.current) {
        responseListener.current.remove();
      }
    };
  }, []);

  return { expoPushToken, error };
}

async function registerForPushNotifications(): Promise<string | null> {
  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') {
    return null;
  }

  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (!projectId) {
    console.warn('Missing EAS projectId in app.json — push tokens unavailable');
    return null;
  }

  const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
  return tokenData.data;
}

async function registerTokenWithBackend(token: string): Promise<void> {
  try {
    await callApi('dashRegisterPushToken', {
      push_token: token,
      platform: Platform.OS,
      device_name: Device.deviceName || 'Unknown',
    });
  } catch (e) {
    console.error('Failed to register push token:', e);
  }
}
