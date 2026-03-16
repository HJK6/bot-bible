import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

const DUOLINGO_GREEN = '#58CC02';

export default function Quiz() {
  const answers = [
    { id: 1, icon: null, label: 'un', number: '1', selected: false },
    { id: 2, icon: 'person', label: "l'homme", selected: false },
    { id: 3, icon: 'paw', label: 'le chat', color: '#9B59B6', bgColor: '#F3E5F5', selected: false },
    { id: 4, icon: 'happy', label: 'le garçon', selected: true },
  ];

  return (
    <View style={styles.container}>
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => router.push('/mocks/duolingo' as any)}>
          <Ionicons name="close" size={28} color="#767676" />
        </TouchableOpacity>

        <View style={styles.progressBarContainer}>
          <View style={styles.progressBarBackground}>
            <View style={[styles.progressBarFill, { width: '30%' }]} />
          </View>
        </View>

        <View style={styles.heartsContainer}>
          <Ionicons name="heart" size={24} color="#FF4B4B" />
          <Text style={styles.heartsText}>5</Text>
        </View>
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.newWordBadge}>
          <Ionicons name="star" size={16} color="#9B59B6" />
          <Text style={styles.newWordText}>NEW WORD</Text>
        </View>

        <Text style={styles.question}>Which of these is "the boy"?</Text>

        <View style={styles.answerGrid}>
          <View style={styles.answerRow}>
            <TouchableOpacity style={styles.answerCard}>
              <View style={styles.answerIconContainer}>
                <Text style={styles.answerNumber}>1</Text>
              </View>
              <Text style={styles.answerLabel}>un</Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.answerCard}>
              <View style={[styles.answerIconContainer, styles.personIconBg]}>
                <Ionicons name="person" size={48} color="#FFFFFF" />
              </View>
              <Text style={styles.answerLabel}>l'homme</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.answerRow}>
            <TouchableOpacity style={styles.answerCard}>
              <View style={[styles.answerIconContainer, { backgroundColor: '#F3E5F5' }]}>
                <Ionicons name="paw" size={48} color="#9B59B6" />
              </View>
              <Text style={styles.answerLabel}>le chat</Text>
            </TouchableOpacity>

            <TouchableOpacity style={[styles.answerCard, styles.answerCardSelected]}>
              <View style={styles.answerIconContainer}>
                <Ionicons name="happy" size={48} color="#4A4A4A" />
              </View>
              <Text style={[styles.answerLabel, styles.answerLabelSelected]}>le garçon</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>

      <View style={styles.bottomSection}>
        <TouchableOpacity style={styles.checkButton}>
          <Text style={styles.checkButtonText}>CHECK</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 60,
    paddingBottom: 16,
  },
  progressBarContainer: {
    flex: 1,
    marginHorizontal: 16,
  },
  progressBarBackground: {
    height: 8,
    backgroundColor: '#E5E5E5',
    borderRadius: 4,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: DUOLINGO_GREEN,
    borderRadius: 4,
  },
  heartsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  heartsText: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#FF4B4B',
    marginLeft: 4,
  },
  content: {
    flex: 1,
    paddingHorizontal: 20,
  },
  newWordBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 16,
    marginBottom: 16,
  },
  newWordText: {
    fontSize: 12,
    fontWeight: 'bold',
    color: DUOLINGO_GREEN,
    marginLeft: 6,
    letterSpacing: 0.5,
  },
  question: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#000000',
    marginBottom: 32,
  },
  answerGrid: {
    marginBottom: 32,
  },
  answerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  answerCard: {
    width: '48%',
    aspectRatio: 1 / 1.1,
    borderWidth: 2,
    borderColor: '#E5E5E5',
    borderRadius: 16,
    padding: 16,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
  },
  answerCardSelected: {
    borderColor: '#4FC3F7',
    backgroundColor: 'rgba(79, 195, 247, 0.1)',
  },
  answerIconContainer: {
    marginBottom: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  answerNumber: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#1CB0F6',
  },
  personIconBg: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#4A4A4A',
  },
  answerLabel: {
    fontSize: 14,
    color: '#767676',
    textAlign: 'center',
  },
  answerLabelSelected: {
    color: DUOLINGO_GREEN,
    fontWeight: 'bold',
  },
  bottomSection: {
    paddingHorizontal: 20,
    paddingBottom: 40,
    paddingTop: 16,
  },
  checkButton: {
    backgroundColor: DUOLINGO_GREEN,
    borderRadius: 12,
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
  },
  checkButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: 'bold',
    letterSpacing: 0.5,
  },
});
