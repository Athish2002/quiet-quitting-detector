import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { SectionHeader } from '../components/SectionHeader';
import { ErrorNote } from '../components/ErrorNote';
import { formatShortDateTime } from '../utils/dateFormatter';

export interface AuditEntry {
  timestamp: string;
  accessor: string;
  subject: string;
  action: string;
  status: 'granted' | 'refused';
  hash: string;
}

export function AccessTrail() {
  const [filterStatus, setFilterStatus] = useState<'all' | 'granted' | 'refused'>('all');

  const { data: auditLog, isLoading, error } = useQuery<AuditEntry[], Error>({
    queryKey: ['audit-log'],
    queryFn: async () => {
      try {
        const response: any = await api.get('/audit/log');
        return Array.isArray(response) ? response : (response.data || []);
      } catch (err: any) {
        if (err.response?.status === 404 || err.status === 404) {
          return [];
        }
        throw err;
      }
    },
    retry: false
  });

  const isError = error && !isLoading;

  const filteredLog = (auditLog ?? []).filter((e) => {
    if (filterStatus === 'all') return true;
    return e.status.toLowerCase() === filterStatus;
  });

  return (
    <div className="page access-trail" aria-labelledby="access-trail-title">
      <SectionHeader
        eyebrow="ACCESS TRAIL"
        title="Who looked at whose assessment."
        intro="Append-only and hash-chained. Refused requests are recorded too — a refusal is itself an audit record. Nothing on this page can edit or delete a row."
      />

      <div className="callout" role="note" aria-label="Integrity Notice">
        <p>
          Every row is cryptographically chained to the one before it. Tampering with or removing any record would break the chain and be detected on the next verification.
        </p>
      </div>

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: '8px', margin: '1.25rem 0 1rem' }}>
        {[
          { id: 'all', label: `All Events (${auditLog?.length ?? 0})` },
          { id: 'granted', label: `Granted (${auditLog?.filter(e => e.status.toLowerCase() === 'granted').length ?? 0})` },
          { id: 'refused', label: `Refused (${auditLog?.filter(e => e.status.toLowerCase() === 'refused').length ?? 0})` },
        ].map((f) => {
          const isActive = filterStatus === f.id;
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilterStatus(f.id as 'all' | 'granted' | 'refused')}
              style={{
                padding: '6px 14px',
                fontSize: '12.5px',
                fontWeight: isActive ? 700 : 500,
                border: '1px solid',
                borderColor: isActive ? 'var(--accent)' : 'var(--rule)',
                background: isActive ? 'var(--accent-bg)' : 'var(--surface)',
                color: isActive ? 'var(--ink)' : 'var(--muted)',
                cursor: 'pointer',
              }}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      {isError && (
        <ErrorNote error={error} />
      )}

      {isLoading && (
        <div className="loading" aria-live="polite">
          Loading access records...
        </div>
      )}

      {!isLoading && !isError && (!auditLog || auditLog.length === 0) && (
        <div className="empty-state" style={{ padding: '2rem', textAlign: 'center', background: 'var(--surface)', border: '1px solid var(--rule)' }}>
          <p style={{ margin: 0, color: 'var(--muted)' }}>No access records yet. Records appear automatically as assessments are opened.</p>
        </div>
      )}

      {!isLoading && !isError && auditLog && auditLog.length > 0 && filteredLog.length === 0 && (
        <div className="empty-state" style={{ padding: '2rem', textAlign: 'center', background: 'var(--surface)', border: '1px solid var(--rule)' }}>
          <p style={{ margin: 0, color: 'var(--muted)' }}>No records match the selected filter.</p>
        </div>
      )}

      {!isLoading && !isError && filteredLog.length > 0 && (
        <table className="modern-table" aria-label="Access Audit Log">
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Accessor</th>
              <th scope="col">Subject</th>
              <th scope="col">Action</th>
              <th scope="col">Status</th>
              <th scope="col">Hash</th>
            </tr>
          </thead>
          <tbody>
            {filteredLog.map((entry, index) => {
              const isRefused = entry.status.toLowerCase() === 'refused';
              return (
                <tr key={`${entry.hash}-${index}`} className={isRefused ? 'row--refused' : ''}>
                  <td>
                    <time dateTime={entry.timestamp} title={entry.timestamp}>
                      {formatShortDateTime(entry.timestamp)}
                    </time>
                  </td>
                  <td>{entry.accessor}</td>
                  <td>{entry.subject}</td>
                  <td>{entry.action}</td>
                  <td>
                    <span 
                      className={`chip ${isRefused ? 'chip--exit' : 'chip--healthy'}`}
                    >
                      {entry.status.toUpperCase()}
                    </span>
                  </td>
                  <td>
                    <code className="monospace">{entry.hash.substring(0, 8)}</code>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
