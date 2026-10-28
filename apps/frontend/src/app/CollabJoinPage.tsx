import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { resolveCollabToken, setCollabServer, setCollabToken } from '../api/client';
import { Button, Icon, LogoMark } from '@design';

export default function CollabJoinPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [status, setStatus] = useState(t('正在加入协作...'));
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token') || '';
    if (!token) {
      setStatus(t('邀请链接缺少 token。'));
      setFailed(true);
      return;
    }
    setCollabServer(window.location.origin);
    setStatus(t('正在验证邀请...'));
    resolveCollabToken(token)
      .then((res) => {
        if (!res.ok || !res.projectId) {
          setStatus(t('邀请无效或已过期。'));
          setFailed(true);
          return;
        }
        setCollabToken(token);
        setStatus(t('已加入协作，正在打开项目...'));
        navigate(`/editor/${res.projectId}`, { replace: true });
      })
      .catch((err) => {
        setStatus(t('加入失败: {{error}}', { error: String(err) }));
        setFailed(true);
      });
  }, [navigate, t]);

  return (
    <div className="op-signed-out">
      <div className="op-signed-out-card">
        <LogoMark size={40} />
        <div style={{ display: 'grid', gap: 'var(--sp-2)', justifyItems: 'center' }}>
          <h1>{t('协作加入')}</h1>
          <p role="status" aria-live="polite" style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--sp-2)', color: failed ? 'var(--danger)' : undefined }}>
            <Icon name={failed ? 'alert-circle' : 'loader'} className={failed ? '' : 'op-spin'} />
            <span>{status}</span>
          </p>
        </div>
        {failed && (
          <Button variant="secondary" icon="layout-grid" onClick={() => navigate('/projects')}>
            {t('All projects')}
          </Button>
        )}
      </div>
    </div>
  );
}
