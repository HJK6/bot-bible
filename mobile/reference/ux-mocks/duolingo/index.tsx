import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

const DUOLINGO_GREEN = '#58CC02';

export default function DuolingoIndex() {
  const options = [
    { icon: 'book', color: '#FF6B6B', bgColor: '#FFE5E5', label: 'School' },
    { icon: 'bar-chart', color: '#4A90D9', bgColor: '#E3F2FD', label: 'Job Opportunities' },
    { icon: 'people', color: '#FFB84D', bgColor: '#FFF3E0', label: 'Family & Friends' },
    { icon: 'airplane', color: '#4ECDC4', bgColor: '#E0F7F6', label: 'Travel' },
    { icon: 'fitness', color: '#FF69B4', bgColor: '#FFE6F2', label: 'Brain Training' },
    { icon: 'color-palette', color: '#FF69B4', bgColor: '#FFE6F2', label: 'Culture' },
    { icon: 'planet', color: '#9B59B6', bgColor: '#F3E5F5', label: 'Other' },
  ];

  return (
    <View style={styles.container}>
      <View style={styles.greenCorner} />

      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => router.replace('/mocks')}>
          <Ionicons name="arrow-back" size={24} color="#3C3C3C" />
        </TouchableOpacity>
        <View style={styles.progressBarContainer}>
          <View style={styles.progressBarBackground}>
            <View style={[styles.progressBarFill, { width: '50%' }]} />
          </View>
        </View>
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Why are you learning a language?</Text>

        <View style={styles.optionsList}>
          {options.map((option, index) => (
            <TouchableOpacity
              key={index}
              style={styles.optionCard}
              onPress={() => router.push('/mocks/duolingo/pick-goal' as any)}
            >
              <View style={[styles.iconCircle, { backgroundColor: option.bgColor }]}>
                <Ionicons name={option.icon as any} size={24} color={option.color} />
              </View>
              <Text style={styles.optionLabel}>{option.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  greenCorner: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: 80,
    height: 80,
    backgroundColor: DUOLINGO_GREEN,
    transform: [{ rotate: '0deg' }],
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
  optionsList: {
    paddingBottom: 40,
  },
  optionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#E5E5E5',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
  },
  iconCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  optionLabel: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#3C3C3C',
  },
});
