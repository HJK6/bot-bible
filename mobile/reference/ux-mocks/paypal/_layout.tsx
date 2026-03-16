import { Stack } from 'expo-router';

export default function PayPalLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="enter-amount" />
      <Stack.Screen name="number-pad" />
    </Stack>
  );
}
