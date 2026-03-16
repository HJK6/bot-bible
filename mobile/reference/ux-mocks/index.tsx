import { View, Text, StyleSheet, TouchableOpacity, SafeAreaView } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

const mocks = [
  {
    title: 'PayPal',
    subtitle: 'Balance, activity & add money flow',
    icon: 'wallet-outline' as const,
    color: '#003087',
    route: '/mocks/paypal' as const,
  },
  {
    title: 'Starbucks',
    subtitle: 'Order favorites, store select & previous orders',
    icon: 'cafe-outline' as const,
    color: '#00704A',
    route: '/mocks/starbucks' as const,
  },
  {
    title: 'Duolingo',
    subtitle: 'Onboarding, goals & quiz',
    icon: 'school-outline' as const,
    color: '#58CC02',
    route: '/mocks/duolingo' as const,
  },
];

export default function MocksMenu() {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.heading}>UX Mocks</Text>
      <Text style={styles.subheading}>Select an experience to preview</Text>

      <View style={styles.cards}>
        {mocks.map((mock) => (
          <TouchableOpacity
            key={mock.title}
            style={[styles.card, { borderLeftColor: mock.color }]}
            activeOpacity={0.7}
            onPress={() => router.push(mock.route as any)}
          >
            <View style={[styles.iconCircle, { backgroundColor: mock.color + '15' }]}>
              <Ionicons name={mock.icon} size={28} color={mock.color} />
            </View>
            <View style={styles.cardText}>
              <Text style={styles.cardTitle}>{mock.title}</Text>
              <Text style={styles.cardSubtitle}>{mock.subtitle}</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#999" />
          </TouchableOpacity>
        ))}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    paddingHorizontal: 20,
    paddingTop: 60,
  },
  heading: {
    fontSize: 32,
    fontWeight: '700',
    color: '#1a1a1a',
    marginBottom: 4,
  },
  subheading: {
    fontSize: 15,
    color: '#888',
    marginBottom: 32,
  },
  cards: {
    gap: 16,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 18,
    borderLeftWidth: 4,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 8,
    elevation: 3,
  },
  iconCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  cardText: {
    flex: 1,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1a1a1a',
    marginBottom: 2,
  },
  cardSubtitle: {
    fontSize: 13,
    color: '#888',
  },
});
