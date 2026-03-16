import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

export default function EnterAmount() {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.container}>
      {/* Top Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="close" size={28} color="#000" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Enter the amount</Text>
        <View style={{ width: 28 }} />
      </View>

      {/* Content */}
      <View style={styles.content}>
        {/* Large Amount Display */}
        <TouchableOpacity style={styles.amountContainer} onPress={() => router.push('/mocks/paypal/number-pad' as any)}>
          <View style={styles.amountRow}>
            <Text style={styles.dollarSign}>$</Text>
            <Text style={styles.dollars}>0</Text>
            <Text style={styles.cents}>.00</Text>
          </View>
        </TouchableOpacity>

        {/* Explanation Text */}
        <View style={styles.explanationContainer}>
          <Text style={styles.explanationText}>
            PayPal works with or without a balance.
          </Text>
          <Text style={styles.explanationText}>
            Any amount you add is immediately in your account.
          </Text>
        </View>
      </View>

      {/* Bottom Button */}
      <View style={styles.bottomContainer}>
        <TouchableOpacity style={styles.addButton}>
          <Text style={styles.addButtonText}>Add Money</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  headerTitle: {
    fontSize: 16,
    color: '#666',
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  amountContainer: {
    marginBottom: 40,
  },
  amountRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  dollarSign: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#000',
  },
  dollars: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#000',
  },
  cents: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#000',
    marginTop: 4,
  },
  explanationContainer: {
    alignItems: 'center',
  },
  explanationText: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    lineHeight: 20,
  },
  bottomContainer: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  addButton: {
    backgroundColor: '#003087',
    paddingVertical: 16,
    borderRadius: 8,
    alignItems: 'center',
  },
  addButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
