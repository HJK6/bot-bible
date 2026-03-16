import { Platform } from 'react-native';
import { Redirect, Slot } from 'expo-router';

export default function StocksLayout() {
  if (Platform.OS !== 'web') {
    return <Redirect href="/" />;
  }
  return <Slot />;
}
