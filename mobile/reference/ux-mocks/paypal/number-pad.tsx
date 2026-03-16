import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, SafeAreaView } from 'react-native';
import { Ionicons, MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

export default function NumberPad() {
  const router = useRouter();

  const renderButton = (label: string | React.ReactElement, onPress?: () => void) => (
    <TouchableOpacity
      style={styles.numberButton}
      onPress={onPress}
      activeOpacity={0.6}
    >
      {typeof label === 'string' ? (
        <Text style={styles.numberText}>{label}</Text>
      ) : (
        label
      )}
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={styles.container}>
      {/* Top Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="close" size={28} color="#000" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Enter the amount</Text>
      </View>

      {/* Amount Display */}
      <View style={styles.amountSection}>
        <Text style={styles.amountText}>$0.00</Text>
      </View>

      {/* Separator Line */}
      <View style={styles.separator} />

      {/* Number Pad */}
      <View style={styles.numberPad}>
        {/* Row 1 */}
        <View style={styles.row}>
          {renderButton('1')}
          {renderButton('2')}
          {renderButton('3')}
        </View>

        {/* Row 2 */}
        <View style={styles.row}>
          {renderButton('4')}
          {renderButton('5')}
          {renderButton('6')}
        </View>

        {/* Row 3 */}
        <View style={styles.row}>
          {renderButton('7')}
          {renderButton('8')}
          {renderButton('9')}
        </View>

        {/* Row 4 */}
        <View style={styles.row}>
          {renderButton('.')}
          {renderButton('0')}
          {renderButton(
            <MaterialIcons name="backspace" size={24} color="#333" />
          )}
        </View>
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
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  headerTitle: {
    fontSize: 14,
    color: '#666',
    marginLeft: 16,
  },
  amountSection: {
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  amountText: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#000',
  },
  separator: {
    height: 1,
    backgroundColor: '#e0e0e0',
    marginHorizontal: 20,
  },
  numberPad: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 20,
    paddingBottom: 40,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginBottom: 8,
  },
  numberButton: {
    flex: 1,
    height: 80,
    alignItems: 'center',
    justifyContent: 'center',
  },
  numberText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#333',
  },
});
