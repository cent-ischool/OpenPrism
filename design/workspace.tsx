/**
 * MOCK users / workspaces layer.
 *
 * Open Prism has no accounts yet. This module fakes the shape of the hosted
 * model (user → workspace memberships → projects) entirely in the browser so
 * the UI can be designed around it. Nothing here talks to the backend.
 * Replace `useWorkspace()`'s data source with real API calls later — the
 * consuming components shouldn't need to change.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

export type WorkspaceRole = 'Owner' | 'Admin' | 'Editor' | 'Commenter' | 'Viewer';

export interface MockUser {
  id: string;
  name: string;
  email: string;
  color: string;
}

export interface WorkspaceMember {
  userId: string;
  role: WorkspaceRole;
  /** Pending invitation (no account yet). */
  invited?: boolean;
}

export interface Workspace {
  id: string;
  name: string;
  kind: 'Personal' | 'Team';
  color: string;
  members: WorkspaceMember[];
}

const COLLAB_NAME_KEY = 'openprism-collab-name';
const STATE_KEY = 'openprism-mock-workspaces-v1';

export const MOCK_USERS: Record<string, MockUser> = {
  me: { id: 'me', name: 'Local user', email: 'you@localhost', color: '#3b6ea8' },
  lena: { id: 'lena', name: 'Lena Park', email: 'lena.park@example.edu', color: '#2f7d5b' },
  marcus: { id: 'marcus', name: 'Marcus Hale', email: 'marcus.hale@example.edu', color: '#8a4fa8' },
  priya: { id: 'priya', name: 'Priya Raman', email: 'priya.raman@example.edu', color: '#a8563b' }
};

const DEFAULT_WORKSPACES: Workspace[] = [
  { id: 'personal', name: 'Personal', kind: 'Personal', color: '#5b6573', members: [{ userId: 'me', role: 'Owner' }] },
  {
    id: 'lab',
    name: 'Research Lab',
    kind: 'Team',
    color: '#1f5fa3',
    members: [
      { userId: 'lena', role: 'Owner' },
      { userId: 'me', role: 'Admin' },
      { userId: 'marcus', role: 'Editor' },
      { userId: 'priya', role: 'Commenter' }
    ]
  }
];

interface StoredState {
  workspaces: Workspace[];
  activeId: string;
  /** projectId → workspaceId. Projects not listed live in Personal. */
  projectWorkspace: Record<string, string>;
  extraUsers: Record<string, MockUser>;
  signedIn: boolean;
}

function load(): StoredState {
  const fallback: StoredState = { workspaces: DEFAULT_WORKSPACES, activeId: 'personal', projectWorkspace: {}, extraUsers: {}, signedIn: true };
  try {
    const raw = window.localStorage.getItem(STATE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<StoredState>;
    return { ...fallback, ...parsed, workspaces: parsed.workspaces?.length ? parsed.workspaces : DEFAULT_WORKSPACES };
  } catch {
    return fallback;
  }
}

function currentUserName() {
  try {
    return window.localStorage.getItem(COLLAB_NAME_KEY)?.trim() || MOCK_USERS.me.name;
  } catch {
    return MOCK_USERS.me.name;
  }
}

interface WorkspaceContextValue {
  user: MockUser;
  users: Record<string, MockUser>;
  workspaces: Workspace[];
  active: Workspace;
  myRole: (ws?: Workspace) => WorkspaceRole;
  isAdmin: (ws?: Workspace) => boolean;
  setActive: (id: string) => void;
  createWorkspace: (name: string) => Workspace;
  renameWorkspace: (id: string, name: string) => void;
  leaveWorkspace: (id: string) => void;
  inviteMember: (email: string, role: WorkspaceRole) => void;
  setMemberRole: (userId: string, role: WorkspaceRole) => void;
  removeMember: (userId: string) => void;
  workspaceOfProject: (projectId: string) => string;
  moveProject: (projectId: string, workspaceId: string) => void;
  signedIn: boolean;
  signOut: () => void;
  signIn: () => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

const COLORS = ['#1f7a8c', '#7a6a1f', '#8a4fa8', '#2f7d5b', '#a8563b'];

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<StoredState>(load);

  useEffect(() => {
    try {
      window.localStorage.setItem(STATE_KEY, JSON.stringify(state));
    } catch {
      /* storage unavailable — keep in memory */
    }
  }, [state]);

  const user = useMemo<MockUser>(() => ({ ...MOCK_USERS.me, name: currentUserName() }), []);
  const users = useMemo(() => ({ ...MOCK_USERS, ...state.extraUsers, me: user }), [state.extraUsers, user]);
  const active = state.workspaces.find((w) => w.id === state.activeId) || state.workspaces[0]!;

  const myRole = useCallback((ws: Workspace = active) => ws.members.find((m) => m.userId === 'me')?.role || 'Viewer', [active]);
  const isAdmin = useCallback((ws: Workspace = active) => ['Owner', 'Admin'].includes(myRole(ws)), [active, myRole]);

  const patchActive = (fn: (ws: Workspace) => Workspace) =>
    setState((s) => ({ ...s, workspaces: s.workspaces.map((w) => (w.id === s.activeId ? fn(w) : w)) }));

  const value: WorkspaceContextValue = {
    user,
    users,
    workspaces: state.workspaces,
    active,
    myRole,
    isAdmin,
    setActive: (id) => setState((s) => ({ ...s, activeId: id })),
    createWorkspace: (name) => {
      const ws: Workspace = { id: `ws-${Date.now()}`, name, kind: 'Team', color: COLORS[state.workspaces.length % COLORS.length]!, members: [{ userId: 'me', role: 'Owner' }] };
      setState((s) => ({ ...s, workspaces: [...s.workspaces, ws], activeId: ws.id }));
      return ws;
    },
    renameWorkspace: (id, name) => setState((s) => ({ ...s, workspaces: s.workspaces.map((w) => (w.id === id ? { ...w, name } : w)) })),
    leaveWorkspace: (id) =>
      setState((s) => ({
        ...s,
        workspaces: s.workspaces.filter((w) => w.id !== id),
        activeId: s.activeId === id ? 'personal' : s.activeId,
        projectWorkspace: Object.fromEntries(Object.entries(s.projectWorkspace).filter(([, w]) => w !== id))
      })),
    inviteMember: (email, role) => {
      const known = Object.values({ ...MOCK_USERS, ...state.extraUsers }).find((u) => u.email.toLowerCase() === email.toLowerCase());
      const id = known?.id || `invite-${email.toLowerCase()}`;
      setState((s) => ({
        ...s,
        extraUsers: known ? s.extraUsers : { ...s.extraUsers, [id]: { id, name: email, email, color: '#66707b' } },
        workspaces: s.workspaces.map((w) => (w.id === s.activeId ? { ...w, members: [...w.members, { userId: id, role, invited: !known }] } : w))
      }));
    },
    setMemberRole: (userId, role) => patchActive((w) => ({ ...w, members: w.members.map((m) => (m.userId === userId ? { ...m, role } : m)) })),
    removeMember: (userId) => patchActive((w) => ({ ...w, members: w.members.filter((m) => m.userId !== userId) })),
    workspaceOfProject: (projectId) => {
      const ws = state.projectWorkspace[projectId];
      return ws && state.workspaces.some((w) => w.id === ws) ? ws : 'personal';
    },
    moveProject: (projectId, workspaceId) => setState((s) => ({ ...s, projectWorkspace: { ...s.projectWorkspace, [projectId]: workspaceId } })),
    signedIn: state.signedIn,
    signOut: () => setState((s) => ({ ...s, signedIn: false })),
    signIn: () => setState((s) => ({ ...s, signedIn: true }))
  };

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used inside <WorkspaceProvider>');
  return ctx;
}
