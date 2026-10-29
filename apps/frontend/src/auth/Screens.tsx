import { useTranslation } from 'react-i18next';
import { Button, Icon, LogoMark } from '@design';

/** Shown while the first credential check / workspace load is in flight. */
export function Splash() {
  const { t } = useTranslation();
  return (
    <div className="op-signed-out" role="status" aria-live="polite">
      <Icon name="loader" className="op-spin" label={t('Loading…')} size={24} />
    </div>
  );
}

/** The workspaces could not be loaded (server down, network). Signing out is always possible. */
export function LoadFailed({ message, onRetry, onSignOut }: { message: string; onRetry: () => void; onSignOut: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="op-signed-out">
      <div className="op-signed-out-card">
        <LogoMark size={40} />
        <div style={{ display: 'grid', gap: 'var(--sp-1)' }}>
          <h1>{t("Couldn't load your workspaces")}</h1>
          <p>{message}</p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <Button variant="primary" icon="refresh" onClick={onRetry}>{t('Try again')}</Button>
          <Button onClick={onSignOut}>{t('Sign out')}</Button>
        </div>
      </div>
    </div>
  );
}
