import type { ReactNode } from 'react';

interface WorkspaceLayoutProps {
  sidebar: ReactNode;
  children: ReactNode;
  className?: string;
  sidebarLabel?: string;
}

export default function WorkspaceLayout({
  sidebar,
  children,
  className = '',
  sidebarLabel = '投资者画像',
}: WorkspaceLayoutProps) {
  return (
    <div className={`profile-workspace ${className}`.trim()}>
      <aside className="profile-workspace-sidebar" aria-label={sidebarLabel}>
        {sidebar}
      </aside>
      <main className="profile-workspace-main">
        {children}
      </main>
    </div>
  );
}
