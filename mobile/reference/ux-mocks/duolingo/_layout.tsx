import { Stack } from 'expo-router';

export default function DuolingoLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="pick-goal" />
      <Stack.Screen name="quiz" />
    </Stack>
  );
}
