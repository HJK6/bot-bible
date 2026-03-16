import { Stack } from 'expo-router';
import { Colors } from '@/constants/Colors';

export default function MocksLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: Colors.surface },
        headerTintColor: Colors.text,
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Agents', headerShown: true }} />
      <Stack.Screen name="agent/[id]" />
      <Stack.Screen name="v2" options={{ headerShown: false }} />
      <Stack.Screen name="v3" options={{ headerShown: false }} />
    </Stack>
  );
}
