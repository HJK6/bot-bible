import { useWindowDimensions } from 'react-native';

export default function useResponsive() {
  const { width } = useWindowDimensions();
  const isDesktop = width >= 768;
  const isWide = width >= 1024;
  const contentWidth = isWide ? 960 : isDesktop ? 720 : width;
  const numColumns = isWide ? 3 : isDesktop ? 2 : 1;

  return { width, isDesktop, isWide, contentWidth, numColumns };
}
