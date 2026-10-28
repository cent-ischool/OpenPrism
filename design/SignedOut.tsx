import { useTranslation } from 'react-i18next';
import { Icon } from './Icon';
import { LogoMark } from './Logo';
import { Avatar } from './ui';
import { useWorkspace } from './workspace';

/** Mock sign-in screen shown after "Sign out". There is no real auth yet. */
export function SignedOut() {
  const { t } = useTranslation();
  const ws = useWorkspace();
  return (
    <div className="op-signed-out">
      <div className="op-signed-out-card">
        <LogoMark size={40} />
        <div style={{ display: 'grid', gap: 'var(--sp-1)' }}>
          <h1>{t("You're signed out")}</h1>
          <p>{t('Pick an account to continue to Open Prism.')}</p>
        </div>
        <button type="button" className="op-signed-out-account" onClick={ws.signIn} autoFocus>
          <Avatar name={ws.user.name} color={ws.user.color} size="lg" />
          <span style={{ display: 'grid', flex: 1, minWidth: 0 }}>
            <strong className="op-truncate">{t('Continue as {{name}}', { name: ws.user.name })}</strong>
            <span className="op-truncate" style={{ color: 'var(--text-3)', fontSize: 'var(--fs-xs)' }}>{ws.user.email}</span>
          </span>
          <Icon name="chevron-right" />
        </button>
        <span className="op-mock-note">{t('Accounts are mocked in this build — no data leaves your machine.')}</span>
      </div>
    </div>
  );
}
