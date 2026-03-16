import { Stack } from 'expo-router';

export default function MocksLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="paypal" />
      <Stack.Screen name="starbucks" />
      <Stack.Screen name="duolingo" />
    </Stack>
  );
}
