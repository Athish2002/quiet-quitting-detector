import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type Role = 'analyst' | 'manager' | 'employee';

export const ROLE_LABELS: Record<Role, { label: string; description: string; icon: string }> = {
  analyst: { 
    label: 'Wellbeing Analyst', 
    description: 'Full diagnostic access. For wellbeing teams who support, never evaluate.', 
    icon: '🔬' 
  },
  manager: { 
    label: 'Manager', 
    description: 'Supportive briefings for your team. Scores and diagnostics are not shown.', 
    icon: '👤' 
  },
  employee: { 
    label: 'Employee', 
    description: 'Your own trajectory. Nobody else\'s data is visible.', 
    icon: '🙋' 
  }
};

const STORAGE_KEY = 'qqd.role';

export const getRole = (): Role | null => {
  const stored = sessionStorage.getItem(STORAGE_KEY);
  if (stored === 'analyst' || stored === 'manager' || stored === 'employee') {
    return stored as Role;
  }
  return null;
};

export const setRoleStorage = (role: Role): void => {
  sessionStorage.setItem(STORAGE_KEY, role);
};

export const clearRole = (): void => {
  sessionStorage.removeItem(STORAGE_KEY);
};

const ACCESS_MATRIX: Record<Role, string[]> = {
  analyst: ['overview', 'cohort', 'person', 'diagnostic', 'ingest', 'simulator', 'history', 'audit'],
  manager: ['briefings', 'cohort', 'person', 'history'],
  employee: ['my-wellbeing', 'person']
};

interface RoleContextType {
  role: Role | null;
  setRole: (role: Role) => void;
  hasAccess: (section: string) => boolean;
}

const RoleContext = createContext<RoleContextType | undefined>(undefined);

interface RoleProviderProps {
  children: ReactNode;
}

export const RoleProvider: React.FC<RoleProviderProps> = ({ children }) => {
  const [role, setRoleState] = useState<Role | null>(() => getRole());

  const setRole = (newRole: Role) => {
    setRoleStorage(newRole);
    setRoleState(newRole);
  };

  const hasAccess = (section: string): boolean => {
    if (!role) return false;
    return ACCESS_MATRIX[role].includes(section);
  };

  useEffect(() => {
    const handleStorageChange = () => {
      setRoleState(getRole());
    };
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  return (
    <RoleContext.Provider value={{ role, setRole, hasAccess }}>
      {children}
    </RoleContext.Provider>
  );
};

export const useRole = (): RoleContextType => {
  const context = useContext(RoleContext);
  if (context === undefined) {
    const defaultRole = getRole() ?? 'analyst';
    return {
      role: defaultRole,
      setRole: (newRole: Role) => setRoleStorage(newRole),
      hasAccess: (section: string) => ACCESS_MATRIX[defaultRole].includes(section),
    };
  }
  return context;
};
