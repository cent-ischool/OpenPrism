// Global styles first so component/page styles imported below can override them.
import '@design/tokens.css';
import './app/App.css';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';
import App from './app/App';
import './i18n';
import i18n from './i18n';
import { initTheme } from '@design/theme';
import { WorkspaceProvider } from '@design/workspace';

initTheme();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nextProvider i18n={i18n}>
      <BrowserRouter>
        <WorkspaceProvider>
          <App />
        </WorkspaceProvider>
      </BrowserRouter>
    </I18nextProvider>
  </React.StrictMode>
);
