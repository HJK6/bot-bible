import { Stack } from 'expo-router';
import { Colors } from '@/constants/Colors';

export default function V3Layout() {
  return (
    <Stack screenOptions={{ headerStyle: { backgroundColor: Colors.background }, headerTintColor: Colors.text }}>
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="agent/[id]" options={{ headerShown: false }} />
    </Stack>
  );
}
