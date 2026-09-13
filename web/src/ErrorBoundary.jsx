import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("QX ErrorBoundary caught error:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '24px',
          margin: '16px 0',
          background: 'rgba(239, 68, 68, 0.08)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '12px',
          color: '#f8fafc',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
          textAlign: 'center'
        }}>
          <AlertTriangle size={32} color="#ef4444" />
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>
            {this.props.title || 'Component Temporarily Unavailable'}
          </h3>
          <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1', maxWidth: '500px' }}>
            {this.state.error?.message || 'An unexpected rendering issue occurred. Click below to reload this section.'}
          </p>
          <button
            onClick={this.handleReset}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              background: '#3b82f6',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            <RefreshCw size={14} /> Retry Workspace Section
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
