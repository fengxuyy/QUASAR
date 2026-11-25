import React, { createContext, useContext, useCallback, type ReactNode } from 'react';

interface NavigationContextType {
  /**
   * Navigate to workspace and select a specific file.
   * @param filePath - The file path (basename or relative path) to select
   * @param archiveId - Optional archive/run ID to switch to before selecting the file
   */
  navigateToFile: (filePath: string, archiveId?: string | null) => void;
}

const NavigationContext = createContext<NavigationContextType | null>(null);

interface NavigationProviderProps {
  children: ReactNode;
  onNavigateToFile: (filePath: string, archiveId?: string | null) => void;
}

/**
 * Provider component that wraps the app and provides navigation callbacks.
 */
export const NavigationProvider: React.FC<NavigationProviderProps> = ({ 
  children, 
  onNavigateToFile 
}) => {
  const navigateToFile = useCallback((filePath: string, archiveId?: string | null) => {
    onNavigateToFile(filePath, archiveId);
  }, [onNavigateToFile]);

  return (
    <NavigationContext.Provider value={{ navigateToFile }}>
      {children}
    </NavigationContext.Provider>
  );
};

/**
 * Hook to access navigation functions from any component.
 */
export const useNavigation = (): NavigationContextType => {
  const context = useContext(NavigationContext);
  if (!context) {
    // Return a no-op function if context is not available
    // This allows components to work even if not wrapped in provider
    return {
      navigateToFile: (_filePath: string, _archiveId?: string | null) => {
        console.warn('NavigationContext not available');
      }
    };
  }
  return context;
};
