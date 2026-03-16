import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

const DUOLINGO_GREEN = '#58CC02';

export default function PickGoal() {
  const goals = [
    { name: 'Casual', time: '5 minutes a day', selected: false },
    { name: 'Regular', time: '10 minutes a day', selected: true },
    { name: 'Serious', time: '15 minutes a day', selected: false },
    { name: 'Insane', time: '20 minutes a day', selected: false },
  ];

  return (
    <View style={styles.container}>
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={24} color="#3C3C3C" />
        </TouchableOpacity>
        <View style={styles.progressBarContainer}>
          <View style={styles.progressBarBackground}>
            <View style={[styles.progressBarFill, { width: '70%' }]} />
          </View>
        </View>
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Pick a goal</Text>

        <View style={styles.goalsList}>
          {goals.map((goal, index) => (
            <TouchableOpacity
              key={index}
              style={[
                styles.goalCard,
                goal.selected && styles.goalCardSelected,
              ]}
            >
              <Text style={[
                styles.goalName,
                goal.selected && styles.goalNameSelected,
              ]}>
                {goal.name}
              </Text>
              <Text style={[
                styles.goalTime,
                goal.selected && styles.goalTimeSelected,
              ]}>
                {goal.time}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.mascotSection}>
          <View style={styles.owlCircle}>
            <Ionicons name="happy-outline" size={32} color="#FFFFFF" />
          </View>
          <View style={styles.speechBubble}>
            <View style={styles.speechBubbleTail} />
            <Text style={styles.speechBubbleText}>
              You can always change this goal later
            </Text>
          </View>
        </View>
      </ScrollView>

      <View style={styles.bottomSection}>
        <TouchableOpacity
          style={styles.continueButton}
          onPress={() => router.push('/mocks/duolingo/quiz' as any)}
        >
          <Text style={styles.continueButtonText}>CONTINUE</Text>
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
    marginLeft: 16,
  },
  progressBarBackground: {
    height: 12,
    backgroundColor: '#E5E5E5',
    borderRadius: 6,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: DUOLINGO_GREEN,
    borderRadius: 6,
  },
  content: {
    flex: 1,
    paddingHorizontal: 20,
  },
  title: {
    fontSize: 26,
    fontWeight: 'bold',
    color: '#000000',
    marginTop: 24,
    marginBottom: 24,
  },
  goalsList: {
    marginBottom: 32,
  },
  goalCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#E5E5E5',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
    backgroundColor: '#FFFFFF',
  },
  goalCardSelected: {
    borderColor: '#4FC3F7',
    backgroundColor: 'rgba(79, 195, 247, 0.08)',
  },
  goalName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#3C3C3C',
  },
  goalNameSelected: {
    color: DUOLINGO_GREEN,
  },
  goalTime: {
    fontSize: 14,
    color: '#767676',
  },
  goalTimeSelected: {
    color: DUOLINGO_GREEN,
  },
  mascotSection: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 16,
    marginBottom: 32,
  },
  owlCircle: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: DUOLINGO_GREEN,
    justifyContent: 'center',
    alignItems: 'center',
  },
  speechBubble: {
    flex: 1,
    backgroundColor: '#F7F7F7',
    borderRadius: 12,
    padding: 12,
    marginLeft: 12,
    position: 'relative',
  },
  speechBubbleTail: {
    position: 'absolute',
    left: -8,
    top: 20,
    width: 0,
    height: 0,
    borderTopWidth: 8,
    borderTopColor: 'transparent',
    borderBottomWidth: 8,
    borderBottomColor: 'transparent',
    borderRightWidth: 8,
    borderRightColor: '#F7F7F7',
  },
  speechBubbleText: {
    fontSize: 14,
    color: '#767676',
  },
  bottomSection: {
    paddingHorizontal: 20,
    paddingBottom: 40,
    paddingTop: 16,
  },
  continueButton: {
    backgroundColor: DUOLINGO_GREEN,
    borderRadius: 12,
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
  },
  continueButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: 'bold',
    letterSpacing: 0.5,
  },
});
