import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Dimensions } from 'react-native';
import { Ionicons, MaterialIcons, FontAwesome } from '@expo/vector-icons';
import { router } from 'expo-router';

const STARBUCKS_GREEN = '#00704A';
const SCREEN_HEIGHT = Dimensions.get('window').height;

export default function StarbucksOrderScreen() {
  const [activeTab, setActiveTab] = useState<'Menu' | 'Featured' | 'Previous' | 'Favorites'>('Favorites');
  const [showStoreModal, setShowStoreModal] = useState(false);

  const handleSearchPress = () => {
    router.replace('/mocks');
  };

  const handleItemPress = () => {
    setShowStoreModal(true);
  };

  const closeModal = () => {
    setShowStoreModal(false);
  };

  const renderFavoriteItem = (
    name: string,
    details: string[],
    iconName: keyof typeof Ionicons.glyphMap,
    bgColor: string
  ) => (
    <TouchableOpacity style={styles.favoriteItem} onPress={handleItemPress}>
      <View style={[styles.itemImage, { backgroundColor: bgColor }]}>
        <Ionicons name={iconName} size={32} color="#fff" />
      </View>
      <View style={styles.itemDetails}>
        <Text style={styles.itemName}>{name}</Text>
        {details.map((detail, index) => (
          <Text key={index} style={styles.itemDetail}>{detail}</Text>
        ))}
        <View style={styles.itemActions}>
          <Ionicons name="heart" size={20} color={STARBUCKS_GREEN} style={styles.actionIcon} />
          <Ionicons name="add-circle-outline" size={20} color={STARBUCKS_GREEN} />
        </View>
      </View>
    </TouchableOpacity>
  );

  const renderPreviousGroup = (date: string, items: Array<{name: string; details: string[]; iconName: keyof typeof Ionicons.glyphMap; bgColor: string; filled: boolean}>) => (
    <View style={styles.previousGroup}>
      <View style={styles.previousHeader}>
        <Text style={styles.previousDate}>{date}</Text>
        <Text style={styles.addAllText}>Add all</Text>
      </View>
      {items.map((item, index) => (
        <View key={index} style={styles.previousItem}>
          <View style={[styles.itemImage, { backgroundColor: item.bgColor }]}>
            <Ionicons name={item.iconName} size={32} color="#fff" />
          </View>
          <View style={styles.itemDetails}>
            <Text style={styles.itemName}>{item.name}</Text>
            {item.details.map((detail, idx) => (
              <Text key={idx} style={styles.itemDetail}>{detail}</Text>
            ))}
            <View style={styles.itemActions}>
              <Ionicons
                name={item.filled ? "heart" : "heart-outline"}
                size={20}
                color={STARBUCKS_GREEN}
                style={styles.actionIcon}
              />
              <Ionicons name="add-circle-outline" size={20} color={STARBUCKS_GREEN} />
            </View>
          </View>
        </View>
      ))}
    </View>
  );

  const renderStoreRow = (name: string, distance: string, prepTime: string) => (
    <View style={styles.storeRow}>
      <View style={styles.storeInfo}>
        <Text style={styles.storeName}>{name}</Text>
        <Text style={styles.storeDetails}>{distance}</Text>
        <Text style={styles.storeDetails}>Prep time {prepTime}</Text>
      </View>
      <View style={styles.storeIcons}>
        <Ionicons name="heart" size={20} color={STARBUCKS_GREEN} style={styles.storeIcon} />
        <Ionicons name="information-circle-outline" size={20} color="#666" />
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Order</Text>
        <TouchableOpacity onPress={handleSearchPress}>
          <Ionicons name="search" size={24} color="#000" />
        </TouchableOpacity>
      </View>

      {/* Tab Bar */}
      <View style={styles.tabBar}>
        {(['Menu', 'Featured', 'Previous', 'Favorites'] as const).map((tab) => (
          <TouchableOpacity
            key={tab}
            style={styles.tab}
            onPress={() => setActiveTab(tab)}
          >
            <Text style={[styles.tabText, activeTab === tab && styles.tabTextActive]}>
              {tab}
            </Text>
            {activeTab === tab && <View style={styles.tabIndicator} />}
          </TouchableOpacity>
        ))}
      </View>

      {/* Content Area */}
      <ScrollView style={styles.content} contentContainerStyle={styles.contentContainer}>
        {activeTab === 'Favorites' && (
          <View>
            {renderFavoriteItem('Caffè Latte', ['Venti', 'Almond'], 'cafe', '#8B6F47')}
            {renderFavoriteItem('Everything Bagel with Cheese', ['Warmed', '1 Plain Cream Cheese'], 'restaurant', '#D2B48C')}
            {renderFavoriteItem('Caffè Mocha', ['Venti'], 'cafe', '#5C4033')}
          </View>
        )}

        {activeTab === 'Previous' && (
          <View>
            {renderPreviousGroup('OCT 14 2:54 PM', [
              { name: 'Cordusio', details: ['Short', '130 Calories'], iconName: 'cafe', bgColor: '#8B6F47', filled: false },
              { name: 'Chocolate Chip Cookie', details: ['570 Calories'], iconName: 'restaurant', bgColor: '#D2B48C', filled: false }
            ])}
            {renderPreviousGroup('OCT 10 8:00 AM', [
              { name: 'Caffè Latte', details: ['Venti', 'Almond'], iconName: 'cafe', bgColor: '#8B6F47', filled: false }
            ])}
          </View>
        )}

        {activeTab === 'Menu' && (
          <View style={styles.emptyState}>
            <Text style={styles.emptyText}>Menu content goes here</Text>
          </View>
        )}

        {activeTab === 'Featured' && (
          <View style={styles.emptyState}>
            <Text style={styles.emptyText}>Featured content goes here</Text>
          </View>
        )}
      </ScrollView>

      {/* Pickup Bar */}
      <View style={styles.pickupBar}>
        <View style={styles.pickupInfo}>
          <Text style={styles.pickupLabel}>Pickup at</Text>
          <View style={styles.pickupStore}>
            <Text style={styles.pickupStoreName}>Imperial Corners</Text>
            <Ionicons name="chevron-down" size={16} color="#000" />
          </View>
        </View>
        <View style={styles.cartContainer}>
          <Ionicons name="cart" size={24} color={STARBUCKS_GREEN} />
          <View style={styles.cartBadge}>
            <Text style={styles.cartBadgeText}>0</Text>
          </View>
        </View>
      </View>

      {/* Bottom Tab Bar */}
      <View style={styles.bottomTabBar}>
        <View style={styles.bottomTab}>
          <Ionicons name="star-outline" size={24} color="#666" />
          <Text style={styles.bottomTabText}>Home</Text>
        </View>
        <View style={styles.bottomTab}>
          <Ionicons name="card-outline" size={24} color="#666" />
          <Text style={styles.bottomTabText}>Cards</Text>
        </View>
        <View style={styles.bottomTab}>
          <Ionicons name="cafe" size={24} color={STARBUCKS_GREEN} />
          <Text style={[styles.bottomTabText, { color: STARBUCKS_GREEN }]}>Order</Text>
        </View>
        <View style={styles.bottomTab}>
          <Ionicons name="gift-outline" size={24} color="#666" />
          <Text style={styles.bottomTabText}>Gift</Text>
        </View>
        <View style={styles.bottomTab}>
          <Ionicons name="location-outline" size={24} color="#666" />
          <Text style={styles.bottomTabText}>Stores</Text>
        </View>
      </View>

      {/* Store Selector Modal */}
      {showStoreModal && (
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={closeModal}
        >
          <TouchableOpacity
            style={styles.modalSheet}
            activeOpacity={1}
            onPress={(e) => e.stopPropagation()}
          >
            <View style={styles.modalHeader}>
              <View style={styles.modalItemRow}>
                <View style={[styles.modalItemImage, { backgroundColor: '#8B6F47' }]}>
                  <Ionicons name="cafe" size={24} color="#fff" />
                </View>
                <Text style={styles.modalItemName}>Caffè Latte</Text>
              </View>
              <TouchableOpacity onPress={closeModal}>
                <Ionicons name="close" size={28} color="#000" />
              </TouchableOpacity>
            </View>

            <View style={styles.selectStoreRow}>
              <Text style={styles.selectStoreText}>Select Store</Text>
              <Text style={styles.viewMapText}>VIEW MAP</Text>
            </View>

            <Text style={styles.favoritesHeader}>FAVORITES</Text>

            <ScrollView style={styles.storeList}>
              {renderStoreRow('Imperial Corners', '8.6 mi', '3 - 7 min')}
              {renderStoreRow('Mebane Oaks Rd & I-85', '21 mi', '4 - 9 min')}
              {renderStoreRow('High Point, NC', '63 mi', '4 - 9 min')}
              {renderStoreRow('Oakwood Drive & Stratford', '78 mi', '4 - 8 min')}
              {renderStoreRow('Ricks Drive & Stratford Road', '78 mi', '4 - 9 min')}
            </ScrollView>
          </TouchableOpacity>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 60,
    paddingBottom: 16,
  },
  headerTitle: {
    fontSize: 32,
    fontWeight: 'bold',
  },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
    paddingHorizontal: 20,
  },
  tab: {
    marginRight: 24,
    paddingBottom: 12,
  },
  tabText: {
    fontSize: 14,
    color: '#666',
  },
  tabTextActive: {
    fontWeight: 'bold',
    color: '#000',
  },
  tabIndicator: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: 3,
    backgroundColor: STARBUCKS_GREEN,
  },
  content: {
    flex: 1,
  },
  contentContainer: {
    paddingBottom: 20,
  },
  favoriteItem: {
    flexDirection: 'row',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  itemImage: {
    width: 56,
    height: 56,
    borderRadius: 28,
    justifyContent: 'center',
    alignItems: 'center',
  },
  itemDetails: {
    flex: 1,
    marginLeft: 12,
  },
  itemName: {
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  itemDetail: {
    fontSize: 13,
    color: '#666',
    marginBottom: 2,
  },
  itemActions: {
    flexDirection: 'row',
    marginTop: 8,
  },
  actionIcon: {
    marginRight: 12,
  },
  previousGroup: {
    marginBottom: 24,
  },
  previousHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  previousDate: {
    fontSize: 13,
    fontWeight: 'bold',
    color: '#666',
  },
  addAllText: {
    fontSize: 13,
    fontWeight: 'bold',
    color: STARBUCKS_GREEN,
  },
  previousItem: {
    flexDirection: 'row',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  emptyState: {
    padding: 40,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 16,
    color: '#666',
  },
  pickupBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
    backgroundColor: '#fff',
  },
  pickupInfo: {
    flex: 1,
  },
  pickupLabel: {
    fontSize: 11,
    color: '#666',
  },
  pickupStore: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 2,
  },
  pickupStoreName: {
    fontSize: 14,
    fontWeight: 'bold',
    marginRight: 4,
  },
  cartContainer: {
    position: 'relative',
  },
  cartBadge: {
    position: 'absolute',
    top: -4,
    right: -8,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: STARBUCKS_GREEN,
    borderRadius: 10,
    width: 20,
    height: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  cartBadgeText: {
    fontSize: 11,
    fontWeight: 'bold',
    color: STARBUCKS_GREEN,
  },
  bottomTabBar: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
    backgroundColor: '#fff',
  },
  bottomTab: {
    alignItems: 'center',
  },
  bottomTabText: {
    fontSize: 11,
    color: '#666',
    marginTop: 4,
  },
  modalOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    height: SCREEN_HEIGHT * 0.75,
    paddingTop: 20,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingBottom: 16,
  },
  modalItemRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  modalItemImage: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalItemName: {
    fontSize: 18,
    fontWeight: 'bold',
    marginLeft: 12,
  },
  selectStoreRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  selectStoreText: {
    fontSize: 16,
    fontWeight: 'bold',
  },
  viewMapText: {
    fontSize: 13,
    fontWeight: 'bold',
    color: STARBUCKS_GREEN,
  },
  favoritesHeader: {
    fontSize: 12,
    fontWeight: 'bold',
    color: '#666',
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  storeList: {
    flex: 1,
  },
  storeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  storeInfo: {
    flex: 1,
  },
  storeName: {
    fontSize: 15,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  storeDetails: {
    fontSize: 13,
    color: '#666',
  },
  storeIcons: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  storeIcon: {
    marginRight: 12,
  },
});
