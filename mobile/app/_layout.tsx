import 'react-native-get-random-values';
import { LogBox } from 'react-native';

// Suppress harmless Expo native module warnings that fire on startup
LogBox.ignoreLogs([
  'Cannot find native module',
  'Calling getExpoPushTokenAsync',
]);

import FontAwesome from '@expo/vector-icons/FontAwesome';
import { DarkTheme, ThemeProvider } from '@react-navigation/native';
import { useFonts } from 'expo-font';
import { Stack, useSegments } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { AppState, Platform, View, StyleSheet } from 'react-native';
import { Authenticator, ThemeProvider as AmplifyThemeProvider } from '@aws-amplify/ui-react-native';
import type { Theme as AmplifyTheme } from '@aws-amplify/ui-react-native';
import * as Notifications from 'expo-notifications';
import * as Updates from 'expo-updates';
import { configureAuth } from '../src/services/auth';
import usePushNotifications from '../src/hooks/usePushNotifications';
import { Colors } from '@/constants/Colors';

export { ErrorBoundary } from 'expo-router';

export const unstable_settings = {
  initialRouteName: '(tabs)',
};

SplashScreen.preventAutoHideAsync();
configureAuth();

const amplifyTheme: AmplifyTheme = {
  tokens: {
    colors: {
      background: {
        primary: Colors.background,
        secondary: Colors.surface,
        tertiary: Colors.surfaceLight,
      },
      font: {
        primary: Colors.text,
        secondary: Colors.textSecondary,
        tertiary: Colors.textMuted,
        interactive: Colors.primary,
      },
      brand: {
        primary: {
          10: '#e0e0ff',
          20: '#c4b5fd',
          40: '#a78bfa',
          60: Colors.primary,
          80: Colors.primaryDark,
          90: '#3730a3',
          100: '#312e81',
        },
      },
      border: {
        primary: Colors.border,
        secondary: Colors.surfaceLight,
        tertiary: Colors.surface,
        focus: Colors.primary,
      },
    },
  },
};

const AppTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    primary: Colors.primary,
    background: Colors.background,
    card: Colors.surface,
    text: Colors.text,
    border: Colors.border,
  },
};

export default function RootLayout() {
  const [loaded, error] = useFonts({
    SpaceMono: require('../assets/fonts/SpaceMono-Regular.ttf'),
    ...FontAwesome.font,
  });
  usePushNotifications();

  // Check for OTA updates on launch and when app comes to foreground
  useEffect(() => {
    async function checkForUpdate() {
      if (__DEV__) return; // Skip in dev mode
      try {
        const update = await Updates.checkForUpdateAsync();
        if (update.isAvailable) {
          await Updates.fetchUpdateAsync();
          await Updates.reloadAsync();
        }
      } catch (e) {
        // Silently fail — will retry next launch
      }
    }
    checkForUpdate();
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') checkForUpdate();
    });
    return () => sub.remove();
  }, []);

  // Clear badge and dismiss notifications when app comes to foreground
  useEffect(() => {
    const clearBadge = () => {
      Notifications.setBadgeCountAsync(0);
      Notifications.dismissAllNotificationsAsync();
    };
    clearBadge();
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') clearBadge();
    });
    return () => sub.remove();
  }, []);

  useEffect(() => {
    if (error) throw error;
  }, [error]);

  useEffect(() => {
    if (loaded) {
      SplashScreen.hideAsync();
    }
  }, [loaded]);

  const segments = useSegments();
  const isPublicRoute = (segments as string[])[0] === 'public';

  if (!loaded) {
    return null;
  }

  const stackContent = (
    <ThemeProvider value={AppTheme}>
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="agent/[id]"
          options={{
            headerStyle: { backgroundColor: Colors.surface },
            headerTintColor: Colors.text,
          }}
        />
        <Stack.Screen name="mocks" options={{ headerShown: false }} />
        <Stack.Screen name="output" options={{ headerShown: false }} />
        <Stack.Screen name="memory" options={{ headerShown: false }} />
        <Stack.Screen name="stocks" options={{ headerShown: false }} />
        <Stack.Screen name="public/[id]" options={{ headerShown: false }} />
      </Stack>
    </ThemeProvider>
  );

  if (isPublicRoute) {
    return (
      <AmplifyThemeProvider theme={amplifyTheme} colorMode="dark">
        {stackContent}
      </AmplifyThemeProvider>
    );
  }

  return (
    <AmplifyThemeProvider theme={amplifyTheme} colorMode="dark">
      <Authenticator.Provider>
        <Authenticator
          Container={(props: any) => (
            <View style={authStyles.container}>
              <View style={authStyles.card}>{props.children}</View>
            </View>
          )}
          components={{
            SignIn: (props: any) => (
              <Authenticator.SignIn {...props} hideSignUp />
            ),
          }}
        >
        {stackContent}
        </Authenticator>
      </Authenticator.Provider>
    </AmplifyThemeProvider>
  );
}

const authStyles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.background,
    ...(Platform.OS === 'web' ? { minHeight: '100vh' as any } : {}),
  },
  card: {
    width: '100%',
    maxWidth: 420,
    padding: 24,
  },
});
