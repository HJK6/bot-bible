import { Stack } from 'expo-router';
import { Colors } from '@/constants/Colors';

export default function V2Layout() {
  return (
    <Stack screenOptions={{ headerStyle: { backgroundColor: Colors.surface }, headerTintColor: Colors.text }}>
      <Stack.Screen name="index" options={{ title: 'Agents · v2', headerShown: true }} />
      <Stack.Screen name="agent/[id]" />
    </Stack>
  );
}
