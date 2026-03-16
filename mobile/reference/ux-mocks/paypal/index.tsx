import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, SafeAreaView, ScrollView } from 'react-native';
import { Ionicons, MaterialIcons, FontAwesome } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

export default function PayPalHome() {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.container}>
      {/* Top Header Bar */}
      <View style={styles.header}>
        <View style={styles.logoContainer}>
          <Text style={styles.logoText}>PP</Text>
        </View>
        <View style={styles.headerRight}>
          <View style={styles.notificationContainer}>
            <Ionicons name="notifications" size={24} color="#fff" />
            <View style={styles.badge} />
          </View>
          <TouchableOpacity onPress={() => router.replace('/mocks')}>
            <Ionicons name="settings-outline" size={24} color="#fff" style={styles.settingsIcon} />
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView style={styles.content}>
        {/* PayPal Balance Section */}
        <TouchableOpacity style={styles.balanceSection} onPress={() => router.push('/mocks/paypal/enter-amount' as any)}>
          <Text style={styles.balanceLabel}>PayPal Balance</Text>
          <Text style={styles.balanceAmount}>$0.00</Text>
        </TouchableOpacity>

        {/* Your Activity Section */}
        <View style={styles.activitySection}>
          <View style={styles.activityHeader}>
            <Text style={styles.activityTitle}>Your activity</Text>
            <Ionicons name="chevron-forward" size={20} color="#666" />
          </View>

          {/* Transaction 1 - Bank */}
          <View style={styles.transactionRow}>
            <View style={[styles.transactionIcon, { backgroundColor: '#0070ba' }]}>
              <Ionicons name="business" size={24} color="#fff" />
            </View>
            <View style={styles.transactionDetails}>
              <Text style={styles.transactionName}>Bank account</Text>
              <Text style={styles.transactionDescription}>Checking ...4829</Text>
            </View>
            <Text style={styles.transactionAmountNegative}>-$230.00</Text>
          </View>

          {/* Transaction 2 - Costco */}
          <View style={styles.transactionRow}>
            <View style={[styles.transactionIcon, { backgroundColor: '#ff9800' }]}>
              <Ionicons name="bag" size={24} color="#fff" />
            </View>
            <View style={styles.transactionDetails}>
              <Text style={styles.transactionName}>Costco Mobile Order</Text>
            </View>
          </View>

          {/* Transaction 3 - Poke */}
          <View style={styles.transactionRow}>
            <View style={[styles.transactionIcon, { backgroundColor: '#4caf50' }]}>
              <Ionicons name="restaurant" size={24} color="#fff" />
            </View>
            <View style={styles.transactionDetails}>
              <Text style={styles.transactionName}>Poke</Text>
            </View>
            <Text style={styles.transactionAmountPositive}>+$13.21</Text>
          </View>
        </View>

        {/* Get the most out of PayPal */}
        <View style={styles.promoCard}>
          <Text style={styles.promoText}>Get the most out of PayPal</Text>
          <Ionicons name="chevron-forward" size={20} color="#666" />
        </View>

        {/* Action Buttons */}
        <View style={styles.actionButtons}>
          <TouchableOpacity style={styles.actionButton}>
            <Text style={styles.actionButtonText}>Send</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionButton}>
            <Text style={styles.actionButtonText}>Request</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>

      {/* Bottom Tab Bar */}
      <View style={styles.tabBar}>
        <TouchableOpacity style={styles.tab}>
          <Ionicons name="home" size={24} color="#003087" />
          <Text style={[styles.tabText, styles.tabTextActive]}>Home</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.tab}>
          <Ionicons name="send" size={24} color="#666" />
          <Text style={styles.tabText}>Send</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.tab}>
          <Ionicons name="list" size={24} color="#666" />
          <Text style={styles.tabText}>Activity</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.tab}>
          <Ionicons name="wallet" size={24} color="#666" />
          <Text style={styles.tabText}>Wallet</Text>
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
    height: 50,
    backgroundColor: '#003087',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
  },
  logoContainer: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoText: {
    color: '#003087',
    fontSize: 16,
    fontWeight: 'bold',
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  notificationContainer: {
    marginRight: 16,
    position: 'relative',
  },
  badge: {
    position: 'absolute',
    top: -2,
    right: -2,
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#ff3b30',
    borderWidth: 1,
    borderColor: '#003087',
  },
  settingsIcon: {
    marginLeft: 8,
  },
  content: {
    flex: 1,
  },
  balanceSection: {
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  balanceLabel: {
    fontSize: 14,
    color: '#666',
    marginBottom: 4,
  },
  balanceAmount: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#000',
  },
  activitySection: {
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  activityHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  activityTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#000',
  },
  transactionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  transactionIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  transactionDetails: {
    flex: 1,
  },
  transactionName: {
    fontSize: 15,
    fontWeight: '500',
    color: '#000',
    marginBottom: 2,
  },
  transactionDescription: {
    fontSize: 13,
    color: '#666',
  },
  transactionAmountNegative: {
    fontSize: 15,
    color: '#666',
  },
  transactionAmountPositive: {
    fontSize: 15,
    color: '#4caf50',
  },
  promoCard: {
    margin: 20,
    padding: 16,
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  promoText: {
    fontSize: 15,
    color: '#000',
  },
  actionButtons: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 20,
  },
  actionButton: {
    flex: 1,
    padding: 14,
    backgroundColor: '#003087',
    borderRadius: 8,
    alignItems: 'center',
    marginHorizontal: 4,
  },
  actionButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  tabBar: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
    backgroundColor: '#fff',
    paddingVertical: 8,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 4,
  },
  tabText: {
    fontSize: 11,
    color: '#666',
    marginTop: 4,
  },
  tabTextActive: {
    color: '#003087',
  },
});
