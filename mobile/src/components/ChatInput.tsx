import React, { useState, useCallback } from 'react';
import {
  View,
  TextInput,
  Pressable,
  StyleSheet,
  ActivityIndicator,
  Platform,
  Image,
  Alert,
} from 'react-native';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import * as ImagePicker from 'expo-image-picker';
import { Colors } from '@/constants/Colors';
import { uploadImage } from '../services/upload';

interface Props {
  onSend: (message: string, imageUrl?: string) => Promise<void>;
  disabled?: boolean;
  placeholder?: string;
  agentId?: string;
}

export default function ChatInput({
  onSend,
  disabled = false,
  placeholder = 'Send a message...',
  agentId,
}: Props) {
  const [value, setValue] = useState('');
  const [sending, setSending] = useState(false);
  const [selectedImageUris, setSelectedImageUris] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);

  const handlePickFromLibrary = useCallback(async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission required', 'Please allow access to your photo library to send images.');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.7,
      allowsMultipleSelection: true,
      selectionLimit: 10,
    });

    if (!result.canceled && result.assets.length > 0) {
      setSelectedImageUris((prev) => [...prev, ...result.assets.map((a) => a.uri)]);
    }
  }, []);

  const handleTakePhoto = useCallback(async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission required', 'Please allow camera access to take photos.');
      return;
    }

    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'],
      quality: 0.7,
    });

    if (!result.canceled && result.assets.length > 0) {
      setSelectedImageUris((prev) => [...prev, result.assets[0].uri]);
    }
  }, []);

  const handleImageButton = useCallback(() => {
    if (Platform.OS === 'web') {
      handlePickFromLibrary();
      return;
    }
    Alert.alert('Add Photo', undefined, [
      { text: 'Take Photo', onPress: handleTakePhoto },
      { text: 'Choose from Library', onPress: handlePickFromLibrary },
      { text: 'Cancel', style: 'cancel' },
    ]);
  }, [handlePickFromLibrary, handleTakePhoto]);

  const handleRemoveImage = useCallback((index: number) => {
    setSelectedImageUris((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleSend = useCallback(async () => {
    const trimmed = value.trim();
    const hasImages = selectedImageUris.length > 0;

    if ((!trimmed && !hasImages) || sending || disabled) return;

    setSending(true);
    try {
      let imageUrls: string[] = [];

      if (hasImages) {
        setUploading(true);
        try {
          imageUrls = await Promise.all(
            selectedImageUris.map((uri) => uploadImage(uri, agentId))
          );
        } catch (err: any) {
          Alert.alert('Upload Failed', err.message || 'Failed to upload image. Please try again.');
          return;
        } finally {
          setUploading(false);
        }
      }

      // Send first image with the text, remaining images as separate messages
      await onSend(trimmed, imageUrls[0]);
      for (let i = 1; i < imageUrls.length; i++) {
        await onSend('', imageUrls[i]);
      }

      setValue('');
      setSelectedImageUris([]);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to send message.');
    } finally {
      setSending(false);
    }
  }, [value, selectedImageUris, sending, disabled, onSend, agentId]);

  const handleKeyPress = useCallback(
    (e: any) => {
      // Enter to send on web (shift+enter for newline)
      if (Platform.OS === 'web' && e.nativeEvent.key === 'Enter' && !e.nativeEvent.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const canSend = (value.trim().length > 0 || selectedImageUris.length > 0) && !sending && !disabled;

  return (
    <View style={styles.wrapper}>
      {/* Image preview strip */}
      {selectedImageUris.length > 0 && (
        <View style={styles.previewStrip}>
          {selectedImageUris.map((uri, index) => (
            <View key={uri} style={styles.previewImageWrapper}>
              <Image source={{ uri }} style={styles.previewImage} />
              <Pressable style={styles.removeButton} onPress={() => handleRemoveImage(index)}>
                <FontAwesome name="times-circle" size={18} color={Colors.textMuted} />
              </Pressable>
            </View>
          ))}
        </View>
      )}

      {/* Input row */}
      <View style={styles.container}>
        <Pressable
          style={[styles.imageButton, disabled && styles.imageButtonDisabled]}
          onPress={handleImageButton}
          disabled={disabled || sending}
        >
          <FontAwesome name="image" size={20} color={disabled ? Colors.textMuted : Colors.primary} />
        </Pressable>

        <TextInput
          style={styles.input}
          value={value}
          onChangeText={setValue}
          onKeyPress={handleKeyPress}
          placeholder={placeholder}
          placeholderTextColor={Colors.textMuted}
          multiline
          maxLength={4000}
          editable={!disabled && !sending}
          onSubmitEditing={Platform.OS !== 'web' ? handleSend : undefined}
          blurOnSubmit={Platform.OS !== 'web'}
          returnKeyType="send"
        />

        <Pressable
          style={[styles.sendButton, !canSend && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={!canSend}
        >
          {sending ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : uploading ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <FontAwesome name="send" size={16} color="#fff" />
          )}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    backgroundColor: Colors.surface,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
  },
  previewStrip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingTop: 8,
    gap: 8,
    flexWrap: 'wrap',
  },
  previewImageWrapper: {
    position: 'relative',
  },
  previewImage: {
    width: 60,
    height: 60,
    borderRadius: 8,
    resizeMode: 'cover',
  },
  removeButton: {
    position: 'absolute',
    top: -6,
    right: -6,
    backgroundColor: Colors.surface,
    borderRadius: 10,
  },
  container: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
  },
  imageButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  imageButtonDisabled: {
    opacity: 0.4,
  },
  input: {
    flex: 1,
    backgroundColor: Colors.background,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    color: Colors.text,
    maxHeight: 120,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: Colors.primary + '40',
  },
});
