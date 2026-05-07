import { useState, useEffect, useCallback } from 'react';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Pagination from '../ui/Pagination';
import type { HyrosSyncHealthResponse, SettingsResponse, SettingsUpdate } from '../../types';
import { getHyrosSyncHealth } from '../../api/analytics';

interface SettingsFormProps {
  settings: SettingsResponse;
  onSave: (data: SettingsUpdate) => Promise<void>;
}

/** Rows per page in Hyros sync visibility table */
const HYROS_SYNC_RUNS_PAGE_SIZE = 3;

function isMasked(value: string | null | undefined): boolean {
  const safeValue = value || '';
  return /^\*+.{0,4}$/.test(safeValue) || safeValue === '';
}

export default function SettingsForm({ settings, onSave }: SettingsFormProps) {
  const [form, setForm] = useState<SettingsUpdate>({
    manychat_api_key: '',
    manychat_page_id: '',
    manychat_account_id: '',
    manychat_outbound_flow_ns: '',
    manychat_outbound_flow_ns_instagram: '',
    meta_pixel_id: '',
    meta_capi_token: '',
    meta_ad_account_id: '',
    meta_page_id: '',
    meta_business_manager_id: '',
    hyros_api_key: '',
  });
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');
  const [hyrosHealth, setHyrosHealth] = useState<HyrosSyncHealthResponse | null>(null);
  const [hyrosHealthLoading, setHyrosHealthLoading] = useState(false);
  const [hyrosSyncRunsPage, setHyrosSyncRunsPage] = useState(1);

  const refreshHyrosHealth = useCallback(async () => {
    if (!settings.hyros_api_key) return;
    setHyrosHealthLoading(true);
    try {
      const h = await getHyrosSyncHealth(50);
      setHyrosHealth(h);
    } catch {
      setHyrosHealth(null);
    } finally {
      setHyrosHealthLoading(false);
    }
  }, [settings.hyros_api_key]);

  useEffect(() => {
    if (!hyrosHealth?.sync_runs.length) return;
    const totalPages = Math.max(
      1,
      Math.ceil(hyrosHealth.sync_runs.length / HYROS_SYNC_RUNS_PAGE_SIZE)
    );
    setHyrosSyncRunsPage((p) => Math.min(p, totalPages));
  }, [hyrosHealth?.sync_runs]);

  useEffect(() => {
    void refreshHyrosHealth();
  }, [refreshHyrosHealth]);

  useEffect(() => {
    setForm({
      manychat_api_key: settings.manychat_api_key || '',
      manychat_page_id: settings.manychat_page_id || '',
      manychat_account_id: settings.manychat_account_id || '',
      manychat_outbound_flow_ns: settings.manychat_outbound_flow_ns ?? '',
      manychat_outbound_flow_ns_instagram:
        settings.manychat_outbound_flow_ns_instagram ?? '',
      meta_pixel_id: settings.meta_pixel_id || '',
      meta_capi_token: settings.meta_capi_token || '',
      meta_ad_account_id: settings.meta_ad_account_id || '',
      meta_page_id: settings.meta_page_id || '',
      meta_business_manager_id: settings.meta_business_manager_id || '',
      hyros_api_key: settings.hyros_api_key || '',
    });
  }, [settings]);

  function updateField(key: keyof SettingsUpdate, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      // Only send fields that were actually changed (not still masked)
      const update: SettingsUpdate = {};
      for (const [key, value] of Object.entries(form)) {
        if (value && !isMasked(value)) {
          (update as Record<string, string>)[key] = value;
        }
      }
      await onSave(update);
      setToast('Settings saved successfully');
      setTimeout(() => setToast(''), 3000);
    } catch {
      setError('Failed to save settings');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {toast && (
        <div className="mb-6 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
          {toast}
        </div>
      )}
      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ManyChat Section */}
      <div className="mb-8">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100">
            <svg className="h-4 w-4 text-blue-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-gray-900">ManyChat</h3>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="API Key"
            type="password"
            value={form.manychat_api_key || ''}
            onChange={(e) => updateField('manychat_api_key', e.target.value)}
            placeholder={isMasked(settings.manychat_api_key) ? 'Enter new API key to update' : ''}
            helpText={isMasked(settings.manychat_api_key) ? 'Current key is masked. Enter a new value to update.' : ''}
            className="sm:col-span-2"
          />
          <Input
            label="Page ID"
            value={form.manychat_page_id || ''}
            onChange={(e) => updateField('manychat_page_id', e.target.value)}
            placeholder="ManyChat Page ID"
          />
          <Input
            label="Account ID"
            value={form.manychat_account_id || ''}
            onChange={(e) => updateField('manychat_account_id', e.target.value)}
            placeholder="ManyChat Account ID"
          />
          <Input
            label="Outbound Flow NS (Messenger)"
            value={form.manychat_outbound_flow_ns || ''}
            onChange={(e) => updateField('manychat_outbound_flow_ns', e.target.value)}
            placeholder="content20260507..."
          />
          <Input
            label="Outbound Flow NS (Instagram)"
            value={form.manychat_outbound_flow_ns_instagram || ''}
            onChange={(e) =>
              updateField('manychat_outbound_flow_ns_instagram', e.target.value)
            }
            placeholder="content20260504..."
          />
        </div>
      </div>

      {/* Meta Section */}
      <div className="mb-8 border-t border-gray-200 pt-8">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100">
            <svg className="h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-gray-900">Meta (Facebook)</h3>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="Pixel ID"
            value={form.meta_pixel_id || ''}
            onChange={(e) => updateField('meta_pixel_id', e.target.value)}
            placeholder="Meta Pixel ID"
          />
          <Input
            label="CAPI Token"
            type="password"
            value={form.meta_capi_token || ''}
            onChange={(e) => updateField('meta_capi_token', e.target.value)}
            placeholder={isMasked(settings.meta_capi_token) ? 'Enter new token to update' : ''}
            helpText={isMasked(settings.meta_capi_token) ? 'Current token is masked. Enter a new value to update.' : ''}
          />
          <Input
            label="Ad Account ID"
            value={form.meta_ad_account_id || ''}
            onChange={(e) => updateField('meta_ad_account_id', e.target.value)}
            placeholder="act_123456789"
          />
          <Input
            label="Page ID"
            value={form.meta_page_id || ''}
            onChange={(e) => updateField('meta_page_id', e.target.value)}
            placeholder="Meta Page ID"
          />
          <Input
            label="Business Manager ID"
            value={form.meta_business_manager_id || ''}
            onChange={(e) => updateField('meta_business_manager_id', e.target.value)}
            placeholder="Business Manager ID"
            className="sm:col-span-2"
          />
        </div>
      </div>

      {/* Hyros Section */}
      <div className="mb-8 border-t border-gray-200 pt-8">
        <div className="mb-4 flex items-center gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-100">
              <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75l5.159-5.159a2.25 2.25 0 013.182 0l1.409 1.409a2.25 2.25 0 003.182 0l3.909-3.909m0 0h-3.375m3.375 0v3.375M3.75 20.25h16.5" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-gray-900">Hyros</h3>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="API Key"
            type="password"
            value={form.hyros_api_key || ''}
            onChange={(e) => updateField('hyros_api_key', e.target.value)}
            placeholder={isMasked(settings.hyros_api_key) ? 'Enter new Hyros API key to update' : ''}
            helpText={isMasked(settings.hyros_api_key) ? 'Current key is masked. Enter a new value to update.' : ''}
            className="sm:col-span-2"
          />
        </div>
        {settings.hyros_api_key && (
          <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-900">
            <div className="font-medium text-emerald-950">Hyros sync visibility</div>
            {hyrosHealthLoading ? (
              <p className="mt-2 text-xs text-emerald-800">Loading recent sync runs…</p>
            ) : hyrosHealth ? (
              <>
                <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-emerald-800">
                  <span>
                    Last logged sync:{' '}
                    <strong className="text-emerald-950">
                      {hyrosHealth.last_synced_at
                        ? new Date(hyrosHealth.last_synced_at).toLocaleString()
                        : '—'}
                    </strong>
                  </span>
                  <span>
                    Avg purchase match rate:{' '}
                    <strong className="text-emerald-950">
                      {hyrosHealth.avg_match_rate != null
                        ? `${hyrosHealth.avg_match_rate}%`
                        : '—'}
                    </strong>{' '}
                    <span className="opacity-75">(matched ÷ Hyros sale rows)</span>
                  </span>
                </div>
                {hyrosHealth.sync_runs.length === 0 ? (
                  <p className="mt-2 text-xs text-emerald-800">
                    No sync runs logged yet — wait for the scheduled job.
                  </p>
                ) : (
                  <div className="mt-3 overflow-hidden rounded border border-emerald-100/80 bg-white/60">
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-xs">
                        <thead>
                          <tr className="border-b border-emerald-100 text-left text-emerald-800">
                            <th className="px-2 py-1.5 font-medium">Synced at</th>
                            <th className="px-2 py-1.5 font-medium text-right">Match %</th>
                            <th className="px-2 py-1.5 font-medium text-right">Unmatched</th>
                            <th className="px-2 py-1.5 font-medium text-right">Sales</th>
                            <th className="px-2 py-1.5 font-medium text-right">Matched</th>
                            <th className="px-2 py-1.5 font-medium text-right">attora_id %</th>
                            <th className="px-2 py-1.5 font-medium text-right">attora_sub</th>
                            <th className="px-2 py-1.5 font-medium text-right">email</th>
                          </tr>
                        </thead>
                        <tbody>
                          {hyrosHealth.sync_runs
                            .slice(
                              (hyrosSyncRunsPage - 1) * HYROS_SYNC_RUNS_PAGE_SIZE,
                              hyrosSyncRunsPage * HYROS_SYNC_RUNS_PAGE_SIZE
                            )
                            .map((run, idx) => (
                              <tr
                                key={`${run.synced_at}-${(hyrosSyncRunsPage - 1) * HYROS_SYNC_RUNS_PAGE_SIZE + idx}`}
                                className="border-b border-emerald-50 last:border-0"
                              >
                                <td className="px-2 py-1.5 whitespace-nowrap tabular-nums">
                                  {new Date(run.synced_at).toLocaleString()}
                                </td>
                                <td className="px-2 py-1.5 text-right tabular-nums">
                                  {run.match_rate_pct != null ? `${run.match_rate_pct}%` : '—'}
                                </td>
                                <td className="px-2 py-1.5 text-right tabular-nums">
                                  {run.unmatched_sales}
                                </td>
                                <td className="px-2 py-1.5 text-right tabular-nums">
                                  {run.sales_scanned}
                                </td>
                                <td className="px-2 py-1.5 text-right tabular-nums">
                                  {run.purchases_matched}
                                </td>
                                <td className="px-2 py-1.5 text-right tabular-nums">
                                  {run.attora_id_signal_pct != null
                                    ? `${run.attora_id_signal_pct}%`
                                    : '—'}
                                </td>
                                <td className="px-2 py-1.5 text-right tabular-nums">
                                  {run.matched_by_attora_sub}
                                </td>
                                <td className="px-2 py-1.5 text-right tabular-nums">
                                  {run.matched_by_email}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                    <Pagination
                      page={hyrosSyncRunsPage}
                      pageSize={HYROS_SYNC_RUNS_PAGE_SIZE}
                      total={hyrosHealth.sync_runs.length}
                      onPageChange={setHyrosSyncRunsPage}
                    />
                  </div>
                )}
              </>
            ) : null}

          </div>
        )}
      </div>

      <div className="flex justify-end border-t border-gray-200 pt-6">
        <Button type="submit" loading={loading} size="lg">
          Save Settings
        </Button>
      </div>
    </form>
  );
}
